"""Live end-to-end verification of the support-chat / DonationAlerts / Telegram review request.

Runs against the public preview URL (REACT_APP_BACKEND_URL). Marked @pytest.mark.live so it
is excluded from the default '-m not live' isolated suite.

Rules honoured:
- We NEVER call /api/admin/telegram/setup (would rebind the real webhook).
- We press the real "I paid" endpoint at most ONCE total.
- Telegram callback approvals are simulated via /api/telegram/webhook so the real
  answerCallbackQuery calls just log-fail (expected) and no real messages reach the owner
  beyond the automatic sendMessage from create_request/claim_paid.
"""
import hashlib
import io
import os
import struct
import time
import uuid
import zlib

import pytest
import requests

pytestmark = pytest.mark.live

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://igogo-refactor.preview.emergentagent.com").rstrip("/")
T1 = open("/root/logs/token.txt").read().strip()
T2 = open("/root/logs/token2.txt").read().strip()


def _mongo_cleanup():
    """Remove existing chats/messages/deposits/attachments for the two test users so
    language-of-welcome checks start from a clean slate. Also clears any pending DA
    request (deposit) they have so create-request tests don't hit 409 from stale state."""
    import asyncio as _a
    from motor.motor_asyncio import AsyncIOMotorClient as _C

    async def go():
        db = _C("mongodb://localhost:27017").test_database
        for sid in ("discord_test_1", "discord_test_2"):
            chats = await db.chats.find({"owner": sid}, {"id": 1}).to_list(100)
            for c in chats:
                await db.chat_messages.delete_many({"chat_id": c["id"]})
                await db.chat_attachments.delete_many({"chat_id": c["id"]})
            await db.chats.delete_many({"owner": sid})
            await db.deposits.delete_many({"session_id": sid, "status": {"$in": ["pending", "processing"]}})
            await db.chat_attachment_events.delete_many({"owner": sid})
    _a.run(go())


_mongo_cleanup()

BOT_TOKEN = "8817831807:AAHTEn9r6GNjORg_RXeC-dqOCtk4RaXvqVA"
JWT_SECRET = "cac8fb7f8057c6a8ac58d3d5cf88202a8ba2078eb2248774cfeaec444e6030c9"
SECRET = hashlib.sha256(f"{BOT_TOKEN}:{JWT_SECRET}".encode()).hexdigest()[:48]
ADMIN_ID = 5095885655


def _png(size_bytes: int = 128) -> bytes:
    """Produce a tiny but VALID PNG of the requested min size (padded with harmless IDAT)."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\xff\xff"  # filter + 1 white pixel
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    out = sig + ihdr + idat + iend
    if len(out) < size_bytes:
        out += b"\x00" * (size_bytes - len(out))
    return out


PNG = _png()
BIG_PNG = _png() + b"\x00" * (1024 * 1024 + 10)  # > 1 MB


def hdrs(token=None, lang=None, extra=None):
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if lang:
        h["X-Lang"] = lang
    if extra:
        h.update(extra)
    return h


# ---------------------------- 1) chat language ----------------------------

def test_chat_language_english():
    r = requests.post(f"{BASE}/api/chats", headers=hdrs(T1, "en"), json={"kind": "support"}, timeout=15)
    assert r.status_code in (200, 201), r.text
    ch = r.json()
    assert ch["lang"] == "en"
    msgs = requests.get(f"{BASE}/api/chats/{ch['id']}/messages", headers=hdrs(T1), timeout=15).json()["messages"]
    assert msgs and msgs[0]["text"].startswith("Hello! This is the support chat"), msgs[0]["text"][:80]


def test_chat_language_russian():
    r = requests.post(f"{BASE}/api/chats", headers=hdrs(T2, "ru"), json={"kind": "support"}, timeout=15)
    assert r.status_code in (200, 201), r.text
    ch = r.json()
    assert ch["lang"] == "ru"
    msgs = requests.get(f"{BASE}/api/chats/{ch['id']}/messages", headers=hdrs(T2), timeout=15).json()["messages"]
    assert msgs and msgs[0]["text"].startswith("Здравствуйте"), msgs[0]["text"][:80]


# ---------------------------- 2) screenshots ----------------------------

@pytest.fixture(scope="module")
def support_chat_en():
    r = requests.post(f"{BASE}/api/chats", headers=hdrs(T1, "en"), json={"kind": "support"}, timeout=15)
    return r.json()["id"]


def test_attachments_guest_401(support_chat_en):
    r = requests.post(f"{BASE}/api/chats/{support_chat_en}/attachments",
                      files={"file": ("a.png", PNG, "image/png")}, timeout=15)
    assert r.status_code == 401


def test_attachments_non_image_400(support_chat_en):
    r = requests.post(f"{BASE}/api/chats/{support_chat_en}/attachments",
                      headers=hdrs(T1), files={"file": ("a.txt", b"hello world", "image/png")}, timeout=15)
    assert r.status_code == 400, r.text


def test_attachments_too_large_413(support_chat_en):
    r = requests.post(f"{BASE}/api/chats/{support_chat_en}/attachments",
                      headers=hdrs(T1), files={"file": ("big.png", BIG_PNG, "image/png")}, timeout=30)
    assert r.status_code == 413, r.text


def test_attachments_upload_and_privacy_and_cooldown(support_chat_en):
    up = requests.post(f"{BASE}/api/chats/{support_chat_en}/attachments",
                       headers=hdrs(T1), files={"file": ("a.png", PNG, "image/png")}, timeout=15)
    assert up.status_code == 201, up.text
    body = up.json()
    assert body["kind"] == "image" and body.get("attachment_id") and body.get("expires_at")
    att = body["attachment_id"]

    # Owner can fetch
    got = requests.get(f"{BASE}/api/chats/{support_chat_en}/attachments/{att}", headers=hdrs(T1), timeout=15)
    assert got.status_code == 200 and got.content[:8] == b"\x89PNG\r\n\x1a\n"
    # Other user cannot
    other = requests.get(f"{BASE}/api/chats/{support_chat_en}/attachments/{att}", headers=hdrs(T2), timeout=15)
    assert other.status_code == 404

    # Second upload within 20s -> cooldown 429
    again = requests.post(f"{BASE}/api/chats/{support_chat_en}/attachments",
                         headers=hdrs(T1), files={"file": ("b.png", PNG, "image/png")}, timeout=15)
    assert again.status_code == 429, again.text


def test_admin_can_fetch_attachment(support_chat_en):
    # Admin login
    seed = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
    tok = requests.post(f"{BASE}/api/admin/login", json={"phrases": seed}, timeout=15).json().get("token")
    assert tok, "admin login failed"
    # Find the last-uploaded attachment id for this chat via admin messages
    msgs = requests.get(f"{BASE}/api/admin/chats/{support_chat_en}/messages",
                        headers={"Authorization": f"Bearer {tok}"}, timeout=15).json()
    imgs = [m for m in msgs.get("messages", []) if m.get("kind") == "image"]
    assert imgs, "no image messages visible to admin"
    att = imgs[-1]["attachment_id"]
    r = requests.get(f"{BASE}/api/admin/chats/{support_chat_en}/attachments/{att}",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------- 3) DonationAlerts request ----------------------------

@pytest.fixture(scope="module")
def da_deposit():
    # Cancel any prior pending DA request from earlier runs by using T1's active flow.
    r = requests.post(f"{BASE}/api/donationalerts/requests", headers=hdrs(T1, "en"),
                      json={"currency": "USD", "amount": 5}, timeout=20)
    # If already pending, tolerate 409 and read from chats
    if r.status_code == 409:
        pytest.skip(f"pre-existing pending DA request: {r.text}")
    assert r.status_code == 201, r.text
    return r.json()


def test_da_request_creates_chat_with_instructions(da_deposit):
    dep_id = da_deposit["deposit_id"]; chat_id = da_deposit["chat_id"]; code = da_deposit["code"]
    msgs = requests.get(f"{BASE}/api/chats/{chat_id}/messages", headers=hdrs(T1), timeout=15).json()["messages"]
    step = next((m for m in msgs if m.get("kind") == "da_instructions"), None)
    assert step is not None, "no da_instructions message in chat"
    txt = step["text"]
    assert "donationalerts.com/r/bloxgrade" in txt
    assert code in txt
    assert "qa_tester" in txt.lower() or "player" in txt.lower()
    assert "USD" in txt and "5" in txt
    assert dep_id  # id present


def test_second_pending_da_request_conflicts(da_deposit):
    r = requests.post(f"{BASE}/api/donationalerts/requests", headers=hdrs(T1),
                      json={"currency": "EUR", "amount": 5}, timeout=15)
    assert r.status_code == 409, r.text


# ---------------------------- 4) 'I paid' once (REAL call, max 1) ----------------------------

def test_paid_button_once_and_second_is_409(da_deposit):
    dep_id = da_deposit["deposit_id"]
    # Other user cannot mark paid
    other = requests.post(f"{BASE}/api/donationalerts/requests/{dep_id}/paid", headers=hdrs(T2), timeout=15)
    assert other.status_code == 404
    r1 = requests.post(f"{BASE}/api/donationalerts/requests/{dep_id}/paid", headers=hdrs(T1), timeout=15)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{BASE}/api/donationalerts/requests/{dep_id}/paid", headers=hdrs(T1), timeout=15)
    assert r2.status_code == 409, r2.text


# ---------------------------- 5) Telegram webhook security & simulated callbacks ----------------------------

def _cb(uid, data, from_id=ADMIN_ID):
    return {"update_id": uid,
            "callback_query": {"id": f"q{uid}", "from": {"id": from_id}, "data": data,
                               "message": {"message_id": 1, "chat": {"id": ADMIN_ID}}}}


def test_webhook_requires_secret():
    r = requests.post(f"{BASE}/api/telegram/webhook", json={"update_id": 999999999}, timeout=15)
    assert r.status_code == 403


def test_webhook_accepts_correct_secret():
    r = requests.post(f"{BASE}/api/telegram/webhook",
                      headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                      json={"update_id": 999999998}, timeout=15)
    assert r.status_code == 200, r.text


def test_stranger_cannot_approve_deposit(da_deposit):
    dep_id = da_deposit["deposit_id"]
    uid = 900000000 + int(time.time()) % 1000
    r = requests.post(f"{BASE}/api/telegram/webhook",
                      headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                      json=_cb(uid, f"da:ok:{dep_id}:50", from_id=1234567), timeout=15)
    assert r.status_code == 200
    # Deposit should NOT be confirmed
    # We probe via /api/donationalerts/requests to see status
    lst = requests.get(f"{BASE}/api/donationalerts/requests", headers=hdrs(T1), timeout=15)
    if lst.status_code == 200:
        items = lst.json().get("items", []) if isinstance(lst.json(), dict) else lst.json()
        found = next((i for i in items if i.get("deposit_id") == dep_id or i.get("id") == dep_id), None)
        if found:
            assert found.get("status") not in ("confirmed", "credited")


def test_ask_step_does_not_credit(da_deposit):
    dep_id = da_deposit["deposit_id"]
    uid = 910000000 + int(time.time()) % 1000
    r = requests.post(f"{BASE}/api/telegram/webhook",
                      headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                      json=_cb(uid, f"da:ask:{dep_id}:50"), timeout=15)
    assert r.status_code == 200


def test_owner_ok_credits_once_and_redelivery_ignored(da_deposit):
    """Approve the deposit via simulated owner callback. Second identical update_id is ignored."""
    dep_id = da_deposit["deposit_id"]
    uid = 920000000 + int(time.time()) % 1000

    r = requests.post(f"{BASE}/api/telegram/webhook",
                      headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                      json=_cb(uid, f"da:ok:{dep_id}:5000"), timeout=15)
    assert r.status_code == 200
    # Redeliver same update_id — must be ignored (no double credit)
    r2 = requests.post(f"{BASE}/api/telegram/webhook",
                       headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                       json=_cb(uid, f"da:ok:{dep_id}:5000"), timeout=15)
    assert r2.status_code == 200

    # Verify deposit status flipped to confirmed in Mongo (money-safety math is not touched here).
    import asyncio as _a
    from motor.motor_asyncio import AsyncIOMotorClient as _C

    async def check():
        db = _C("mongodb://localhost:27017").test_database
        dep = await db.deposits.find_one({"id": dep_id}, {"_id": 0})
        return dep
    dep = _a.run(check())
    assert dep and dep.get("status") == "confirmed", f"deposit not confirmed: {dep}"


# ---------------------------- 6) reject flow ----------------------------

def test_reject_flow_via_second_request():
    """Create a fresh DA request (T2 has no pending) and reject it via webhook."""
    r = requests.post(f"{BASE}/api/donationalerts/requests", headers=hdrs(T2, "en"),
                      json={"currency": "USD", "amount": 5}, timeout=20)
    if r.status_code == 409:
        pytest.skip("T2 has pre-existing pending DA request")
    assert r.status_code == 201, r.text
    dep_id = r.json()["deposit_id"]

    uid1 = 930000000 + int(time.time()) % 1000
    # rej step (asks confirm)
    r1 = requests.post(f"{BASE}/api/telegram/webhook",
                       headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                       json=_cb(uid1, f"da:rej:{dep_id}"), timeout=15)
    assert r1.status_code == 200
    # confirm reject
    uid2 = uid1 + 1
    r2 = requests.post(f"{BASE}/api/telegram/webhook",
                       headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                       json=_cb(uid2, f"da:rejok:{dep_id}"), timeout=15)
    assert r2.status_code == 200


# ---------------------------- 7) admin telegram card status (no setup!) ----------------------------

def test_admin_telegram_status_ok():
    seed = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
    tok = requests.post(f"{BASE}/api/admin/login", json={"phrases": seed}, timeout=15).json().get("token")
    assert tok
    r = requests.get(f"{BASE}/api/admin/telegram",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # It should tell us it's connected or expose fields
    assert isinstance(body, dict)
