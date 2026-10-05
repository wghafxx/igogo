import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def withdrawal_api(isolated_server):
    server = isolated_server
    server.db = AsyncMongoMockClient().test
    server.require_admin = AsyncMock(return_value={"jti": "admin"})
    server.bank_add = AsyncMock(return_value=1000)
    skin = {"uid": "skin-1", "name": "Test skin", "price": 100, "rarity": "pink"}
    withdrawal = {"id": "withdrawal-1", "session_id": "player-1", "item": skin,
                  "status": "pending", "created_at": server.now_utc()}

    async def setup():
        await server.db.users.create_index("session_id", unique=True)
        await server.db.user_locks.create_index("session_id", unique=True)
        await server.db.withdrawals.create_index("id", unique=True)
        await server.db.item_history.create_index("id", unique=True)
        await server.db.users.insert_one({"session_id": "player-1", "nickname": "Player", "balance": 10,
                                          "roblox_nick": "Player", "roblox_link": "https://www.roblox.com/users/1/profile", "skins": []})
        await server.db.withdrawals.insert_one(dict(withdrawal))
        await server.db.item_history.insert_one({"id": "legacy-history", "session_id": "player-1",
            "kind": "withdraw_requested", "item": skin, "price": 100, "created_at": withdrawal["created_at"]})
    asyncio.run(setup())

    async def user(_request):
        return await server.db.users.find_one({"session_id": "player-1"}, {"_id": 0})
    server.require_user = user

    async def request(path="/api/admin/withdrawals/withdrawal-1/cancel", *, reason="Нет подходящих скинов", method="POST"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await client.request(method, path, **({"json": {"reason": reason}} if method == "POST" else {}))

    return SimpleNamespace(server=server, db=server.db, request=request, skin=skin, withdrawal=withdrawal)


def test_cancellation_returns_skin_and_exposes_reason_only_to_owner(withdrawal_api):
    async def check():
        a = withdrawal_api
        response = await a.request(reason="  Нет подходящих скинов\nПопробуйте позже  ")
        assert response.status_code == 200
        user = await a.db.users.find_one({"session_id": "player-1"})
        assert user["skins"] == [a.skin] and user["balance"] == 10
        for path in ("/api/admin/withdrawals?status=cancelled", "/api/profile"):
            response = await a.request(path, method="GET")
            assert response.status_code == 200
            body = response.json()
            rows = body if isinstance(body, list) else body["withdrawals"]
            assert rows[0]["status"] == "cancelled"
            assert rows[0]["cancellation_reason"] == "Нет подходящих скинов\nПопробуйте позже"
        history = await a.db.item_history.find_one({"id": "legacy-history"})
        assert history["kind"] == "withdraw_cancelled"
        assert history["withdrawal_id"] == "withdrawal-1"
        a.server.bank_add.assert_not_awaited()
        async def other(_request):
            return {"session_id": "other-player", "balance": 0, "skins": []}
        a.server.require_user = other
        response = await a.request("/api/profile", method="GET")
        assert response.json()["withdrawals"] == []
        assert response.json()["item_history"] == []
    asyncio.run(check())


def test_parallel_cancellations_return_once_and_keep_first_reason(withdrawal_api):
    async def check():
        a = withdrawal_api
        responses = await asyncio.gather(*(a.request(reason=f"Причина {i}") for i in range(8)))
        assert all(r.status_code == 200 for r in responses)
        user = await a.db.users.find_one({"session_id": "player-1"})
        assert user["skins"] == [a.skin]
        assert user["returned_withdrawals"] == ["withdrawal-1"]
        assert await a.db.item_history.count_documents({}) == 1
        saved = await a.db.withdrawals.find_one({"id": "withdrawal-1"})
        await a.request(reason="Переписать причину")
        assert (await a.db.withdrawals.find_one({"id": "withdrawal-1"}))["cancellation_reason"] == saved["cancellation_reason"]
    asyncio.run(check())


@pytest.mark.parametrize("first", ["cancel", "done"])
def test_completed_and_cancelled_actions_are_mutually_exclusive(withdrawal_api, first):
    async def check():
        a = withdrawal_api
        other = "done" if first == "cancel" else "cancel"
        first_response, other_response = await asyncio.gather(
            a.request(f"/api/admin/withdrawals/withdrawal-1/{first}"),
            a.request(f"/api/admin/withdrawals/withdrawal-1/{other}"),
        )
        assert sorted([first_response.status_code, other_response.status_code]) == [200, 404]
        w = await a.db.withdrawals.find_one({"id": "withdrawal-1"})
        user = await a.db.users.find_one({"session_id": "player-1"})
        assert len(user["skins"]) == (1 if w["status"] == "cancelled" else 0)
        assert a.server.bank_add.await_count == (1 if w["status"] == "done" else 0)
    asyncio.run(check())


def test_interruption_after_return_recovers_without_reissuing_sold_skin(withdrawal_api, monkeypatch):
    async def check():
        import withdrawal_cancellation as module
        a = withdrawal_api
        original = module.resolve_history
        monkeypatch.setattr(module, "resolve_history", AsyncMock(side_effect=RuntimeError("connection interrupted")))
        with pytest.raises(RuntimeError):
            await a.request()
        assert (await a.db.withdrawals.find_one({"id": "withdrawal-1"}))["status"] == "cancelling"
        assert (await a.request("/api/admin/withdrawals/withdrawal-1/done")).status_code == 404
        # The player can sell the returned skin before the failed request is retried.
        await a.db.users.update_one({"session_id": "player-1"}, {"$set": {"skins": []}, "$inc": {"balance": 100}})
        monkeypatch.setattr(module, "resolve_history", original)
        assert (await a.request()).status_code == 200
        user = await a.db.users.find_one({"session_id": "player-1"})
        assert user["skins"] == [] and user["balance"] == 110
        assert (await a.db.withdrawals.find_one({"id": "withdrawal-1"}))["status"] == "cancelled"
        assert await a.db.item_history.count_documents({}) == 1
    asyncio.run(check())


def test_returned_skin_can_be_withdrawn_again_without_rewriting_old_reason(withdrawal_api):
    async def check():
        a = withdrawal_api
        await a.request(reason="Первая отмена")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=a.server.app), base_url="http://test") as client:
            response = await client.post("/api/skins/withdraw", json={"uids": [a.skin["uid"]]})
        assert response.status_code == 200
        new = await a.db.withdrawals.find_one({"status": "pending"})
        assert new["id"] != "withdrawal-1"
        await a.request(f"/api/admin/withdrawals/{new['id']}/cancel", reason="Вторая отмена")
        user = await a.db.users.find_one({"session_id": "player-1"})
        assert user["skins"] == [a.skin]
        assert (await a.db.item_history.find_one({"id": "legacy-history"}))["cancellation_reason"] == "Первая отмена"
        assert (await a.db.item_history.find_one({"withdrawal_id": new["id"]}))["cancellation_reason"] == "Вторая отмена"
        assert await a.db.item_history.count_documents({}) == 2
    asyncio.run(check())


@pytest.mark.parametrize("reason", ["", " \n ", None, "а" * 1001])
def test_empty_or_long_reason_cannot_cancel(withdrawal_api, reason):
    async def check():
        a = withdrawal_api
        assert (await a.request(reason=reason)).status_code == 422
        assert (await a.db.withdrawals.find_one({"id": "withdrawal-1"}))["status"] == "pending"
        assert not (await a.db.users.find_one({"session_id": "player-1"}))["skins"]
    asyncio.run(check())


def test_cancellation_requires_admin(withdrawal_api):
    a = withdrawal_api
    a.server.require_admin.side_effect = HTTPException(403, "Forbidden")
    assert asyncio.run(a.request()).status_code == 403
    assert asyncio.run(a.db.withdrawals.find_one({"id": "withdrawal-1"}))["status"] == "pending"


def test_missing_player_can_be_recovered_and_unknown_withdrawal_rejected(withdrawal_api):
    async def check():
        a = withdrawal_api
        assert (await a.request("/api/admin/withdrawals/missing/cancel")).status_code == 404
        user = await a.db.users.find_one({"session_id": "player-1"})
        await a.db.users.delete_one({"session_id": "player-1"})
        assert (await a.request()).status_code == 409
        assert (await a.db.withdrawals.find_one({"id": "withdrawal-1"}))["status"] == "cancelling"
        await a.db.users.insert_one(user)
        from withdrawal_cancellation import finish_cancellation
        await finish_cancellation(a.db, await a.db.withdrawals.find_one({"id": "withdrawal-1"}))
        assert (await a.db.users.find_one({"session_id": "player-1"}))["skins"] == [a.skin]
    asyncio.run(check())
