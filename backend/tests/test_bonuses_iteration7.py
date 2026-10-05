"""Iteration 7 live tests: bonus chain, anti-abuse, weekly bonus, admin weekly toggle.

Uses REACT_APP_BACKEND_URL (public ingress), creates fresh players directly in Mongo so the
seeded PlayerTester chain is not disturbed. Non-destructive: each test creates its own fresh
session_id and leaves state behind under TEST_bonus_* nicknames for inspection.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def mkplayer(suffix: str, nick_prefix: str = "bonus") -> dict:
    sid = f"TEST_bonus_{suffix}_{uuid.uuid4().hex[:6]}"
    roblox_nick = f"{nick_prefix}_{uuid.uuid4().hex[:6]}"
    doc = {
        "session_id": sid,
        "discord_id": f"TESTBONUS{uuid.uuid4().hex[:10]}",
        "nickname": f"TESTbonus_{suffix}",
        "roblox_display_name": "Player Nickname",
        "roblox_nick": roblox_nick,
        "roblox_nick_normalized": roblox_nick.lower(),
        "roblox_link": "https://www.roblox.com/users/777/profile",
        "balance": 0.0,
        "skins": [],
        "created_at": datetime.now(timezone.utc),
    }
    mongo.users.update_one({"session_id": sid}, {"$set": doc}, upsert=True)
    return {"session_id": sid, "roblox_nick": roblox_nick, "token": mktoken(sid), "headers": {"Authorization": f"Bearer {mktoken(sid)}"}}


@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{API}/admin/login", json={"phrases": ADMIN_PHRASE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def admin_deposit(admin_headers, player, rap: float) -> str:
    """Create a deposit via chat and let admin confirm it. Returns credited amount is handled by callers."""
    chat = requests.post(f"{API}/chats", headers=player["headers"], json={"kind": "deposit", "expected_rap": max(rap, 200)})
    assert chat.status_code in (200, 201), chat.text
    cid = chat.json()["id"]
    r = requests.post(f"{API}/admin/chats/{cid}/deposit", headers=admin_headers,
                      json={"rap": rap, "request_id": uuid.uuid4().hex})
    assert r.status_code == 200, r.text
    return cid


# --- Bonus state visibility ---

class TestBonusesState:
    def test_fresh_player_g1_inactive(self):
        p = mkplayer("state")
        r = requests.get(f"{API}/bonuses", headers=p["headers"])
        assert r.status_code == 200, r.text
        data = r.json()
        g1 = next(g for g in data["gifts"] if g["id"] == "g1")
        assert g1["status"] == "inactive"
        for gid in ("g2", "g3", "g4"):
            g = next(g for g in data["gifts"] if g["id"] == gid)
            assert g["status"] == "locked"
        assert data["wager"]["x"] == 5
        assert data["wager"]["required"] == 0.0
        assert data["weekly"]["access"] is False

    def test_activate_sets_g1_waiting(self):
        p = mkplayer("activate")
        r = requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        assert r.status_code == 200, r.text
        g1 = next(g for g in r.json()["gifts"] if g["id"] == "g1")
        assert g1["status"] == "waiting"

    def test_claim_before_deposit_409(self):
        p = mkplayer("preclaim")
        requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        r = requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])
        assert r.status_code == 409, r.text


# --- Full chain: g1 (percent) -> g2 (skin) -> wager / withdraw block ---

class TestBonusChain:
    def test_g1_claim_credits_15pct_and_blocks_withdraw(self, admin_headers):
        p = mkplayer("chain")
        requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        # Admin confirms 600 RAP deposit → net=600*0.8=480, g1 amount = 480*0.15 = 72.00
        admin_deposit(admin_headers, p, 600)
        state = requests.get(f"{API}/bonuses", headers=p["headers"]).json()
        g1 = next(g for g in state["gifts"] if g["id"] == "g1")
        assert g1["status"] == "claimable", state
        assert g1["amount"] == 72.0
        before = requests.get(f"{API}/auth/me", headers=p["headers"]).json()["balance"]
        r = requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])
        assert r.status_code == 200, r.text
        after = requests.get(f"{API}/auth/me", headers=p["headers"]).json()["balance"]
        assert round(after - before, 2) == 72.0
        # Second claim rejected 409
        r2 = requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])
        assert r2.status_code == 409
        # Wager required = 72 * 5 = 360
        wager = requests.get(f"{API}/bonuses", headers=p["headers"]).json()["wager"]
        assert wager["required"] == 360.0 and wager["left"] == 360.0
        # Grant a 20 RAP skin so a withdraw can be attempted (not bonus), then withdraw must be blocked
        skin = {"uid": uuid.uuid4().hex, "name": "RegSkin", "type": "AK-47", "price": 25, "rarity": "Covert"}
        mongo.users.update_one({"session_id": p["session_id"]}, {"$push": {"skins": skin}})
        w = requests.post(f"{API}/skins/withdraw", headers=p["headers"], json={"uids": [skin["uid"]]})
        assert w.status_code == 400 and "Сначала отыграйте бонус" in w.json()["detail"]

    def test_g2_requires_new_deposit_after_g1_and_adds_bonus_flagged_skin(self, admin_headers):
        p = mkplayer("chain2")
        requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        admin_deposit(admin_headers, p, 600)  # qualifies g1
        requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])
        # Before new deposit, g2 should be waiting
        state_before = requests.get(f"{API}/bonuses", headers=p["headers"]).json()
        g2b = next(g for g in state_before["gifts"] if g["id"] == "g2")
        assert g2b["status"] == "waiting"
        # New qualifying deposit (>=215) AFTER g1 claim
        admin_deposit(admin_headers, p, 215)
        state = requests.get(f"{API}/bonuses", headers=p["headers"]).json()
        g2 = next(g for g in state["gifts"] if g["id"] == "g2")
        assert g2["status"] == "claimable", state
        r = requests.post(f"{API}/bonuses/gifts/g2/claim", headers=p["headers"])
        assert r.status_code == 200, r.text
        # Skin added with bonus:true
        user = mongo.users.find_one({"session_id": p["session_id"]}, {"_id": 0, "skins": 1})
        bonus_skins = [s for s in user["skins"] if s.get("bonus")]
        assert len(bonus_skins) == 1
        assert bonus_skins[0]["id"] == "case-glove-case"
        # Bonus skin: cannot sell or withdraw
        uid = bonus_skins[0]["uid"]
        sell = requests.post(f"{API}/skins/sell", headers=p["headers"], json={"uids": [uid]})
        assert sell.status_code == 400 and "Подарочный скин" in sell.json()["detail"]
        wd = requests.post(f"{API}/skins/withdraw", headers=p["headers"], json={"uids": [uid]})
        assert wd.status_code == 400 and "Подарочный скин" in wd.json()["detail"]
        # g3 should be locked/waiting (needs *new* deposit >=500 after g2 claim)
        g3 = next(g for g in state["gifts"] if g["id"] == "g3")
        assert g3["status"] in ("locked", "waiting")


# --- Anti-abuse ---

class TestAntiAbuse:
    def test_same_roblox_nick_on_second_account_blocked(self, admin_headers):
        # Simulate a prior bonus claim on another session_id using the SAME roblox_nick,
        # then verify the bonus guard rejects the second account's claim with 409.
        p2 = mkplayer("twinB")
        mongo.bonus_claims.insert_one({
            "id": uuid.uuid4().hex, "session_id": "TEST_bonus_twinA_fake",
            "kind": "g1", "roblox_nick": p2["roblox_nick"].lower(),
            "amount": 72.0, "at": datetime.now(timezone.utc), "deposit_id": uuid.uuid4().hex,
        })
        requests.post(f"{API}/bonuses/activate", headers=p2["headers"])
        admin_deposit(admin_headers, p2, 600)
        r2 = requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p2["headers"])
        assert r2.status_code == 409 and "другом аккаунте" in r2.json()["detail"], r2.text

    def test_bonus_skin_can_be_used_in_upgrade(self, admin_headers):
        p = mkplayer("upgradeuse")
        requests.post(f"{API}/bonuses/activate", headers=p["headers"])
        admin_deposit(admin_headers, p, 600)
        requests.post(f"{API}/bonuses/gifts/g1/claim", headers=p["headers"])
        admin_deposit(admin_headers, p, 215)
        requests.post(f"{API}/bonuses/gifts/g2/claim", headers=p["headers"])
        user = mongo.users.find_one({"session_id": p["session_id"]}, {"_id": 0, "skins": 1})
        bonus = next(s for s in user["skins"] if s.get("bonus"))
        # pick a target of higher price
        tgt = mongo.shop_items.find_one({"price": {"$gte": max(100, bonus["price"] * 2)}}, {"_id": 0})
        assert tgt
        r = requests.post(f"{API}/upgrade", headers=p["headers"], json={
            "session_id": p["session_id"], "bet_amount": 0,
            "bet_items": [{"uid": bonus["uid"]}],
            "target_item": tgt,
        })
        # Upgrade accepted (200) regardless of win/loss
        assert r.status_code == 200, r.text


# --- Weekly bonus ---

class TestWeekly:
    def test_weekly_without_access_requires_support(self):
        p = mkplayer("weekly_na")
        r = requests.post(f"{API}/bonuses/weekly/claim", headers=p["headers"])
        assert r.status_code == 403

    def test_admin_toggle_weekly_access(self, admin_headers):
        p = mkplayer("weekly_toggle")
        r = requests.put(f"{API}/admin/players/{p['session_id']}/weekly-bonus",
                         headers=admin_headers, json={"enabled": True})
        assert r.status_code == 200, r.text
        state = requests.get(f"{API}/bonuses", headers=p["headers"]).json()["weekly"]
        assert state["access"] is True
        # name_ok False (display_name = 'Player Nickname'), so cannot claim yet
        r = requests.post(f"{API}/bonuses/weekly/claim", headers=p["headers"])
        assert r.status_code == 409 and "bloxgrade" in r.json()["detail"].lower()

    def test_weekly_requires_name_games_and_once_per_week(self, admin_headers):
        p = mkplayer("weekly_full")
        # Set access, bloxgrade display name
        requests.put(f"{API}/admin/players/{p['session_id']}/weekly-bonus",
                     headers=admin_headers, json={"enabled": True})
        mongo.users.update_one({"session_id": p["session_id"]},
                               {"$set": {"roblox_display_name": "bloxgrade"}})
        # Not enough games
        r = requests.post(f"{API}/bonuses/weekly/claim", headers=p["headers"])
        assert r.status_code == 409 and "игр" in r.json()["detail"].lower()
        # Inject 10 upgrade rows with stake>=1 in current week
        now = datetime.now(timezone.utc)
        rows = [{"id": uuid.uuid4().hex, "session_id": p["session_id"],
                 "bet_amount": 2.0, "items_total": 0.0, "created_at": now} for _ in range(10)]
        mongo.upgrades.insert_many(rows)
        state = requests.get(f"{API}/bonuses", headers=p["headers"]).json()["weekly"]
        assert state["games"] >= 10 and state["can_claim"] is True
        bal_before = requests.get(f"{API}/auth/me", headers=p["headers"]).json()["balance"]
        r = requests.post(f"{API}/bonuses/weekly/claim", headers=p["headers"])
        assert r.status_code == 200, r.text
        bal_after = requests.get(f"{API}/auth/me", headers=p["headers"]).json()["balance"]
        assert round(bal_after - bal_before, 2) == 20.0
        # Second claim → 409
        r2 = requests.post(f"{API}/bonuses/weekly/claim", headers=p["headers"])
        assert r2.status_code == 409

    def test_weekly_counts_only_games_with_stake_ge_1(self, admin_headers):
        p = mkplayer("weekly_tiny")
        requests.put(f"{API}/admin/players/{p['session_id']}/weekly-bonus",
                     headers=admin_headers, json={"enabled": True})
        mongo.users.update_one({"session_id": p["session_id"]},
                               {"$set": {"roblox_display_name": "bloxgrade"}})
        now = datetime.now(timezone.utc)
        rows = [{"id": uuid.uuid4().hex, "session_id": p["session_id"],
                 "bet_amount": 0.5, "items_total": 0.0, "created_at": now} for _ in range(15)]
        mongo.upgrades.insert_many(rows)
        state = requests.get(f"{API}/bonuses", headers=p["headers"]).json()["weekly"]
        assert state["games"] == 0, state


# --- Regression: /api/upgrade still works ---

class TestUpgradeRegression:
    def test_upgrade_still_ok(self):
        p = mkplayer("upgrade_reg")
        mongo.users.update_one({"session_id": p["session_id"]}, {"$inc": {"balance": 100.0}})
        tgt = mongo.shop_items.find_one({"price": {"$gte": 50, "$lte": 200}}, {"_id": 0})
        r = requests.post(f"{API}/upgrade", headers=p["headers"], json={
            "session_id": p["session_id"], "bet_amount": 10, "bet_items": [], "target_item": tgt,
        })
        assert r.status_code == 200, r.text
        assert "unavailable prize" not in r.text.lower()
