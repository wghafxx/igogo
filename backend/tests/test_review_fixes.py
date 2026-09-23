"""Regressions for the code-review fixes (static paths, logout revocation, withdraw intent, chat races, idempotent chat deposit)."""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def api(isolated_server):
    s = isolated_server
    s.db = AsyncMongoMockClient().review
    s.chat.now = s.now_utc

    async def setup():
        await s.db.users.create_index("session_id", unique=True)
        await s.db.user_locks.create_index("session_id", unique=True)
        await s.db.withdrawals.create_index("id", unique=True)
        await s.db.item_history.create_index("id", unique=True)
        await s.db.deposits.create_index("admin_request_id", unique=True, partialFilterExpression={"admin_request_id": {"$type": "string"}})
        await s.chat.ensure_indexes(s.db)
        await s.db.users.insert_one({"session_id": "discord_1", "discord_id": "1", "nickname": "P1", "balance": 0,
                                     "roblox_display_name": "Player", "roblox_nick": "player_1", "roblox_link": "https://www.roblox.com/users/1/profile",
                                     "skins": [{"uid": "u1", "name": "Skin", "price": 50}, {"uid": "u2", "name": "Skin 2", "price": 60}]})
    asyncio.run(setup())

    async def call(method, path, token=None, **kw):
        headers = kw.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app), base_url="http://test") as c:
            return await c.request(method, path, headers=headers, **kw)
    s.call = lambda *a, **kw: asyncio.run(call(*a, **kw))
    s.run = asyncio.run
    return s


def test_static_files_cannot_escape_root(api, tmp_path):
    root = tmp_path / "static"
    root.mkdir()
    (root / "ok.txt").write_text("ok")
    (tmp_path / "secret.txt").write_text("secret")
    (root / "link.txt").symlink_to(tmp_path / "secret.txt")
    root = root.resolve()
    assert api.safe_static_file(root, "ok.txt") == root / "ok.txt"
    for bad in ("../secret.txt", "a/../../secret.txt", "link.txt", "", "missing.txt"):
        assert api.safe_static_file(root, bad) is None


def test_logout_revokes_copied_tokens(api):
    token = api.make_token("discord_1", extra={"sv": 0})
    copy = api.make_token("discord_1")  # legacy token without sv claim
    assert api.call("GET", "/api/auth/me", token).status_code == 200
    assert api.call("GET", "/api/auth/me", copy).status_code == 200
    assert api.call("POST", "/api/auth/logout", token).status_code == 200
    assert api.call("GET", "/api/auth/me", token).status_code == 401
    assert api.call("GET", "/api/auth/me", copy).status_code == 401
    # A revoked token cannot log the account out again.
    fresh = api.make_token("discord_1", extra={"sv": 1})
    assert api.call("POST", "/api/auth/logout", token).status_code == 200
    assert api.call("GET", "/api/auth/me", fresh).status_code == 200


def test_withdraw_writes_intent_and_recovers_after_crash(api):
    token = api.make_token("discord_1")
    r = api.call("POST", "/api/skins/withdraw", token, json={"uids": ["u1"]})
    assert r.status_code == 200, r.text
    rows = api.run(api.db.withdrawals.find({}, {"_id": 0}).to_list(None))
    assert [w["status"] for w in rows] == ["pending"]
    assert rows[0]["recipient"]["roblox_nick"] == "player_1"
    user = api.run(api.db.users.find_one({"session_id": "discord_1"}))
    assert [sk["uid"] for sk in user["skins"]] == ["u2"] and not user.get("withdrawal_ops")

    # Crash after the skin left the inventory: the marker proves it, recovery creates the request.
    old = api.now_utc() - timedelta(minutes=10)
    async def crashed():
        await api.db.withdrawals.insert_one({"id": "w-crash", "session_id": "discord_1", "item": {"uid": "u2", "price": 60}, "status": "reserving", "op_id": "op-a", "created_at": old})
        await api.db.users.update_one({"session_id": "discord_1"}, {"$pull": {"skins": {"uid": "u2"}}, "$addToSet": {"withdrawal_ops": "op-a"}})
        # Crash before the removal: intent is dropped, skin stays with the player.
        await api.db.withdrawals.insert_one({"id": "w-lost", "session_id": "discord_1", "item": {"uid": "zz", "price": 60}, "status": "reserving", "op_id": "op-b", "created_at": old})
        await api.resume_withdrawal_ops()
    api.run(crashed())
    assert api.run(api.db.withdrawals.find_one({"id": "w-crash"}))["status"] == "pending"
    assert api.run(api.db.withdrawals.find_one({"id": "w-lost"})) is None
    assert api.run(api.db.item_history.find_one({"id": "withdrawal:w-crash"}))["kind"] == "withdraw_requested"


def test_failed_removal_leaves_no_request(api):
    api.take_skins = AsyncMock(side_effect=api.HTTPException(status_code=400, detail="Скины уже использованы"))
    r = api.call("POST", "/api/skins/withdraw", api.make_token("discord_1"), json={"uids": ["u1"]})
    assert r.status_code == 400
    assert api.run(api.db.withdrawals.count_documents({})) == 0


def test_parallel_chat_creation_yields_one_chat(api):
    async def race():
        profile = {"nickname": "P1", "registered": True}
        await asyncio.gather(*(api.chat.create_chat(api.db, "discord_1", profile, "support") for _ in range(5)))
    api.run(race())
    assert api.run(api.db.chats.count_documents({"owner": "discord_1"})) == 1


def test_admin_summary_and_list_paging_are_complete(api):
    async def seed():
        now = api.now_utc()
        await api.db.chats.insert_many([{"id": f"c{i}", "owner": f"guest:x{i}", "status": "open" if i % 2 else "active", "admin_unread": 1,
                                         "nickname": f"G{i}", "updated_at": now - timedelta(seconds=i), "last_message": None} for i in range(650)])
    api.run(seed())
    summary = api.run(api.chat.admin_summary(api.db))
    assert summary == {"open": 325, "active": 325, "unread": 650}
    first = api.run(api.chat.admin_list(api.db, "all", None, 0, 200))
    second = api.run(api.chat.admin_list(api.db, "all", None, 600, 200))
    assert first["has_more"] and first["total"] == 650 and len(first["items"]) == 200
    assert not second["has_more"] and len(second["items"]) == 50


def test_reopen_archives_instead_of_deleting(api):
    async def flow():
        chat = await api.chat.create_chat(api.db, "discord_1", {"nickname": "P1", "registered": True}, "support", "hello")
        await api.chat.clear_messages(api.db, chat["id"])
        return chat
    chat = api.run(flow())
    assert api.run(api.db.chat_messages.count_documents({"chat_id": chat["id"]})) == 0
    assert api.run(api.db.chat_messages_archive.count_documents({"chat_id": chat["id"]})) == 2


def test_repeated_chat_deposit_command_credits_once(api):
    api.require_admin = AsyncMock(return_value={"jti": "admin"})
    calls = []

    async def confirm(db, deposit_id, rap, note):
        dep = await db.deposits.find_one({"id": deposit_id})
        already = dep["status"] == "confirmed"
        if not already:
            calls.append(deposit_id)
            await db.deposits.update_one({"id": deposit_id}, {"$set": {"status": "confirmed", "credited": rap * 0.8}})
        return {"credited": rap * 0.8, "already_confirmed": already}
    api.confirm_deposit = confirm
    chat = api.run(api.chat.create_chat(api.db, "discord_1", {"nickname": "P1", "registered": True}, "support"))
    body = {"rap": 500, "request_id": "cmd-12345678"}
    first = api.call("POST", f"/api/admin/chats/{chat['id']}/deposit", json=body)
    retry = api.call("POST", f"/api/admin/chats/{chat['id']}/deposit", json=body)
    assert first.status_code == retry.status_code == 200, (first.text, retry.text)
    assert first.json()["deposit_id"] == retry.json()["deposit_id"]
    assert retry.json()["already_confirmed"] is True
    assert len(calls) == 1 and api.run(api.db.deposits.count_documents({})) == 1
    # A new command (new id) is a new deposit.
    assert api.call("POST", f"/api/admin/chats/{chat['id']}/deposit", json={"rap": 500, "request_id": "cmd-87654321"}).status_code == 200
    assert len(calls) == 2


def test_cryptobot_invoice_with_unsaved_id_is_recovered(api):
    cb = api.cb
    doc = {"id": "cryptobot:req-1", "payment_method": "cryptobot", "session_id": "discord_1", "status": "creating",
           "amount_rub": 100.0, "currency": "USDT", "expected_rap": 200.0, "quoted_rap": 200.0, "promo_bonus": 0.0,
           "created_at": api.now_utc(), "next_check_at": api.now_utc()}
    invoice = {"invoice_id": 77, "payload": doc["id"], "amount": "100.00", "fiat": "RUB", "status": "active",
               "bot_invoice_url": "https://t.me/CryptoBot?start=x"}

    class Gateway:
        enabled = True
        async def call(self, method, payload=None):
            assert method == "getInvoices"
            return {"items": [invoice]}
    api.run(api.db.deposits.insert_one(dict(doc)))
    result = api.run(cb.synchronize(api.db, Gateway(), doc))
    assert result["provider_invoice_id"] == "77" and result["status"] == "awaiting_payment"
