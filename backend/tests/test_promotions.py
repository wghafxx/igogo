"""Promo API, unique-account statistics and migration in an isolated Mongo mock.

Install backend/requirements-test.txt, then run pytest tests/test_promotions.py.
"""

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient
from mongomock.collection import Collection


@pytest.fixture
def promo_api(isolated_server, monkeypatch):
    original_create_index = Collection.create_index

    def create_index(collection, keys, **kwargs):
        # mongomock 4.3 revalidates existing partial indexes against *all* rows.
        # MongoDB returns an unchanged index immediately; preserve that behavior.
        key_list = [(keys, 1)] if isinstance(keys, str) else keys
        name = kwargs.get("name", "_".join(f"{key}_{direction}" for key, direction in key_list))
        existing = collection.index_information().get(name)
        expected = {"key": key_list, **kwargs}
        expected.pop("name", None)
        if existing and {k: v for k, v in existing.items() if k != "v"} == expected:
            return name
        return original_create_index(collection, keys, **kwargs)

    monkeypatch.setattr(Collection, "create_index", create_index)
    server = isolated_server
    server.db = AsyncMongoMockClient()["promotions_test"]
    db = server.db

    async def setup():
        await server.ensure_promotions(db)
        await db.user_locks.create_index("session_id", unique=True)
        await db.users.insert_many([{
            "session_id": f"discord_{i}", "discord_id": str(i), "nickname": f"Player {i}",
            "balance": 0, "skins": [], "roblox_nick": f"Player{i}",
            "roblox_link": f"https://www.roblox.com/users/{i}/profile",
        } for i in (1, 2)])
        await db.admin_sessions.insert_one({
            "jti": "promo-admin", "revoked": False, "expires_at": server.now_utc() + timedelta(hours=1),
            "ua_hash": hashlib.sha256(b"PromoTest").hexdigest()[:32],
        })

    asyncio.run(setup())
    admin_token = server.make_token("admin", "admin", extra={
        "type": "admin", "jti": "promo-admin", "seed_version": hashlib.sha256(server.ADMIN_SEED_HASH).hexdigest(),
    })

    async def send(method, path, *, who="admin", **kwargs):
        token = admin_token if who == "admin" else server.make_token(who) if who else None
        headers = {"User-Agent": "PromoTest"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await client.request(method, path, headers=headers, **kwargs)

    def request(method, path, **kwargs):
        return asyncio.run(send(method, path, **kwargs))

    def apply(code, who="discord_1"):
        return request("POST", "/api/promo/apply", who=who, json={"code": code})

    def promos():
        response = request("GET", "/api/admin/promos")
        assert response.status_code == 200, response.text
        return {promo["code"]: promo for promo in response.json()}

    return SimpleNamespace(server=server, db=db, request=request, send=send, apply=apply, promos=promos)


def test_default_promos_accept_mixed_case_and_keep_gold_reward(promo_api):
    api = promo_api
    for code, bonus in ((" pelMen ", .10), ("inkab00m", .09), ("sinzuku", .075), ("xyipachosik", .067)):
        response = api.apply(code)
        assert response.status_code == 200, response.text
        assert response.json()["promo_code"] == code.strip().upper()
        assert response.json()["promo_bonus"] == bonus
    assert api.apply("pelmen").json()["gold_nick"] is True
    assert {code: row["unique_users"] for code, row in api.promos().items()} == {
        "PELMEN": 1, "INKAB00M": 1, "SINZUKU": 1, "XYIPACHOSIK": 1,
    }


def test_only_sinzuku_is_seeded_as_media_with_launch_terms(promo_api):
    rows = promo_api.promos()
    assert rows["SINZUKU"]["is_media"] is True
    assert rows["SINZUKU"]["percent"] == 7.5
    assert rows["SINZUKU"]["media_percent"] == 13
    for code in ("PELMEN", "INKAB00M", "XYIPACHOSIK"):
        assert rows[code]["is_media"] is False
        assert rows[code]["media_percent"] == rows[code]["media_payout_rub"] == 0


def test_media_launch_updates_existing_bonus_once_and_preserves_saved_deposits(promo_api):
    api = promo_api
    api.apply("sinzuku")

    async def upgrade_old_terms():
        await api.db.migrations.delete_one({"_id": "media-promo-sinzuku-start-v1"})
        await api.db.promo_codes.update_one({"id": "default-sinzuku"}, {
            "$set": {"percent": 10}, "$unset": {"is_media": "", "media_percent": ""}})
        await api.db.users.update_one({"session_id": "discord_1"}, {"$set": {"promo_bonus": .1}})
        await api.db.deposits.insert_one({"id": "before-media-launch", "promo_id": "default-sinzuku",
            "promo_code": "SINZUKU", "promo_bonus": .1, "status": "pending", "expected_rap": 200})
        saved_deposit = await api.db.deposits.find_one({"id": "before-media-launch"})
        await api.server.ensure_promotions(api.db)
        assert (await api.db.users.find_one({"session_id": "discord_1"}))["promo_bonus"] == .075
        assert await api.db.deposits.find_one({"id": "before-media-launch"}) == saved_deposit

    asyncio.run(upgrade_old_terms())
    assert api.promos()["SINZUKU"]["media_percent"] == 13
    response = api.request("PUT", "/api/admin/promos/default-sinzuku", json={
        "code": "SINZUKU", "percent": 8, "is_media": True, "media_percent": 17})
    assert response.status_code == 200, response.text
    for _ in range(2):
        asyncio.run(api.server.ensure_promotions(api.db))
    row = api.promos()["SINZUKU"]
    assert row["percent"] == 8 and row["media_percent"] == 17
    assert api.request("GET", "/api/auth/me", who="discord_1").json()["promo_bonus"] == .08


def test_launch_does_not_resurrect_deleted_media_code(promo_api):
    api = promo_api
    assert api.request("DELETE", "/api/admin/promos/default-sinzuku").status_code == 200
    asyncio.run(api.db.migrations.delete_one({"_id": "media-promo-sinzuku-start-v1"}))
    asyncio.run(api.server.ensure_promotions(api.db))
    assert "SINZUKU" not in api.promos()


def test_media_crud_defaults_preserves_legacy_edits_and_can_remove_mark(promo_api):
    api = promo_api
    created = api.request("POST", "/api/admin/promos", json={
        "code": "STREAM", "percent": 7.5, "is_media": True})
    assert created.status_code == 201, created.text
    promo = created.json()
    assert promo["is_media"] is True and promo["media_percent"] == 13
    assert api.apply("stream").json()["promo_bonus"] == .075
    path = f"/api/admin/promos/{promo['id']}"
    changed = api.request("PUT", path, json={"code": "STREAM_NEW", "percent": 8})
    assert changed.status_code == 200, changed.text
    assert changed.json()["is_media"] is True and changed.json()["media_percent"] == 13
    assert changed.json()["unique_users"] == 1
    assert api.request("GET", "/api/auth/me", who="discord_1").json()["promo_bonus"] == .08
    removed = api.request("PUT", path, json={"code": "STREAM_NEW", "percent": 8, "is_media": False})
    assert removed.status_code == 200, removed.text
    assert removed.json()["is_media"] is False and removed.json()["media_percent"] == 0
    reenabled = api.request("PUT", path, json={"code": "STREAM_NEW", "percent": 7.5, "is_media": True})
    assert reenabled.status_code == 200, reenabled.text
    assert reenabled.json()["media_percent"] == 13
    ordinary = api.request("POST", "/api/admin/promos", json={"code": "ORDINARY", "percent": 10}).json()
    assert ordinary["is_media"] is False and ordinary["media_percent"] == 0


@pytest.mark.parametrize("rate", [-1, 100.01, "NaN", "Infinity", 13.001])
def test_invalid_media_rates_are_rejected(promo_api, rate):
    body = {"code": "SINZUKU", "percent": 7.5, "is_media": True, "media_percent": rate}
    assert promo_api.request("POST", "/api/admin/promos", json=body).status_code == 422
    assert promo_api.request("PUT", "/api/admin/promos/default-sinzuku", json=body).status_code == 422


def test_only_media_percent_promos_can_have_commission(promo_api):
    api = promo_api
    body = {"code": "NO_MARK", "percent": 7.5, "media_percent": 13}
    assert api.request("POST", "/api/admin/promos", json=body).status_code == 422
    assert api.request("PUT", "/api/admin/promos/default-pelmen", json=body).status_code == 422
    for extra in ({"is_media": True}, {"media_percent": 13}):
        assert api.request("POST", "/api/admin/promos", json={"code": "GIFT", "type": "rap_fixed",
            "amount_rap": 100, "max_uses": 10, **extra}).status_code == 422


def test_media_salary_uses_gross_confirmed_deposits_and_selected_period(promo_api):
    api = promo_api
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    base = {"promo_id": "default-sinzuku", "promo_code": "SINZUKU", "rap": 1000,
            "status": "confirmed", "session_id": "discord_1", "resolved_at": start,
            "credited": 100000}
    asyncio.run(api.db.deposits.insert_many([
        {**base, "id": "skin"},
        {**base, "id": "card", "payment_method": "donationalerts", "resolved_at": end},
        {**base, "id": "crypto", "payment_method": "cryptobot", "rap": 100000},
        {**base, "id": "pending", "status": "pending"},
        {**base, "id": "rejected", "status": "rejected"},
    ]))
    asyncio.run(api.db.promo_gifts.insert_one({"id": "gift", "promo_id": "default-sinzuku", "amount_rap": 100000}))
    row = api.promos()["SINZUKU"]
    assert row["deposited_rap"] == 102000
    assert row["media_payout_rub"] == 3315
    response = api.request("GET", "/api/admin/promos", params={"date_from": start.isoformat(), "date_to": end.isoformat()})
    assert response.status_code == 200, response.text
    row = next(p for p in response.json() if p["code"] == "SINZUKU")
    assert row["deposited_rap"] == 101000 and row["media_payout_rub"] == 3282.5
    renamed = api.request("PUT", "/api/admin/promos/default-sinzuku", json={"code": "NEW_MEDIA", "percent": 7.5})
    assert renamed.status_code == 200, renamed.text
    assert api.promos()["NEW_MEDIA"]["media_payout_rub"] == 3315
    assert api.server.promos.media_payout_rub(1000, 13) == 32.5
    assert api.server.promos.media_payout_rub(3, 13) == .1  # Round the period total to kopecks.
    assert api.server.promos.media_payout_rub(1000, 0) == 0


def test_repeated_and_parallel_activations_count_accounts_once(promo_api):
    api = promo_api

    async def activate_many():
        return await asyncio.gather(*[
            api.send("POST", "/api/promo/apply", who="discord_1", json={"code": "pelmen"})
            for _ in range(12)
        ])

    assert all(r.status_code == 200 for r in asyncio.run(activate_many()))
    assert api.promos()["PELMEN"]["unique_users"] == 1
    assert api.apply("pelmen", "discord_2").status_code == 200
    api.apply("inkab00m")
    api.apply("pelmen")
    assert api.promos()["PELMEN"]["unique_users"] == 2
    assert api.promos()["INKAB00M"]["unique_users"] == 1


def test_same_discord_account_with_another_session_does_not_inflate_count(promo_api):
    api = promo_api
    api.apply("pelmen")
    asyncio.run(api.db.users.insert_one({"session_id": "another-session", "discord_id": "1", "nickname": "Player"}))
    assert api.apply("pelmen", "another-session").status_code == 200
    assert api.promos()["PELMEN"]["unique_users"] == 1


def test_crud_rename_keeps_statistics_and_updates_active_bonus(promo_api):
    api = promo_api
    created = api.request("POST", "/api/admin/promos", json={"code": "spring", "percent": 12.34})
    assert created.status_code == 201, created.text
    promo = created.json()
    assert promo["code"] == "SPRING" and promo["unique_users"] == 0
    assert api.apply("spring").json()["promo_bonus"] == .1234
    changed = api.request("PUT", f"/api/admin/promos/{promo['id']}", json={"code": "summer", "percent": 9.5})
    assert changed.status_code == 200, changed.text
    assert changed.json()["unique_users"] == 1
    assert api.apply("spring").status_code == 400
    me = api.request("GET", "/api/auth/me", who="discord_1").json()
    assert (me["promo_code"], me["promo_bonus"]) == ("SUMMER", .095)
    api.apply("summer")
    assert api.promos()["SUMMER"]["unique_users"] == 1
    assert api.request("DELETE", f"/api/admin/promos/{promo['id']}").status_code == 200
    assert api.apply("summer").status_code == 400
    me = api.request("GET", "/api/auth/me", who="discord_1").json()
    assert me["promo_code"] is None and me["promo_bonus"] == 0


def test_seed_edits_and_deletions_survive_restart(promo_api):
    api = promo_api
    api.apply("pelmen")
    api.request("PUT", "/api/admin/promos/default-pelmen", json={"code": "dumpling", "percent": 15})
    api.request("DELETE", "/api/admin/promos/default-inkab00m")
    for _ in range(2):
        asyncio.run(api.server.ensure_promotions(api.db))
    rows = api.promos()
    assert "PELMEN" not in rows and "INKAB00M" not in rows
    assert rows["DUMPLING"]["percent"] == 15 and rows["DUMPLING"]["unique_users"] == 1


def test_duplicate_codes_are_case_insensitive(promo_api):
    api = promo_api
    created = api.request("POST", "/api/admin/promos", json={"code": "pElMeN", "percent": 9})
    assert created.status_code == 409
    updated = api.request("PUT", "/api/admin/promos/default-inkab00m", json={"code": "pelmen", "percent": 9})
    assert updated.status_code == 409


def test_recreated_code_has_new_identity_and_does_not_inherit_old_accounts(promo_api):
    api = promo_api
    api.apply("pelmen")
    assert api.request("DELETE", "/api/admin/promos/default-pelmen").status_code == 200
    response = api.request("POST", "/api/admin/promos", json={"code": "pelmen", "percent": 11})
    assert response.status_code == 201
    assert response.json()["id"] != "default-pelmen" and response.json()["unique_users"] == 0
    asyncio.run(api.server.ensure_promotions(api.db))
    assert api.promos()["PELMEN"]["percent"] == 11
    assert api.request("GET", "/api/auth/me", who="discord_1").json()["promo_bonus"] == 0


@pytest.mark.parametrize("body", [
    {"code": "", "percent": 10}, {"code": "two words", "percent": 10},
    {"code": "A" * 33, "percent": 10}, {"code": "A", "percent": 0},
    {"code": "A", "percent": -1}, {"code": "A", "percent": 50.01},
    {"code": "A", "percent": "NaN"}, {"code": "A", "percent": "Infinity"},
    {"code": "A", "percent": 1.234}, {"code": "A"},
])
def test_invalid_promo_data_is_rejected(promo_api, body):
    assert promo_api.request("POST", "/api/admin/promos", json=body).status_code == 422
    assert promo_api.request("PUT", "/api/admin/promos/default-pelmen", json=body).status_code == 422


@pytest.mark.parametrize("who", [None, "discord_1"])
def test_all_management_routes_require_real_admin_session(promo_api, who):
    for method, path, kwargs in (
        ("GET", "/api/admin/promos", {}),
        ("POST", "/api/admin/promos", {"json": {"code": "test", "percent": 10}}),
        ("PUT", "/api/admin/promos/default-pelmen", {"json": {"code": "test", "percent": 10}}),
        ("DELETE", "/api/admin/promos/default-pelmen", {}),
    ):
        assert promo_api.request(method, path, who=who, **kwargs).status_code == 403


def test_invalid_or_unauthenticated_activation_does_not_count(promo_api):
    assert promo_api.apply("missing").status_code == 400
    assert promo_api.apply("pelmen", who=None).status_code == 401
    assert all(row["unique_users"] == 0 for row in promo_api.promos().values())


def test_unknown_or_already_deleted_promos_return_404(promo_api):
    assert promo_api.request("DELETE", "/api/admin/promos/missing").status_code == 404
    assert promo_api.request("PUT", "/api/admin/promos/missing", json={"code": "test", "percent": 10}).status_code == 404
    promo_api.request("DELETE", "/api/admin/promos/default-pelmen")
    assert promo_api.request("PUT", "/api/admin/promos/default-pelmen", json={"code": "test", "percent": 10}).status_code == 404


def test_migration_recovers_unique_accounts_from_users_and_deposit_history(promo_api):
    api = promo_api

    async def migrate():
        await api.db.migrations.delete_one({"_id": "promo-activation-history-v1"})
        await api.db.users.update_one({"session_id": "discord_1"}, {"$set": {"promo_code": "SINZUKU", "promo_bonus": .1}})
        await api.db.deposits.insert_many([
            {"id": str(i), "session_id": sid, "promo_code": code, "promo_bonus": .067, "status": "confirmed"}
            for i, (sid, code) in enumerate([
                ("discord_1", "SINZUKU"), ("discord_1", "SINZUKU"),
                ("discord_1", "XYIPACHOSIK"), ("discord_2", "XYIPACHOSIK"),
            ])
        ])
        before = await api.db.deposits.find({}).to_list(None)
        await api.server.ensure_promotions(api.db)
        await api.server.ensure_promotions(api.db)
        assert await api.db.deposits.find({}).to_list(None) == before
        assert (await api.db.users.find_one({"session_id": "discord_1"}))["promo_id"] == "default-sinzuku"

    asyncio.run(migrate())
    assert api.promos()["SINZUKU"]["unique_users"] == 1
    assert api.promos()["XYIPACHOSIK"]["unique_users"] == 2
    api.apply("xyipachosik")
    assert api.promos()["XYIPACHOSIK"]["unique_users"] == 2


def test_deposits_freeze_terms_but_new_requests_resolve_edits_and_deletions(promo_api):
    api = promo_api
    asyncio.run(api.db.users.update_one({"session_id": "discord_1"}, {"$set": {
        "roblox_display_name": "Player", "roblox_nick": "player_1", "roblox_link": "https://www.roblox.com/users/1/profile"}}))
    api.apply("pelmen")
    body = {"description": "Test skins", "expected_rap": 200, "receiver_id": "support"}

    def deposit():
        response = api.request("POST", "/api/deposits", who="discord_1", json=body)
        assert response.status_code == 200, response.text
        # One active skin request per player: settle the previous one before the next request.
        asyncio.run(api.db.deposits.update_one({"id": response.json()["id"]}, {"$set": {"created_at": api.server.now_utc() - timedelta(minutes=2), "status": "rejected"}}))
        return response.json()

    original = deposit()
    assert original["promo_bonus"] == .1
    api.request("PUT", "/api/admin/promos/default-pelmen", json={"code": "newpelmen", "percent": 20})
    # Simulate stale cache from an overlapping activation/update.
    asyncio.run(api.db.users.update_one({"session_id": "discord_1"}, {"$set": {"promo_code": "PELMEN", "promo_bonus": .1}}))
    changed = deposit()
    assert changed["promo_code"] == "NEWPELMEN" and changed["promo_bonus"] == .2
    api.request("DELETE", "/api/admin/promos/default-pelmen")
    asyncio.run(api.db.users.update_one({"session_id": "discord_1"}, {"$set": {"promo_id": "default-pelmen", "promo_code": "NEWPELMEN", "promo_bonus": .2}}))
    removed = deposit()
    assert removed["promo_code"] is None and removed["promo_bonus"] == 0
    assert asyncio.run(api.db.deposits.find_one({"id": original["id"]}))["promo_bonus"] == .1
    assert asyncio.run(api.db.deposits.find_one({"id": changed["id"]}))["promo_bonus"] == .2
    assert asyncio.run(api.db.promo_activations.count_documents({"promo_id": "default-pelmen"})) == 1


# ---------------------------------------------------------------------------
# rap_fixed: instant RAP gifts (disabled by default until budget is approved)
# ---------------------------------------------------------------------------

def test_confirmed_deposits_count_gross_rap_once_without_bonuses(promo_api):
    api = promo_api
    asyncio.run(api.db.users.update_one({"session_id": "discord_1"}, {"$set": {
        "roblox_display_name": "Player", "roblox_nick": "player_1",
        "roblox_link": "https://www.roblox.com/users/1/profile"}}))
    api.apply("pelmen")
    response = api.request("POST", "/api/deposits", who="discord_1", json={
        "description": "Actual skins", "expected_rap": 9999, "receiver_id": "support"})
    assert response.status_code == 200, response.text
    dep_id = response.json()["id"]
    assert api.promos()["PELMEN"]["deposited_rap"] == 0
    for _ in range(2):
        confirmed = api.request("POST", f"/api/admin/deposits/{dep_id}/confirm", json={"rap": 200})
        assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["credited"] == 176  # 20% fee, then +10% bonus.
    stats = api.promos()["PELMEN"]
    assert stats["deposited_rap"] == stats["skin_deposited_rap"] == 200
    assert stats["cash_deposited_rap"] == 0
    assert stats["deposit_count"] == stats["depositors"] == 1
    api.apply("sinzuku")
    assert api.promos()["PELMEN"]["deposited_rap"] == 200
    assert api.promos()["SINZUKU"]["deposited_rap"] == 0


def test_promo_deposit_totals_include_repeat_paid_methods_but_exclude_nonpayments(promo_api):
    api = promo_api
    now = api.server.now_utc()
    base = {"promo_id": "default-pelmen", "promo_code": "PELMEN", "status": "confirmed",
            "session_id": "discord_1", "resolved_at": now, "rap": 60, "credited": 1000}
    docs = [{**base, "id": "skin"},
            {**base, "id": "xrocket", "payment_method": "xrocket", "rap": 70},
            {**base, "id": "cryptobot", "payment_method": "cryptobot", "rap": 200.12,
             "session_id": "another-session", "discord_id": "1"},
            {**base, "id": "card", "payment_method": "donationalerts", "rap": 500},
            {**base, "id": "second-player", "session_id": "discord_2", "rap": 100.01},
            {**base, "id": "missing-actual", "rap": None, "expected_rap": 100000},
            {**base, "id": "without-promo", "promo_id": None},
            {**base, "id": "other-promo", "promo_id": "default-sinzuku"},
            *[{**base, "id": status, "status": status, "rap": 10000} for status in (
                "pending", "processing", "rejected", "cancelled", "awaiting_payment", "expired", "payment_error")]]
    asyncio.run(api.db.deposits.insert_many(docs))
    asyncio.run(api.db.promo_gifts.insert_one({"id": "gift", "promo_id": "default-pelmen", "amount_rap": 100000}))
    asyncio.run(api.db.admin_coin_grants.insert_one({"id": "grant", "session_id": "discord_1", "amount_rap": 100000}))
    for _ in range(2):
        stats = api.promos()["PELMEN"]
        assert stats["deposited_rap"] == 930.13
        assert stats["skin_deposited_rap"] == 160.01
        assert stats["cash_deposited_rap"] == 770.12
        assert stats["deposit_count"] == 5
        assert stats["depositors"] == 2


def test_promo_deposit_period_uses_confirmation_time_with_exclusive_end(promo_api):
    api = promo_api
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    base = {"promo_id": "default-pelmen", "status": "confirmed", "rap": 60,
            "session_id": "discord_1", "created_at": start - timedelta(days=30)}
    asyncio.run(api.db.deposits.insert_many([
        {**base, "id": "before", "resolved_at": start - timedelta(microseconds=1)},
        {**base, "id": "start", "resolved_at": start},
        {**base, "id": "last", "resolved_at": end - timedelta(microseconds=1)},
        {**base, "id": "end", "resolved_at": end},
        {**base, "id": "undated"},
    ]))
    api.apply("pelmen")
    response = api.request("GET", "/api/admin/promos", params={
        "date_from": "2026-10-01T05:00:00+05:00", "date_to": end.isoformat()})
    assert response.status_code == 200, response.text
    row = next(p for p in response.json() if p["code"] == "PELMEN")
    assert row["deposited_rap"] == 120 and row["deposit_count"] == 2
    assert row["unique_users"] == 1  # Activations remain all-time.
    assert api.promos()["PELMEN"]["deposited_rap"] == 300
    for params in ({"date_from": end.isoformat(), "date_to": start.isoformat()},
                   {"date_from": start.isoformat(), "date_to": start.isoformat()},
                   {"date_from": "not-a-date"}):
        assert api.request("GET", "/api/admin/promos", params=params).status_code == 422
    for params, expected in (({"date_from": end.isoformat()}, 60),
                             ({"date_to": start.isoformat()}, 60)):
        response = api.request("GET", "/api/admin/promos", params=params)
        assert next(p for p in response.json() if p["code"] == "PELMEN")["deposited_rap"] == expected


def test_promo_rename_preserves_deposits_recreation_does_not_inherit_them(promo_api):
    api = promo_api
    asyncio.run(api.db.deposits.insert_many([
        {"id": "old", "status": "confirmed", "promo_id": "default-pelmen", "promo_code": "PELMEN", "rap": 200},
        {"id": "legacy", "status": "confirmed", "promo_code": "PELMEN", "rap": 9000},
    ]))
    api.request("PUT", "/api/admin/promos/default-pelmen", json={"code": "renamed", "percent": 10})
    assert api.promos()["RENAMED"]["deposited_rap"] == 200
    api.request("DELETE", "/api/admin/promos/default-pelmen")
    new = api.request("POST", "/api/admin/promos", json={"code": "pelmen", "percent": 10}).json()
    assert api.promos()["PELMEN"]["deposited_rap"] == 0
    asyncio.run(api.db.deposits.insert_one({
        "id": "new", "status": "confirmed", "promo_id": new["id"], "promo_code": "PELMEN", "rap": 60}))
    assert api.promos()["PELMEN"]["deposited_rap"] == 60


def test_gift_promo_never_reports_gift_or_deposit_turnover(promo_api, monkeypatch):
    api = promo_api
    _enable_rap(monkeypatch)
    gift = _create_rap(api, "GIFT_STATS", 100, 5).json()
    assert api.apply("GIFT_STATS").status_code == 200
    # Even malformed legacy links to a gift promo must not turn gifts into revenue.
    asyncio.run(api.db.deposits.insert_one({
        "id": "invalid-gift-deposit", "status": "confirmed", "promo_id": gift["id"], "rap": 10000}))
    row = api.promos()["GIFT_STATS"]
    assert row["deposited_rap"] == row["skin_deposited_rap"] == row["cash_deposited_rap"] == 0
    assert row["deposit_count"] == row["depositors"] == 0
    assert row["used_count"] == 1

def _enable_rap(monkeypatch):
    monkeypatch.setenv("RAP_FIXED_ENABLED", "1")


def _create_rap(api, code="GIFT100", amount=100, max_uses=10, expires_at=None):
    body = {"code": code, "type": "rap_fixed", "amount_rap": amount, "max_uses": max_uses}
    if expires_at is not None:
        body["expires_at"] = expires_at
    return api.request("POST", "/api/admin/promos", json=body)


def _balance(api, who="discord_1"):
    async def get():
        doc = await api.db.users.find_one({"session_id": who}, {"balance": 1})
        return float((doc or {}).get("balance") or 0)
    return asyncio.run(get())


def test_rap_disabled_flag_blocks_create_and_apply(promo_api, monkeypatch):
    api = promo_api
    monkeypatch.setenv("RAP_FIXED_ENABLED", "0")
    created = api.request("POST", "/api/admin/promos", json={
        "code": "GIFTX", "type": "rap_fixed", "amount_rap": 10, "max_uses": 5})
    assert created.status_code == 400, created.text
    assert "отключены" in created.json()["detail"]
    # Prepare a gift while enabled, then disable and try to apply.
    monkeypatch.setenv("RAP_FIXED_ENABLED", "1")
    assert _create_rap(api, "GIFTX", 10, 5).status_code == 201
    monkeypatch.setenv("RAP_FIXED_ENABLED", "0")
    response = api.apply("giftx")
    assert response.status_code == 400, response.text
    assert "отключены" in response.json()["detail"]
    assert _balance(api) == 0
    assert api.promos()["GIFTX"]["unique_users"] == 0


def test_rap_happy_path_keeps_percent_and_reports_gift(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    api.apply("pelmen")
    before = api.request("GET", "/api/auth/me", who="discord_1").json()
    assert before["promo_code"] == "PELMEN" and before["promo_bonus"] == 0.1
    assert _create_rap(api, "GIFT100", 100.5, 10).status_code == 201
    first = api.apply("gift100")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["gift_type"] == "rap_fixed"
    assert body["gift_amount"] == 100.5
    assert body["gift_already_received"] is False
    assert body["balance"] == 100.5
    # Active percent bonus is untouched.
    assert body["promo_code"] == "PELMEN" and body["promo_bonus"] == 0.1
    second = api.apply("GIFT100")
    assert second.status_code == 200, second.text
    assert second.json()["gift_already_received"] is True
    assert second.json()["balance"] == 100.5
    assert second.json()["promo_code"] == "PELMEN"
    assert api.promos()["GIFT100"]["unique_users"] == 1
    # Second account gets its own issuance.
    assert api.apply("gift100", "discord_2").json()["gift_already_received"] is False
    assert _balance(api, "discord_2") == 100.5
    assert api.promos()["GIFT100"]["unique_users"] == 2
    # Separate gift journal, no fictitious deposit / bank / referral writes.
    async def check():
        assert await api.db.deposits.count_documents({}) == 0
        assert await api.db.promo_gifts.count_documents({}) == 2
        assert await api.db.promo_activations.count_documents({}) >= 1
        gifts = await api.db.promo_gifts.find({}).to_list(None)
        assert sorted(g["amount_rap"] for g in gifts) == [100.5, 100.5]
        assert await api.db.referral_rewards.count_documents({}) == 0
    asyncio.run(check())


def test_rap_parallel_same_account_credits_once(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    assert _create_rap(api, "PARA", 25, 10).status_code == 201

    async def burst():
        return await asyncio.gather(*[
            api.send("POST", "/api/promo/apply", who="discord_1", json={"code": "PARA"})
            for _ in range(12)
        ])
    responses = asyncio.run(burst())
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    flags = [r.json()["gift_already_received"] for r in responses]
    assert flags.count(False) == 1 and flags.count(True) == 11
    assert _balance(api) == 25
    assert api.promos()["PARA"]["unique_users"] == 1


def test_rap_last_slot_race_two_accounts_only_one_wins(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    assert _create_rap(api, "LAST1", 40, 1).status_code == 201

    async def race():
        return await asyncio.gather(*[
            api.send("POST", "/api/promo/apply", who=who, json={"code": "LAST1"})
            for who in ("discord_1", "discord_2")
        ])
    first, second = asyncio.run(race())
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409], (first.text, second.text)
    winner = first if first.status_code == 200 else second
    loser = second if winner is first else first
    assert "исчерпан" in loser.json()["detail"]
    assert winner.json()["gift_amount"] == 40
    total = _balance(api, "discord_1") + _balance(api, "discord_2")
    assert total == 40
    assert api.promos()["LAST1"]["unique_users"] == 1


def test_rap_requires_discord_account(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    assert _create_rap(api, "NEEDDISC", 10, 5).status_code == 201
    asyncio.run(api.db.users.insert_one({
        "session_id": "guest-1", "nickname": "Guest", "balance": 0, "skins": []}))
    response = api.apply("needdisc", "guest-1")
    assert response.status_code == 400, response.text
    assert "Discord" in response.json()["detail"]
    assert api.promos()["NEEDDISC"]["unique_users"] == 0


@pytest.mark.parametrize("body", [
    {"code": "R1", "type": "rap_fixed", "amount_rap": 0, "max_uses": 5},
    {"code": "R1", "type": "rap_fixed", "amount_rap": -5, "max_uses": 5},
    {"code": "R1", "type": "rap_fixed", "amount_rap": 10.001, "max_uses": 5},
    {"code": "R1", "type": "rap_fixed", "amount_rap": "NaN", "max_uses": 5},
    {"code": "R1", "type": "rap_fixed", "amount_rap": "Infinity", "max_uses": 5},
    {"code": "R1", "type": "rap_fixed", "amount_rap": 100001, "max_uses": 5},
    {"code": "R1", "type": "rap_fixed", "amount_rap": 10},
    {"code": "R1", "type": "rap_fixed", "max_uses": 5},
    {"code": "R1", "type": "rap_fixed", "amount_rap": 10, "max_uses": 0},
    {"code": "R1", "type": "rap_fixed", "amount_rap": 10, "max_uses": -3},
    {"code": "R1", "type": "rap_fixed", "amount_rap": 10, "max_uses": 2.5},
    {"code": "R1", "type": "rap_fixed", "amount_rap": 10, "max_uses": 5, "percent": 5},
    {"code": "R1", "type": "deposit_percent", "percent": 10, "amount_rap": 5},
    {"code": "R1", "type": "deposit_percent", "percent": 10, "max_uses": 5},
    {"code": "R1", "type": "deposit_percent", "percent": 10, "expires_at": "2030-01-01T00:00:00Z"},
])
def test_rap_invalid_payloads_rejected(promo_api, monkeypatch, body):
    _enable_rap(monkeypatch)
    api = promo_api
    response = api.request("POST", "/api/admin/promos", json=body)
    assert response.status_code == 422, (body, response.text)


def test_rap_forbids_type_change_and_amount_freeze(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    pid = _create_rap(api, "FREEZE", 50, 5).json()["id"]
    assert api.apply("freeze").status_code == 200
    assert api.request("PUT", f"/api/admin/promos/{pid}", json={
        "code": "FREEZE", "type": "deposit_percent", "percent": 10}).status_code == 400
    assert api.request("PUT", f"/api/admin/promos/{pid}", json={
        "code": "FREEZE", "type": "rap_fixed", "amount_rap": 60, "max_uses": 5}).status_code == 400
    assert api.request("PUT", f"/api/admin/promos/{pid}", json={
        "code": "FREEZE", "type": "rap_fixed", "amount_rap": 50, "max_uses": 0}).status_code in (400, 422)
    # Growing the limit and renaming are allowed; stats survive the rename.
    assert api.request("PUT", f"/api/admin/promos/{pid}", json={
        "code": "FROZEN2", "type": "rap_fixed", "amount_rap": 50, "max_uses": 8}).status_code == 200
    assert api.promos()["FROZEN2"]["unique_users"] == 1
    assert api.apply("freeze").status_code == 400


def test_rap_same_discord_different_session_no_double(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    assert _create_rap(api, "SESS", 30, 10).status_code == 201
    assert api.apply("sess").json()["gift_already_received"] is False
    asyncio.run(api.db.users.insert_one(
        {"session_id": "another-session", "discord_id": "1", "nickname": "Alt", "balance": 0, "skins": []}))
    second = api.apply("sess", "another-session")
    assert second.status_code == 200, second.text
    assert second.json()["gift_already_received"] is True
    assert _balance(api, "another-session") == 0
    assert _balance(api, "discord_1") == 30
    assert api.promos()["SESS"]["unique_users"] == 1


def test_rap_deletion_keeps_issued_but_blocks_new(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    pid = _create_rap(api, "TODEL", 15, 5).json()["id"]
    assert api.apply("todel").status_code == 200
    assert api.request("DELETE", f"/api/admin/promos/{pid}").status_code == 200
    # Issued balance is NOT revoked.
    assert _balance(api) == 15
    assert api.apply("todel").status_code == 400
    assert _balance(api) == 15


def test_rap_expiry_blocks_new_activations(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert _create_rap(api, "OLD", 10, 5, expires_at=past).status_code == 201
    assert api.apply("old").status_code == 400
    assert _balance(api) == 0
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    pid = _create_rap(api, "SOON", 10, 5, expires_at=future).json()["id"]
    assert api.apply("soon").status_code == 200
    # Expire it after the booking: repeats are already redeemed (idempotent),
    # new accounts are blocked.
    api.request("PUT", f"/api/admin/promos/{pid}", json={
        "code": "SOON", "type": "rap_fixed", "amount_rap": 10, "max_uses": 5,
        "expires_at": past})
    assert api.apply("soon", "discord_2").status_code == 400
    assert _balance(api, "discord_2") == 0


def test_rap_reserved_completes_after_delete_or_expire_via_resume(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    pid = _create_rap(api, "CRASH", 77, 5).json()["id"]

    async def book_without_credit():
        promo = await api.db.promo_codes.find_one({"id": pid})
        await api.server.promos.reserve_rap_slot(api.db, pid, "discord:1")
        await api.db.promo_gift_ops.update_one(
            {"promo_id": pid, "account_key": "discord:1"},
            {"$setOnInsert": {
                "promo_id": pid, "account_key": "discord:1", "session_id": "discord_1",
                "discord_id": "1", "amount_rap": 77.0, "promo_code": "CRASH",
                "created_at": api.server.now_utc()}},
            upsert=True)
        await api.db.promo_gift_ops.update_one(
            {"promo_id": pid, "account_key": "discord:1"},
            {"$set": {"status": "reserved", "reserved_at": api.server.now_utc(),
                      "updated_at": api.server.now_utc()}})
    asyncio.run(book_without_credit())
    assert _balance(api) == 0
    # Delete while reserved: startup recovery must still settle per saved terms.
    assert api.request("DELETE", f"/api/admin/promos/{pid}").status_code == 200
    resumed = asyncio.run(api.server.promos.resume_incomplete_gifts(api.db))
    assert resumed == 1
    assert _balance(api) == 77
    gifts = asyncio.run(api.db.promo_gifts.find({}).to_list(None))
    assert len(gifts) == 1 and gifts[0]["amount_rap"] == 77


def test_rap_recreation_warns_and_starts_new_counter(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    pid = _create_rap(api, "REUSE", 20, 5).json()["id"]
    assert api.apply("reuse").status_code == 200
    assert api.request("DELETE", f"/api/admin/promos/{pid}").status_code == 200
    recreated = _create_rap(api, "reuse", 20, 5)
    assert recreated.status_code == 201, recreated.text
    assert "warning" in recreated.json()
    assert "новая акция" in recreated.json()["warning"]
    assert recreated.json()["id"] != pid
    assert recreated.json()["unique_users"] == 0
    # Same Discord account may take the NEW promo (new promo_id => new issuance).
    assert api.apply("reuse").json()["gift_already_received"] is False
    assert _balance(api) == 40


def test_rap_rate_limit_blocks_flood(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    assert _create_rap(api, "FLOOD", 1, 1000).status_code == 201
    statuses = [api.apply("flood").status_code for _ in range(31)]
    assert statuses[-1] == 429
    assert "минуту" in api.apply("flood").json()["detail"]


def test_rap_gift_journal_lists_redemptions(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    assert _create_rap(api, "JOUR", 12, 5).status_code == 201
    assert api.apply("jour").status_code == 200
    response = api.request("GET", "/api/admin/promo-gifts", who="admin")
    assert response.status_code == 200, response.text
    assert any(g["promo_code"] == "JOUR" and g["amount_rap"] == 12 for g in response.json())
    assert api.request("GET", "/api/admin/promo-gifts", who="discord_1").status_code == 403


def test_rap_gifts_hit_net_but_not_bank_or_pool(promo_api, monkeypatch):
    _enable_rap(monkeypatch)
    api = promo_api
    assert _create_rap(api, "BANKTIE", 40, 5).status_code == 201
    assert api.apply("banktie").status_code == 200
    assert api.apply("banktie", "discord_2").status_code == 200
    bank = api.request("GET", "/api/admin/bank").json()
    assert bank["gifts_total"] == 80
    assert bank["gifts_count"] == 2
    # Liabilities grew by gifts, bank/pool untouched -> net cut by gifts.
    assert bank["bank"] == 0
    assert bank["liabilities"]["balances"] == 80
    assert bank["net"] == -80


def test_rap_real_mongo_races_if_available(promo_api, monkeypatch):
    """Same-account + last-slot races on a REAL MongoDB (not just mongomock).

    Skipped when no MongoDB is reachable; mongomock-only races are covered above.
    """
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except Exception:
        pytest.skip("motor not available")
    url = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")

    loop = asyncio.new_event_loop()  # motor clients are bound to one event loop
    run = loop.run_until_complete
    async def probe():
        client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=800)
        try:
            await client.admin.command("ping")
            return client
        except Exception:
            try:
                client.close()
            except Exception:
                pass
            return None
    client = run(probe())
    if client is None:
        pytest.skip("no real MongoDB reachable")
    try:
        _enable_rap(monkeypatch)
        api = promo_api
        server = api.server
        real_db = client["rap_race_test"]
        async def setup():
            for name in ("promo_codes", "promo_gift_ops", "promo_gifts", "users", "migrations"):
                try:
                    await real_db.drop_collection(name)
                except Exception:
                    pass
            await server.ensure_promotions(real_db)
            await real_db.users.insert_many([{
                "session_id": f"discord_{i}", "discord_id": str(i),
                "nickname": f"P{i}", "balance": 0, "skins": []} for i in (1, 2)])
        run(setup())
        promo_id = "race-real-1"

        async def seed():
            await real_db.promo_codes.insert_one({
                "id": promo_id, "code": "REALRACE", "type": "rap_fixed",
                "amount_rap": 10.0, "max_uses": 5, "expires_at": None,
                "reserved_count": 0, "reserved_keys": [],
                "gold_nick": False, "deleted": False,
                "created_at": datetime.now(timezone.utc)})
        run(seed())

        async def one_apply():
            promo = await real_db.promo_codes.find_one({"id": promo_id})
            user = await real_db.users.find_one({"session_id": "discord_1"})
            return await server.promos.apply_rap_gift(real_db, promo, user)

        async def burst_same():
            return await asyncio.gather(*[one_apply() for _ in range(10)])
        results = run(burst_same())
        assert sum(1 for r in results if not r["already"]) == 1
        user = run(real_db.users.find_one({"session_id": "discord_1"}))
        assert float(user["balance"]) == 10.0

        # Last slot with two different accounts.
        async def wipe():
            await real_db.promo_codes.update_one(
                {"id": promo_id}, {"$set": {"max_uses": 1, "reserved_count": 0, "reserved_keys": []}})
            await real_db.promo_gift_ops.delete_many({})
            await real_db.promo_gifts.delete_many({})
            await real_db.users.update_many({}, {"$set": {"balance": 0}, "$unset": {"claimed_promo_gifts": ""}})
        run(wipe())

        async def apply_as(sid):
            promo = await real_db.promo_codes.find_one({"id": promo_id})
            user = await real_db.users.find_one({"session_id": sid})
            return await server.promos.apply_rap_gift(real_db, promo, user)

        async def race_last():
            return await asyncio.gather(apply_as("discord_1"), apply_as("discord_2"), return_exceptions=True)
        outcomes = run(race_last())
        ok = [o for o in outcomes if not isinstance(o, Exception)]
        errors = [o for o in outcomes if isinstance(o, Exception)]
        assert len(ok) == 1 and len(errors) == 1
        balances = run(real_db.users.find({}).to_list(None))
        assert sum(float(u.get("balance") or 0) for u in balances) == 10.0
    finally:
        try:
            client.close()
        except Exception:
            pass

