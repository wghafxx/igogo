"""Backend tests for skin-based bets (bet_items uid), uid backfill and shop images."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

BACKEND_ENV = dotenv_values("/app/backend/.env")
MAX_CHANCE = 0.75

BIRD_HUNT = {
    "id": "awp-bird-hunt",
    "name": "Bird Hunt",
    "type": "AWP",
    "price": 1125.0,
    "rarity": "red",
    "image": "https://bloxstrike.net/items/bloxstrike-live/91355488643704.png",
}
ANODIZED = {
    "id": "m4a1s-anodized-red",
    "name": "Anodized Red",
    "type": "M4A1-S",
    "price": 1580.0,
    "rarity": "red",
    "image": "https://bloxstrike.net/items/bloxstrike-live/87908365282079.png",
}


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


@pytest.fixture(scope="module")
def session_id():
    return f"TEST_bet_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module", autouse=True)
def cleanup(mongo, session_id):
    yield
    mongo.users.delete_many({"session_id": session_id})
    mongo.upgrades.delete_many({"session_id": session_id})
    mongo.drops.delete_many({"session_id": session_id})


def seed(mongo, session_id, skins, balance=5000.0):
    mongo.users.update_one(
        {"session_id": session_id},
        {"$set": {"balance": float(balance), "skins": skins, "nickname": "TEST_bettor"}},
        upsert=True,
    )


# --- uid backfill on GET /api/user/{id} ---
def test_uid_backfill_for_legacy_skins(client, mongo, session_id):
    legacy = {k: v for k, v in BIRD_HUNT.items()}  # no uid
    seed(mongo, session_id, [legacy])
    r = client.get(f"{BASE_URL}/api/user/{session_id}")
    assert r.status_code == 200, r.text
    skins = r.json()["skins"]
    assert len(skins) == 1
    assert skins[0].get("uid"), "uid was not backfilled"
    # persisted in mongo
    stored = mongo.users.find_one({"session_id": session_id})["skins"]
    assert stored[0].get("uid") == skins[0]["uid"]


# --- bet_items ownership validation ---
def test_bet_item_unknown_uid_400(client, mongo, session_id):
    seed(mongo, session_id, [{**BIRD_HUNT, "uid": "uid-own-1"}])
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 0,
        "bet_items": [{"uid": "not-mine"}],
        "target_item": ANODIZED, "chance": 0.5,
    })
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Выбранных скинов нет в вашем инвентаре"


def test_bet_item_duplicate_uids_400(client, mongo, session_id):
    seed(mongo, session_id, [{**BIRD_HUNT, "uid": "uid-own-1"}])
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 0,
        "bet_items": [{"uid": "uid-own-1"}, {"uid": "uid-own-1"}],
        "target_item": ANODIZED, "chance": 0.5,
    })
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Выбранных скинов нет в вашем инвентаре"


def test_bet_over_75_percent_of_target_400(client, mongo, session_id):
    """Bird Hunt (1125) vs Glove Case (43) -> way above 75% of target."""
    seed(mongo, session_id, [{**BIRD_HUNT, "uid": "uid-own-1"}])
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 0,
        "bet_items": [{"uid": "uid-own-1"}],
        "target_item": {"id": "case-glove-case", "name": "Glove Case", "type": "Case", "price": 43.0},
        "chance": 0.5,
    })
    assert r.status_code == 400, r.text
    assert "75%" in r.json()["detail"]


def test_bet_amount_over_75_percent_of_target_400(client, mongo, session_id):
    seed(mongo, session_id, [], balance=5000.0)
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 1300.0, "bet_items": [],
        "target_item": ANODIZED, "chance": 0.75,
    })
    assert r.status_code == 400, r.text
    assert "75%" in r.json()["detail"]


# --- happy path: skin consumed regardless of outcome ---
def test_bet_skin_removed_and_balance_debited(client, mongo, session_id):
    seed(mongo, session_id, [{**BIRD_HUNT, "uid": "uid-consume"}], balance=1000.0)
    chance = round(BIRD_HUNT["price"] / ANODIZED["price"], 4)  # 0.712
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 10.0,
        "bet_items": [{"uid": "uid-consume"}],
        "target_item": ANODIZED, "chance": chance,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert abs(d["chance"] - chance) < 1e-9
    assert abs(d["balance"] - 990.0) < 1e-6
    assert d["win"] == (abs(d["angle"]) < d["chance"] * 180)

    user = client.get(f"{BASE_URL}/api/user/{session_id}").json()
    assert abs(user["balance"] - 990.0) < 1e-6
    assert all(s.get("uid") != "uid-consume" for s in user["skins"]), "bet skin was not removed"
    if d["win"]:
        won = [s for s in user["skins"] if s.get("name") == "Anodized Red"]
        assert won and won[0].get("uid"), "won skin missing or missing uid"


def test_win_pushes_uid_and_drop_with_image(client, mongo, session_id):
    """Retry with a fresh skin each time until a win, then check skins + live-drops image."""
    won = None
    for i in range(40):
        uid = f"uid-loop-{i}"
        seed(mongo, session_id, [{**BIRD_HUNT, "uid": uid}], balance=1000.0)
        r = client.post(f"{BASE_URL}/api/upgrade", json={
            "session_id": session_id, "bet_amount": 0,
            "bet_items": [{"uid": uid}],
            "target_item": ANODIZED, "chance": 0.7120,
        })
        assert r.status_code == 200, r.text
        if r.json()["win"]:
            won = r.json()
            break
    assert won is not None, "no win in 40 tries at 71.2%"

    skins = client.get(f"{BASE_URL}/api/user/{session_id}").json()["skins"]
    target_skins = [s for s in skins if s.get("name") == "Anodized Red"]
    assert target_skins, skins
    assert target_skins[0]["uid"]
    assert target_skins[0]["image"] == ANODIZED["image"]

    drops = client.get(f"{BASE_URL}/api/live-drops?limit=30")
    assert drops.status_code == 200, drops.text
    mine = [d for d in drops.json() if d["session_id"] == session_id]
    assert mine, "no drop for the winning session"
    assert mine[0]["item_name"] == "Anodized Red"
    assert mine[0]["item_image"] == ANODIZED["image"]
    assert mine[0]["item_price"] == 1580.0


# --- shop images ---
def test_shop_items_have_images(client):
    r = client.get(f"{BASE_URL}/api/shop")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 8, items
    for it in items:
        assert it.get("image"), it
        assert "_id" not in it
    by_name = {it["name"]: it for it in items}
    assert by_name["Midas"]["image"].endswith("126726654780672.png")
    assert by_name["Anodized Red"]["image"].endswith("87908365282079.png")
