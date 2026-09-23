"""Live end-to-end tests over the public REACT_APP_BACKEND_URL for the review-request items.

Covers: JWT revocation, skin withdraw + recipient snapshot, admin deposit idempotency,
admin chats paging + summary, chats concurrent create, live-drops, path traversal (via
static route), and shop/buy request_id idempotency.

Marked 'live' so it is skipped by the isolated suite.  Uses pymongo directly for
setup/cleanup because we need to reset session_version, restore skins, etc.
"""
from __future__ import annotations

import concurrent.futures
import os
import time
import uuid
from typing import Optional

import jwt
import pymongo
import pytest
import requests
from dotenv import load_dotenv


load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]

SESSION_ID = "discord_test_1"
ADMIN_PHRASES = ["alpha", "bravo", "charlie", "delta", "echo",
                 "foxtrot", "golf", "hotel", "india", "juliet"]

pytestmark = pytest.mark.live


# ---------- fixtures / helpers ----------
@pytest.fixture(scope="module")
def mongo():
    client = pymongo.MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _sign(sv: int, sub: str = SESSION_ID, role: str = "user") -> str:
    return jwt.encode(
        {"sub": sub, "role": role, "sv": sv, "exp": int(time.time()) + 3600},
        JWT_SECRET, algorithm="HS256",
    )


@pytest.fixture(scope="module")
def user_token(mongo):
    doc = mongo.users.find_one({"session_id": SESSION_ID}, {"session_version": 1})
    assert doc, "seeded user discord_test_1 missing"
    sv = int(doc.get("session_version") or 0)
    return _sign(sv), sv


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"phrases": ADMIN_PHRASES}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ---------- basic connectivity ----------
def test_auth_me_works_with_current_sv(user_token):
    tok, _ = user_token
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth(tok), timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == SESSION_ID
    assert data["balance"] >= 0
    assert data["roblox_nick"], "user must have roblox profile linked"


def test_auth_me_rejects_stale_sv(user_token):
    _, sv = user_token
    stale = _sign(sv - 100 if sv >= 100 else 999999)  # any wrong sv
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth(stale), timeout=15)
    # stale token → treated as guest → 401 on /api/auth/me
    assert r.status_code == 401, r.text


def test_live_drops_endpoint():
    r = requests.get(f"{BASE_URL}/api/live-drops", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------- admin chats: paging + summary ----------
def test_admin_chats_list_shape(admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/chats",
                     params={"status": "all", "offset": 0, "limit": 5},
                     headers=auth(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("items", "has_more", "offset", "total"):
        assert key in data, f"missing {key} in {data.keys()}"
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)


def test_admin_chats_summary_shape(admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/chats/summary",
                     headers=auth(admin_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    for key in ("open", "active", "unread"):
        assert key in data, f"missing {key}"
        assert isinstance(data[key], int)


# ---------- chats: concurrent create yields one chat per owner ----------
def _post_chat(tok: str) -> requests.Response:
    return requests.post(f"{BASE_URL}/api/chats",
                         json={"kind": "support", "text": "hello"},
                         headers=auth(tok), timeout=15)


def test_concurrent_chat_creation_yields_one(mongo, user_token):
    tok, _ = user_token
    # cleanup any existing open chats for this owner (support kind only)
    mongo.chats.delete_many({"owner": SESSION_ID, "kind": "support"})
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(lambda _: _post_chat(tok), range(5)))
    codes = [r.status_code for r in results]
    assert all(c in (200, 201) for c in codes), codes
    ids = {r.json()["id"] for r in results}
    assert len(ids) == 1, f"expected 1 chat, got {len(ids)}: {ids}"


# ---------- admin deposit request_id idempotency ----------
def test_admin_chat_deposit_request_id_idempotent(mongo, user_token, admin_token):
    tok, _ = user_token
    # clean any active skin-deposits
    mongo.deposits.delete_many({"session_id": SESSION_ID, "payment_method": {"$nin": ["xrocket", "cryptobot"]}, "status": {"$in": ["pending", "processing"]}})
    # create deposit chat
    r = requests.post(f"{BASE_URL}/api/chats",
                      json={"kind": "deposit", "expected_rap": 300},
                      headers=auth(tok), timeout=15)
    assert r.status_code in (200, 201), r.text
    chat_id = r.json()["id"]

    # snapshot balance & deposits count
    u_before = requests.get(f"{BASE_URL}/api/auth/me", headers=auth(tok), timeout=15).json()
    bal_before = float(u_before["balance"])
    dep_count_before = mongo.deposits.count_documents({"session_id": SESSION_ID})

    req_id = f"live-test-{uuid.uuid4()}"
    body = {"rap": 300, "note": "live e2e", "request_id": req_id}

    r1 = requests.post(f"{BASE_URL}/api/admin/chats/{chat_id}/deposit",
                       json=body, headers=auth(admin_token), timeout=20)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    r2 = requests.post(f"{BASE_URL}/api/admin/chats/{chat_id}/deposit",
                       json=body, headers=auth(admin_token), timeout=20)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()

    assert d1.get("deposit_id") == d2.get("deposit_id"), (d1, d2)
    assert d2.get("already_confirmed") is True, d2

    # user balance credited once, not twice
    u_after = requests.get(f"{BASE_URL}/api/auth/me", headers=auth(tok), timeout=15).json()
    bal_after = float(u_after["balance"])
    delta = bal_after - bal_before
    credited = float(d1.get("balance_credited") or d1.get("credited") or 0)
    # allow for issued_skins portion; ensure two calls don't double the increase
    assert delta <= credited + 0.01, f"balance grew {delta} > single credit {credited}"

    # only one deposit doc for this request_id
    key = f"chat:{chat_id}:{req_id}"
    matching = list(mongo.deposits.find({"admin_request_id": key}))
    assert len(matching) == 1


# ---------- skins withdraw recipient snapshot + recipient_changed ----------
def _restore_user(mongo, snapshot):
    mongo.users.update_one({"session_id": SESSION_ID}, {"$set": snapshot})


def test_skin_withdraw_snapshot_and_recipient_changed(mongo, user_token, admin_token):
    tok, _ = user_token
    user = mongo.users.find_one({"session_id": SESSION_ID}, {"_id": 0})
    skins = list(user.get("skins") or [])
    assert skins, "seeded user should have at least one skin"
    target = next((s for s in skins if float(s.get("price") or 0) >= 20), None)
    assert target, "need a skin priced >=20 RAP"
    uid = target["uid"]

    orig = {"roblox_nick": user["roblox_nick"], "roblox_link": user["roblox_link"],
            "roblox_display_name": user.get("roblox_display_name")}

    # cleanup: cancel any pending withdrawals for this user first
    for w in mongo.withdrawals.find({"session_id": SESSION_ID, "status": "pending"}, {"id": 1}):
        requests.post(f"{BASE_URL}/api/admin/withdrawals/{w['id']}/cancel",
                      json={"reason": "test cleanup"}, headers=auth(admin_token), timeout=15)

    r = requests.post(f"{BASE_URL}/api/skins/withdraw",
                      json={"uids": [uid]}, headers=auth(tok), timeout=20)
    assert r.status_code == 200, r.text
    fresh = r.json()
    assert not any((s.get("uid") == uid) for s in fresh.get("skins") or []), "skin still in inventory"

    # no reserving rows left
    assert mongo.withdrawals.count_documents({"session_id": SESSION_ID, "status": "reserving"}) == 0
    # user doc has no leftover withdrawal_ops
    doc = mongo.users.find_one({"session_id": SESSION_ID}, {"withdrawal_ops": 1})
    assert not (doc.get("withdrawal_ops") or []), doc.get("withdrawal_ops")

    # withdrawal row has recipient snapshot
    w = mongo.withdrawals.find_one({"session_id": SESSION_ID, "status": "pending", "item.uid": uid}, {"_id": 0})
    assert w and w.get("recipient"), w
    for k in ("roblox_nick", "roblox_display_name", "roblox_link"):
        assert w["recipient"].get(k) == user.get(k), (k, w["recipient"], user)
    withdrawal_id = w["id"]

    # admin list returns recipient + recipient_changed=false
    r = requests.get(f"{BASE_URL}/api/admin/withdrawals", params={"status": "pending"},
                     headers=auth(admin_token), timeout=15)
    assert r.status_code == 200
    row = next(x for x in r.json() if x["id"] == withdrawal_id)
    assert row.get("recipient")
    assert row.get("recipient_changed") is False

    # simulate user changing roblox_link
    mongo.users.update_one({"session_id": SESSION_ID},
                           {"$set": {"roblox_link": "https://www.roblox.com/users/99999999/profile"}})
    try:
        r = requests.get(f"{BASE_URL}/api/admin/withdrawals", params={"status": "pending"},
                         headers=auth(admin_token), timeout=15)
        row = next(x for x in r.json() if x["id"] == withdrawal_id)
        assert row.get("recipient_changed") is True
    finally:
        _restore_user(mongo, orig)
        # cancel to restore skin
        rc = requests.post(f"{BASE_URL}/api/admin/withdrawals/{withdrawal_id}/cancel",
                           json={"reason": "restore after test"}, headers=auth(admin_token), timeout=15)
        assert rc.status_code == 200, rc.text
        # confirm skin is back
        u2 = mongo.users.find_one({"session_id": SESSION_ID}, {"skins": 1})
        assert any(s.get("uid") == uid for s in (u2.get("skins") or [])), "skin should be restored"


# ---------- shop/buy request_id idempotency ----------
def test_shop_buy_idempotent(mongo, user_token):
    tok, _ = user_token
    # find a cheap shop item
    item = mongo.shop_items.find_one({"price": {"$lte": 50}}, {"_id": 0, "id": 1, "price": 1})
    if not item:
        pytest.skip("no cheap shop item")
    u_before = requests.get(f"{BASE_URL}/api/auth/me", headers=auth(tok), timeout=15).json()
    bal_before = float(u_before["balance"])
    price = float(item["price"])
    if bal_before < price:
        # top up via direct Mongo update to avoid touching bank flows
        mongo.users.update_one({"session_id": SESSION_ID}, {"$inc": {"balance": price + 5}})
        bal_before = float(mongo.users.find_one({"session_id": SESSION_ID})["balance"])

    req_id = str(uuid.uuid4())
    body = {"request_id": req_id, "items": [{"id": item["id"], "quantity": 1}], "expected_total": price}
    r1 = requests.post(f"{BASE_URL}/api/shop/buy", json=body, headers=auth(tok), timeout=20)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{BASE_URL}/api/shop/buy", json=body, headers=auth(tok), timeout=20)
    assert r2.status_code == 200, r2.text

    u_after = requests.get(f"{BASE_URL}/api/auth/me", headers=auth(tok), timeout=15).json()
    delta = bal_before - float(u_after["balance"])
    assert abs(delta - price) < 0.01, f"debited {delta} for price {price} (must be once)"

    # inline receipts trimmed to at most 20
    inline = (mongo.users.find_one({"session_id": SESSION_ID}, {"shop_receipts": 1}) or {}).get("shop_receipts") or []
    assert len(inline) <= 20


# ---------- static path traversal ----------
def test_static_path_traversal_rejected():
    # The safe_static_file backend helper (unit-tested in test_review_fixes.py) rejects '../' and
    # symlink escapes. Here we just verify no traversal ever exposes /etc/passwd content over
    # the public URL, whichever process handles /static/*.
    for path in ["/static/../../../../../etc/passwd", "/static/..%2f..%2f..%2fetc%2fpasswd"]:
        r = requests.get(f"{BASE_URL}{path}", timeout=10)
        assert "root:" not in r.text, (path, r.text[:200])


# ---------- JWT revocation via logout — MUST be LAST ----------
def test_zzz_logout_revokes_token(mongo, user_token):
    tok, sv = user_token
    # copy the token — same content, we'll use both after logout
    tok_copy = tok

    r = requests.post(f"{BASE_URL}/api/auth/logout", headers=auth(tok), timeout=15)
    assert r.status_code == 200, r.text

    # session_version was incremented
    doc = mongo.users.find_one({"session_id": SESSION_ID}, {"session_version": 1})
    assert int(doc.get("session_version") or 0) == sv + 1

    # original token now rejected on protected endpoints
    for path, expected in (("/api/auth/me", 401), ("/api/profile", 401), ("/api/chats", 401)):
        r = requests.get(f"{BASE_URL}{path}", headers=auth(tok_copy), timeout=15)
        assert r.status_code == expected, (path, r.status_code, r.text)

    # /api/upgrade requires user token → must be 401 with stale token
    r = requests.post(f"{BASE_URL}/api/upgrade",
                      json={"session_id": SESSION_ID, "target_item": {"id": "nonexistent"},
                            "bet_amount": 1.0, "bet_items": []},
                      headers=auth(tok_copy), timeout=15)
    assert r.status_code == 401, r.text

    # regenerate token with new sv for next runs (so token.txt-based flows continue to work)
    new_tok = _sign(sv + 1)
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth(new_tok), timeout=15)
    assert r.status_code == 200
    # persist for the frontend automation
    with open("/root/logs/token.txt", "w") as fh:
        fh.write(new_tok)
