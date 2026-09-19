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
def api(isolated_server):
    s = isolated_server
    url = os.environ.get("ADMIN_TEST_MONGO_URL")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000) if url else AsyncMongoMockClient()
    if url:
        client.get_io_loop = asyncio.get_running_loop
    s.db = db = client["admin_tools_" + uuid.uuid4().hex]
    real_auth = s.require_admin
    s.require_admin = AsyncMock(return_value={"jti": "operator-1"})

    async def setup():
        await s.admin_commands.ensure_commands(db)
        await s.admin_coins.ensure_indexes(db)
        await db.users.create_index("session_id", unique=True)
        await db.users.insert_many([{"session_id": sid, "nickname": sid, "discord_id": sid, "balance": 12.5, "skins": []} for sid in ("player", "other")])
        await db.chats.insert_one({"id": "chat", "owner": "player", "nickname": "player", "status": "open", "guest": False})
        await db.bank_state.insert_one({"id": "main", "bank": 100, "commission_profit": 20, "pool": 5})
    run(setup())

    async def request(path, method="GET", **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app, raise_app_exceptions=False), base_url="http://test") as c:
            return await c.request(method, "/api" + path, **kwargs)

    try:
        yield SimpleNamespace(s=s, db=db, request=request, real_auth=real_auth)
    finally:
        if url:
            async def cleanup():
                await client.drop_database(db.name)
            run(cleanup())
        client.close()


def coins(amount="2500000.25", **fields):
    return {"request_id": str(uuid.uuid4()), "amount": amount, "note": "DonationAlerts", **fields}


@pytest.mark.parametrize("scenario", ["guest", "question", "deposit"])
def test_new_chat_welcomes_once_including_question_and_deposit(api, scenario):
    async def check():
        chat = api.s.chat
        owner = "guest:new-visitor" if scenario == "guest" else "new-player"
        profile = {"nickname": "New player", "registered": scenario != "guest"}
        deposit = {"id": "new-deposit", "expected_rap": 200} if scenario == "deposit" else None
        text = "Как пополнить?" if scenario == "question" else None
        created = await chat.create_chat(api.db, owner, profile, "deposit" if deposit else "support", text, deposit)
        messages = await chat.messages(api.db, created["id"])
        assert messages[0]["kind"] == "welcome" and messages[0]["sender"] == "admin"
        assert created["status"] == "open"  # The greeting does not accept the chat for an operator.
        for currency in ("BYN", "EUR", "KZT", "RUB", "UAH", "USD", "BRL", "TRY", "PLN", "UZS"):
            assert currency in messages[0]["text"]
        if text:
            assert messages[-1]["text"] == text
        if deposit:
            assert any(m.get("kind") == "deposit_request" for m in messages)
        reused = await chat.create_chat(api.db, owner, profile, "support")
        assert reused["id"] == created["id"]
        await api.db.chats.update_one({"id": created["id"]}, {"$set": {"status": "closed", "toggle_at": chat.now() - timedelta(minutes=4)}})
        reopened = await chat.create_chat(api.db, owner, profile, "support")
        assert reopened["id"] == created["id"] and reopened["status"] == "open"
        assert await api.db.chat_messages.count_documents({"chat_id": created["id"], "kind": "welcome"}) == 1
    run(check())


def test_default_commands_edit_delete_restart_and_reuse_name(api):
    async def check():
        a = api
        rows = (await a.request("/admin/commands")).json()
        assert {r["command"] for r in rows} == {"nick", "donat"}
        nick = next(r for r in rows if r["command"] == "nick")
        r = await a.request(f"/admin/commands/{nick['id']}", "PUT", json={"command": "/HELLO", "text": "Добрый день, {args}"})
        assert r.status_code == 200 and r.json()["command"] == "hello"
        await a.s.admin_commands.ensure_commands(a.db)
        assert (await a.request("/admin/commands")).json()[1]["text"] == "Добрый день, {args}"
        assert (await a.request(f"/admin/commands/{nick['id']}", "DELETE")).status_code == 200
        await a.s.admin_commands.ensure_commands(a.db)
        assert [r["command"] for r in (await a.request("/admin/commands")).json()] == ["donat"]
        assert (await a.request("/admin/commands", "POST", json={"command": "hello", "text": "Новая команда"})).status_code == 201
        assert (await a.request("/admin/commands", "POST", json={"command": "/DONAT", "text": "Дубликат"})).status_code == 409
    run(check())


def test_expands_nick_and_donation_but_preserves_ordinary_text(api):
    async def check():
        for text in ("/NICK Builder_123", "/donat", "Привет {nick}"):
            r = await api.request("/admin/chats/chat/messages", "POST", json={"text": text})
            assert r.status_code == 201, r.text
            message = r.json()["text"]
            if text.startswith("/NICK"):
                assert "Roblox Builder_123" in message and "{nick}" not in message
                assert "BloxStrike" in message and "очереди" in message
            elif text == "/donat":
                assert "https://www.donationalerts.com/r/bloxgrade" in message
            else:
                assert message == text
        stored = await api.db.chat_messages.find({"sender": "admin"}).to_list(None)
        assert len(stored) == 3 and not any(r["text"].startswith("/") for r in stored)
    run(check())


@pytest.mark.parametrize("text", ["/nick", "/missing", "/", "/donat surplus", " "])
def test_invalid_command_does_not_accept_chat_or_send_message(api, text):
    async def check():
        r = await api.request("/admin/chats/chat/messages", "POST", json={"text": text})
        assert r.status_code == (422 if not text.strip() else 400)
        assert (await api.db.chats.find_one({"id": "chat"}))["status"] == "open"
        assert await api.db.chat_messages.count_documents({}) == 0
    run(check())


def test_custom_template_literal_arguments_and_expansion_length(api):
    async def check():
        r = await api.request("/admin/commands", "POST", json={"command": "test", "text": "Аргумент {args}; снова {nick}"})
        assert r.status_code == 201
        result = await api.request("/admin/chats/chat/messages", "POST", json={"text": r"/test {nick} $& \1"})
        assert result.json()["text"] == r"Аргумент {nick} $& \1; снова {nick} $& \1"
        too_long = await api.request("/admin/chats/chat/messages", "POST", json={"text": "/test " + "я" * 1100})
        assert too_long.status_code == 400
    run(check())


@pytest.mark.parametrize("payload", [{"command": "1test", "text": "x"}, {"command": "a b", "text": "x"}, {"command": "test", "text": "   "}])
def test_invalid_template(api, payload):
    assert run(api.request("/admin/commands", "POST", json=payload)).status_code == 422


def test_large_manual_grant_has_no_commission_or_bank_limit_and_is_idempotent(api):
    async def check():
        payload = coins()
        results = await asyncio.gather(*(api.request("/admin/players/player/coins", "POST", json=payload) for _ in range(12)))
        assert all(r.status_code == 200 for r in results), [r.text for r in results]
        user = await api.db.users.find_one({"session_id": "player"})
        assert user["balance"] == 2500012.75
        assert user["admin_coin_receipts"] == [payload["request_id"]]
        assert await api.db.admin_coin_grants.count_documents({}) == 1
        op = await api.db.admin_coin_grants.find_one({})
        assert (op["admin_jti"], op["note"], op["status"]) == ("operator-1", "DonationAlerts", "completed")
        history = (await api.request("/admin/players/player/coins")).json()
        assert len(history) == 1 and history[0]["amount"] == 2500000.25
        bank = await api.db.bank_state.find_one({})
        assert (bank["bank"], bank["commission_profit"], bank["pool"]) == (100, 20, 5)
        assert await api.db.deposits.count_documents({}) == 0
    run(check())


def test_different_concurrent_grants_are_all_credited(api):
    async def check():
        results = await asyncio.gather(*(api.request("/admin/players/player/coins", "POST", json=coins("0.25")) for _ in range(16)))
        assert all(r.status_code == 200 for r in results)
        assert (await api.db.users.find_one({"session_id": "player"}))["balance"] == 16.5
    run(check())


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "1.001", "35184372088833"])
def test_invalid_coin_amount_does_not_change_balance(api, amount):
    async def check():
        assert (await api.request("/admin/players/player/coins", "POST", json=coins(amount))).status_code == 422
        assert (await api.db.users.find_one({"session_id": "player"}))["balance"] == 12.5
        assert await api.db.admin_coin_grants.count_documents({}) == 0
    run(check())


def test_request_id_cannot_be_reused_for_another_amount_or_player(api):
    async def check():
        payload = coins("100")
        assert (await api.request("/admin/players/player/coins", "POST", json=payload)).status_code == 200
        for sid, changed in [("other", payload), ("player", {**payload, "amount": "101"}), ("player", {**payload, "note": "changed"})]:
            assert (await api.request(f"/admin/players/{sid}/coins", "POST", json=changed)).status_code == 409
        assert (await api.db.users.find_one({"session_id": "player"}))["balance"] == 112.5
        assert (await api.db.users.find_one({"session_id": "other"}))["balance"] == 12.5
    run(check())


def test_missing_user_and_technical_balance_overflow(api):
    async def check():
        assert (await api.request("/admin/players/missing/coins", "POST", json=coins())).status_code == 404
        await api.db.users.update_one({"session_id": "player"}, {"$set": {"balance": api.s.admin_coins.MAX_BALANCE}})
        assert (await api.request("/admin/players/player/coins", "POST", json=coins("1"))).status_code == 400
        assert (await api.db.users.find_one({"session_id": "player"}))["balance"] == api.s.admin_coins.MAX_BALANCE
    run(check())


def test_restart_completes_credit_after_write_without_adding_again(api, monkeypatch):
    if os.environ.get("ADMIN_TEST_MONGO_URL"):
        pytest.skip("Fault injection uses mongomock")
    original = Collection.update_one
    def fail_after_credit(self, query, update, *args, **kwargs):
        if self.name == "admin_coin_grants" and update.get("$set", {}).get("status") == "completed":
            raise RuntimeError("Simulated lost connection after balance write")
        return original(self, query, update, *args, **kwargs)
    async def check():
        payload = coins("50")
        monkeypatch.setattr(Collection, "update_one", fail_after_credit)
        assert (await api.request("/admin/players/player/coins", "POST", json=payload)).status_code == 500
        assert (await api.db.users.find_one({"session_id": "player"}))["balance"] == 62.5
        monkeypatch.setattr(Collection, "update_one", original)
        await api.s.admin_coins.resume_pending(api.db)
        assert (await api.request("/admin/players/player/coins", "POST", json=payload)).status_code == 200
        assert (await api.db.users.find_one({"session_id": "player"}))["balance"] == 62.5
        assert (await api.db.admin_coin_grants.find_one({}))["status"] == "completed"
    run(check())


def test_all_admin_tools_require_admin_session(api):
    async def check():
        api.s.require_admin = api.real_auth
        for path, method, payload in [
            ("/admin/commands", "GET", None), ("/admin/commands", "POST", {"command": "hello", "text": "Hello"}),
            ("/admin/commands/default-nick", "PUT", {"command": "nick", "text": "Hello"}),
            ("/admin/commands/default-nick", "DELETE", None), ("/admin/players/player/coins", "POST", coins()),
            ("/admin/players/player/coins", "GET", None), ("/admin/chats/chat/messages", "POST", {"text": "/donat"}),
        ]:
            assert (await api.request(path, method, **({"json": payload} if payload else {}))).status_code == 403
        assert (await api.db.users.find_one({"session_id": "player"}))["balance"] == 12.5
    run(check())
