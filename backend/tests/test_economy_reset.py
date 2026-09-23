import asyncio
import os
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from mongomock.collection import Collection


run = asyncio.run
OLD_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def economy(api):
    async def seed():
        s, db = api.s, api.db
        await s.economy_guard.ensure(db)
        s.app.state.economy_guard_ready = True
        await db.users.update_one({"session_id": "player"}, {"$set": {
            "skins": [{"uid": "old-skin", "price": 100}], "roblox_nick": "KeepMe",
            "promo_code": "BONUS", "promo_bonus": .5, "gold_nick": True,
            "referral_earned_cents": 500, "referred_by": "other", "referral_qualified_at": s.now_utc(),
            "shop_receipts": [{"id": OLD_ID, "skins": [{"uid": "old-skin"}]}],
            "credited_deposits": ["old-deposit"], "claimed_promo_gifts": ["old-gift"],
        }})
        await db.upgrades.insert_many([
            {"id": "game1", "session_id": "player", "win": True, "bet_amount": 50, "target_item": {"price": 100}, "created_at": s.now_utc()},
            {"id": "game2", "session_id": "player", "win": False, "bet_amount": 30, "forced_loss": True, "forced_reason": "pool", "created_at": s.now_utc()},
        ])
        for name in ("drops", "item_history", "luck_cycles", "bank_ledger", "promo_activations", "referral_rewards"):
            await db[name].insert_one({"id": "old", "session_id": "player", "created_at": s.now_utc()})
        await db.promo_gifts.insert_one({"id": "gift", "amount_rap": 500})
        await db.promo_gift_ops.insert_one({"id": "gift-op", "status": "reserved"})
        await db.promo_codes.insert_one({"id": "promo", "code": "BONUS", "reserved_count": 10, "reserved_keys": ["player"]})
        await db.deposits.insert_many([
            {"id": "old-deposit", "session_id": "player", "status": "processing", "settlement_version": 1},
            {"id": f"xrocket:{OLD_ID}", "payment_method": "xrocket", "status": "awaiting_payment"},
            {"id": f"cryptobot:{OLD_ID}", "payment_method": "cryptobot", "status": "processing"},
        ])
        await db.withdrawals.insert_one({"id": "pending", "session_id": "player", "status": "cancelling", "item": {"price": 78}})
        await db.rains.insert_one({"id": "rain", "status": "active", "left": 500, "return_pending": True})
        await db.admin_coin_grants.insert_one({"id": OLD_ID, "session_id": "player", "amount": 50.0, "note": "old", "status": "pending"})
        await db.bank_settings.insert_one({"id": "main", "rtp_target": .87})
        await db.rain_settings.insert_one({"id": "main", "pool_threshold": 3500})
        await db.shop_items.insert_one({"id": "catalog-item", "price": 100})
        await db.admin_commands.insert_one({"id": "custom", "command": "custom", "text": "Keep", "deleted": False})
    run(seed())
    return api


def payload(**overrides):
    return {"pin": "1001", "scope": "full_economy", "request_id": str(uuid.uuid4()), **overrides}


async def reset(a, body=None):
    return await a.request("/admin/bank/reset", "POST", json=body or payload())


def test_all_financial_stats_zero_but_upgrade_counter_and_accounts_remain(economy):
    async def check():
        a = economy
        response = await reset(a)
        assert response.status_code == 200, response.text
        assert response.json()["upgrades_total"] == 2
        bank_response = await a.request("/admin/bank")
        assert bank_response.status_code == 200, bank_response.text
        bank = bank_response.json()
        for key in ("bank", "pool", "commission_profit", "available_bank", "net", "deposits_total", "withdrawals_total", "adjustments_total", "gifts_total", "gifts_count"):
            assert bank[key] == 0, (key, bank[key])
        assert all(v == 0 for v in bank["liabilities"].values())
        assert bank["rtp"] == bank["rtp_24h"] == {"wagered": 0, "paid": 0, "rtp": 0}
        assert bank["games"] == {"total": 0, "wins": 0, "forced_losses": 0, "forced_by": {}}
        assert bank["ledger"] == bank["forced_top"] == []
        assert bank["settings"]["rtp_target"] == .87
        players = (await a.request("/admin/players")).json()
        assert len(players) == 2
        for row in players:
            for key in ("deposits", "games", "wins", "forced", "wagered", "paid", "rtp", "balance", "inventory", "withdrawn", "net"):
                assert row[key] == 0, (key, row)
        assert (await a.request("/stats")).json()["upgrades"] == 2
        for name in a.s.economy_reset.WIPE:
            assert await a.db[name].count_documents({}) == 0, name
        user = await a.db.users.find_one({"session_id": "player"})
        assert user["roblox_nick"] == "KeepMe" and user["discord_id"] == "player"
        assert user["balance"] == user["promo_bonus"] == user["referral_earned_cents"] == 0
        assert user["skins"] == [] and user["gold_nick"] is False
        assert await a.db.shop_items.count_documents({}) == 1
        assert await a.db.chats.count_documents({}) == 1
        assert (await a.request("/admin/players/player/coins")).json() == []
        assert (await a.db.promo_codes.find_one({}))["reserved_count"] == 0
        assert await a.db.admin_audit.count_documents({"event": "economy_reset"}) == 1
        assert (await a.s.rain_settings())["pool_threshold"] == 3500
    run(check())


@pytest.mark.parametrize("body,status", [({}, 422), ({"pin": "1001"}, 422), (payload(pin="0000"), 403), (payload(scope="bank_only"), 422)])
def test_wrong_pin_and_old_client_cannot_wipe(economy, body, status):
    async def check():
        assert (await economy.request("/admin/bank/reset", "POST", json=body)).status_code == status
        assert (await economy.db.users.find_one({"session_id": "player"}))["balance"] == 12.5
        assert await economy.db.upgrades.count_documents({}) == 2
    run(check())


def test_admin_auth_required(economy):
    economy.s.require_admin = economy.real_auth
    assert run(reset(economy)).status_code == 403


def test_repeat_request_does_not_erase_new_money_and_next_reset_keeps_cumulative_counter(economy):
    async def check():
        a = economy
        body = payload()
        assert (await reset(a, body)).status_code == 200
        await a.db.users.update_one({"session_id": "player"}, {"$set": {"balance": 99}})
        await a.db.upgrades.insert_one({"id": "new", "win": False})
        assert (await reset(a, body)).status_code == 200
        assert (await a.db.users.find_one({"session_id": "player"}))["balance"] == 99
        assert await a.s.count_upgrades() == 3
        assert (await reset(a)).status_code == 200
        assert await a.s.count_upgrades() == 3
        assert (await a.db.users.find_one({"session_id": "player"}))["balance"] == 0
    run(check())


def test_old_credits_invoices_and_purchase_retries_cannot_restore_value(economy):
    async def check():
        a = economy
        assert (await reset(a)).status_code == 200
        await a.s.admin_coins.resume_pending(a.db)
        await a.s.promos.resume_incomplete_gifts(a.db)
        await a.s.referrals.reconcile_once(a.db)
        await a.s.resume_rain_returns(a.db)
        result = await a.request("/admin/players/player/coins", "POST", json={"request_id": OLD_ID, "amount": 50, "note": "old"})
        assert result.status_code == 409 and "сброс" in result.json()["detail"]
        user = await a.db.users.find_one({"session_id": "player"})
        for module in (a.s.xp, a.s.cb):
            with pytest.raises(HTTPException) as error:
                await module.create_invoice(a.db, SimpleNamespace(enabled=True), user, OLD_ID, Decimal(50), "USDT", "http://test")
            assert error.value.status_code == 409
        with pytest.raises(HTTPException) as error:
            await a.s.purchase_skins(a.db, user, OLD_ID, [{"id": "catalog-item", "quantity": 1}], 100)
        assert error.value.status_code == 409
        assert user["balance"] == 0 and user["skins"] == []
        assert await a.s.payout_pool() == 0
    run(check())


def test_reset_waits_for_inflight_operations_and_blocks_new_requests(economy):
    async def check():
        a = economy
        entered, finish = asyncio.Event(), asyncio.Event()
        async def writer():
            async with a.s.economy_guard.operation(a.db):
                entered.set()
                await finish.wait()
                await a.db.users.update_one({"session_id": "player"}, {"$inc": {"balance": 500}})
        writing = asyncio.create_task(writer())
        await entered.wait()
        resetting = asyncio.create_task(reset(a))
        for _ in range(200):
            if (await a.db.economy_control.find_one({"_id": "main"}))["resetting"]:
                break
            await asyncio.sleep(.01)
        assert not resetting.done()
        assert (await a.request("/stats")).status_code == 503
        finish.set()
        await writing
        result = await resetting
        assert result.status_code == 200, result.text
        assert (await a.db.users.find_one({"session_id": "player"}))["balance"] == 0
        assert (await a.request("/stats")).status_code == 200
    run(check())


def test_busy_reset_changes_nothing_and_reopens_gate(economy, monkeypatch):
    async def check():
        a = economy
        monkeypatch.setattr(a.s.economy_reset, "drain", AsyncMock(side_effect=HTTPException(409, "busy")))
        assert (await reset(a)).status_code == 409
        assert (await a.db.users.find_one({"session_id": "player"}))["balance"] == 12.5
        assert (await a.request("/stats")).status_code == 200
        assert await a.db.economy_resets.count_documents({}) == 0
    run(check())


def test_partial_failure_blocks_writes_and_startup_finishes_same_reset(economy, monkeypatch):
    if os.environ.get("ADMIN_TEST_MONGO_URL"):
        pytest.skip("Mock fault injection; other tests also run on real MongoDB")
    original = Collection.delete_many
    def fail_after_users(self, *args, **kwargs):
        if self.name == "upgrades":
            raise RuntimeError("simulated database interruption")
        return original(self, *args, **kwargs)
    async def check():
        a = economy
        body = payload()
        monkeypatch.setattr(Collection, "delete_many", fail_after_users)
        assert (await reset(a, body)).status_code == 500
        assert (await a.request("/stats")).status_code == 503
        assert (await a.db.users.find_one({"session_id": "player"}))["balance"] == 0
        monkeypatch.setattr(Collection, "delete_many", original)
        await a.s.economy_reset.resume(a.db)
        assert (await a.request("/stats")).json()["upgrades"] == 2
        assert (await reset(a, body)).status_code == 200
        assert await a.db.upgrades.count_documents({}) == 0
    run(check())
