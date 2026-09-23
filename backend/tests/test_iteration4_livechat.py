"""Iteration 4: live chat + admin chats-tab tests.

Covers:
- MIN_DEPOSIT_RAP=200 in /api/deposit/info
- Guest chat single-owner behaviour + cooldown
- Admin chats listing, search, messages payload
- Admin deposit preview + confirm via chat (JWT-authenticated user)
- Admin bulk-done withdrawals + per-item cancel
"""
import os
import time
import uuid
import jwt
import requests
import pytest
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
JWT_SECRET = os.environ["JWT_SECRET"]
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN_PHRASE = "alpha bravo charlie delta echo foxtrot golf hotel india juliet".split()
QA_SESSION = "test-session-qa-1"
UA = "iter4-tests/1.0"


@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="session")
def qa_jwt():
    return jwt.encode(
        {"sub": QA_SESSION, "role": "user",
         "exp": datetime.now(timezone.utc) + timedelta(hours=2),
         "iat": datetime.now(timezone.utc)},
        JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Content-Type": "application/json"})
    r = s.post(f"{API}/admin/login", json={"phrases": ADMIN_PHRASE})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="session")
def user_client(qa_jwt):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Content-Type": "application/json",
                      "Authorization": f"Bearer {qa_jwt}"})
    return s


# ---- deposit info ----
def test_deposit_info_min_rap():
    r = requests.get(f"{API}/deposit/info", headers={"User-Agent": UA})
    assert r.status_code == 200
    assert r.json()["min_rap"] == 200


# ---- guest chat single-chat + cooldown ----
def test_guest_chat_single_and_cooldown(mongo):
    guest = f"iter4-guest-{uuid.uuid4().hex[:12]}"
    h = {"User-Agent": UA, "X-Session-Id": guest, "Content-Type": "application/json"}

    r1 = requests.post(f"{API}/chats", json={"kind": "support", "text": "hi"}, headers=h)
    assert r1.status_code == 201, r1.text
    chat_id = r1.json()["id"]

    r2 = requests.post(f"{API}/chats", json={"kind": "support", "text": "hi again"}, headers=h)
    assert r2.status_code == 201
    assert r2.json()["id"] == chat_id, "second POST /chats should return same chat"

    mine = requests.get(f"{API}/chats", headers=h).json()
    assert len(mine["chats"]) == 1
    assert 100 < mine["cooldown_seconds"] <= 180

    # close during cooldown -> 429
    rc = requests.post(f"{API}/chats/{chat_id}/close", headers=h)
    assert rc.status_code == 429
    assert rc.headers.get("Retry-After")
    assert "сек" in rc.json().get("detail", "")

    # message while open -> 201
    rm = requests.post(f"{API}/chats/{chat_id}/messages", json={"text": "still open"}, headers=h)
    assert rm.status_code == 201

    # admin closes the chat -> user posting returns 409
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Content-Type": "application/json"})
    r = s.post(f"{API}/admin/login", json={"phrases": ADMIN_PHRASE})
    assert r.status_code == 200
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    rac = s.post(f"{API}/admin/chats/{chat_id}/close")
    assert rac.status_code == 200

    rm2 = requests.post(f"{API}/chats/{chat_id}/messages", json={"text": "after close"}, headers=h)
    assert rm2.status_code == 409

    # reopen during cooldown -> 429 (toggle_at just set on close)
    rr = requests.post(f"{API}/chats/{chat_id}/reopen", headers=h)
    assert rr.status_code == 429

    mongo.chats.delete_one({"id": chat_id})
    mongo.chat_messages.delete_many({"chat_id": chat_id})


# ---- admin listing + search ----
def test_admin_chats_list_and_search(admin_client, user_client, mongo):
    # Ensure QA user has a chat
    r = user_client.post(f"{API}/chats", json={"kind": "support", "text": "Iter4 qa hello"})
    assert r.status_code == 201, r.text
    qa_chat_id = r.json()["id"]

    r = admin_client.get(f"{API}/admin/chats", params={"status": "all"})
    assert r.status_code == 200
    chats = r.json()
    assert any(c["id"] == qa_chat_id for c in chats)
    qa = next(c for c in chats if c["id"] == qa_chat_id)
    assert "online" in qa and isinstance(qa["online"], bool)
    assert "waiting_seconds" in qa
    assert "balance" in qa

    # waiting-first ordering: chats with waiting_since must come before those without
    waiting = [c for c in chats if c.get("waiting_since")]
    non = [c for c in chats if not c.get("waiting_since")]
    if waiting and non:
        idx_w = chats.index(waiting[-1])
        idx_n = chats.index(non[0])
        assert idx_w < idx_n, "waiting chats must come first"

    r = admin_client.get(f"{API}/admin/chats", params={"status": "all", "q": "QA"})
    assert r.status_code == 200
    assert any(c["id"] == qa_chat_id for c in r.json())

    r = admin_client.get(f"{API}/admin/search", params={"q": "qa_rob"})
    assert r.status_code == 200
    hits = r.json()
    assert any(u["session_id"] == QA_SESSION for u in hits)
    u = next(u for u in hits if u["session_id"] == QA_SESSION)
    assert u["chat_id"] == qa_chat_id
    assert "balance" in u and "skins_count" in u and "roblox_link" in u


# ---- admin deposit via chat ----
def test_admin_chat_deposit_flow(admin_client, user_client, mongo):
    # Create deposit-kind chat request for QA user (JWT)
    r = user_client.post(f"{API}/chats", json={"kind": "deposit", "expected_rap": 300})
    assert r.status_code == 201, r.text
    chat_id = r.json()["id"]

    # rap < 200 -> 400
    r = admin_client.post(f"{API}/admin/chats/{chat_id}/deposit/preview", json={"rap": 100})
    assert r.status_code == 400

    # valid preview
    r = admin_client.post(f"{API}/admin/chats/{chat_id}/deposit/preview", json={"rap": 300})
    assert r.status_code == 200, r.text
    plan = r.json()
    # 20% fee => 240 credited
    assert abs(float(plan["credited"]) - 240.0) < 1e-6
    assert "issued_skins" in plan
    assert "balance_credited" in plan

    # snapshot balance
    before = mongo.users.find_one({"session_id": QA_SESSION}, {"_id": 0, "balance": 1, "skins": 1})
    prev_balance = float(before.get("balance") or 0)
    prev_skins = len(before.get("skins") or [])

    # confirm
    r = admin_client.post(f"{API}/admin/chats/{chat_id}/deposit", json={"rap": 300, "note": "qa"})
    assert r.status_code == 200, r.text
    result = r.json()
    assert "deposit_id" in result
    dep_id = result["deposit_id"]

    # verify user balance/skins updated
    after = mongo.users.find_one({"session_id": QA_SESSION}, {"_id": 0, "balance": 1, "skins": 1})
    new_balance = float(after.get("balance") or 0)
    new_skins = len(after.get("skins") or [])
    assert new_balance + new_skins > prev_balance + prev_skins, "balance or skins should increase"

    # deposit confirmed
    dep = mongo.deposits.find_one({"id": dep_id}, {"_id": 0})
    assert dep["status"] == "confirmed"

    # bank_ledger entry
    lg = mongo.bank_ledger.find_one({"kind": "deposit", "ref_id": dep_id})
    assert lg is not None, "bank_ledger deposit entry expected"

    # system message posted in chat
    msgs = admin_client.get(f"{API}/admin/chats/{chat_id}/messages").json()["messages"]
    assert any(m["sender"] == "system" and "Пополнение подтверждено" in m["text"] for m in msgs)


# ---- admin withdrawals via chat ----
def test_admin_chat_withdrawals(admin_client, user_client, mongo):
    # Ensure a chat exists for QA
    r = user_client.post(f"{API}/chats", json={"kind": "support", "text": "wd test"})
    chat_id = r.json()["id"]

    # Clean prior test withdrawals
    mongo.withdrawals.delete_many({"session_id": QA_SESSION, "item.name": {"$regex": "^ITER4_"}})

    # Seed 2 pending
    for i in range(2):
        mongo.withdrawals.insert_one({
            "id": str(uuid.uuid4()),
            "session_id": QA_SESSION,
            "item": {"uid": f"uid-{i}", "name": f"ITER4_skin_{i}", "type": "knife", "price": 100 + i * 50},
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        })

    # GET messages -> withdrawals_total = sum
    r = admin_client.get(f"{API}/admin/chats/{chat_id}/messages")
    assert r.status_code == 200
    data = r.json()
    total = round(sum(float((w.get("item") or {}).get("price") or 0)
                      for w in data["withdrawals"]
                      if w["item"]["name"].startswith("ITER4_")), 2)
    # Our seeded total = 250. withdrawals_total covers all pending, might include older
    assert data["withdrawals_total"] >= 250
    assert total == 250

    # bulk done
    r = admin_client.post(f"{API}/admin/chats/{chat_id}/withdrawals/done")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["done"] >= 2

    # Verify pending count now 0
    remaining = mongo.withdrawals.count_documents({"session_id": QA_SESSION, "status": "pending"})
    assert remaining == 0

    # Seed one more and cancel it
    wid = str(uuid.uuid4())
    mongo.withdrawals.insert_one({
        "id": wid, "session_id": QA_SESSION,
        "item": {"uid": "uid-c", "name": "ITER4_cancel_me", "type": "knife", "price": 300},
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })
    r = admin_client.post(f"{API}/admin/withdrawals/{wid}/cancel", json={"reason": "iter4 cancel test"})
    assert r.status_code == 200, r.text

    doc = mongo.withdrawals.find_one({"id": wid})
    assert doc["status"] in ("cancelled", "canceled"), f"got {doc['status']}"

    # system message posted about cancel
    msgs = admin_client.get(f"{API}/admin/chats/{chat_id}/messages").json()["messages"]
    assert any(m["sender"] == "system" and ("отмен" in m["text"].lower()) for m in msgs), \
        "expected a cancel system message"

    # Cleanup any leftover test withdrawals
    mongo.withdrawals.delete_many({"session_id": QA_SESSION, "item.name": {"$regex": "^ITER4_"}})


# ---- admin deposit for guest -> 400 ----
def test_admin_chat_deposit_guest_rejected(admin_client, mongo):
    guest = f"iter4-guest2-{uuid.uuid4().hex[:12]}"
    r = requests.post(f"{API}/chats", json={"kind": "support", "text": "g"},
                      headers={"User-Agent": UA, "X-Session-Id": guest})
    chat_id = r.json()["id"]

    r = admin_client.post(f"{API}/admin/chats/{chat_id}/deposit", json={"rap": 300})
    assert r.status_code == 400

    mongo.chats.delete_one({"id": chat_id})
    mongo.chat_messages.delete_many({"chat_id": chat_id})
