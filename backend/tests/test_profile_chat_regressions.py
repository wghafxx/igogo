"""Isolated regressions for mandatory profiles, request limits and chat retention."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

PROFILE = {"roblox_display_name": "Blox Player", "roblox_nick": "Builder_123", "roblox_link": "https://www.roblox.com/users/123/profile"}
run = asyncio.run


@pytest.fixture
def api(isolated_server):
    server = isolated_server
    client = AsyncMongoMockClient()
    server.db = db = client.regressions
    user = {"session_id": "player", "nickname": "Player", "balance": 0, "skins": [], "discord_id": "123", **PROFILE}

    async def setup():
        await db.users.insert_one(dict(user))
        await db.user_locks.create_index("session_id", unique=True)
        await server.chat.ensure_indexes(db)
    run(setup())
    async def require_user(request):
        return await db.users.find_one({"session_id": "player"}, {"_id": 0})
    async def identity(request):
        return "player", {**await require_user(request), "registered": True}
    server.require_user = require_user
    server.chat_identity = identity
    server.require_admin = AsyncMock(return_value={"jti": "operator"})

    async def request(method, path, **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as c:
            return await c.request(method, "/api" + path, **kwargs)
    yield SimpleNamespace(s=server, db=db, user=user, request=request)
    client.close()


def test_profile_roundtrip_and_username_normalization(api):
    async def check():
        response = await api.request("POST", "/profile/roblox", json={**PROFILE, "roblox_nick": "@Builder_123"})
        assert response.status_code == 200, response.text
        assert all(response.json()[k] == v for k, v in PROFILE.items())
        stored = await api.db.users.find_one({"session_id": "player"})
        assert stored["roblox_nick_normalized"] == "builder_123"
    run(check())


@pytest.mark.parametrize("fields", [
    {"roblox_display_name": "  "}, {"roblox_display_name": "Bad\nName"}, {"roblox_nick": "bad name"},
    {"roblox_link": "https://www.roblox.com.evil.test/users/123/profile"},
    {"roblox_link": "https://www.roblox.com/games/123"},
    {"roblox_link": "https://www.roblox.com/share?code=abc&type=Game"},
    {"roblox_link": "https://user:pass@www.roblox.com/users/123/profile"},
])
def test_profile_rejects_invalid_fields_without_writing(api, fields):
    response = run(api.request("POST", "/profile/roblox", json={**PROFILE, **fields}))
    assert response.status_code in (400, 422)
    assert run(api.db.users.find_one({"session_id": "player"}))["roblox_link"] == PROFILE["roblox_link"]


def test_duplicate_username_is_case_insensitive(api):
    run(api.db.users.insert_one({"session_id": "other", "roblox_nick": "BUILDER_123"}))
    response = run(api.request("POST", "/profile/roblox", json=PROFILE))
    assert response.status_code == 400


@pytest.mark.parametrize("path,body", [
    ("/chats", {"kind": "deposit", "expected_rap": 300}),
    ("/chats", {"kind": "support", "for_topup": True, "text": "СБП"}),
    ("/deposits", {"receiver_id": "support", "description": "Test skins", "expected_rap": 300}),
    ("/payments/xrocket/invoices", {"request_id": "11223344-1122-4122-8122-112233445566", "amount_rub": 100, "currency": "USDT"}),
    ("/payments/cryptobot/invoices", {"request_id": "11223344-1122-4122-8122-112233445566", "amount_rub": 100, "currency": "USDT"}),
])
def test_missing_display_name_blocks_every_topup_entry(api, path, body):
    run(api.db.users.update_one({"session_id": "player"}, {"$unset": {"roblox_display_name": ""}}))
    response = run(api.request("POST", path, json=body))
    assert response.status_code == 400, response.text
    assert "Display Name" in response.json()["detail"]
    assert run(api.db.deposits.count_documents({})) == 0
    assert run(api.db.chats.count_documents({})) == 0


def test_support_remains_available_without_profile(api):
    run(api.db.users.update_one({"session_id": "player"}, {"$unset": {"roblox_display_name": ""}}))
    assert run(api.request("POST", "/chats", json={"kind": "support", "text": "Нужна помощь"})).status_code == 201


def test_single_active_request_allows_retry_after_cancellation(api):
    async def check():
        body = {"kind": "deposit", "expected_rap": 300}
        first, second = await asyncio.gather(api.request("POST", "/chats", json=body), api.request("POST", "/chats", json=body))
        assert sorted([first.status_code, second.status_code]) == [201, 409]
        assert await api.db.deposits.count_documents({}) == 1
        deposit = await api.db.deposits.find_one({})
        assert (await api.request("POST", f"/deposits/{deposit['id']}/cancel")).status_code == 200
        assert (await api.request("POST", "/chats", json=body)).status_code == 201
    run(check())


def test_active_request_is_visible_even_with_many_completed_payments(api):
    async def check():
        old = api.s.now_utc() - timedelta(days=5)
        await api.db.deposits.insert_one({"id": "active", "session_id": "player", "status": "pending", "created_at": old})
        await api.db.deposits.insert_many([{"id": str(i), "session_id": "player", "status": "confirmed", "created_at": api.s.now_utc()} for i in range(70)])
        result = await api.request("GET", "/deposits/my")
        assert result.json()[0]["id"] == "active"
        assert len(result.json()) == 51
    run(check())


def test_newest_messages_load_and_storage_is_bounded(api):
    async def check():
        chat = await api.s.chat.create_chat(api.db, "player", api.user, "support")
        created = api.s.chat.now()
        await api.db.chat_messages.insert_many([{"id": str(i), "chat_id": chat["id"], "sender": "user", "text": str(i), "created_at": created + timedelta(milliseconds=i)} for i in range(350)])
        rows = await api.s.chat.messages(api.db, chat["id"])
        assert len(rows) == 200 and rows[-1]["text"] == "349" and rows[0]["text"] == "150"
        # Seeded times include the future; use a past window for the next send.
        await api.db.chat_messages.update_many({"chat_id": chat["id"]}, {"$set": {"created_at": created - timedelta(seconds=1)}})
        await api.s.chat.post_message(api.db, chat, "admin", "Новое сообщение")
        assert await api.db.chat_messages.count_documents({"chat_id": chat["id"]}) == 200
        for path in (f"/chats/{chat['id']}/messages", f"/admin/chats/{chat['id']}/messages"):
            response = await api.request("GET", path)
            assert response.status_code == 200, response.text
            assert response.json()["messages"][-1]["text"] == "Новое сообщение"
    run(check())


@pytest.mark.parametrize("reopen", ["user", "create", "admin", "admin_message"])
def test_reopening_clears_previous_conversation_but_keeps_payments(api, reopen):
    async def check():
        chat = await api.s.chat.create_chat(api.db, "player", api.user, "support", "Старое сообщение")
        await api.db.deposits.insert_one({"id": "receipt", "chat_id": chat["id"], "status": "confirmed"})
        await api.db.chats.update_one({"id": chat["id"]}, {"$set": {"status": "closed", "toggle_at": api.s.chat.now() - timedelta(minutes=4)}})
        chat = await api.db.chats.find_one({"id": chat["id"]}, {"_id": 0})
        if reopen == "user": await api.s.chat.user_reopen(api.db, chat)
        elif reopen == "admin": await api.s.chat.accept(api.db, chat["id"], "operator")
        elif reopen == "admin_message":
            response = await api.request("POST", f"/admin/chats/{chat['id']}/messages", json={"text": "Новое обращение"})
            assert response.status_code == 201
            assert (await api.db.chats.find_one({"id": chat["id"]}))["status"] == "active"
        else: await api.s.chat.create_chat(api.db, "player", api.user, "support", "Новое обращение")
        rows = await api.s.chat.messages(api.db, chat["id"])
        assert not any(row["text"] == "Старое сообщение" for row in rows)
        assert await api.db.deposits.count_documents({"id": "receipt"}) == 1
    run(check())


@pytest.mark.parametrize("code,text", [("long_wait", "Долгое ожидание"), ("illiquid_skin", "Неликвидный скин"), ("yellow_tag", "Жёлтая табличка на скине"), ("no_reason", "Без причины"), ("Скин не передан", "Скин не передан")])
def test_rejection_notification_is_russian(api, code, text):
    async def check():
        chat = await api.s.chat.create_chat(api.db, "player", api.user, "support")
        await api.db.deposits.insert_one({"id": "deposit", "chat_id": chat["id"], "status": "pending"})
        response = await api.request("POST", "/admin/deposits/deposit/reject", json={"reason": code})
        assert response.status_code == 200
        rows = await api.s.chat.messages(api.db, chat["id"])
        assert rows[-1]["text"] == f"Заявка на пополнение отклонена. Причина: {text}"
    run(check())
