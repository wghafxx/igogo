"""Backend tests for the roulette/upgrade endpoint math and validation.
Updated for the real-shop-target requirement (target_item.id must exist in shop_items)."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

MIN_CHANCE = 0.01
MAX_CHANCE = 0.75
# real shop item: AWP | Bird Hunt, price 1125 -> 75% cap = 843.75
TARGET_ID = "awp-bird-hunt"
TARGET_PRICE = 1125.0


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def session_id():
    return f"TEST_upg_{uuid.uuid4().hex[:8]}"


def set_balance(sid, amount):
    """Set balance directly in Mongo (no API for funding)."""
    from pymongo import MongoClient
    env = dotenv_values("/app/backend/.env")
    mc = MongoClient(env["MONGO_URL"])
    mc[env["DB_NAME"]].users.update_one({"session_id": sid}, {"$set": {"balance": float(amount)}})
    mc.close()


def target():
    return {"id": TARGET_ID}


# --- user bootstrap ---
def test_create_user_and_fund(client, session_id):
    r = client.get(f"{BASE_URL}/api/user/{session_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] == session_id
    assert data["balance"] == 0.0
    assert "_id" not in data
    set_balance(session_id, 100000)
    r2 = client.get(f"{BASE_URL}/api/user/{session_id}")
    assert r2.json()["balance"] == 100000.0


# --- upgrade math ---
@pytest.mark.parametrize("chance", [0.125, 0.25, 0.5, 0.75])
def test_upgrade_math_consistency(client, session_id, chance):
    set_balance(session_id, 100000)
    for _ in range(10):
        r = client.post(f"{BASE_URL}/api/upgrade", json={
            "session_id": session_id,
            "bet_amount": 1,
            "bet_items": [],
            "target_item": target(),
            "chance": chance,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        expected_chance = max(MIN_CHANCE, min(MAX_CHANCE, chance))
        assert abs(d["chance"] - expected_chance) < 1e-9
        assert abs(d["angle"] - (d["roll"] * 360 - 180)) < 1e-6
        assert d["win"] == (abs(d["angle"]) < d["chance"] * 180)
        assert -180 <= d["angle"] <= 180
        assert isinstance(d["id"], str)
        assert isinstance(d["upgrades_total"], int)


def test_chance_clamped_low(client, session_id):
    set_balance(session_id, 100000)
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 1, "bet_items": [],
        "target_item": target(), "chance": 0.0001,
    })
    assert r.status_code == 200, r.text
    assert abs(r.json()["chance"] - MIN_CHANCE) < 1e-9


def test_chance_above_max_rejected(client, session_id):
    """chance > 0.75 must be rejected with 400 and the Russian message."""
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 1, "bet_items": [],
        "target_item": target(), "chance": 1.0,
    })
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Максимальный шанс — 75%"


def test_chance_at_max_allowed(client, session_id):
    set_balance(session_id, 100000)
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 1, "bet_items": [],
        "target_item": target(), "chance": MAX_CHANCE,
    })
    assert r.status_code == 200, r.text
    assert abs(r.json()["chance"] - MAX_CHANCE) < 1e-9


def test_balance_decreases_by_bet(client, session_id):
    set_balance(session_id, 100000)
    before = client.get(f"{BASE_URL}/api/user/{session_id}").json()["balance"]
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 25.5, "bet_items": [],
        "target_item": target(), "chance": 0.5,
    })
    assert r.status_code == 200, r.text
    assert abs(r.json()["balance"] - (before - 25.5)) < 1e-6
    after = client.get(f"{BASE_URL}/api/user/{session_id}").json()["balance"]
    assert abs(after - (before - 25.5)) < 1e-6


def test_win_pushes_skin_and_creates_drop(client, session_id):
    """Retry at max chance until win, then verify skin + live drop (real DB item)."""
    won = None
    for _ in range(40):
        set_balance(session_id, 100000)
        r = client.post(f"{BASE_URL}/api/upgrade", json={
            "session_id": session_id, "bet_amount": 1, "bet_items": [],
            "target_item": target(), "chance": MAX_CHANCE,
        })
        assert r.status_code == 200, r.text
        if r.json()["win"]:
            won = r.json()
            break
    assert won is not None, "no win in 40 tries at 75% chance"

    skins = client.get(f"{BASE_URL}/api/user/{session_id}").json()["skins"]
    mine = [s for s in skins if s.get("id") == TARGET_ID]
    assert mine, skins
    assert mine[-1]["price"] == TARGET_PRICE
    assert mine[-1]["image"] and mine[-1]["uid"]

    drops = client.get(f"{BASE_URL}/api/live-drops?limit=50")
    assert drops.status_code == 200, drops.text
    items = drops.json()
    mine_drops = [d for d in items if d["session_id"] == session_id]
    assert mine_drops, items[:3]
    assert mine_drops[0]["item_image"]
    assert mine_drops[0]["item_type"] != "balance"


# --- validation / errors ---
def test_bet_zero_no_items_400(client, session_id):
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 0, "bet_items": [],
        "target_item": target(), "chance": 0.5,
    })
    assert r.status_code == 400, r.text
    assert "detail" in r.json()


def test_bet_over_balance_400(client, session_id):
    bal = client.get(f"{BASE_URL}/api/user/{session_id}").json()["balance"]
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": bal + 1000000, "bet_items": [],
        "target_item": target(), "chance": 0.5,
    })
    assert r.status_code == 400, r.text


def test_missing_target_item_400(client, session_id):
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 1, "bet_items": [], "chance": 0.5,
    })
    assert r.status_code == 400, r.text


def test_invalid_chance_422(client, session_id):
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": 1, "bet_items": [],
        "target_item": target(), "chance": 0,
    })
    assert r.status_code == 422, r.text


def test_negative_bet_422(client, session_id):
    r = client.post(f"{BASE_URL}/api/upgrade", json={
        "session_id": session_id, "bet_amount": -5, "bet_items": [],
        "target_item": target(), "chance": 0.5,
    })
    assert r.status_code == 422, r.text


# --- cleanup ---
def test_cleanup(session_id):
    from pymongo import MongoClient
    env = dotenv_values("/app/backend/.env")
    mc = MongoClient(env["MONGO_URL"])
    db = mc[env["DB_NAME"]]
    db.users.delete_many({"session_id": session_id})
    db.upgrades.delete_many({"session_id": session_id})
    db.drops.delete_many({"session_id": session_id})
    assert db.users.find_one({"session_id": session_id}) is None
    mc.close()
