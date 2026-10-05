"""Iteration 8 live tests: commission-funded bonuses.

Verifies:
  * public catalog + thresholds (g1 500 / g2 215 / g3 760 / g4 2000)
  * fresh-player g1 claimable amount = 72 for 600 RAP deposit, debits bank_state.commission_profit by 72
  * bank_ledger has 'bonus' entry with commission_used
  * g2 'waiting' at 214 RAP, 'claimable' at 215, claim decreases commission by 43 and gives bonus skin
  * commission_share=0.2 setting raises thresholds and caps g1 amount
  * insufficient commission -> 409 and no state change
  * concurrent claims: exactly one wins
  * weekly bonus debits commission_profit; settings respected
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
JWT_SECRET = os.environ["JWT_SECRET"]
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ADMIN_PHRASE = "alpha bravo charlie delta echo foxtrot golf hotel india juliet".split()

mongo = MongoClient(MONGO_URL)[DB_NAME]


def mktoken(sid: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sid, "role": "user", "exp": now + timedelta(days=30), "iat": now, "sv": 0},
                      JWT_SECRET, algorithm="HS256")


def mkplayer(suffix: str) -> dict:
    sid = f"TEST_bonus8_{suffix}_{uuid.uuid4().hex[:6]}"
    roblox_nick = f"b8_{uuid.uuid4().hex[:6]}"
    doc = {
        "session_id": sid, "discord_id": f"TESTB8{uuid.uuid4().hex[:10]}",
        "nickname": f"TESTbonus8_{suffix}", "roblox_display_name": "Player Nickname",
        "roblox_nick": roblox_nick, "roblox_nick_normalized": roblox_nick.lower(),
        "roblox_link": "https://www.roblox.com/users/777/profile",
        "balance": 0.0, "skins": [], "created_at": datetime.now(timezone.utc),
    }
    mongo.users.update_one({"session_id": sid}, {"$set": doc}, upsert=True)
    tok = mktoken(sid)
    return {"session_id": sid, "roblox_nick": roblox_nick, "token": tok,
            "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{API}/admin/login", json={"phrases": ADMIN_PHRASE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def admin_deposit(admin_headers, player, rap: float) -> str:
    chat = requests.post(f"{API}/chats", headers=player["headers"],
                         json={"kind": "deposit", "expected_rap": max(int(rap), 200)})
    assert chat.status_code in (200, 201), chat.text
    cid = chat.json()["id"]
    r = requests.post(f"{API}/admin/chats/{cid}/deposit", headers=admin_headers,
                      json={"rap": rap, "request_id": uuid.uuid4().hex})
    assert r.status_code == 200, r.text
    return cid


def commission_profit() -> float:
    doc = mongo.bank_state.find_one({"id": "main"}, {"_id": 0, "commission_profit": 1}) or {}
    return float(doc.get("commission_profit") or 0.0)


# ---------- Public catalog ----------
class TestCatalog:
    def test_catalog_thresholds(self):
        r = requests.get(f"{API}/bonuses/catalog")
        assert r.status_code == 200, r.text
        gifts = {g["id"]: g for g in r.json()["gifts"]}
        assert gifts["g1"]["min_rap"] == 500.0
        assert gifts["g2"]["min_rap"] == 215.0, gifts["g2"]
        assert gifts["g3"]["min_rap"] == 760.0, gifts["g3"]
        assert gifts["g4"]["min_rap"] == 2000.0, gifts["g4"]
        # ensure items are attached
        assert gifts["g2"]["item"]["price"] == 43
        assert gifts["g3"]["item"]["price"] == 152
        assert gifts["g4"]["item"]["price"] == 299


# ---------- Commission-funded g1 ----------
class TestCommissionFlow:
    def test_g1_claim_debits_commission_profit(self, admin_headers):
        p = mkplayer("g1take")
        requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        admin_deposit(admin_headers, p, 600)
        state = requests.get(f"{API}/bonuses", headers=p["headers"]).json()
        g1 = next(g for g in state["gifts"] if g["id"] == "g1")
        assert g1["status"] == "claimable" and g1["amount"] == 72.0
        before_profit = commission_profit()
        before_bal = requests.get(f"{API}/auth/me", headers=p["headers"]).json()["balance"]
        r = requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])
        assert r.status_code == 200, r.text
        after_profit = commission_profit()
        after_bal = requests.get(f"{API}/auth/me", headers=p["headers"]).json()["balance"]
        assert round(after_bal - before_bal, 2) == 72.0
        assert round(before_profit - after_profit, 2) == 72.0
        # bank_ledger entry
        row = mongo.bank_ledger.find_one({"kind": "bonus", "session_id": p["session_id"]},
                                         sort=[("created_at", -1)])
        assert row is not None
        assert round(float(row["commission_used"]), 2) == 72.0

    def test_g2_waiting_below_215_and_claimable_at_215(self, admin_headers):
        p = mkplayer("g2thr")
        requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        admin_deposit(admin_headers, p, 600)
        r = requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])
        assert r.status_code == 200, r.text
        # 214 is below threshold
        admin_deposit(admin_headers, p, 214)
        g2 = next(g for g in requests.get(f"{API}/bonuses", headers=p["headers"]).json()["gifts"] if g["id"] == "g2")
        assert g2["status"] == "waiting", g2
        # 215 qualifies
        admin_deposit(admin_headers, p, 215)
        g2 = next(g for g in requests.get(f"{API}/bonuses", headers=p["headers"]).json()["gifts"] if g["id"] == "g2")
        assert g2["status"] == "claimable", g2
        before_profit = commission_profit()
        r = requests.post(f"{API}/bonuses/gifts/g2/claim", headers=p["headers"])
        assert r.status_code == 200, r.text
        after_profit = commission_profit()
        assert round(before_profit - after_profit, 2) == 43.0
        # skin added, bonus:true
        user = mongo.users.find_one({"session_id": p["session_id"]}, {"_id": 0, "skins": 1})
        bonus_skins = [s for s in user["skins"] if s.get("bonus")]
        assert len(bonus_skins) == 1 and bonus_skins[0]["id"] == "case-glove-case"


# ---------- commission_share setting ----------
class TestCommissionShare:
    def test_share_raises_thresholds_and_caps_g1(self, admin_headers):
        # Set commission_share = 0.2
        r = requests.put(f"{API}/admin/bonuses/settings", headers=admin_headers,
                         json={"commission_share": 0.2})
        assert r.status_code == 200, r.text
        try:
            cat = requests.get(f"{API}/bonuses/catalog").json()["gifts"]
            g2 = next(g for g in cat if g["id"] == "g2")
            assert g2["min_rap"] >= 1075.0, g2  # ceil(43/(0.2*0.2)) = 1075
            # Fresh deposit of 1200 → g1 amount min(1200*0.8*0.15, 1200*0.2*0.2)=min(144,48)=48
            p = mkplayer("share")
            requests.post(f"{API}/bonuses/activate", headers=p["headers"])
            admin_deposit(admin_headers, p, 1200)
            state = requests.get(f"{API}/bonuses", headers=p["headers"]).json()
            g1 = next(g for g in state["gifts"] if g["id"] == "g1")
            assert g1["status"] == "claimable" and g1["amount"] == 48.0, g1
        finally:
            r = requests.put(f"{API}/admin/bonuses/settings", headers=admin_headers,
                             json={"commission_share": 1.0})
            assert r.status_code == 200


# ---------- Insufficient commission ----------
class TestInsufficientCommission:
    def test_409_when_commission_too_low(self, admin_headers):
        p = mkplayer("lowcomm")
        requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        admin_deposit(admin_headers, p, 600)
        # Save current commission, then set it to 1.0 (less than 72)
        original = commission_profit()
        mongo.bank_state.update_one({"id": "main"}, {"$set": {"commission_profit": 1.0}})
        try:
            before_bal = requests.get(f"{API}/auth/me", headers=p["headers"]).json()["balance"]
            r = requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])
            assert r.status_code == 409, r.text
            assert "недоступны" in r.json()["detail"].lower()
            after_bal = requests.get(f"{API}/auth/me", headers=p["headers"]).json()["balance"]
            assert before_bal == after_bal
            assert commission_profit() == 1.0  # unchanged
        finally:
            mongo.bank_state.update_one({"id": "main"}, {"$set": {"commission_profit": original}})

    def test_concurrent_claims_only_one_succeeds(self, admin_headers):
        p = mkplayer("race")
        requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        admin_deposit(admin_headers, p, 600)
        before_profit = commission_profit()

        async def one_claim(client):
            return await client.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])

        async def run():
            async with httpx.AsyncClient(timeout=30) as c:
                return await asyncio.gather(*[one_claim(c) for _ in range(6)])

        results = asyncio.run(run())
        codes = [r.status_code for r in results]
        assert codes.count(200) == 1, codes
        assert codes.count(409) == 5, codes
        after_profit = commission_profit()
        # Exactly 72 debited once
        assert round(before_profit - after_profit, 2) == 72.0
        # Only one claim doc
        n = mongo.bonus_claims.count_documents({"session_id": p["session_id"], "kind": "g1"})
        assert n == 1


# ---------- Weekly bonus commission ----------
class TestWeeklyCommission:
    def test_weekly_debits_commission(self, admin_headers):
        p = mkplayer("wk")
        requests.put(f"{API}/admin/players/{p['session_id']}/weekly-bonus",
                     headers=admin_headers, json={"enabled": True})
        mongo.users.update_one({"session_id": p["session_id"]},
                               {"$set": {"roblox_display_name": "bloxgrade"}})
        now = datetime.now(timezone.utc)
        rows = [{"id": uuid.uuid4().hex, "session_id": p["session_id"],
                 "bet_amount": 2.0, "items_total": 0.0, "created_at": now} for _ in range(10)]
        mongo.upgrades.insert_many(rows)
        before_profit = commission_profit()
        r = requests.post(f"{API}/bonuses/weekly/claim", headers=p["headers"])
        assert r.status_code == 200, r.text
        after_profit = commission_profit()
        assert round(before_profit - after_profit, 2) == 20.0

    def test_bonuses_endpoint_exposes_weekly_settings_and_wager_x(self):
        p = mkplayer("exp")
        data = requests.get(f"{API}/bonuses", headers=p["headers"]).json()
        assert data["weekly"]["amount"] == 20.0
        assert data["weekly"]["min_games"] == 10
        assert data["wager"]["x"] == 5


# ---------- Admin invalid value ----------
class TestAdminValidation:
    def test_admin_rejects_g1_pct_over_cap(self, admin_headers):
        r = requests.put(f"{API}/admin/bonuses/settings", headers=admin_headers,
                         json={"g1_pct": 0.9})
        assert r.status_code == 400, r.text
