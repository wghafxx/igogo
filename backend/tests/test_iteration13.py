"""Iteration 13: pointer/zone consistency, forced-loss on bank insolvency, RTP guards, bank adjust guard.

Live site — all test users are prefixed qa_ and removed in teardown. No successful bank adjust.
"""
import os
import random
import string
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE_URL}/api"
UA = "qa-iteration13/1.0"

_mc = MongoClient(os.environ["MONGO_URL"])
db = _mc[os.environ["DB_NAME"]]

CLEARANCE = 1.4  # assert margin (server uses 1.5)


def _sid(tag):
    return "qa_" + tag + "_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def mint(sid):
    return jwt.encode({"sub": sid, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                      os.environ["JWT_SECRET"], algorithm="HS256")


def make_user(sid, balance):
    db.users.insert_one({
        "session_id": sid, "nickname": "QA " + sid[-6:], "balance": float(balance), "skins": [],
        "discord_id": "qa" + sid[-6:], "created_at": datetime.now(timezone.utc),
    })
    return mint(sid)


def purge(sid):
    for col in ("users", "upgrades", "drops", "presence", "item_history"):
        db[col].delete_many({"session_id": sid})


def client(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


def spin(sess, sid, item_id, bet):
    return sess.post(f"{API}/upgrade", json={
        "session_id": sid, "bet_amount": bet, "bet_items": [],
        "target_item": {"id": item_id},
    }, timeout=30)


def check_clearance(data):
    """Returns None if ok, else violation description."""
    half = data["chance"] * 180
    a = abs(data["angle"])
    if data["win"] and a > half - CLEARANCE:
        return f"WIN angle {a:.3f} > half-{CLEARANCE} ({half - CLEARANCE:.3f}) chance={data['chance']}"
    if not data["win"] and a < half + CLEARANCE:
        return f"LOSS angle {a:.3f} < half+{CLEARANCE} ({half + CLEARANCE:.3f}) chance={data['chance']}"
    return None


# ---------- game config ----------
class TestGameConfig:
    def test_game_config_defaults(self):
        r = requests.get(f"{API}/game-config", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["rtp"] == pytest.approx(0.9)
        assert d["max_bet_ratio"] == pytest.approx(0.75 / 0.9, abs=1e-4)
        assert d["min_chance"] == pytest.approx(0.01)
        assert d["max_chance"] == pytest.approx(0.75)


# ---------- MAIN BUG: pointer / zone consistency ----------
class TestPointerConsistency:
    @pytest.fixture(scope="class")
    def user(self):
        sid = _sid("ptr")
        token = make_user(sid, 4000)
        yield sid, token
        purge(sid)

    def test_200_spins_low_chance(self, user):
        sid, token = user
        sess = client(token)
        viol, wins, statuses = [], 0, set()
        for i in range(200):
            r = spin(sess, sid, "case-chrysalis", 5)
            statuses.add(r.status_code)
            if r.status_code != 200:
                pytest.fail(f"spin {i} -> {r.status_code} {r.text[:300]}")
            d = r.json()
            assert d["chance"] == pytest.approx(5 / 44 * 0.9, abs=1e-6)
            wins += 1 if d["win"] else 0
            v = check_clearance(d)
            if v:
                viol.append((i, v, d))
        print(f"low-chance 200 spins: wins={wins}, statuses={statuses}, violations={len(viol)}")
        assert not viol, viol[:5]

    def test_60_spins_high_chance(self, user):
        sid, token = user
        sess = client(token)
        viol, wins = [], 0
        for i in range(60):
            r = spin(sess, sid, "case-1", 30)
            if r.status_code != 200:
                pytest.fail(f"spin {i} -> {r.status_code} {r.text[:300]}")
            d = r.json()
            assert d["chance"] == pytest.approx(30 / 88 * 0.9, abs=1e-6)
            wins += 1 if d["win"] else 0
            v = check_clearance(d)
            if v:
                viol.append((i, v, d))
        print(f"high-chance 60 spins: chance~{30/88*0.9:.4f} wins={wins} violations={len(viol)}")
        assert not viol, viol[:5]

    def test_balance_debited_and_persisted(self, user):
        sid, token = user
        sess = client(token)
        before = float(db.users.find_one({"session_id": sid})["balance"])
        r = spin(sess, sid, "case-chrysalis", 5)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["balance"] == pytest.approx(before - 5, abs=1e-6)
        assert float(db.users.find_one({"session_id": sid})["balance"]) == pytest.approx(d["balance"], abs=1e-6)
        doc = db.upgrades.find_one({"id": d["id"]})
        assert doc is not None and doc["win"] == d["win"] and doc["chance"] == pytest.approx(d["chance"])


# ---------- Forced loss when the bank cannot pay ----------
class TestForcedLossBank:
    def test_insolvent_bank_forces_loss(self):
        r = requests.get(f"{API}/game-config", timeout=20)
        assert r.status_code == 200
        # measure headroom via admin bank endpoint
        admin = admin_client()
        b = admin.get(f"{API}/admin/bank", timeout=30)
        assert b.status_code == 200, b.text
        bank_info = b.json()
        bank = float(bank_info["bank"])
        liab = float(bank_info["liabilities"]["total"])
        headroom = bank - liab
        target_price = 1580.0
        spins = 6
        # every losing spin debits 700 (liabilities shrink -> headroom grows), so start deep enough
        # to keep headroom + 700 < target_price for all `spins` iterations.
        target_headroom = -2700.0
        balance = headroom - target_headroom
        sid = _sid("bank")
        token = make_user(sid, balance)
        try:
            b2 = admin.get(f"{API}/admin/bank", timeout=30).json()
            new_headroom = float(b2["bank"]) - float(b2["liabilities"]["total"])
            print(f"bank={bank} liab={liab} headroom_before={headroom:.2f} qa_balance={balance:.2f} headroom_now={new_headroom:.2f}")
            assert new_headroom < target_price, "could not create insolvent-for-prize state"
            sess = client(token)
            wins, honest_wins, forced_bank = 0, 0, 0
            for i in range(spins):
                r = spin(sess, sid, "m4a1s-anodized-red", 700)
                assert r.status_code == 200, r.text
                d = r.json()
                assert d["win"] is False, f"paid out with insufficient bank: {d}"
                wins += 1 if d["win"] else 0
                doc = db.upgrades.find_one({"id": d["id"]}, {"_id": 0})
                if doc.get("forced_loss"):
                    honest_wins += 1
                    assert doc.get("forced_reason") == "bank", doc
                    assert doc["protection"].get("bank_can_pay") is False, doc["protection"]
                    forced_bank += 1
                v = check_clearance(d)
                assert v is None, v
            bal = float(db.users.find_one({"session_id": sid})["balance"])
            assert bal == pytest.approx(balance - spins * 700, abs=1e-6), f"bet not debited: {bal}"
            print(f"forced-loss test: spins={spins} wins={wins} honest_wins_forced={forced_bank}")
            assert forced_bank > 0, "no honest win occurred in the window -> inconclusive, re-run"
        finally:
            purge(sid)


# ---------- Admin: RTP setting range + bank adjust guard ----------
def admin_client():
    s = client()
    creds = open("/app/memory/test_credentials.md", encoding="utf-8").read()
    phrases = None
    for line in creds.splitlines():
        parts = line.strip().split()
        if len(parts) == 10 and all(len(p) == 9 and p.isalnum() for p in parts):
            phrases = parts
            break
    assert phrases, "admin seed phrases not found in /app/memory/test_credentials.md"
    r = s.post(f"{API}/admin/login", json={"phrases": phrases}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


class TestAdminGuards:
    @pytest.fixture(scope="class")
    def admin(self):
        s = admin_client()
        yield s
        s.put(f"{API}/admin/bank/settings", json={"rtp_target": 0.9}, timeout=30)

    def test_rtp_below_min_rejected(self, admin):
        r = admin.put(f"{API}/admin/bank/settings", json={"rtp_target": 0.5}, timeout=30)
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
        assert float(requests.get(f"{API}/game-config", timeout=20).json()["rtp"]) == pytest.approx(0.9)

    def test_rtp_08_and_075(self, admin):
        r = admin.put(f"{API}/admin/bank/settings", json={"rtp_target": 0.8}, timeout=30)
        assert r.status_code == 200, r.text
        cfg = requests.get(f"{API}/game-config", timeout=20).json()
        assert cfg["rtp"] == pytest.approx(0.8)
        assert cfg["max_bet_ratio"] == pytest.approx(0.9375, abs=1e-4)

        r = admin.put(f"{API}/admin/bank/settings", json={"rtp_target": 0.75}, timeout=30)
        assert r.status_code == 200, r.text
        cfg = requests.get(f"{API}/game-config", timeout=20).json()
        assert cfg["rtp"] == pytest.approx(0.75)
        assert cfg["max_bet_ratio"] == pytest.approx(1.0, abs=1e-6)

        r = admin.put(f"{API}/admin/bank/settings", json={"rtp_target": 0.9}, timeout=30)
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/game-config", timeout=20).json()["rtp"] == pytest.approx(0.9)

    def test_rtp_above_one_rejected(self, admin):
        r = admin.put(f"{API}/admin/bank/settings", json={"rtp_target": 1.2}, timeout=30)
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"

    def test_bank_adjust_cannot_go_negative(self, admin):
        before = float(admin.get(f"{API}/admin/bank", timeout=30).json()["bank"])
        r = admin.post(f"{API}/admin/bank/adjust", json={"amount": -(before + 1), "note": "qa guard"}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        assert "минус" in r.json().get("detail", "")
        after = float(admin.get(f"{API}/admin/bank", timeout=30).json()["bank"])
        assert after == pytest.approx(before, abs=1e-6), "bank changed by rejected adjust"

    def test_bank_adjust_zero_rejected(self, admin):
        r = admin.post(f"{API}/admin/bank/adjust", json={"amount": 0, "note": "qa"}, timeout=30)
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"


def teardown_module(module):
    for col in ("users", "upgrades", "drops", "presence", "item_history"):
        db[col].delete_many({"session_id": {"$regex": "^qa_"}})
