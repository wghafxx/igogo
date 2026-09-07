"""BLOXGRADE iteration-3 backend tests: upgrade validation/limits, deposit info, promo,
profile, skins sell/withdraw, roblox link, live-drops integrity."""
import os
import sys
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = base_url.rstrip("/") + "/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")

SESSION_PREFIX = "discord_test_qa3"


@pytest.fixture(scope="module")
def mongo():
    cl = MongoClient(MONGO_URL)
    yield cl[DB_NAME]
    cl.close()


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def shop_items(client):
    r = client.get(f"{API}/shop")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 2
    return items


@pytest.fixture(scope="class")
def SESSION(request):
    """Unique session per test class so xdist workers do not race on the same user."""
    return f"{SESSION_PREFIX}_{request.cls.__name__}"


@pytest.fixture(scope="class")
def token(SESSION):
    from server import make_token  # noqa: E402
    return make_token(SESSION)


@pytest.fixture(scope="class")
def auth(client, token):
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def reset_user(mongo, SESSION, db_skins=None, balance=999000.0):
    mongo.users.update_one(
        {"session_id": SESSION},
        {"$set": {
            "session_id": SESSION,
            "balance": balance,
            "nickname": "QATester",
            "avatar": "https://cdn.discordapp.com/embed/avatars/0.png",
            "discord_id": "1",
            "skins": db_skins or [],
        }},
        upsert=True,
    )


@pytest.fixture(scope="class", autouse=True)
def setup_user(mongo, client, SESSION):
    client.get(f"{API}/user/{SESSION}")
    reset_user(mongo, SESSION)
    yield
    mongo.users.delete_many({"session_id": SESSION})
    mongo.item_history.delete_many({"session_id": SESSION})
    mongo.upgrades.delete_many({"session_id": SESSION})
    mongo.drops.delete_many({"session_id": SESSION})
    mongo.withdrawals.delete_many({"session_id": SESSION})


# ---------- deposit info ----------
class TestDeposit:
    def test_deposit_info(self, client, SESSION):
        r = client.get(f"{API}/deposit/info")
        assert r.status_code == 200
        d = r.json()
        assert "roblox.com/share" in d["friend_url"]
        assert d["min_rap"] == 20
        assert d["fee"] == 0.2


# ---------- promo ----------
class TestPromo:
    def test_promo_no_auth(self, client, SESSION):
        r = requests.post(f"{API}/promo/apply", json={"code": "sinzuku"})
        assert r.status_code == 401

    def test_promo_valid_lowercase(self, auth, client, SESSION):
        r = auth.post(f"{API}/promo/apply", json={"code": "sinzuku"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["promo_code"] == "SINZUKU"
        assert d["promo_bonus"] == 0.1
        me = auth.get(f"{API}/auth/me").json()
        assert me["promo_code"] == "SINZUKU" and me["promo_bonus"] == 0.1

    def test_promo_invalid(self, auth, SESSION):
        r = auth.post(f"{API}/promo/apply", json={"code": "NOPE123"})
        assert r.status_code == 400
        assert "detail" in r.json()


# ---------- roblox profile ----------
class TestRoblox:
    def test_save_roblox(self, auth, SESSION):
        r = auth.post(f"{API}/profile/roblox", json={
            "roblox_nick": "TestBuilder",
            "roblox_link": "https://www.roblox.com/share?code=abc&type=Profile",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["roblox_nick"] == "TestBuilder"
        me = auth.get(f"{API}/auth/me").json()
        assert me["roblox_nick"] == "TestBuilder"
        assert me["roblox_link"] == "https://www.roblox.com/share?code=abc&type=Profile"

    def test_bad_link_domain(self, auth, SESSION):
        r = auth.post(f"{API}/profile/roblox", json={
            "roblox_nick": "TestBuilder",
            "roblox_link": "https://evil.example.com/share?code=abc",
        })
        assert r.status_code == 400

    def test_short_nick(self, auth, SESSION):
        r = auth.post(f"{API}/profile/roblox", json={
            "roblox_nick": "ab",
            "roblox_link": "https://www.roblox.com/share?code=abc",
        })
        assert r.status_code == 422


# ---------- upgrade ----------
class TestUpgradeValidation:
    def test_missing_target(self, client, mongo, SESSION):
        reset_user(mongo, SESSION)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 10, "bet_items": [], "chance": 0.5})
        assert r.status_code == 400
        assert "Выберите скин" in r.json()["detail"]

    def test_unknown_target(self, client, mongo, SESSION):
        reset_user(mongo, SESSION)
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 10, "bet_items": [],
            "target_item": {"id": "does-not-exist"}, "chance": 0.5})
        assert r.status_code == 400
        assert "не найден" in r.json()["detail"]

    def test_chance_above_max(self, client, mongo, shop_items, SESSION):
        reset_user(mongo, SESSION)
        target = max(shop_items, key=lambda i: i["price"])
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 10, "bet_items": [],
            "target_item": {"id": target["id"]}, "chance": 0.9})
        assert r.status_code == 400
        assert "75" in r.json()["detail"]

    def test_bet_above_75pct(self, client, mongo, shop_items, SESSION):
        reset_user(mongo, SESSION)
        target = max(shop_items, key=lambda i: i["price"])
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": target["price"] * 0.75 + 1, "bet_items": [],
            "target_item": {"id": target["id"]}, "chance": 0.75})
        assert r.status_code == 400
        assert "75%" in r.json()["detail"]

    def test_invalid_bet_item_uid(self, client, mongo, shop_items, SESSION):
        reset_user(mongo, SESSION)
        target = max(shop_items, key=lambda i: i["price"])
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [{"uid": "bogus-uid"}],
            "target_item": {"id": target["id"]}, "chance": 0.3})
        assert r.status_code == 400
        assert "инвентаре" in r.json()["detail"]

    def test_bet_items_total_over_limit(self, client, mongo, shop_items, SESSION):
        cheap = min(shop_items, key=lambda i: i["price"])
        target = sorted(shop_items, key=lambda i: i["price"])[1]
        # give user an expensive skin, target cheap one -> over 75%
        expensive = max(shop_items, key=lambda i: i["price"])
        reset_user(mongo, SESSION, [{**expensive, "uid": "qa-uid-exp"}])
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": 0, "bet_items": [{"uid": "qa-uid-exp"}],
            "target_item": {"id": target["id"] if target["price"] < expensive["price"] else cheap["id"]},
            "chance": 0.75})
        assert r.status_code == 400
        assert "75%" in r.json()["detail"]
        # skin must NOT be consumed on rejected upgrade
        u = mongo.users.find_one({"session_id": SESSION})
        assert any(sk.get("uid") == "qa-uid-exp" for sk in u["skins"])


class TestUpgradeFlow:
    def test_bet_skin_consumed_and_balance_debited(self, client, mongo, shop_items, SESSION):
        cheap = min(shop_items, key=lambda i: i["price"])
        target = max(shop_items, key=lambda i: i["price"])
        reset_user(mongo, SESSION, [{**cheap, "uid": "qa-uid-1"}], balance=1000.0)
        bet = 50.0
        r = client.post(f"{API}/upgrade", json={
            "session_id": SESSION, "bet_amount": bet, "bet_items": [{"uid": "qa-uid-1"}],
            "target_item": {"id": target["id"]},
            "chance": (bet + cheap["price"]) / target["price"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["balance"] == pytest.approx(1000.0 - bet)
        assert 0 < d["chance"] <= 0.75
        u = mongo.users.find_one({"session_id": SESSION})
        assert not any(sk.get("uid") == "qa-uid-1" for sk in u["skins"])
        assert u["balance"] == pytest.approx(1000.0 - bet)
        if d["win"]:
            assert any(sk["id"] == target["id"] and sk.get("uid") and sk.get("image")
                       for sk in u["skins"])

    def test_win_pushes_skin_drop_and_history(self, client, mongo, shop_items, SESSION):
        """Retry at 75% chance until a win occurs, then assert win side-effects."""
        target = max(shop_items, key=lambda i: i["price"])
        win_res = None
        for _ in range(25):
            reset_user(mongo, SESSION, [], balance=999000.0)
            bet = round(target["price"] * 0.75, 2)
            r = client.post(f"{API}/upgrade", json={
                "session_id": SESSION, "bet_amount": bet, "bet_items": [],
                "target_item": {"id": target["id"]}, "chance": 0.75})
            assert r.status_code == 200, r.text
            if r.json()["win"]:
                win_res = r.json()
                break
        assert win_res is not None, "no win in 25 tries at 75% chance (p<1e-14) - RNG broken"

        u = mongo.users.find_one({"session_id": SESSION})
        won = [sk for sk in u["skins"] if sk["id"] == target["id"]]
        assert won, "won skin not added to user"
        assert won[0].get("uid") and won[0].get("image")

        drops = client.get(f"{API}/live-drops?limit=50").json()
        mine = [d for d in drops if d["session_id"] == SESSION]
        assert mine, "win did not create a live drop"
        assert mine[0]["item_image"]
        assert mine[0]["item_name"] == target["name"]

        hist = mongo.item_history.find_one({"session_id": SESSION, "kind": "won"})
        assert hist is not None and hist["price"] == pytest.approx(target["price"])


# ---------- profile ----------
class TestProfile:
    def test_profile_no_auth(self, SESSION):
        r = requests.get(f"{API}/profile")
        assert r.status_code == 401

    def test_profile_shape(self, auth, mongo, shop_items, SESSION):
        reset_user(mongo, SESSION, [{**shop_items[0], "uid": "qa-p-1"}], balance=500.0)
        r = auth.get(f"{API}/profile")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user"]["session_id"] == SESSION
        assert d["user"]["balance"] == 500.0
        for k in ("upgrades", "wins", "withdrawn_count", "withdrawn_sum"):
            assert k in d["stats"]
        assert isinstance(d["item_history"], list)
        assert isinstance(d["games"], list)
        assert "best_drop" in d
        assert "_id" not in d["user"]
        assert all("_id" not in h for h in d["item_history"])
        assert all("_id" not in g for g in d["games"])


class TestSellWithdraw:
    def test_sell_increases_balance(self, auth, mongo, shop_items, SESSION):
        item = shop_items[0]
        reset_user(mongo, SESSION, [{**item, "uid": "qa-s-1"}], balance=100.0)
        r = auth.post(f"{API}/skins/sell", json={"uids": ["qa-s-1"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["balance"] == pytest.approx(100.0 + item["price"])
        assert not any(sk.get("uid") == "qa-s-1" for sk in d["skins"])
        me = auth.get(f"{API}/auth/me").json()
        assert me["balance"] == pytest.approx(100.0 + item["price"])
        h = mongo.item_history.find_one({"session_id": SESSION, "kind": "sold"})
        assert h and h["price"] == pytest.approx(item["price"])

    def test_sell_invalid_uid(self, auth, mongo, shop_items, SESSION):
        reset_user(mongo, SESSION, [{**shop_items[0], "uid": "qa-s-2"}], balance=0.0)
        r = auth.post(f"{API}/skins/sell", json={"uids": ["nope"]})
        assert r.status_code == 400

    def test_withdraw_creates_pending(self, auth, mongo, shop_items, SESSION):
        item = shop_items[1]
        reset_user(mongo, SESSION, [{**item, "uid": "qa-w-1"}], balance=0.0)
        mongo.withdrawals.delete_many({"session_id": SESSION})
        before = auth.get(f"{API}/profile").json()["stats"]["withdrawn_count"]
        r = auth.post(f"{API}/skins/withdraw", json={"uids": ["qa-w-1"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["balance"] == 0.0
        assert not any(sk.get("uid") == "qa-w-1" for sk in d["skins"])
        w = mongo.withdrawals.find_one({"session_id": SESSION})
        assert w and w["status"] == "pending" and w["item"]["uid"] == "qa-w-1"
        after = auth.get(f"{API}/profile").json()
        assert after["stats"]["withdrawn_count"] == before + 1
        assert after["stats"]["withdrawn_sum"] >= item["price"]
        assert any(h["kind"] == "withdrawn" for h in after["item_history"])

    def test_sell_all(self, auth, mongo, shop_items, SESSION):
        skins = [{**shop_items[i], "uid": f"qa-all-{i}"} for i in range(2)]
        total = sum(s["price"] for s in skins)
        reset_user(mongo, SESSION, skins, balance=0.0)
        r = auth.post(f"{API}/skins/sell", json={"uids": [s["uid"] for s in skins]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["balance"] == pytest.approx(total)
        assert d["skins"] == []


# ---------- live drops integrity ----------
class TestLiveDrops:
    def test_no_null_image_or_balance_type(self, client, SESSION):
        r = client.get(f"{API}/live-drops?limit=100")
        assert r.status_code == 200
        for d in r.json():
            assert d["item_image"], f"drop with empty image: {d}"
            assert d["item_type"] != "balance", f"balance drop present: {d}"
            assert d["item_price"] >= 0
