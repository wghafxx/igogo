"""Iteration 4 backend tests: promo, deposit info, profile, roblox link, sell/withdraw, upgrade validation."""
import os
import sys
import uuid

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
MONGO_URL = backend_env.get("MONGO_URL")
DB_NAME = backend_env.get("DB_NAME")

SESSION = "discord_test_1"


def make_jwt(sid=SESSION):
    from server import make_token

    return make_token(sid)


@pytest.fixture(scope="session")
def token():
    return make_jwt()


@pytest.fixture(scope="session")
def mongo():
    from pymongo import MongoClient

    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture
def client(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture
def anon():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def seed_skins(mongo, n=3):
    shop = list(mongo.shop_items.find({}, {"_id": 0}).sort("price", 1).limit(n))
    skins = [{**it, "uid": str(uuid.uuid4())} for it in shop]
    mongo.users.update_one(
        {"session_id": SESSION},
        {"$set": {"balance": 999000.0, "nickname": "Tester", "discord_id": "1",
                  "avatar": "https://cdn.discordapp.com/embed/avatars/0.png", "skins": skins}},
        upsert=True,
    )
    return skins


# --- deposit info / promo ---
class TestPromoAndDeposit:
    def test_deposit_info(self, anon):
        r = anon.get(f"{API}/deposit/info")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["friend_url"].startswith("https://www.roblox.com/share?code=114adf7ac7b01243b752faf7c6c71b28")
        assert d["min_rap"] == 20
        assert abs(d["fee"] - 0.20) < 1e-9

    def test_promo_requires_auth(self, anon):
        r = anon.post(f"{API}/promo/apply", json={"code": "SINZUKU"})
        assert r.status_code == 401, r.text

    def test_promo_apply_lowercase(self, client, mongo):
        r = client.post(f"{API}/promo/apply", json={"code": "sinzuku"})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["promo_code"] == "SINZUKU"
        assert abs(u["promo_bonus"] - 0.10) < 1e-9
        # persisted
        me = client.get(f"{API}/auth/me").json()
        assert me["promo_code"] == "SINZUKU"
        assert abs(me["promo_bonus"] - 0.10) < 1e-9

    def test_promo_unknown_code(self, client):
        r = client.post(f"{API}/promo/apply", json={"code": "ABC"})
        assert r.status_code == 400
        assert "не найден" in r.json()["detail"]


# --- profile ---
class TestProfile:
    def test_profile_requires_auth(self, anon):
        assert anon.get(f"{API}/profile").status_code == 401

    def test_profile_shape(self, client, mongo):
        seed_skins(mongo)
        r = client.get(f"{API}/profile")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user"]["nickname"] == "Tester"
        assert d["user"]["discord_id"] == "1"
        assert abs(d["user"]["balance"] - 999000.0) < 1e-6
        assert len(d["user"]["skins"]) == 3
        for key in ("upgrades", "wins", "withdrawn_count", "withdrawn_sum"):
            assert key in d["stats"]
        assert isinstance(d["item_history"], list)
        assert isinstance(d["games"], list)
        assert '"_id"' not in r.text and "'_id'" not in r.text

    def test_roblox_requires_auth(self, anon):
        r = anon.post(f"{API}/profile/roblox", json={"roblox_nick": "Tester", "roblox_link": "https://www.roblox.com/share?code=abc"})
        assert r.status_code == 401

    def test_roblox_save_and_persist(self, client):
        link = "https://www.roblox.com/share?code=abc&type=Profile"
        r = client.post(f"{API}/profile/roblox", json={"roblox_nick": "TestBuilder", "roblox_link": link})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["roblox_nick"] == "TestBuilder"
        assert u["roblox_link"] == link
        me = client.get(f"{API}/auth/me").json()
        assert me["roblox_nick"] == "TestBuilder"
        assert me["roblox_link"] == link

    def test_roblox_reject_foreign_link(self, client):
        r = client.post(f"{API}/profile/roblox", json={"roblox_nick": "TestBuilder", "roblox_link": "https://evil.com/x"})
        assert r.status_code == 400
        assert "roblox.com" in r.json()["detail"]


# --- sell / withdraw ---
class TestSellWithdraw:
    def test_sell_requires_auth(self, anon):
        assert anon.post(f"{API}/skins/sell", json={"uids": ["x"]}).status_code == 401

    def test_withdraw_requires_auth(self, anon):
        assert anon.post(f"{API}/skins/withdraw", json={"uids": ["x"]}).status_code == 401

    def test_sell_unknown_uid_400(self, client):
        r = client.post(f"{API}/skins/sell", json={"uids": [str(uuid.uuid4())]})
        assert r.status_code == 400
        assert "инвентаре" in r.json()["detail"]

    def test_sell_empty_400(self, client):
        assert client.post(f"{API}/skins/sell", json={"uids": []}).status_code == 400

    def test_sell_credits_balance_and_removes(self, client, mongo):
        skins = seed_skins(mongo)
        before = client.get(f"{API}/auth/me").json()["balance"]
        target = skins[0]
        r = client.post(f"{API}/skins/sell", json={"uids": [target["uid"]]})
        assert r.status_code == 200, r.text
        u = r.json()
        assert abs(u["balance"] - (before + float(target["price"]))) < 1e-6
        assert target["uid"] not in [s["uid"] for s in u["skins"]]
        prof = client.get(f"{API}/profile").json()
        assert target["uid"] not in [s["uid"] for s in prof["user"]["skins"]]
        assert any(h["kind"] == "sold" and h["item"]["uid"] == target["uid"] for h in prof["item_history"])

    def test_withdraw_removes_and_records(self, client, mongo):
        skins = seed_skins(mongo)
        target = skins[1]
        before = client.get(f"{API}/auth/me").json()["balance"]
        r = client.post(f"{API}/skins/withdraw", json={"uids": [target["uid"]]})
        assert r.status_code == 200, r.text
        u = r.json()
        assert abs(u["balance"] - before) < 1e-6  # no balance change
        assert target["uid"] not in [s["uid"] for s in u["skins"]]
        prof = client.get(f"{API}/profile").json()
        assert prof["stats"]["withdrawn_count"] >= 1
        assert any(h["kind"] == "withdrawn" and h["item"]["uid"] == target["uid"] for h in prof["item_history"])
        assert mongo.withdrawals.find_one({"session_id": SESSION, "item.uid": target["uid"]}) is not None


# --- upgrade validation ---
class TestUpgradeValidation:
    def _target(self, mongo):
        return list(mongo.shop_items.find({}, {"_id": 0}).sort("price", -1).limit(1))[0]

    def test_chance_above_max_400(self, client, mongo):
        t = self._target(mongo)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 1, "bet_items": [],
            "target_item": {"id": t["id"]}, "chance": 0.9})
        assert r.status_code == 400, r.text
        assert "75" in r.json()["detail"]

    def test_target_without_id_400(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 1, "bet_items": [],
            "target_item": {"name": "x"}, "chance": 0.5})
        assert r.status_code == 400, r.text

    def test_unknown_target_400(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 1, "bet_items": [],
            "target_item": {"id": str(uuid.uuid4())}, "chance": 0.5})
        assert r.status_code == 400, r.text
        assert "не найден" in r.json()["detail"]

    def test_bet_above_75_percent_of_target_400(self, client, mongo):
        t = self._target(mongo)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": float(t["price"]) * 0.8, "bet_items": [],
            "target_item": {"id": t["id"]}, "chance": 0.5})
        assert r.status_code == 400, r.text
        assert "75%" in r.json()["detail"]

    def test_bet_item_not_owned_400(self, client, mongo):
        t = self._target(mongo)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [{"uid": str(uuid.uuid4())}],
            "target_item": {"id": t["id"]}, "chance": 0.5})
        assert r.status_code == 400, r.text

    def test_upgrade_with_bet_item_consumes_skin(self, client, mongo):
        skins = seed_skins(mongo)
        t = self._target(mongo)
        sk = skins[2]
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [{"uid": sk["uid"]}],
            "target_item": {"id": t["id"]}, "chance": float(sk["price"]) / float(t["price"])})
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["id", "win", "roll", "chance", "angle", "balance", "upgrades_total"]) <= set(d)
        assert -180 <= d["angle"] <= 180
        assert (abs(d["angle"]) < d["chance"] * 180) == d["win"]
        fresh = mongo.users.find_one({"session_id": SESSION}, {"_id": 0})
        assert sk["uid"] not in [s["uid"] for s in fresh["skins"]]
