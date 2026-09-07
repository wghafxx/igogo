"""Iteration-3 backend tests: real shop target validation, MAX_CHANCE 75%,
skin-vs-skin bets (bet_items uid), win -> inventory + live-drop with image."""
import os
import subprocess

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

BACKEND_ENV = dotenv_values("/app/backend/.env")
SESSION = "discord_test_1"
MAX_CHANCE = 0.75
GLOVE = {"id": "case-glove-case", "price": 43.0, "rarity": "red", "name": "Glove Case"}


@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient(BACKEND_ENV["MONGO_URL"])
    yield mc[BACKEND_ENV["DB_NAME"]]
    mc.close()


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module", autouse=True)
def bootstrap(client, mongo):
    client.get(f"{API}/user/{SESSION}")
    mongo.users.update_one({"session_id": SESSION}, {"$set": {"balance": 1000.0}})
    yield


def set_balance(mongo, amount=1000.0):
    mongo.users.update_one({"session_id": SESSION}, {"$set": {"balance": float(amount)}})


def give_skin(mongo, uid, item):
    mongo.users.update_one({"session_id": SESSION}, {"$pull": {"skins": {"uid": uid}}})
    mongo.users.update_one({"session_id": SESSION}, {"$push": {"skins": {**item, "uid": uid}}})


# ---------- JWT ----------
class TestToken:
    def test_make_token_and_auth_me(self, client):
        out = subprocess.run(
            ["python", "-c", "from server import make_token; print(make_token('discord_test_1'))"],
            cwd="/app/backend", capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        token = out.stdout.strip().splitlines()[-1]
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        assert r.json()["session_id"] == SESSION


# ---------- shop / drops / user integrity ----------
class TestCatalogIntegrity:
    def test_shop_has_8_items_all_with_images(self, client):
        r = client.get(f"{API}/shop")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 8, [i["id"] for i in items]
        for it in items:
            assert it.get("image"), it
            assert "_id" not in it
        by_name = {i["name"]: i for i in items}
        assert by_name["Midas"]["image"].endswith("126726654780672.png")
        assert by_name["Anodized Red"]["image"].endswith("87908365282079.png")

    def test_live_drops_have_no_balance_pseudo_items(self, client):
        r = client.get(f"{API}/live-drops?limit=100")
        assert r.status_code == 200, r.text
        for d in r.json():
            assert d["item_type"] != "balance", d
            assert d["item_image"], d

    def test_user_skins_all_have_uid(self, client):
        r = client.get(f"{API}/user/{SESSION}")
        assert r.status_code == 200, r.text
        for sk in r.json()["skins"]:
            assert sk.get("uid"), sk

    def test_click_sound_asset_available(self, client):
        r = client.get(f"{BASE_URL}/sounds/click.mp3")
        assert r.status_code == 200, r.status_code


# ---------- target validation ----------
class TestTargetValidation:
    def test_missing_target_400(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 10, "bet_items": [], "chance": 0.5})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Выберите скин для апгрейда"

    def test_target_without_id_400(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 10, "bet_items": [],
            "target_item": {"name": "Balance upgrade", "type": "balance", "price": 100},
            "chance": 0.5})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Выберите скин для апгрейда"

    def test_target_id_not_in_shop_400(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 10, "bet_items": [],
            "target_item": {"id": "TEST_does_not_exist", "price": 999999},
            "chance": 0.5})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Скин для апгрейда не найден"

    def test_no_bet_at_all_400(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [],
            "target_item": {"id": GLOVE["id"]}, "chance": 0.5})
        assert r.status_code == 400, r.text


# ---------- chance / limit validation ----------
class TestLimits:
    def test_chance_above_max_400(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 10, "bet_items": [],
            "target_item": {"id": GLOVE["id"]}, "chance": 0.9})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Максимальный шанс — 75%"

    def test_chance_above_one_422(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 10, "bet_items": [],
            "target_item": {"id": GLOVE["id"]}, "chance": 1.5})
        assert r.status_code == 422, r.text

    def test_bet_over_75_percent_of_target_400(self, client, mongo):
        set_balance(mongo, 1000.0)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 40.0, "bet_items": [],
            "target_item": {"id": GLOVE["id"]}, "chance": 0.75})
        assert r.status_code == 400, r.text
        assert "75%" in r.json()["detail"]

    def test_bet_at_exactly_75_percent_ok(self, client, mongo):
        set_balance(mongo, 1000.0)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 32.25, "bet_items": [],
            "target_item": {"id": GLOVE["id"]}, "chance": 0.75})
        assert r.status_code == 200, r.text
        assert abs(r.json()["chance"] - 0.75) < 1e-9

    def test_bet_over_balance_400(self, client, mongo):
        set_balance(mongo, 5.0)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 30.0, "bet_items": [],
            "target_item": {"id": GLOVE["id"]}, "chance": 0.69})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Недостаточно баланса"
        set_balance(mongo, 1000.0)


# ---------- success path ----------
class TestSuccessPath:
    def test_balance_bet_success_and_math(self, client, mongo):
        # isolated session so parallel workers can't mutate the balance mid-test
        sid = "TEST_v3_math"
        client.get(f"{API}/user/{sid}")
        mongo.users.update_one({"session_id": sid}, {"$set": {"balance": 1000.0}})
        r = client.post(f"{API}/upgrade", json={
            "session_id": sid, "bet_amount": 20.0, "bet_items": [],
            "target_item": {"id": GLOVE["id"]}, "chance": 0.4651})
        assert r.status_code == 200, r.text
        d = r.json()
        assert abs(d["balance"] - 980.0) < 1e-6
        assert abs(d["angle"] - (d["roll"] * 360 - 180)) < 1e-6
        assert d["win"] == (abs(d["angle"]) < d["chance"] * 180)
        assert client.get(f"{API}/user/{sid}").json()["balance"] == pytest.approx(980.0)
        mongo.users.delete_many({"session_id": sid})
        mongo.upgrades.delete_many({"session_id": sid})
        mongo.drops.delete_many({"session_id": sid})

    def test_stored_upgrade_uses_db_item(self, mongo, client):
        set_balance(mongo, 1000.0)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 20.0, "bet_items": [],
            "target_item": {"id": GLOVE["id"], "price": 999999, "rarity": "gold", "image": None},
            "chance": 0.4651})
        assert r.status_code == 200, r.text
        doc = mongo.upgrades.find_one({"id": r.json()["id"]})
        tgt = doc["target_item"]
        assert tgt["price"] == 43.0, tgt
        assert tgt["rarity"] == "red", tgt
        assert tgt["image"], tgt

    def test_win_adds_skin_and_drop_with_image(self, client, mongo):
        won = None
        for _ in range(40):
            set_balance(mongo, 1000.0)
            r = client.post(f"{API}/upgrade", json={
                "session_id": SESSION, "bet_amount": 32.25, "bet_items": [],
                "target_item": {"id": GLOVE["id"]}, "chance": 0.75})
            assert r.status_code == 200, r.text
            if r.json()["win"]:
                won = r.json()
                break
        assert won is not None, "no win in 40 tries at 75%"

        skins = client.get(f"{API}/user/{SESSION}").json()["skins"]
        mine = [s for s in skins if s.get("id") == GLOVE["id"]]
        assert mine, skins
        assert mine[-1].get("uid") and mine[-1].get("image")

        drops = client.get(f"{API}/live-drops?limit=10").json()
        newest = drops[0]
        assert newest["item_image"], newest
        assert newest["item_type"] != "balance", newest
        assert newest["session_id"] == SESSION, newest


# ---------- skin vs skin ----------
class TestSkinVsSkin:
    def test_skin_bet_success_and_uid_consumed(self, client, mongo):
        item = {"id": "case-glove-case", "type": "Case", "name": "Glove Case", "price": 43.0,
                "rarity": "red", "image": "https://bloxstrike.net/items/bloxstrike-live/123594181073716.png"}
        give_skin(mongo, "test-uid-1", item)
        set_balance(mongo, 1000.0)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [{"uid": "test-uid-1"}],
            "target_item": {"id": "case-1"}, "chance": 0.4886})
        assert r.status_code == 200, r.text
        assert abs(r.json()["balance"] - 1000.0) < 1e-6

        skins = client.get(f"{API}/user/{SESSION}").json()["skins"]
        assert all(s.get("uid") != "test-uid-1" for s in skins), "bet skin not removed"

        r2 = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [{"uid": "test-uid-1"}],
            "target_item": {"id": "case-1"}, "chance": 0.4886})
        assert r2.status_code == 400, r2.text
        assert r2.json()["detail"] == "Выбранных скинов нет в вашем инвентаре"

    def test_unowned_uid_400(self, client):
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [{"uid": "TEST_not_mine"}],
            "target_item": {"id": "case-1"}, "chance": 0.5})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Выбранных скинов нет в вашем инвентаре"

    def test_skin_bet_over_75_percent_400(self, client, mongo):
        big = {"id": "m4a1s-anodized-red", "type": "M4A1-S", "name": "Anodized Red", "price": 1580.0,
               "rarity": "red", "image": "https://bloxstrike.net/items/bloxstrike-live/87908365282079.png"}
        give_skin(mongo, "test-uid-big", big)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [{"uid": "test-uid-big"}],
            "target_item": {"id": GLOVE["id"]}, "chance": 0.75})
        assert r.status_code == 400, r.text
        assert "75%" in r.json()["detail"]
        # not consumed on failure
        skins = client.get(f"{API}/user/{SESSION}").json()["skins"]
        assert any(s.get("uid") == "test-uid-big" for s in skins)
        mongo.users.update_one({"session_id": SESSION}, {"$pull": {"skins": {"uid": "test-uid-big"}}})
