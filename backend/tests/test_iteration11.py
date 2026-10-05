"""Iteration 11: gold promo XYIPACHOSIK, live-drops enrichment, public profile /api/users/{discord_id}."""
import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/") + "/api"
JWT_SECRET = backend_env.get("JWT_SECRET") or os.environ["JWT_SECRET"]
MONGO_URL = backend_env.get("MONGO_URL")
DB_NAME = backend_env.get("DB_NAME")


def mint(sub):
    return jwt.encode({"sub": sub, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session")
def user1():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {mint('discord_test_1')}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def user2(mongo):
    """Second user (never used the gold promo) created for the SINZUKU regression check."""
    mongo.users.update_one(
        {"session_id": "discord_test_2"},
        {"$set": {"session_id": "discord_test_2", "discord_id": "2", "nickname": "Tester2", "balance": 0, "skins": [], "gold_nick": False, "promo_code": None, "promo_bonus": 0.0}},
        upsert=True,
    )
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {mint('discord_test_2')}", "Content-Type": "application/json"})
    yield s
    mongo.users.delete_one({"session_id": "discord_test_2"})
    mongo.drops.delete_many({"session_id": "discord_test_2"})


# ---------- promo ----------
class TestPromo:
    def test_gold_promo_lowercase(self, user1):
        r = user1.post(f"{BASE_URL}/promo/apply", json={"code": "xyipachosik"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["promo_code"] == "XYIPACHOSIK"
        assert abs(d["promo_bonus"] - 0.067) < 1e-9
        assert d["gold_nick"] is True
        # verify persisted
        me = user1.get(f"{BASE_URL}/auth/me").json()
        assert me["gold_nick"] is True and me["promo_code"] == "XYIPACHOSIK"

    def test_sinzuku_no_gold(self, user2):
        r = user2.post(f"{BASE_URL}/promo/apply", json={"code": "SINZUKU"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["promo_code"] == "SINZUKU"
        assert abs(d["promo_bonus"] - 0.10) < 1e-9
        assert d["gold_nick"] is False
        me = user2.get(f"{BASE_URL}/auth/me").json()
        assert me["gold_nick"] is False

    def test_unknown_code(self, user1):
        r = user1.post(f"{BASE_URL}/promo/apply", json={"code": "NOPE123"})
        assert r.status_code == 400
        assert "не найден" in r.json().get("detail", "")

    def test_promo_requires_auth(self):
        r = requests.post(f"{BASE_URL}/promo/apply", json={"code": "SINZUKU"})
        assert r.status_code == 401

    def test_no_balance_leak_after_gold(self, user1):
        """gold user public profile must not expose balance"""
        r = requests.get(f"{BASE_URL}/users/1")
        assert r.status_code == 200
        assert "balance" not in r.json()


# ---------- live drops ----------
class TestLiveDrops:
    def test_enriched(self):
        r = requests.get(f"{BASE_URL}/live-drops")
        assert r.status_code == 200, r.text
        drops = r.json()
        assert isinstance(drops, list) and len(drops) > 0
        mine = [d for d in drops if d.get("discord_id") == "1"]
        assert mine, "no drops for discord_test_1 (discord_id=1) in live feed"
        for d in mine:
            assert d["gold_nick"] is True
            assert d["avatar"]
            assert d["discord_id"] == "1"
            assert "_id" not in d
            assert d["item_name"] and d["nickname"]

    def test_limit_param(self):
        r = requests.get(f"{BASE_URL}/live-drops", params={"limit": 3})
        assert r.status_code == 200
        assert len(r.json()) <= 3


# ---------- public profile ----------
class TestPublicProfile:
    def test_ok(self):
        r = requests.get(f"{BASE_URL}/users/1")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("nickname", "avatar", "discord_id", "gold_nick", "stats", "best_drop", "drops"):
            assert k in d, f"missing {k}"
        assert d["discord_id"] == "1"
        assert d["gold_nick"] is True
        s = d["stats"]
        for k in ("upgrades", "wins", "withdrawn_count", "withdrawn_sum", "inventory_count", "inventory_value"):
            assert k in s, f"missing stat {k}"
            assert isinstance(s[k], (int, float))
        assert s["inventory_count"] == 3, f"expected 3 skins, got {s['inventory_count']}"
        assert isinstance(d["drops"], list) and len(d["drops"]) >= 8
        assert d["best_drop"] is not None
        # best drop must be the max priced drop
        assert d["best_drop"]["item_price"] >= max(x["item_price"] for x in d["drops"])
        # no sensitive fields
        for leak in ("balance", "session_id", "_id", "promo_bonus", "roblox_link"):
            assert leak not in d, f"leaked {leak}"

    def test_drops_have_no_session_id_leak(self):
        d = requests.get(f"{BASE_URL}/users/1").json()
        # Drop model includes session_id; flag if exposed publicly
        leaked = [x for x in d["drops"] if "session_id" in x]
        assert not leaked, "drops[] exposes internal session_id"

    def test_unknown_404(self):
        r = requests.get(f"{BASE_URL}/users/doesnotexist")
        assert r.status_code == 404
        assert r.json()["detail"] == "Игрок не найден"
