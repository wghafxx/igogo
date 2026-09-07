"""Iteration 5: security hardening, atomic debit/sell, deposits + admin panel, roblox profile."""
import os
import sys
import time
import uuid
import asyncio
import hashlib
import concurrent.futures as cf

import pytest
import requests
from dotenv import dotenv_values

sys.path.insert(0, "/app/backend")

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = backend_env.get("MONGO_URL") or os.environ["MONGO_URL"]
DB_NAME = backend_env.get("DB_NAME") or os.environ["DB_NAME"]

TEST_SID = "discord_test_1"
OTHER_SID = "discord_test_2"
REAL_SID = "discord_1047876193824808992"
ADMIN_PHRASE = "0u1o0gyxz"


def make_jwt(sid, role="user"):
    from server import make_token
    return make_token(sid, role=role) if role == "user" else make_token(sid, role=role, hours=12)


@pytest.fixture(scope="session")
def tok_a():
    return make_jwt(TEST_SID)


DEP_SID = "discord_test_dep"
WD_SID = "discord_test_wd"


@pytest.fixture(scope="session")
def tok_dep():
    return make_jwt(DEP_SID)


@pytest.fixture(scope="session")
def tok_wd():
    return make_jwt(WD_SID)


@pytest.fixture(scope="session")
def tok_b():
    return make_jwt(OTHER_SID)


@pytest.fixture(scope="session")
def mongo():
    from pymongo import MongoClient
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/admin/login", json={"phrase": ADMIN_PHRASE}, timeout=20)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code} {r.text[:300]}")
    return r.json()["token"]


def h(t):
    return {"Authorization": f"Bearer {t}"}


def ensure_user(sid, token, mongo, balance=None, skins=None):
    requests.get(f"{API}/user/{sid}", headers=h(token), timeout=20)
    upd = {}
    if balance is not None:
        upd["balance"] = float(balance)
    if skins is not None:
        upd["skins"] = skins
    if upd:
        mongo.users.update_one({"session_id": sid}, {"$set": upd})


# ---------------- Security: /api/user/{session_id} ----------------
class TestUserEndpointSecurity:
    def test_discord_user_without_token_401(self):
        r = requests.get(f"{API}/user/{REAL_SID}", timeout=20)
        assert r.status_code == 401, r.text[:300]

    def test_discord_user_with_other_token_401(self, tok_a):
        r = requests.get(f"{API}/user/{REAL_SID}", headers=h(tok_a), timeout=20)
        assert r.status_code == 401, r.text[:300]

    def test_discord_user_with_own_token_200(self, tok_a):
        r = requests.get(f"{API}/user/{TEST_SID}", headers=h(tok_a), timeout=20)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["session_id"] == TEST_SID

    def test_guest_session_allowed(self):
        r = requests.get(f"{API}/user/anon-{uuid.uuid4().hex[:8]}", timeout=20)
        assert r.status_code == 200
        assert r.json()["balance"] == 0

    def test_admin_token_not_valid_on_auth_me(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=h(admin_token), timeout=20)
        assert r.status_code == 401, r.text[:300]

    def test_user_token_not_valid_on_admin_route(self, tok_a):
        r = requests.get(f"{API}/admin/deposits", headers=h(tok_a), timeout=20)
        assert r.status_code == 403, r.text[:300]

    def test_source_archive_removed(self):
        r = requests.get(f"{API}/source/archive", timeout=20)
        assert r.status_code == 404


# ---------------- Security: /api/upgrade ----------------
class TestUpgradeSecurity:
    def test_upgrade_without_token_401(self):
        r = requests.post(f"{API}/upgrade", json={
            "session_id": TEST_SID, "bet_amount": 1, "bet_items": [],
            "target_item": {"id": "case-glove-case"}, "chance": 0.02}, timeout=20)
        assert r.status_code == 401

    def test_upgrade_cross_user_token_401(self, tok_b):
        r = requests.post(f"{API}/upgrade", headers=h(tok_b), json={
            "session_id": TEST_SID, "bet_amount": 1, "bet_items": [],
            "target_item": {"id": "case-glove-case"}, "chance": 0.02}, timeout=20)
        assert r.status_code == 401


# ---------------- Atomic debit / sell ----------------
class TestAtomicity:
    def test_no_double_spend_concurrent_upgrades(self, tok_a, mongo):
        ensure_user(TEST_SID, tok_a, mongo, balance=100)
        payload = {"session_id": TEST_SID, "bet_amount": 30, "bet_items": [],
                   "target_item": {"id": "case-glove-case"}, "chance": 0.6979}

        def fire(_):
            return requests.post(f"{API}/upgrade", headers=h(tok_a), json=payload, timeout=40)

        with cf.ThreadPoolExecutor(max_workers=5) as ex:
            results = list(ex.map(fire, range(5)))
        codes = [r.status_code for r in results]
        successes = sum(1 for c in codes if c == 200)
        print("upgrade concurrency codes:", codes)
        assert successes <= 3, f"double spend: {successes} successes on balance 100/bet 30"
        user = mongo.users.find_one({"session_id": TEST_SID})
        bal = float(user["balance"])
        assert bal >= 0, f"negative balance {bal}"
        # winnings are skins, not balance, so balance is deterministic
        assert abs(bal - (100 - 30 * successes)) < 0.01, f"balance {bal} vs expected {100 - 30*successes}"

    def test_concurrent_sell_credits_once(self, tok_a, mongo):
        uid = f"TEST_{uuid.uuid4().hex[:8]}"
        skin = {"uid": uid, "id": "case-glove-case", "name": "Glove Case", "type": "Case",
                "price": 43.0, "rarity": "red", "image": "https://x/y.png"}
        ensure_user(TEST_SID, tok_a, mongo, balance=0, skins=[skin])
        before = float(mongo.users.find_one({"session_id": TEST_SID})["balance"])

        def fire(_):
            return requests.post(f"{API}/skins/sell", headers=h(tok_a), json={"uids": [uid]}, timeout=40)

        with cf.ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(fire, range(3)))
        print("sell concurrency codes:", [r.status_code for r in results])
        after = float(mongo.users.find_one({"session_id": TEST_SID})["balance"])
        assert abs((after - before) - 43.0) < 0.01, f"credited {after - before} instead of 43"
        assert not [s for s in mongo.users.find_one({"session_id": TEST_SID}).get("skins", []) if s.get("uid") == uid]


# ---------------- Roblox profile ----------------
class TestRobloxProfile:
    def test_save_and_read_back(self, tok_a, mongo):
        ensure_user(TEST_SID, tok_a, mongo)
        r = requests.post(f"{API}/profile/roblox", headers=h(tok_a), json={
            "roblox_nick": "TestBuilder", "roblox_link": "https://www.roblox.com/share?code=abc"}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["roblox_nick"] == "TestBuilder"
        assert d["roblox_link"] == "https://www.roblox.com/share?code=abc"
        me = requests.get(f"{API}/auth/me", headers=h(tok_a), timeout=20).json()
        assert me["roblox_nick"] == "TestBuilder"
        assert me["roblox_link"] == "https://www.roblox.com/share?code=abc"

    def test_bad_link_400(self, tok_a):
        r = requests.post(f"{API}/profile/roblox", headers=h(tok_a), json={
            "roblox_nick": "TestBuilder", "roblox_link": "https://evil.com/share?code=abc"}, timeout=20)
        assert r.status_code == 400, r.text[:300]

    def test_roblox_requires_auth(self):
        r = requests.post(f"{API}/profile/roblox", json={
            "roblox_nick": "TestBuilder", "roblox_link": "https://www.roblox.com/x"}, timeout=20)
        assert r.status_code == 401


# ---------------- Deposits + admin ----------------
class TestDeposits:
    def test_deposit_requires_auth(self):
        r = requests.post(f"{API}/deposits", json={"description": "TEST_sent trade"}, timeout=20)
        assert r.status_code == 401
        assert requests.get(f"{API}/deposits/my", timeout=20).status_code == 401

    def test_create_list_and_pending_limit(self, tok_dep, mongo):
        ensure_user(DEP_SID, tok_dep, mongo)
        mongo.deposits.delete_many({"session_id": DEP_SID})
        ids = []
        for i in range(5):
            r = requests.post(f"{API}/deposits", headers=h(tok_dep), json={"description": f"TEST_dep_{i}"}, timeout=20)
            assert r.status_code == 200, r.text[:300]
            d = r.json()
            assert d["status"] == "pending" and d["amount"] is None
            assert "_id" not in d
            ids.append(d["id"])
        r6 = requests.post(f"{API}/deposits", headers=h(tok_dep), json={"description": "TEST_dep_6"}, timeout=20)
        assert r6.status_code == 400, f"6th pending should be 400, got {r6.status_code}"
        mine = requests.get(f"{API}/deposits/my", headers=h(tok_dep), timeout=20).json()
        assert set(ids).issubset({d["id"] for d in mine})

    def test_admin_login_wrong_phrase_403(self):
        r = requests.post(f"{API}/admin/login", json={"phrase": "wrong-phrase-xyz"},
                          headers={"X-Forwarded-For": "9.9.9.9"}, timeout=20)
        assert r.status_code == 403, r.text[:300]

    def test_admin_deposits_pending_sorted_oldest_first(self, admin_token):
        r = requests.get(f"{API}/admin/deposits?status=pending", headers=h(admin_token), timeout=20)
        assert r.status_code == 200, r.text[:300]
        docs = r.json()
        created = [d["created_at"] for d in docs]
        assert created == sorted(created), "pending deposits not oldest-first"
        assert all("_id" not in d for d in docs)

    def test_confirm_credits_balance_with_promo(self, tok_dep, admin_token, mongo):
        ensure_user(DEP_SID, tok_dep, mongo)
        assert requests.post(f"{API}/promo/apply", headers=h(tok_dep), json={"code": "SINZUKU"}, timeout=20).json()["promo_bonus"] == 0.10
        mongo.deposits.delete_many({"session_id": DEP_SID})
        dep = requests.post(f"{API}/deposits", headers=h(tok_dep), json={"description": "TEST_confirm"}, timeout=20).json()
        assert dep["promo_bonus"] == 0.10
        bal_before = requests.get(f"{API}/auth/me", headers=h(tok_dep), timeout=20).json()["balance"]
        c = requests.post(f"{API}/admin/deposits/{dep['id']}/confirm", headers=h(admin_token), json={"amount": 80}, timeout=20)
        assert c.status_code == 200, c.text[:300]
        assert c.json()["credited"] == 88.0
        bal_after = requests.get(f"{API}/auth/me", headers=h(tok_dep), timeout=20).json()["balance"]
        assert abs(bal_after - bal_before - 88.0) < 0.01, f"credited {bal_after - bal_before}"
        again = requests.post(f"{API}/admin/deposits/{dep['id']}/confirm", headers=h(admin_token), json={"amount": 80}, timeout=20)
        assert again.status_code == 404, f"double confirm allowed: {again.status_code}"
        conf = requests.get(f"{API}/admin/deposits?status=confirmed", headers=h(admin_token), timeout=20).json()
        row = next((d for d in conf if d["id"] == dep["id"]), None)
        assert row and row["amount"] == 80 and row["credited"] == 88.0

    def test_reject_flow(self, tok_dep, admin_token, mongo):
        ensure_user(DEP_SID, tok_dep, mongo)
        mongo.deposits.delete_many({"session_id": DEP_SID})
        dep = requests.post(f"{API}/deposits", headers=h(tok_dep), json={"description": "TEST_reject"}, timeout=20).json()
        bal_before = requests.get(f"{API}/auth/me", headers=h(tok_dep), timeout=20).json()["balance"]
        r = requests.post(f"{API}/admin/deposits/{dep['id']}/reject", headers=h(admin_token), timeout=20)
        assert r.status_code == 200, r.text[:300]
        assert requests.post(f"{API}/admin/deposits/{dep['id']}/reject", headers=h(admin_token), timeout=20).status_code == 404
        bal_after = requests.get(f"{API}/auth/me", headers=h(tok_dep), timeout=20).json()["balance"]
        assert abs(bal_after - bal_before) < 0.01, "reject must not credit balance"
        rej = requests.get(f"{API}/admin/deposits?status=rejected", headers=h(admin_token), timeout=20).json()
        assert any(d["id"] == dep["id"] for d in rej)

    def test_invalid_status_filter_400(self, admin_token):
        assert requests.get(f"{API}/admin/deposits?status=bogus", headers=h(admin_token), timeout=20).status_code == 400

    def test_confirm_amount_validation(self, admin_token, tok_dep, mongo):
        mongo.deposits.delete_many({"session_id": DEP_SID, "description": "TEST_neg"})
        dep = requests.post(f"{API}/deposits", headers=h(tok_dep), json={"description": "TEST_neg"}, timeout=20).json()
        r = requests.post(f"{API}/admin/deposits/{dep['id']}/confirm", headers=h(admin_token), json={"amount": -5}, timeout=20)
        assert r.status_code == 422, r.status_code
        requests.post(f"{API}/admin/deposits/{dep['id']}/reject", headers=h(admin_token), timeout=20)


# ---------------- Withdrawals admin flow ----------------
class TestWithdrawals:
    def test_withdraw_then_admin_done(self, tok_wd, admin_token, mongo):
        uid = f"TEST_{uuid.uuid4().hex[:8]}"
        skin = {"uid": uid, "id": "case-glove-case", "name": "Glove Case", "type": "Case",
                "price": 43.0, "rarity": "red", "image": "https://x/y.png"}
        ensure_user(WD_SID, tok_wd, mongo, skins=[skin])
        w = requests.post(f"{API}/skins/withdraw", headers=h(tok_wd), json={"uids": [uid]}, timeout=20)
        assert w.status_code == 200, w.text[:300]
        assert all(s.get("uid") != uid for s in w.json()["skins"])
        pend = requests.get(f"{API}/admin/withdrawals?status=pending", headers=h(admin_token), timeout=20)
        assert pend.status_code == 200
        row = next((d for d in pend.json() if d["item"].get("uid") == uid), None)
        assert row is not None, "withdrawal not listed for admin"
        assert row.get("user") and row["user"]["session_id"] == WD_SID
        d = requests.post(f"{API}/admin/withdrawals/{row['id']}/done", headers=h(admin_token), timeout=20)
        assert d.status_code == 200, d.text[:300]
        assert requests.post(f"{API}/admin/withdrawals/{row['id']}/done", headers=h(admin_token), timeout=20).status_code == 404
        done = requests.get(f"{API}/admin/withdrawals?status=done", headers=h(admin_token), timeout=20).json()
        assert any(x["id"] == row["id"] for x in done)

    def test_withdraw_requires_auth(self):
        assert requests.post(f"{API}/skins/withdraw", json={"uids": ["x"]}, timeout=20).status_code == 401
        assert requests.get(f"{API}/admin/withdrawals", timeout=20).status_code == 403


# ---------------- Regression basics ----------------
class TestRegression:
    def test_shop_has_8_red_items(self):
        r = requests.get(f"{API}/shop", timeout=20)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 8, len(items)
        assert all(i["rarity"] == "red" for i in items)
        assert all("_id" not in i for i in items)

    def test_stats_and_rarities(self):
        s = requests.get(f"{API}/stats", timeout=20)
        assert s.status_code == 200 and "online" in s.json()
        assert len(requests.get(f"{API}/rarities", timeout=20).json()) == 8

    def test_deposit_info(self):
        d = requests.get(f"{API}/deposit/info", timeout=20).json()
        assert d["min_rap"] == 20 and d["fee"] == 0.20 and "roblox.com" in d["friend_url"]

    def test_live_drops(self):
        r = requests.get(f"{API}/live-drops?limit=5", timeout=20)
        assert r.status_code == 200 and isinstance(r.json(), list)


# ---------------- Rate limit (LAST, fake IP) ----------------
class TestZZRateLimit:
    def test_admin_login_rate_limit(self):
        ip = f"1.2.3.{int(time.time()) % 200 + 20}"
        codes = []
        for _ in range(6):
            r = requests.post(f"{API}/admin/login", json={"phrase": "nope-nope"},
                              headers={"X-Forwarded-For": ip}, timeout=20)
            codes.append(r.status_code)
        print("rate limit codes:", codes)
        assert codes[:5] == [403] * 5, codes
        assert codes[5] == 429, codes
