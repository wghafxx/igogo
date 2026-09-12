"""Promo API, unique-account statistics and migration in an isolated Mongo mock.

Install backend/requirements-test.txt, then run pytest tests/test_promotions.py.
"""

import asyncio
import hashlib
from datetime import timedelta
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
    for code, bonus in ((" pelMen ", .10), ("inkab00m", .09), ("sinzuku", .10), ("xyipachosik", .067)):
        response = api.apply(code)
        assert response.status_code == 200, response.text
        assert response.json()["promo_code"] == code.strip().upper()
        assert response.json()["promo_bonus"] == bonus
    assert api.apply("pelmen").json()["gold_nick"] is True
    assert {code: row["unique_users"] for code, row in api.promos().items()} == {
        "PELMEN": 1, "INKAB00M": 1, "SINZUKU": 1, "XYIPACHOSIK": 1,
    }


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
    api.apply("pelmen")
    body = {"description": "Test skins", "expected_rap": 100, "receiver_id": "ysrent1"}

    def deposit():
        response = api.request("POST", "/api/deposits", who="discord_1", json=body)
        assert response.status_code == 200, response.text
        asyncio.run(api.db.deposits.update_one({"id": response.json()["id"]}, {"$set": {"created_at": api.server.now_utc() - timedelta(minutes=2)}}))
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
