"""Support chat: language-aware auto replies, screenshots with limits/expiry, DonationAlerts + Telegram approvals."""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import da_phrases
import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
ADMIN = 5095885655


@pytest.fixture
def api(isolated_server, monkeypatch):
    s = isolated_server
    s.db = AsyncMongoMockClient().support
    s.chat.now = s.now_utc
    monkeypatch.setenv("DONATIONALERTS_URL", "https://www.donationalerts.com/r/bloxgrade")
    bot = s.dp.TelegramBot("123:abc", str(ADMIN), "secret")
    bot.sent = []

    async def call(method, payload=None, files=None):
        bot.sent.append((method, payload))
        return {"message_id": len(bot.sent)} if method in ("sendMessage", "sendPhoto") else True
    bot.call = call
    s.tg_bot = bot
    s.bot = bot

    async def setup():
        await s.db.users.create_index("session_id", unique=True)
        await s.db.user_locks.create_index("session_id", unique=True)
        await s.chat.ensure_indexes(s.db)
        await s.chat_attachments.ensure_indexes(s.db)
        for sid in ("discord_1", "discord_2"):
            await s.db.users.insert_one({"session_id": sid, "discord_id": sid[-1], "nickname": f"P{sid[-1]}", "balance": 0, "skins": [],
                                         "roblox_display_name": "Player", "roblox_nick": f"player_{sid[-1]}", "roblox_link": "https://www.roblox.com/users/1/profile"})
    asyncio.run(setup())

    async def request(method, path, token=None, lang=None, **kw):
        headers = kw.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if lang:
            headers["X-Lang"] = lang
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app), base_url="http://test") as c:
            return await c.request(method, path, headers=headers, **kw)
    s.call = lambda *a, **kw: asyncio.run(request(*a, **kw))
    s.run = asyncio.run
    s.t1, s.t2 = s.make_token("discord_1"), s.make_token("discord_2")
    return s


def test_auto_replies_follow_site_language(api):
    chat = api.call("POST", "/api/chats", api.t1, lang="en", json={"kind": "support"}).json()
    rows = api.call("GET", f"/api/chats/{chat['id']}/messages", api.t1).json()["messages"]
    assert chat["lang"] == "en" and rows[0]["text"].startswith("Hello! This is the support chat")
    guest = api.call("POST", "/api/chats", None, lang="ru", json={"kind": "support"}, headers={"X-Session-Id": "6f1c2b9e-1111-4a2b-9c3d-123456789abc"}).json()
    rows = api.call("GET", f"/api/chats/{guest['id']}/messages", None, headers={"X-Session-Id": "6f1c2b9e-1111-4a2b-9c3d-123456789abc"}).json()["messages"]
    assert rows[0]["text"].startswith("Здравствуйте")


def test_screenshots_are_limited_private_and_expire(api):
    chat = api.call("POST", "/api/chats", api.t1, json={"kind": "support"}).json()
    url = f"/api/chats/{chat['id']}/attachments"
    guest = api.call("POST", url, None, files={"file": ("a.png", PNG, "image/png")}, headers={"X-Session-Id": "g"})
    assert guest.status_code == 401
    assert api.call("POST", url, api.t1, files={"file": ("a.txt", b"hello", "image/png")}).status_code == 400
    assert api.call("POST", url, api.t1, files={"file": ("big.png", PNG + b"0" * (1024 * 1024), "image/png")}).status_code == 413
    ok = api.call("POST", url, api.t1, files={"file": ("a.png", PNG, "image/png")})
    assert ok.status_code == 201 and ok.json()["kind"] == "image"
    att = ok.json()["attachment_id"]
    got = api.call("GET", f"{url}/{att}", api.t1)
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    assert api.call("GET", f"/api/chats/{chat['id']}/attachments/{att}", api.t2).status_code == 404
    assert api.call("POST", url, api.t1, files={"file": ("a.png", PNG, "image/png")}).status_code == 429  # cooldown

    async def age():
        await api.db.chat_attachments.update_many({}, {"$set": {"created_at": api.now_utc() - timedelta(hours=1)}})
        for i in range(4):
            await api.db.chat_attachments.insert_one({"_id": f"x{i}", "chat_id": chat["id"], "owner": "discord_1", "size": 1,
                                                      "created_at": api.now_utc() - timedelta(hours=2), "expires_at": api.now_utc() + timedelta(days=3)})
    api.run(age())
    assert api.call("POST", url, api.t1, files={"file": ("a.png", PNG, "image/png")}).status_code == 429  # 5 per day
    api.run(api.db.chat_attachments.update_one({"_id": att}, {"$set": {"expires_at": api.now_utc() - timedelta(seconds=1)}}))
    assert api.call("GET", f"{url}/{att}", api.t1).status_code == 404
    info = api.run(api.db.chat_attachments.index_information())
    assert any(v.get("expireAfterSeconds") == 0 for v in info.values())


def _update(api, uid, data, from_id=ADMIN):
    return {"update_id": uid, "callback_query": {"id": f"q{uid}", "from": {"id": from_id}, "data": data,
                                                  "message": {"message_id": 1, "chat": {"id": ADMIN}}}}


def test_donationalerts_flow_only_owner_can_approve(api):
    res = api.call("POST", "/api/donationalerts/requests", api.t1, lang="en", json={"currency": "RUB", "amount": 250})
    assert res.status_code == 201, res.text
    dep_id, chat_id = res.json()["deposit_id"], res.json()["chat_id"]
    rows = api.call("GET", f"/api/chats/{chat_id}/messages", api.t1).json()["messages"]
    steps = next(m for m in rows if m.get("kind") == "da_instructions")
    assert "donationalerts.com/r/bloxgrade" in steps["text"] and res.json()["phrase"] in steps["text"] and "player_1" in steps["text"]
    assert steps["phrase"] == res.json()["phrase"] and res.json()["phrase"] in da_phrases.PHRASES
    assert api.call("POST", "/api/donationalerts/requests", api.t1, json={"currency": "USD", "amount": 5}).status_code == 409

    assert api.call("POST", f"/api/donationalerts/requests/{dep_id}/paid", api.t2).status_code == 404
    assert api.call("POST", f"/api/donationalerts/requests/{dep_id}/paid", api.t1).status_code == 200
    assert api.call("POST", f"/api/donationalerts/requests/{dep_id}/paid", api.t1).status_code == 409  # once only
    sent = [p for m, p in api.bot.sent if m == "sendMessage"]
    assert len(sent) == 1 and sent[0]["chat_id"] == ADMIN and "250" in sent[0]["text"]

    confirm = AsyncMock(return_value={"credited": 500.0, "already_confirmed": False})
    api.dp.confirm_deposit = confirm
    handle = lambda upd: api.run(api.dp.handle_update(api.db, api.bot, upd, api.notify_deposit_rejected))  # noqa: E731
    handle(_update(api, 1, f"da:ok:{dep_id}:25000", from_id=111))  # stranger
    confirm.assert_not_called()
    handle(_update(api, 2, f"da:ask:{dep_id}:25000"))
    confirm.assert_not_called()  # first tap only asks
    handle(_update(api, 3, f"da:ok:{dep_id}:25000"))
    handle(_update(api, 3, f"da:ok:{dep_id}:25000"))  # redelivered update is ignored
    confirm.assert_called_once()
    assert confirm.call_args.args[1:3] == (dep_id, 500.0)


def test_webhook_requires_secret_and_reject_flow(api):
    assert api.call("POST", "/api/telegram/webhook", json={"update_id": 1}).status_code == 403
    ok = api.call("POST", "/api/telegram/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": api.bot.secret})
    assert ok.status_code == 200
    dep_id = api.call("POST", "/api/donationalerts/requests", api.t1, json={"currency": "USD", "amount": 5}).json()["deposit_id"]
    api.call("POST", f"/api/donationalerts/requests/{dep_id}/paid", api.t1)
    handle = lambda upd: api.run(api.dp.handle_update(api.db, api.bot, upd, api.notify_deposit_rejected))  # noqa: E731
    handle(_update(api, 10, f"da:rej:{dep_id}"))
    assert api.run(api.db.deposits.find_one({"id": dep_id}))["status"] == "pending"
    handle(_update(api, 11, f"da:rejok:{dep_id}"))
    dep = api.run(api.db.deposits.find_one({"id": dep_id}))
    assert dep["status"] == "rejected" and dep["rejection_reason"] == "payment_not_found"


def test_check_message_buttons_never_touch_money(api):
    api.run(api.dp.send_test(api.bot))
    assert api.bot.sent[-1][0] == "sendMessage" and "ПРОВЕРОЧНОЕ" in api.bot.sent[-1][1]["text"]
    confirm = AsyncMock()
    api.dp.confirm_deposit = confirm
    for i, action in enumerate(("ask", "ok", "rej", "no", "amt", "back")):
        api.run(api.dp.handle_update(api.db, api.bot, _update(api, 500 + i, f"da:test:{action}"), api.notify_deposit_rejected))
    confirm.assert_not_called()
    assert api.run(api.db.deposits.count_documents({})) == 0
    api.run(api.dp.handle_update(api.db, api.bot, _update(api, 600, "da:test:ok", from_id=1), api.notify_deposit_rejected))
    assert api.bot.sent[-1][1].get("text") == "Нет доступа"


def test_phrases_do_not_repeat_within_last_five(api):
    async def issue(n):
        got = []
        for i in range(n):
            phrase = await da_phrases.pick_phrase(api.db, __import__("random").choice)
            await api.db.deposits.insert_one({"id": f"d{i}", "payment_method": "donationalerts", "status": "rejected",
                                              "da_phrase": phrase, "created_at": api.now_utc() + __import__("datetime").timedelta(seconds=i)})
            got.append(phrase)
        return got
    got = api.run(issue(200))
    assert all(got[i] not in got[max(0, i - 5):i] for i in range(len(got)))
    assert len(set(got)) > 30
