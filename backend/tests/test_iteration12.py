"""Iteration 12: fair fixed-house-edge model (RTP 0.90), honest roll, solvency-only guard."""
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
FE = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or FE.get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"
JWT_SECRET = os.environ["JWT_SECRET"]

ADMIN_PHRASES = ["0u1o0gyxz", "bg7gw7mnt", "zm7pcp8ip", "5hccvev8s", "7i59vojax",
                 "q8bheol0k", "di8ihi1wr", "g5bkbe61g", "kiulp6xqy", "5mdyfh6hp"]

QA_MAIN = "qa_fair_main"
QA_SOLV = "qa_solvency"
QA_SIDS = [QA_MAIN, QA_SOLV]


@pytest.fixture(scope="session")
def mdb():
    client = MongoClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


def token_for(sid):
    return jwt.encode({"sub": sid, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                      JWT_SECRET, algorithm="HS256")


def mk_user(mdb, sid, balance):
    mdb.users.update_one({"session_id": sid}, {"$set": {
        "session_id": sid, "nickname": "QA " + sid, "balance": float(balance), "skins": [],
        "discord_id": "qa" + sid, "avatar": None,
    }}, upsert=True)


def client_for(sid):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token_for(sid)}"})
    return s


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "User-Agent": "qa-tester/1.0"})
    r = s.post(f"{BASE_URL}/admin/login", json={"phrases": ADMIN_PHRASES})
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="session", autouse=True)
def cleanup(mdb):
    yield
    for coll in ["users", "upgrades", "drops", "presence", "item_history", "luck_cycles"]:
        mdb[coll].delete_many({"session_id": {"$in": QA_SIDS}})
    print("cleanup done for", QA_SIDS)


# ---------- game config ----------
class TestGameConfig:
    def test_game_config(self):
        r = requests.get(f"{BASE_URL}/game-config")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["rtp"] == 0.9, d
        assert d["min_chance"] == 0.01
        assert d["max_chance"] == 0.75
        assert abs(d["max_bet_ratio"] - 0.8333) < 0.001, d


# ---------- upgrade validation ----------
class TestUpgradeValidation:
    def test_chance_formula(self, mdb):
        mk_user(mdb, QA_MAIN, 6000)
        c = client_for(QA_MAIN)
        r = c.post(f"{BASE_URL}/upgrade", json={
            "session_id": QA_MAIN, "bet_amount": 44, "bet_items": [],
            "target_item": {"id": "case-1"}, "chance": 0.99,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert abs(d["chance"] - 0.45) < 1e-6, d
        assert isinstance(d["win"], bool)
        mdb.users.update_one({"session_id": QA_MAIN}, {"$set": {"skins": []}})

    def test_bet_above_max_ratio(self, mdb):
        mk_user(mdb, QA_MAIN, 6000)
        c = client_for(QA_MAIN)
        r = c.post(f"{BASE_URL}/upgrade", json={
            "session_id": QA_MAIN, "bet_amount": 80, "bet_items": [],
            "target_item": {"id": "case-1"}, "chance": 0.5,
        })
        assert r.status_code == 400, r.text
        assert "не может превышать" in r.json()["detail"], r.json()
        assert "83" in r.json()["detail"]

    def test_chance_below_min(self, mdb):
        mk_user(mdb, QA_MAIN, 6000)
        c = client_for(QA_MAIN)
        # bet 10 on 1580 -> chance 0.0057 < 1%
        r = c.post(f"{BASE_URL}/upgrade", json={
            "session_id": QA_MAIN, "bet_amount": 10, "bet_items": [],
            "target_item": {"id": "m4a1s-anodized-red"}, "chance": 0.01,
        })
        assert r.status_code == 400, r.text
        assert "1%" in r.json()["detail"], r.json()


# ---------- statistical fairness ----------
class TestFairness:
    def test_300_spins(self, mdb):
        mk_user(mdb, QA_MAIN, 20000)
        mdb.upgrades.delete_many({"session_id": QA_MAIN})
        c = client_for(QA_MAIN)
        n, wins, errors = 300, 0, []
        for i in range(n):
            r = c.post(f"{BASE_URL}/upgrade", json={
                "session_id": QA_MAIN, "bet_amount": 44, "bet_items": [],
                "target_item": {"id": "case-1"}, "chance": 0.45,
            })
            if r.status_code != 200:
                errors.append((r.status_code, r.text[:150]))
                mdb.users.update_one({"session_id": QA_MAIN}, {"$set": {"balance": 20000.0, "skins": []}})
                continue
            d = r.json()
            assert abs(d["chance"] - 0.45) < 1e-6
            if d["win"]:
                wins += 1
                mdb.users.update_one({"session_id": QA_MAIN}, {"$set": {"skins": []}})
            if d["balance"] < 500:
                mdb.users.update_one({"session_id": QA_MAIN}, {"$set": {"balance": 20000.0}})
        rate = wins / n
        forced = mdb.upgrades.count_documents({"session_id": QA_MAIN, "forced_loss": True})
        docs = list(mdb.upgrades.find({"session_id": QA_MAIN}, {"_id": 0, "protection": 1}).limit(5))
        print(f"win rate {rate:.3f} wins={wins}/{n} forced={forced} errors={len(errors)} {errors[:3]}")
        print("protection sample:", docs[0]["protection"] if docs else None)
        assert not errors, errors[:3]
        assert forced == 0, f"{forced} forced losses recorded"
        for doc in docs:
            p = doc["protection"]
            assert "player" not in p, p
            assert set(["rtp", "bank", "liabilities"]).issubset(p.keys()), p
            assert p["rtp"] == 0.9
        assert 0.38 <= rate <= 0.52, f"win rate {rate} outside fair band"


# ---------- solvency refusal ----------
class TestSolvency:
    def test_solvency_refusal_and_cheap_ok(self, mdb, admin):
        r = admin.get(f"{BASE_URL}/admin/bank")
        assert r.status_code == 200, r.text
        bank = r.json()
        headroom = bank["bank"] - bank["liabilities"]["total"]
        print("bank", bank["bank"], "liab", bank["liabilities"]["total"], "headroom", headroom)
        # inflate liabilities so that residual headroom ~200: headroom+700 < 1580 but > case-1 (88)
        balance = headroom - 200
        assert balance > 700, f"not enough headroom to run solvency test: {headroom}"
        mk_user(mdb, QA_SOLV, balance)
        c = client_for(QA_SOLV)
        try:
            r = c.post(f"{BASE_URL}/upgrade", json={
                "session_id": QA_SOLV, "bet_amount": 700, "bet_items": [],
                "target_item": {"id": "m4a1s-anodized-red"}, "chance": 0.4,
            })
            assert r.status_code == 400, f"expected refusal, got {r.status_code} {r.text[:200]}"
            assert "недоступен для апгрейда" in r.json()["detail"], r.json()
            after = mdb.users.find_one({"session_id": QA_SOLV})
            assert abs(after["balance"] - balance) < 1e-6, f"balance debited: {after['balance']} vs {balance}"
            # cheap target still playable
            r2 = c.post(f"{BASE_URL}/upgrade", json={
                "session_id": QA_SOLV, "bet_amount": 44, "bet_items": [],
                "target_item": {"id": "case-1"}, "chance": 0.45,
            })
            assert r2.status_code == 200, f"cheap upgrade refused: {r2.status_code} {r2.text[:200]}"
            assert abs(r2.json()["chance"] - 0.45) < 1e-6
        finally:
            mdb.users.delete_one({"session_id": QA_SOLV})
            mdb.upgrades.delete_many({"session_id": QA_SOLV})
            mdb.drops.delete_many({"session_id": QA_SOLV})
            mdb.item_history.delete_many({"session_id": QA_SOLV})


# ---------- admin ----------
class TestAdmin:
    def test_bank_settings_only_rtp(self, admin):
        r = admin.get(f"{BASE_URL}/admin/bank")
        assert r.status_code == 200, r.text
        st = r.json()["settings"]
        assert "rtp_target" in st, st
        for legacy in ["drain_chance", "max_multiplier", "min_multiplier", "luck_cycle"]:
            assert legacy not in st, st
        # only rtp_target is a tunable knob (updated_at is metadata written by the PUT)
        assert set(st.keys()) <= {"rtp_target", "updated_at"}, st

    def test_put_rtp_and_config_reflects(self, admin):
        try:
            r = admin.put(f"{BASE_URL}/admin/bank/settings", json={"rtp_target": 0.85})
            assert r.status_code == 200, r.text
            assert r.json()["rtp_target"] == 0.85
            cfg = requests.get(f"{BASE_URL}/game-config").json()
            assert cfg["rtp"] == 0.85, cfg
            assert abs(cfg["max_bet_ratio"] - 0.75 / 0.85) < 1e-6, cfg
        finally:
            rr = admin.put(f"{BASE_URL}/admin/bank/settings", json={"rtp_target": 0.9})
            assert rr.status_code == 200 and rr.json()["rtp_target"] == 0.9
            assert requests.get(f"{BASE_URL}/game-config").json()["rtp"] == 0.9

    def test_players_no_cycle(self, admin):
        r = admin.get(f"{BASE_URL}/admin/players")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        for row in rows[:20]:
            assert "cycle" not in row, row
            assert "_id" not in row


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
