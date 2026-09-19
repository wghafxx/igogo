"""Bank reserve, pool adjustments and luck refunds without external services."""
import asyncio
import os
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from mongomock.collection import Collection
from mongomock_motor import AsyncMongoMockClient
from motor.motor_asyncio import AsyncIOMotorClient

run = asyncio.run


@pytest.fixture
def bank_api(isolated_server):
    s = isolated_server
    mongo_url = os.environ.get("BANK_TEST_MONGO_URL")
    if mongo_url:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=2000)
        # These synchronous tests use asyncio.run for setup and each scenario.
        client.get_io_loop = asyncio.get_running_loop
    else:
        client = AsyncMongoMockClient()
    s.db = db = client["bank_tests_" + uuid.uuid4().hex]
    s.require_admin = AsyncMock(return_value={"jti": "admin"})

    async def setup():
        for name in ("bank_state", "bank_ledger", "rains", "withdrawals"):
            await db[name].create_index("id", unique=True)
        await db.bank_state.insert_one({"id": "main", "bank": 1000, "pool": 500, "commission_profit": 200})
        await db.bank_lock.insert_one({"id": "main", "locked_until": s.now_utc() - timedelta(seconds=1)})
        await db.users.insert_one({"session_id": "discord_1", "discord_id": "1", "balance": 100, "skins": []})
    run(setup())

    async def request(path, method="POST", **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app), base_url="http://test") as client:
            return await client.request(method, "/api" + path, **kwargs)

    async def state():
        return await db.bank_state.find_one({"id": "main"})

    async def rain(**fields):
        doc = {"id": "rain-1", "v": 2, "status": "active", "budget": 1000, "left": 650,
               "spent": 350, "wins": [], "closes_at": s.now_utc() + timedelta(minutes=10), **fields}
        await db.rains.insert_one(doc)
        return doc

    async def withdrawal(price=100, wid="w1"):
        await db.withdrawals.insert_one({"id": wid, "session_id": "discord_1", "status": "pending",
            "item": {"uid": wid, "name": "Test", "price": price}, "created_at": s.now_utc()})

    try:
        yield SimpleNamespace(s=s, db=db, request=request, state=state, rain=rain, withdrawal=withdrawal)
    finally:
        if mongo_url:
            async def cleanup():
                await client.drop_database(db.name)
            run(cleanup())
        client.close()


def test_manual_luck_close_refunds_v2_left_once(bank_api):
    async def check():
        a = bank_api
        await a.rain()
        results = await asyncio.gather(*(a.request("/admin/rain/close") for _ in range(8)))
        assert sum(r.json().get("returned", 0) for r in results) == 650
        state = await a.state()
        assert (state["pool"], state["bank"], state["commission_profit"]) == (1150, 1000, 200)
        rain = await a.db.rains.find_one({"id": "rain-1"})
        assert rain["status"] == "closed" and rain["left"] == 0 and rain["returned_amount"] == 650
    run(check())


@pytest.mark.parametrize("legacy", [False, True])
def test_timeout_and_legacy_close_refund_only_unused_budget(bank_api, legacy):
    async def check():
        a = bank_api
        fields = {"slices": [{"amount": 20}, {"amount": 30, "session_id": "winner"}], "v": 1} if legacy else {}
        await a.rain(closes_at=a.s.now_utc() - timedelta(seconds=1), **fields)
        result = await a.s.rain_maybe_close()
        assert result["returned_amount"] == (20 if legacy else 650)
        await a.s.rain_maybe_close()
        assert (await a.state())["pool"] == (520 if legacy else 1150)
    run(check())


def test_refund_recovers_after_money_written_before_rain_finished(bank_api, monkeypatch):
    if os.environ.get("BANK_TEST_MONGO_URL"):
        pytest.skip("Fault injection into mongomock; financial writes also run against real MongoDB")
    async def check():
        from rain_settlement import resume_rain_returns
        a = bank_api
        await a.rain()
        original = Collection.update_one

        def interrupted(collection, query, update, *args, **kwargs):
            if collection.name == "rains" and update.get("$set", {}).get("return_pending") is False:
                raise RuntimeError("lost connection after refund")
            return original(collection, query, update, *args, **kwargs)

        monkeypatch.setattr(Collection, "update_one", interrupted)
        with pytest.raises(RuntimeError):
            await a.request("/admin/rain/close")
        assert (await a.state())["pool"] == 1150
        monkeypatch.setattr(Collection, "update_one", original)
        await resume_rain_returns(a.db)
        await resume_rain_returns(a.db)
        assert (await a.state())["pool"] == 1150
        assert (await a.db.rains.find_one({}))["returned_amount"] == 650
    run(check())


def test_pool_can_increase_decrease_and_reach_zero_without_changing_bank(bank_api):
    async def check():
        a = bank_api
        for amount, expected in ((100, 600), (-250, 350), (-350, 0)):
            r = await a.request("/admin/bank/pool", json={"amount": amount, "note": "test adjustment"})
            assert r.status_code == 200, r.text
            assert r.json()["pool"] == expected
        state = await a.state()
        assert (state["bank"], state["commission_profit"]) == (1000, 200)
        entries = await a.db.bank_ledger.find({"kind": "pool"}).to_list(None)
        assert [e["amount"] for e in entries] == [100, -250, -350]
    run(check())


@pytest.mark.parametrize("amount", [0, 0.001, -0.001, -500.01, -1000001])
def test_invalid_pool_change_does_not_write(bank_api, amount):
    async def check():
        a = bank_api
        r = await a.request("/admin/bank/pool", json={"amount": amount, "note": "test"})
        assert r.status_code in (400, 422)
        assert (await a.state())["pool"] == 500
        assert await a.db.bank_ledger.count_documents({}) == 0
    run(check())


def test_concurrent_pool_decreases_cannot_overdraw_or_use_active_luck(bank_api):
    async def check():
        a = bank_api
        await a.rain()
        results = await asyncio.gather(*(a.request("/admin/bank/pool", json={"amount": -300, "note": "test"}) for _ in range(2)))
        assert sorted(r.status_code for r in results) == [200, 400]
        assert (await a.state())["pool"] == 200
        assert (await a.db.rains.find_one({}))["left"] == 650
    run(check())


@pytest.mark.parametrize("method,fee,expected", [(None, .2, 200), ("xrocket", 0, 0), ("cryptobot", 0, 0), ("xrocket", .2, 0)])
def test_deposit_commission_is_exact_twenty_percent_and_repeat_safe(bank_api, method, fee, expected):
    async def check():
        from deposit_settlement import settle_deposit
        a = bank_api
        dep = {"id": "dep-1", "session_id": "discord_1", "rap": 1000, "fee": fee,
               "payment_method": method, "status": "processing", "issued_skins": [],
               "balance_credited": 880, "credited": 880, "skins_total": 0,
               "planned_at": a.s.now_utc(), "amount_rub": 500}
        await a.db.deposits.insert_one(dict(dep))
        await asyncio.gather(*(settle_deposit(a.db, dep) for _ in range(5)))
        state = await a.state()
        assert state["bank"] == 2000 and state["commission_profit"] == 200 + expected
        assert state["pool"] == 500
        assert (await a.db.users.find_one({}))["balance"] == 980
        assert await a.db.bank_ledger.count_documents({"kind": "deposit"}) == 1
    run(check())


def test_historical_commission_only_uses_verified_recorded_fees(bank_api):
    async def check():
        from bank_accounting import reserve_historical_commissions
        a = bank_api
        for dep_id, fee, status, posted, method in (
            ("skin", .2, "confirmed", True, None), ("pending", .2, "pending", True, None),
            ("unknown", None, "confirmed", True, None), ("unposted", .2, "confirmed", False, None),
            ("crypto", .2, "confirmed", True, "cryptobot"),
        ):
            await a.db.deposits.insert_one({"id": dep_id, "rap": 1000, "fee": fee, "status": status, "payment_method": method})
            if posted:
                await a.db.bank_ledger.insert_one({"id": dep_id, "kind": "deposit", "ref_id": dep_id, "amount": 1000})
        await asyncio.gather(*(reserve_historical_commissions(a.db) for _ in range(3)))
        assert (await a.state())["commission_profit"] == 400
        assert (await a.state())["bank"] == 1000
        assert (await a.state())["commission_deposits"] == ["skin"]
    run(check())


def test_admin_profit_is_commission_only_and_adjustments_cannot_spend_it(bank_api):
    async def check():
        a = bank_api
        data = (await a.request("/admin/bank", "GET")).json()
        assert (data["bank"], data["commission_profit"], data["available_bank"], data["net"]) == (1000, 200, 800, 700)
        r = await a.request("/admin/bank/adjust", json={"amount": -801, "note": "test"})
        assert r.status_code == 400 and (await a.state())["bank"] == 1000
        r = await a.request("/admin/bank/adjust", json={"amount": 100, "note": "test"})
        assert r.status_code == 200
        data = (await a.request("/admin/bank", "GET")).json()
        assert data["commission_profit"] == 200 and data["net"] == 800
    run(check())


def test_player_withdrawal_cannot_consume_commission_and_retries_cannot_double_debit(bank_api):
    async def check():
        a = bank_api
        await a.withdrawal(801)
        r = await a.request("/admin/withdrawals/w1/done")
        assert r.status_code == 409
        assert (await a.db.withdrawals.find_one({}))["status"] == "pending"
        assert (await a.state())["bank"] == 1000
        await a.db.withdrawals.update_one({"id": "w1"}, {"$set": {"item.price": 800}})
        r = await a.request("/admin/withdrawals/w1/done")
        assert r.status_code == 200, r.text
        await a.request("/admin/withdrawals/w1/done")
        state = await a.state()
        assert state["bank"] == state["commission_profit"] == 200
        assert await a.db.bank_ledger.count_documents({"kind": "withdrawal"}) == 1
    run(check())


def test_concurrent_withdrawals_cannot_overdraw_player_bank(bank_api):
    async def check():
        a = bank_api
        await a.withdrawal(500, "w1")
        await a.withdrawal(500, "w2")
        results = await asyncio.gather(*(a.request(f"/admin/withdrawals/{wid}/done") for wid in ("w1", "w2")))
        assert sorted(r.status_code for r in results) == [200, 409]
        state = await a.state()
        assert (state["bank"], state["commission_profit"]) == (500, 200)
        assert await a.db.withdrawals.count_documents({"status": "pending"}) == 1
        assert await a.db.withdrawals.count_documents({"status": "done"}) == 1
    run(check())


def test_withdrawal_retry_after_debit_repairs_history_without_second_payment(bank_api, monkeypatch):
    async def check():
        a = bank_api
        await a.withdrawal(100)
        original = a.s.resolve_history
        monkeypatch.setattr(a.s, "resolve_history", AsyncMock(side_effect=RuntimeError("interrupted after debit")))
        with pytest.raises(RuntimeError):
            await a.request("/admin/withdrawals/w1/done")
        assert (await a.state())["bank"] == 900
        assert (await a.db.withdrawals.find_one({}))["status"] == "paying"
        monkeypatch.setattr(a.s, "resolve_history", original)
        r = await a.request("/admin/withdrawals/w1/done")
        assert r.status_code == 200, r.text
        assert (await a.state())["bank"] == 900
        assert (await a.state())["commission_profit"] == 200
        assert await a.db.bank_ledger.count_documents({"kind": "withdrawal"}) == 1
        assert (await a.db.withdrawals.find_one({}))["status"] == "done"
    run(check())


@pytest.mark.parametrize("luck", [False, True])
def test_commission_is_not_available_for_normal_or_luck_win(bank_api, luck):
    async def check():
        a = bank_api
        await a.db.bank_state.update_one({"id": "main"}, {"$set": {"bank": 200, "commission_profit": 100, "pool": 1000}})
        await a.db.shop_items.insert_one({"id": "target", "name": "Target", "price": 150, "rarity": "pink"})
        if luck:
            await a.rain()
        a.s._rng = SimpleNamespace(random=lambda: .5, uniform=lambda lo, hi: lo)
        r = await a.request("/upgrade", json={"session_id": "discord_1", "bet_amount": 50, "target_item": {"id": "target"}},
                            headers={"Authorization": f"Bearer {a.s.make_token('discord_1')}"})
        assert r.status_code == 200, r.text
        game = await a.db.upgrades.find_one({})
        assert not game["win"] and game["forced_reason"] == "bank"
        assert game["chance"] == pytest.approx(50 / 150 * .85)
        assert game["display_chance"] == pytest.approx(50 / 150)
        assert (await a.state())["commission_profit"] == 100
        assert not (await a.db.users.find_one({}))["skins"]
    run(check())


def test_empty_pool_forced_loss_and_rtp_refill_remain_unchanged(bank_api):
    async def check():
        a = bank_api
        await a.db.bank_state.update_one({"id": "main"}, {"$set": {"pool": 0}})
        await a.db.shop_items.insert_one({"id": "target", "name": "Target", "price": 100, "rarity": "pink"})
        a.s._rng = SimpleNamespace(random=lambda: .5, uniform=lambda lo, hi: lo)
        r = await a.request("/upgrade", json={"session_id": "discord_1", "bet_amount": 50, "target_item": {"id": "target"}},
                            headers={"Authorization": f"Bearer {a.s.make_token('discord_1')}"})
        assert r.status_code == 200, r.text
        game = await a.db.upgrades.find_one({})
        assert game["forced_reason"] == "pool" and not game["win"]
        assert game["chance"] == .425 and game["display_chance"] == .5
        assert (await a.state())["pool"] == 50 * .85 - 1
        assert (await a.state())["commission_profit"] == 200
        assert a.s.win_chance(100, 100, 1) == .75
        assert a.s.MIN_CHANCE == .01 and a.s.MAX_CHANCE == .75
    run(check())
