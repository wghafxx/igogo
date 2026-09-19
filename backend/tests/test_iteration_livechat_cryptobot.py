"""Backend tests for live-chat + CryptoBot iteration.

Covers:
- Guest chat CRUD, ownership isolation and 3-open-chats limit
- Deposit chat (auth required, creates deposit doc, expected_rap validation)
- Admin chat flow (accept, message auto-accept, close, reopen)
- Deposit via chat -> admin confirm / reject notifications in the chat
- CryptoBot info/create/list/refresh/webhook signature
"""
import hashlib
import hmac
import json
import os
import string
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pymongo
import pytest
import requests

# ---------- config ----------
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE:
    # fall back to reading /app/frontend/.env
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip().rstrip("/")

BACKEND_ENV = {}
for line in Path("/app/backend/.env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        BACKEND_ENV[k.strip()] = v.strip().strip('"').strip("'")

JWT_SECRET = BACKEND_ENV["JWT_SECRET"]
MONGO_URL = BACKEND_ENV["MONGO_URL"]
DB_NAME = BACKEND_ENV["DB_NAME"]
CRYPTOBOT_TOKEN = BACKEND_ENV.get("CRYPTOBOT_API_TOKEN", "")

ADMIN_PHRASE = "ember tidal falcon marble quartz signal harbor velvet cobalt lantern".split()
UA = "iteration3-tester/1.0"

mongo = pymongo.MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def _now():
    return datetime.now(timezone.utc)


def mint_user_token(session_id):
    payload = {
        "sub": session_id, "role": "user",
        "exp": _now() + timedelta(hours=2), "iat": _now(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def rand_guest():
    import random
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


# ---------- shared fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
    return s


@pytest.fixture(scope="module")
def admin_token(session):
    r = session.post(f"{BASE}/api/admin/login", json={"phrases": ADMIN_PHRASE}, headers={"User-Agent": UA})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "User-Agent": UA, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_user():
    session_id = "TESTUSR" + uuid.uuid4().hex[:16]
    doc = {
        "session_id": session_id, "balance": 0.0,
        "nickname": f"TEST_{session_id[:6]}", "skins": [], "created_at": _now(),
    }
    db.users.insert_one(dict(doc))
    token = mint_user_token(session_id)
    yield {"session_id": session_id, "token": token, "headers": {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA}}
    # cleanup - delete test user + their deposits + chats
    db.deposits.delete_many({"session_id": session_id})
    db.chats.delete_many({"owner": session_id})
    db.users.delete_one({"session_id": session_id})


# ---------- Guest chat basic ----------
class TestGuestChat:
    def test_chats_get_without_header_or_token_returns_401(self, session):
        r = session.get(f"{BASE}/api/chats", headers={"User-Agent": UA})
        assert r.status_code == 401

    def test_chats_get_with_bad_session_id_401(self, session):
        r = session.get(f"{BASE}/api/chats", headers={"User-Agent": UA, "X-Session-Id": "short"})
        assert r.status_code == 401

    def test_chats_get_with_valid_guest_returns_empty_list(self, session):
        guest = rand_guest()
        r = session.get(f"{BASE}/api/chats", headers={"User-Agent": UA, "X-Session-Id": guest})
        assert r.status_code == 200
        data = r.json()
        assert "chats" in data and "unread" in data
        # cleanup
        db.chats.delete_many({"owner": f"guest:{guest}"})

    def test_guest_can_create_support_chat_and_send_message(self, session):
        guest = rand_guest()
        h = {"User-Agent": UA, "X-Session-Id": guest, "Content-Type": "application/json"}
        r = session.post(f"{BASE}/api/chats", json={"kind": "support", "text": "hello"}, headers=h)
        assert r.status_code == 201, r.text
        chat = r.json()
        assert chat["status"] == "open"
        assert chat["guest"] is True
        assert chat["nickname"].startswith("Гость")
        chat_id = chat["id"]

        # messages endpoint returns messages including 'hello'
        r2 = session.get(f"{BASE}/api/chats/{chat_id}/messages", headers=h)
        assert r2.status_code == 200
        data = r2.json()
        texts = [m["text"] for m in data["messages"]]
        assert "hello" in texts

        # post another message
        r3 = session.post(f"{BASE}/api/chats/{chat_id}/messages", json={"text": "follow up"}, headers=h)
        assert r3.status_code == 201

        # admin_unread should have been incremented in DB
        db_chat = db.chats.find_one({"id": chat_id})
        assert db_chat["admin_unread"] >= 2  # 'hello' + 'follow up'

        # different guest cannot access
        other = rand_guest()
        r4 = session.get(f"{BASE}/api/chats/{chat_id}/messages", headers={"User-Agent": UA, "X-Session-Id": other, "Content-Type": "application/json"})
        assert r4.status_code == 404
        db.chats.delete_many({"owner": f"guest:{guest}"})
        db.chat_messages.delete_many({"chat_id": chat_id})

    def test_guest_max_3_non_closed_chats(self, session):
        guest = rand_guest()
        h = {"User-Agent": UA, "X-Session-Id": guest, "Content-Type": "application/json"}
        created = []
        for _ in range(3):
            r = session.post(f"{BASE}/api/chats", json={"kind": "support", "text": "hi"}, headers=h)
            assert r.status_code == 201
            created.append(r.json()["id"])
        r4 = session.post(f"{BASE}/api/chats", json={"kind": "support", "text": "hi"}, headers=h)
        assert r4.status_code == 429
        # cleanup
        db.chats.delete_many({"owner": f"guest:{guest}"})
        for cid in created:
            db.chat_messages.delete_many({"chat_id": cid})


# ---------- Deposit chat auth ----------
class TestDepositChat:
    def test_deposit_chat_requires_login(self, session):
        guest = rand_guest()
        h = {"User-Agent": UA, "X-Session-Id": guest, "Content-Type": "application/json"}
        r = session.post(f"{BASE}/api/chats", json={"kind": "deposit", "expected_rap": 100}, headers=h)
        assert r.status_code == 401

    def test_authenticated_user_creates_deposit_chat(self, session, test_user):
        r = session.post(f"{BASE}/api/chats", json={"kind": "deposit", "expected_rap": 100}, headers=test_user["headers"])
        assert r.status_code == 201, r.text
        chat = r.json()
        assert chat["kind"] == "deposit"
        assert chat["deposit_id"]
        assert chat["expected_rap"] == 100
        # messages: first should be 'deposit_request'
        r2 = session.get(f"{BASE}/api/chats/{chat['id']}/messages", headers=test_user["headers"])
        assert r2.status_code == 200
        msgs = r2.json()["messages"]
        assert any(m.get("kind") == "deposit_request" for m in msgs)
        # deposit doc exists with via_chat True
        dep = db.deposits.find_one({"id": chat["deposit_id"]})
        assert dep is not None
        assert dep.get("via_chat") is True
        assert dep["chat_id"] == chat["id"]
        assert dep["status"] == "pending"
        # deposits/my returns it
        r3 = session.get(f"{BASE}/api/deposits/my", headers=test_user["headers"])
        assert r3.status_code == 200
        ids = [d["id"] for d in r3.json()]
        assert dep["id"] in ids

    def test_expected_rap_below_60_returns_422(self, session, test_user):
        r = session.post(f"{BASE}/api/chats", json={"kind": "deposit", "expected_rap": 30}, headers=test_user["headers"])
        assert r.status_code == 422


# ---------- Admin chat flow ----------
class TestAdminChat:
    def test_admin_endpoints_without_token_403(self, session):
        r = session.get(f"{BASE}/api/admin/chats", headers={"User-Agent": UA})
        assert r.status_code == 403

    def test_admin_flow_accept_message_close_reopen(self, session, admin_headers):
        # create a guest chat first
        guest = rand_guest()
        gh = {"User-Agent": UA, "X-Session-Id": guest, "Content-Type": "application/json"}
        r = session.post(f"{BASE}/api/chats", json={"kind": "support", "text": "help me"}, headers=gh)
        assert r.status_code == 201
        chat_id = r.json()["id"]

        # summary
        r = session.get(f"{BASE}/api/admin/chats/summary", headers=admin_headers)
        assert r.status_code == 200 and set(r.json().keys()) >= {"open", "active", "unread"}

        # list open contains this chat
        r = session.get(f"{BASE}/api/admin/chats?status=open", headers=admin_headers)
        assert r.status_code == 200
        assert any(c["id"] == chat_id for c in r.json())

        # accept
        r = session.post(f"{BASE}/api/admin/chats/{chat_id}/accept", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "active"

        # a system message should be appended
        r = session.get(f"{BASE}/api/admin/chats/{chat_id}/messages", headers=admin_headers)
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert any(m["sender"] == "system" and "Оператор" in m["text"] for m in msgs)

        # admin sends msg -> user_unread++
        r = session.post(f"{BASE}/api/admin/chats/{chat_id}/messages", json={"text": "hi from admin"}, headers=admin_headers)
        assert r.status_code == 201

        # guest sees unread badge
        r = session.get(f"{BASE}/api/chats", headers=gh)
        assert r.status_code == 200
        assert r.json()["unread"] >= 1

        # guest fetches messages -> resets user_unread
        r = session.get(f"{BASE}/api/chats/{chat_id}/messages", headers=gh)
        assert r.status_code == 200 and r.json()["chat"]["user_unread"] == 0

        # admin close
        r = session.post(f"{BASE}/api/admin/chats/{chat_id}/close", headers=admin_headers)
        assert r.status_code == 200 and r.json()["status"] == "closed"

        # user message re-opens
        r = session.post(f"{BASE}/api/chats/{chat_id}/messages", json={"text": "still here"}, headers=gh)
        assert r.status_code == 201
        db_chat = db.chats.find_one({"id": chat_id})
        assert db_chat["status"] == "open"

        # cleanup
        db.chats.delete_many({"owner": f"guest:{guest}"})
        db.chat_messages.delete_many({"chat_id": chat_id})

    def test_admin_message_to_open_chat_auto_accepts(self, session, admin_headers):
        guest = rand_guest()
        gh = {"User-Agent": UA, "X-Session-Id": guest, "Content-Type": "application/json"}
        r = session.post(f"{BASE}/api/chats", json={"kind": "support", "text": "auto-accept?"}, headers=gh)
        chat_id = r.json()["id"]
        r = session.post(f"{BASE}/api/admin/chats/{chat_id}/messages", json={"text": "ok"}, headers=admin_headers)
        assert r.status_code == 201
        db_chat = db.chats.find_one({"id": chat_id})
        assert db_chat["status"] == "active"
        db.chats.delete_many({"owner": f"guest:{guest}"})
        db.chat_messages.delete_many({"chat_id": chat_id})


# ---------- Deposit via chat -> admin confirm / reject ----------
class TestDepositViaChatSettlement:
    def test_admin_confirm_notifies_chat_and_settles(self, session, admin_headers, test_user):
        # create deposit chat
        r = session.post(f"{BASE}/api/chats", json={"kind": "deposit", "expected_rap": 100}, headers=test_user["headers"])
        assert r.status_code == 201
        chat_id = r.json()["id"]
        dep_id = r.json()["deposit_id"]
        # admin sees deposit info via admin/chats/{id}/messages
        r = session.get(f"{BASE}/api/admin/chats/{chat_id}/messages", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["deposit"] is not None
        assert r.json()["deposit"]["id"] == dep_id

        # pending list should NOT include cryptobot/xrocket, includes this deposit
        r = session.get(f"{BASE}/api/admin/deposits?status=pending", headers=admin_headers)
        assert r.status_code == 200
        assert any(d["id"] == dep_id for d in r.json())

        # confirm
        r = session.post(f"{BASE}/api/admin/deposits/{dep_id}/confirm", json={"rap": 100}, headers=admin_headers)
        assert r.status_code == 200, r.text

        # system message about settlement appears
        r = session.get(f"{BASE}/api/admin/chats/{chat_id}/messages", headers=admin_headers)
        msgs = r.json()["messages"]
        assert any(m["sender"] == "system" and "подтверждено" in m["text"].lower() for m in msgs)

    def test_admin_reject_notifies_chat(self, session, admin_headers, test_user):
        r = session.post(f"{BASE}/api/chats", json={"kind": "deposit", "expected_rap": 120}, headers=test_user["headers"])
        assert r.status_code == 201
        chat_id = r.json()["id"]
        dep_id = r.json()["deposit_id"]
        r = session.post(f"{BASE}/api/admin/deposits/{dep_id}/reject", json={"reason": "no_reason"}, headers=admin_headers)
        assert r.status_code == 200
        r = session.get(f"{BASE}/api/admin/chats/{chat_id}/messages", headers=admin_headers)
        msgs = r.json()["messages"]
        assert any(m["sender"] == "system" and "отклонена" in m["text"].lower() for m in msgs)


# ---------- CryptoBot ----------
class TestCryptoBot:
    def test_info(self, session):
        r = session.get(f"{BASE}/api/payments/cryptobot/info")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is True
        assert data["min_rub"] == 35
        assert isinstance(data["currencies"], list) and "USDT" in data["currencies"]

    def test_create_invoice_requires_auth(self, session):
        r = session.post(f"{BASE}/api/payments/cryptobot/invoices",
                         json={"request_id": str(uuid.uuid4()), "amount_rub": 35})
        assert r.status_code == 401

    def test_amount_below_min_returns_422(self, session, test_user):
        r = session.post(f"{BASE}/api/payments/cryptobot/invoices",
                         json={"request_id": str(uuid.uuid4()), "amount_rub": 10}, headers=test_user["headers"])
        assert r.status_code == 422

    def test_create_and_idempotent_and_list(self, session, test_user):
        rid = str(uuid.uuid4())
        r = session.post(f"{BASE}/api/payments/cryptobot/invoices",
                         json={"request_id": rid, "amount_rub": 35}, headers=test_user["headers"])
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["id"] == f"cryptobot:{rid}"
        assert inv["status"] == "awaiting_payment"
        assert inv["invoice_url"].startswith("https://t.me/")
        assert inv["currency"] == "CryptoBot"
        assert inv["expected_rap"] == 70
        assert inv["quoted_rap"] == 70
        assert inv["payment_method"] == "cryptobot"

        # idempotent
        r2 = session.post(f"{BASE}/api/payments/cryptobot/invoices",
                          json={"request_id": rid, "amount_rub": 35}, headers=test_user["headers"])
        assert r2.status_code == 200
        assert r2.json()["id"] == inv["id"]
        assert r2.json()["invoice_url"] == inv["invoice_url"]

        # list
        r3 = session.get(f"{BASE}/api/payments/cryptobot/invoices", headers=test_user["headers"])
        assert r3.status_code == 200
        assert any(x["id"] == inv["id"] for x in r3.json())

        # by id
        r4 = session.get(f"{BASE}/api/payments/cryptobot/invoices/{inv['id']}", headers=test_user["headers"])
        assert r4.status_code == 200

        # refresh (may still be awaiting_payment)
        r5 = session.post(f"{BASE}/api/payments/cryptobot/invoices/{inv['id']}/refresh", headers=test_user["headers"])
        assert r5.status_code == 200
        assert r5.json()["status"] in ("awaiting_payment", "expired")

        # admin sees cryptobot deposit
        # (using admin_headers requires the fixture: request session-level admin token via db)
        # confirm-attempt on cryptobot deposit should be 409 (auto-managed)
        # -- move to separate test with admin_headers

    def test_admin_lists_cryptobot_and_confirm_409(self, session, admin_headers, test_user):
        # create a fresh invoice first
        rid = str(uuid.uuid4())
        r = session.post(f"{BASE}/api/payments/cryptobot/invoices",
                         json={"request_id": rid, "amount_rub": 35}, headers=test_user["headers"])
        # If we've hit the 2-invoice limit we may want to reuse the previous one; but this
        # is fine because CryptoBot invoices are cheap to look up. Still, in this test we
        # already created one in previous test (that's #1); this is #2 = max 2.
        assert r.status_code == 200, r.text
        inv_id = r.json()["id"]

        r2 = session.get(f"{BASE}/api/admin/deposits?status=cryptobot", headers=admin_headers)
        assert r2.status_code == 200
        assert any(d["id"] == inv_id for d in r2.json())

        # status=pending must exclude cryptobot
        r3 = session.get(f"{BASE}/api/admin/deposits?status=pending", headers=admin_headers)
        assert r3.status_code == 200
        assert all(d.get("payment_method") != "cryptobot" for d in r3.json())

        r4 = session.post(f"{BASE}/api/admin/deposits/{inv_id}/confirm",
                          json={"rap": 70}, headers=admin_headers)
        assert r4.status_code == 409

    def test_webhook_without_signature_401(self, session):
        r = session.post(f"{BASE}/api/payments/cryptobot/webhook", json={"foo": "bar"})
        assert r.status_code == 401

    def test_webhook_with_valid_sig_unknown_invoice_returns_ok(self, session):
        body = json.dumps({
            "update_id": 9_876_543,
            "update_type": "invoice_paid",
            "request_date": _now().isoformat(),
            "payload": {"invoice_id": 999999, "status": "paid"},
        }).encode()
        secret = hashlib.sha256(CRYPTOBOT_TOKEN.encode()).digest()
        sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
        r = session.post(f"{BASE}/api/payments/cryptobot/webhook",
                         data=body,
                         headers={"crypto-pay-api-signature": sig,
                                  "Content-Type": "application/json", "User-Agent": UA})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
