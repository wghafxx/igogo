"""Post-reset verification: clean bank state, bank-0 deny reason, win path possible with bank headroom, final reset."""
import os
import subprocess
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
frontend_env = dotenv_values("/app/frontend/.env")
base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base.rstrip("/") + "/api"

SEED = ["0u1o0gyxz", "bg7gw7mnt", "zm7pcp8ip", "5hccvev8s", "7i59vojax", "q8bheol0k", "di8ihi1wr", "g5bkbe61g", "kiulp6xqy", "5mdyfh6hp"]
SID = "TEST_reset_player_1"

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

state = {}


def admin_headers():
    s = requests.Session()
    s.headers.update({"User-Agent": "pytest-post-reset"})
    r = s.post(f"{BASE_URL}/admin/login", json={"phrases": SEED})
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def player_session():
    tok = jwt.encode(
        {"sub": SID, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        os.environ["JWT_SECRET"], algorithm="HS256",
    )
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


class TestPostReset:
    # --- 1. clean state verification (must run before any test data is created) ---
    def test_01_clean_state(self):
        a = admin_headers()
        state["admin"] = a
        r = a.get(f"{BASE_URL}/admin/bank")
        assert r.status_code == 200, r.text
        d = r.json()
        print("BANK STATE:", d)
        assert d["bank"] == 0, f"bank not 0: {d['bank']}"
        assert d["liabilities"]["total"] == 0, d["liabilities"]
        assert d["games"]["total"] == 0, d["games"]
        assert d["games"]["wins"] == 0
        assert d["rtp"]["wagered"] == 0 and d["rtp"]["paid"] == 0
        assert d.get("ledger") in (None, []) or len(d["ledger"]) == 0, d.get("ledger")
        # live preview traffic can auto-create zero-balance guest users; they must carry no liability
        for u in db.users.find({}, {"_id": 0, "session_id": 1, "balance": 1, "skins": 1}):
            assert float(u.get("balance") or 0) == 0, u
            assert not u.get("skins"), u
        assert db.upgrades.count_documents({}) == 0
        assert db.luck_cycles.count_documents({}) == 0

    # --- 2. edge: bank 0 + player balance => payout denied with reason 'bank' (by design) ---
    def test_02_bank_zero_denies_payout(self):
        a = state["admin"]
        shop = a.get(f"{BASE_URL}/shop", params={"sort": "price_asc", "limit": 200}).json()["items"]
        target = min((s for s in shop if 80 <= s["price"] <= 110), key=lambda s: s["price"])
        state["target"] = target
        print("TARGET:", target["id"], target["price"])
        db.users.update_one({"session_id": SID}, {"$set": {
            "session_id": SID, "balance": 500.0, "nickname": "TEST_Player", "skins": [], "discord_id": "9999",
            "created_at": datetime.now(timezone.utc),
        }}, upsert=True)
        p = player_session()
        state["player"] = p
        forced_bank = 0
        for _ in range(6):
            r = p.post(f"{BASE_URL}/upgrade", json={"session_id": SID, "bet_amount": 50, "target_item": {"id": target["id"]}})
            assert r.status_code == 200, r.text
            assert r.json()["win"] is False, "won with bank=0 — insolvency risk"
        stats = state["admin"].get(f"{BASE_URL}/admin/bank").json()["games"]
        print("GAMES after bank=0 rounds:", stats)
        forced_bank = stats["forced_by"].get("bank", 0)
        assert forced_bank > 0, f"expected forced_by bank>0, got {stats['forced_by']}"

    # --- 3. win path possible once bank has headroom ---
    def test_03_wins_happen_with_bank_headroom(self):
        a = state["admin"]
        r = a.post(f"{BASE_URL}/admin/bank/adjust", json={"amount": 5000, "note": "TEST_seed_bank"})
        assert r.status_code == 200, r.text
        assert r.json()["bank"] >= 5000
        db.users.update_one({"session_id": SID}, {"$set": {"balance": 500.0}})
        p = state["player"]
        target = state["target"]
        wins = 0
        games = 0
        for i in range(40):
            bal = p.get(f"{BASE_URL}/auth/me").json()["balance"]
            if bal < 50:
                db.users.update_one({"session_id": SID}, {"$set": {"balance": 500.0}})
            r = p.post(f"{BASE_URL}/upgrade", json={"session_id": SID, "bet_amount": 50, "target_item": {"id": target["id"]}})
            assert r.status_code == 200, r.text
            games += 1
            wins += int(r.json()["win"])
        bank = a.get(f"{BASE_URL}/admin/bank").json()
        print(f"games={games} wins={wins}")
        print("BANK:", {k: bank[k] for k in ("bank", "liabilities", "rtp", "games", "net") if k in bank})
        assert wins > 0, f"NO WINS in {games} games with bank headroom; forced_by={bank['games']['forced_by']}"

    # --- 4. mandatory cleanup + verification ---
    def test_04_cleanup_and_verify(self):
        out = subprocess.run(["python3", "/app/backend/tests/reset_all.py"], capture_output=True, text=True, timeout=120)
        print(out.stdout, out.stderr)
        assert out.returncode == 0, out.stderr
        a = admin_headers()  # admin_sessions wiped -> login again
        d = a.get(f"{BASE_URL}/admin/bank").json()
        print("BANK AFTER CLEANUP:", d)
        assert d["bank"] == 0
        assert d["liabilities"]["total"] == 0
        assert d["games"]["total"] == 0
        assert db.users.count_documents({"balance": {"$gt": 0}}) == 0
        assert db.upgrades.count_documents({}) == 0
        assert db.shop_items.count_documents({}) > 0, "shop items must be kept"
