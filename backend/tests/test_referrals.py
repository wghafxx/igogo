import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient
from mongomock.collection import Collection

run = asyncio.run


@pytest.fixture
def referral_api(isolated_server, monkeypatch):
    server = isolated_server
    db = server.db = AsyncMongoMockClient().referrals
    refs = server.referrals
    real_client = httpx.AsyncClient
    original_find_and_update = Collection.find_one_and_update

    def projected_update(collection, query, changes, *args, **kwargs):
        # mongomock re-queries after updates; retaining _id matches MongoDB's
        # post-update projection when a consumed skin no longer matches the query.
        projection = kwargs.get("projection")
        hide_id = kwargs.get("return_document") and projection and projection.get("_id") == 0
        if hide_id:
            kwargs["projection"] = {**projection, "_id": 1} if any(v for k, v in projection.items() if k != "_id") else None
        result = original_find_and_update(collection, query, changes, *args, **kwargs)
        if hide_id and result:
            result.pop("_id", None)
        return result

    monkeypatch.setattr(Collection, "find_one_and_update", projected_update)

    async def setup():
        await db.users.create_index("session_id", unique=True)
        await db.bank_state.create_index("id", unique=True)
        await db.bank_ledger.create_index("id", unique=True)
        await refs.ensure_indexes(db)
        await db.users.insert_many([
            {"session_id": "discord_1", "discord_id": "1", "nickname": "Inviter", "balance": 0, "skins": [], "created_at": refs.now()},
            {"session_id": "discord_2", "discord_id": "2", "nickname": "Friend", "balance": 1000, "skins": [], "referred_by": "discord_1", "created_at": refs.now()},
            {"session_id": "discord_3", "discord_id": "3", "nickname": "Other", "balance": 1000, "skins": [], "created_at": refs.now()},
        ])
        await db.shop_items.insert_one({"id": "target", "price": 1000, "name": "Target", "rarity": "pink"})
        await db.bank_state.insert_one({"id": "main", "bank": 10000, "pool": 10000})
    run(setup())
    server.upgrade_rate_ok = lambda sid: True
    server.bank_settings = AsyncMock(return_value={"rtp_target": .85})
    server.ensure_pool = AsyncMock()
    server.rain_maybe_close = AsyncMock()
    server.rain_maybe_start = AsyncMock(return_value=None)
    server.rain_active = AsyncMock(return_value=None)
    server.luck_boosted = AsyncMock(return_value=False)
    server._rng = SimpleNamespace(random=lambda: 0.0)

    async def send(method="GET", path="/api/referrals", who="discord_1", **kwargs):
        headers = kwargs.pop("headers", {})
        if who:
            headers["Authorization"] = f"Bearer {server.make_token(who)}"
        async with real_client(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await client.request(method, path, headers=headers, **kwargs)

    async def game(balance=0, skins=None, who="discord_2"):
        return await send("POST", "/api/upgrade", who, json={"session_id": who, "bet_amount": balance,
                         "bet_items": skins or [], "target_item": {"id": "target"}})

    async def deposit(dep_id="d1", rap=100, **fields):
        doc = {"id": dep_id, "session_id": "discord_2", "nickname": "Friend", "status": "processing", "rap": rap,
               "credited": rap * .8, "balance_credited": rap * .8, "issued_skins": [], "skins_total": 0,
               "planned_at": refs.now(), **fields}
        await db.deposits.insert_one(dict(doc))
        return doc

    return SimpleNamespace(server=server, db=db, refs=refs, send=send, game=game, deposit=deposit, real_client=real_client)


def test_referral_link_is_stable_unique_private_and_requires_login(referral_api):
    async def check():
        a = referral_api
        responses = await asyncio.gather(*(a.send() for _ in range(5)))
        links = {r.json()["url"] for r in responses}
        assert len(links) == 1
        code = parse_qs(urlsplit(links.pop()).query)["ref"][0]
        assert a.refs.CODE_PATTERN.fullmatch(code)
        assert (await a.send(who="discord_3")).json()["url"] != responses[0].json()["url"]
        assert (await a.send(who=None)).status_code == 401
        assert "discord_2" not in str(responses[0].json())
        assert responses[0].json()["invites"][0]["nickname"] == "Friend"
        assert (await a.send(who="discord_3")).json()["invited_count"] == 0
    run(check())


def test_25_rap_requires_100_in_completed_balance_and_skin_wagers(referral_api):
    async def check():
        a = referral_api
        await a.db.users.update_one({"session_id": "discord_2"}, {"$push": {"skins": {"uid": "skin", "price": 60}}})
        assert (await a.game(39.99, [{"uid": "skin"}])).status_code == 200
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == 0
        # A rejected game and a forged skin price must not count as wagering.
        assert (await a.game(40, [{"uid": "missing", "price": 10000}])).status_code == 400
        assert (await a.game(20)).status_code == 200
        user = await a.db.users.find_one({"session_id": "discord_1"})
        assert user["balance"] == 25
        assert (await a.game(100)).status_code == 200
        await a.refs.reconcile_once(a.db)
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == 25
        assert await a.db.referral_rewards.count_documents({"kind": "qualified"}) == 1
        summary = (await a.send()).json()
        assert summary["qualified_count"] == 1 and summary["earned_rap"] == 25
    run(check())


@pytest.mark.parametrize("amount,qualifies", [(99.99, False), (99.995, False), (100, True), (100.01, True)])
def test_exact_wager_threshold(referral_api, amount, qualifies):
    async def check():
        a = referral_api
        assert (await a.game(amount)).status_code == 200
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == (25 if qualifies else 0)
    run(check())


def test_parallel_milestones_pay_only_once(referral_api):
    async def check():
        a = referral_api
        responses = await asyncio.gather(*(a.game(60) for _ in range(4)))
        assert all(r.status_code == 200 for r in responses)
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == 25
        assert await a.db.referral_rewards.count_documents({}) == 1
    run(check())


@pytest.mark.parametrize("rap,expected", [(35, 1.23), (100, 3.5), (123.45, 4.32)])
def test_deposit_percent_is_immediate_based_on_gross_and_repeat_safe(referral_api, rap, expected):
    async def check():
        from deposit_settlement import settle_deposit
        a = referral_api
        doc = await a.deposit(rap=rap, promo_bonus=.1)
        # Before verified settlement, no reward can be credited.
        await a.refs.reward_deposit(a.db, doc)
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == 0
        await settle_deposit(a.db, doc)
        await settle_deposit(a.db, doc)
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == expected
        assert await a.db.referral_rewards.count_documents({"kind": "qualified"}) == 0
        assert (await a.db.bank_state.find_one({"id": "main"}))["bank"] == 10000 + rap
        assert (await a.send()).json()["deposit_earned_rap"] == expected
    run(check())


def test_deposit_rewards_continue_after_qualification_and_time_passes(referral_api):
    async def check():
        from deposit_settlement import settle_deposit
        a = referral_api
        await a.db.users.update_one({"session_id": "discord_2"}, {"$set": {"created_at": a.refs.now() - timedelta(days=1500)}})
        assert (await a.game(100)).status_code == 200
        for i in range(3):
            await settle_deposit(a.db, await a.deposit(f"deposit-{i}"))
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == 35.5
        assert (await a.send()).json()["deposit_earned_rap"] == 10.5
    run(check())


def test_interrupted_credit_recovers_without_paying_again(referral_api, monkeypatch):
    async def check():
        a = referral_api
        original = Collection.update_one
        failed = False
        def interrupted(collection, query, changes, *args, **kwargs):
            nonlocal failed
            if collection.name == "referral_rewards" and changes.get("$set", {}).get("status") == "paid" and not failed:
                failed = True
                raise RuntimeError("interrupted after balance credit")
            return original(collection, query, changes, *args, **kwargs)
        monkeypatch.setattr(Collection, "update_one", interrupted)
        # The game still succeeds; the persisted event and reward are retried later.
        assert (await a.game(100)).status_code == 200
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == 25
        assert await a.db.upgrades.count_documents({"referral_pending": True}) == 1
        await a.refs.reconcile_once(a.db)
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == 25
        assert await a.db.upgrades.count_documents({"referral_pending": True}) == 0
        assert (await a.db.referral_rewards.find_one({}))["status"] == "paid"
    run(check())


def test_self_referral_and_unreferred_accounts_never_reward(referral_api):
    async def check():
        from deposit_settlement import settle_deposit
        a = referral_api
        await a.db.users.update_one({"session_id": "discord_2"}, {"$set": {"referred_by": "discord_2"}})
        await settle_deposit(a.db, await a.deposit())
        assert (await a.game(100)).status_code == 200
        assert (await a.game(100, who="discord_3")).status_code == 200
        assert await a.db.referral_rewards.count_documents({}) == 0
    run(check())


def test_referral_failure_does_not_block_payment_and_recovers_without_user_action(referral_api, monkeypatch):
    async def check():
        from deposit_settlement import settle_deposit
        a = referral_api
        original = a.refs.reward_deposit
        monkeypatch.setattr(a.refs, "reward_deposit", AsyncMock(side_effect=RuntimeError("temporary failure")))
        result = await settle_deposit(a.db, await a.deposit())
        assert result["ok"] is True
        assert (await a.db.deposits.find_one({"id": "d1"}))["status"] == "confirmed"
        assert (await a.db.deposits.find_one({"id": "d1"}))["referral_pending"] is True
        assert (await a.db.users.find_one({"session_id": "discord_2"}))["balance"] == 1080
        monkeypatch.setattr(a.refs, "reward_deposit", original)
        await a.refs.reconcile_once(a.db)
        await a.refs.reconcile_once(a.db)
        assert (await a.db.users.find_one({"session_id": "discord_1"}))["balance"] == 3.5
        assert "referral_pending" not in await a.db.deposits.find_one({"id": "d1"})
    run(check())


@pytest.mark.parametrize("discord_id,referral", [("4", "valid"), ("3", "valid"), ("1", "valid"), ("4", "invalid")])
def test_oauth_attributes_only_new_accounts_from_verified_login_state(referral_api, monkeypatch, discord_id, referral):
    async def check():
        a = referral_api
        code = await a.refs.referral_code(a.db, "discord_1") if referral == "valid" else "f" * 16
        login = await a.send(path=f"/api/auth/discord/login?ref={code}", who=None)
        assert login.status_code == 307
        state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
        def discord_provider(request):
            return httpx.Response(200, json={"access_token": "test-discord-token"} if request.url.path.endswith("/token") else {"id": discord_id, "username": "New friend"})
        monkeypatch.setattr(a.server.httpx, "AsyncClient", lambda **kwargs: a.real_client(transport=httpx.MockTransport(discord_provider), **kwargs))
        response = await a.send(path=f"/api/auth/discord/callback?code=test&state={state}&ref=forged", who=None, headers={"Cookie": f"bg_oauth_state={state}"})
        assert response.status_code == 307 and "/auth/callback#token=" in response.headers["location"]
        user = await a.db.users.find_one({"session_id": f"discord_{discord_id}"})
        assert user.get("referred_by") == ("discord_1" if discord_id == "4" and referral == "valid" else None)
        assert await a.db.oauth_states.count_documents({}) == 0
    run(check())
