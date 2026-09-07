"""Iteration 7: per-player automatic throttle (player_deny_probability), admin bank settings, /admin/players."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pymongo
import pytest
import requests
from dotenv import dotenv_values, load_dotenv

load_dotenv("/app/backend/.env")
frontend_env = dotenv_values("/app/frontend/.env")
base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base.rstrip("/") + "/api"

UA = "iteration7-tester/1.0"
SEED = ["0u1o0gyxz", "bg7gw7mnt", "zm7pcp8ip", "5hccvev8s", "7i59vojax", "q8bheol0k", "di8ihi1wr", "g5bkbe61g", "kiulp6xqy", "5mdyfh6hp"]
GAME_COLLECTIONS = ["users", "deposits", "upgrades", "drops", "withdrawals", "item_history", "bank_state", "bank_ledger", "bank_settings"]
GLOVE_CASE = "case-glove-case"
GLOVE_PRICE = 43.0


@pytest.fixture(scope="module")
def db():
    client = pymongo.MongoClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin(db):
    """Admin session (token bound to User-Agent). Clears login lockout first."""
    db.login_attempts.delete_many({})
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
    r = s.post(f"{BASE}/admin/login", json={"phrases": SEED})
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


def user_session(sid):
    tok = jwt.encode({"sub": sid, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, os.environ["JWT_SECRET"], algorithm="HS256")
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "User-Agent": UA, "Authorization": f"Bearer {tok}"})
    return s


def make_player(db, admin, rap, balance):
    """Create a player with a confirmed deposit of `rap` RAP and a Mongo-set balance."""
    sid = f"discord_it7_{uuid.uuid4().hex[:8]}"
    db.users.insert_one({"session_id": sid, "balance": 0.0, "nickname": f"IT7_{sid[-4:]}", "skins": [], "discord_id": sid, "created_at": datetime.now(timezone.utc)})
    u = user_session(sid)
    dep = u.post(f"{BASE}/deposits", json={"description": "TEST_it7 deposit"})
    assert dep.status_code == 200, dep.text
    conf = admin.post(f"{BASE}/admin/deposits/{dep.json()['id']}/confirm", json={"rap": rap})
    assert conf.status_code == 200, conf.text
    db.users.update_one({"session_id": sid}, {"$set": {"balance": float(balance)}})
    return sid, u


# ---------- PUT /api/admin/bank/settings ----------
class TestBankSettings:
    def test_empty_payload_400(self, admin):
        r = admin.put(f"{BASE}/admin/bank/settings", json={})
        assert r.status_code == 400, r.text
        assert "detail" in r.json()

    def test_personal_rtp_out_of_range_422(self, admin):
        r = admin.put(f"{BASE}/admin/bank/settings", json={"personal_rtp": 0.4})
        assert r.status_code == 422, r.text

    def test_takeout_multiplier_out_of_range_422(self, admin):
        r = admin.put(f"{BASE}/admin/bank/settings", json={"takeout_multiplier": 6})
        assert r.status_code == 422, r.text

    def test_strictness_out_of_range_422(self, admin):
        assert admin.put(f"{BASE}/admin/bank/settings", json={"strictness": 2.0}).status_code == 422
        assert admin.put(f"{BASE}/admin/bank/settings", json={"strictness": 0.1}).status_code == 422

    def test_valid_update_persists_and_ledger_entry(self, admin, db):
        r = admin.put(f"{BASE}/admin/bank/settings", json={"strictness": 1.2, "personal_rtp": 0.8})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["strictness"] == 1.2 and body["personal_rtp"] == 0.8
        assert body["rtp_target"] == 0.90 or isinstance(body["rtp_target"], float)

        g = admin.get(f"{BASE}/admin/bank")
        assert g.status_code == 200
        st = g.json()["settings"]
        assert st["strictness"] == 1.2, st
        assert st["personal_rtp"] == 0.8, st
        assert "takeout_multiplier" in st and "rtp_target" in st

        led = list(db.bank_ledger.find({"kind": "settings"}, {"_id": 0}).sort("created_at", -1).limit(1))
        assert led, "no kind=settings ledger entry created"
        assert led[0]["note"] and "Жёсткость" in led[0]["note"] and "120%" in led[0]["note"], led[0]["note"]
        assert led[0]["amount"] == 0.0

        # restore defaults for later simulations
        assert admin.put(f"{BASE}/admin/bank/settings", json={"strictness": 1.0, "personal_rtp": 0.85, "takeout_multiplier": 2.0, "rtp_target": 0.9}).status_code == 200

    def test_no_admin_token_forbidden(self):
        r = requests.put(f"{BASE}/admin/bank/settings", json={"strictness": 1.0}, headers={"User-Agent": UA})
        assert r.status_code in (401, 403), r.status_code


# ---------- GET /api/admin/players ----------
class TestAdminPlayers:
    def test_requires_admin(self):
        r = requests.get(f"{BASE}/admin/players", headers={"User-Agent": UA})
        assert r.status_code in (401, 403), r.status_code

    def test_returns_rows_with_expected_fields(self, admin, db):
        # ensure at least one game exists
        if db.upgrades.count_documents({}) == 0:
            pytest.skip("no upgrades in db yet; covered by throttle tests")
        r = admin.get(f"{BASE}/admin/players")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and rows
        keys = {"session_id", "nickname", "deposits", "wagered", "paid", "rtp", "games", "wins", "forced", "balance", "inventory", "withdrawn", "net", "last_game"}
        for row in rows:
            assert keys <= set(row), keys - set(row)
            assert "_id" not in row
            assert isinstance(row["session_id"], str)
            expected_rtp = (row["paid"] / row["wagered"]) if row["wagered"] else 0.0
            assert abs(row["rtp"] - expected_rtp) < 1e-6


# ---------- take-out cap / per-player throttle ----------
class TestPlayerThrottle:
    def test_takeout_cap_enforced(self, admin, db):
        for c in GAME_COLLECTIONS:
            db[c].delete_many({})
        admin.put(f"{BASE}/admin/bank/settings", json={"strictness": 1.0, "personal_rtp": 0.85, "takeout_multiplier": 2.0, "rtp_target": 0.9})
        sid, u = make_player(db, admin, rap=50, balance=5000)
        assert admin.post(f"{BASE}/admin/bank/adjust", json={"amount": 20000, "note": "TEST_it7 topup"}).status_code == 200

        bet = round(GLOVE_PRICE * 0.75, 2)
        ok = 0
        for _ in range(60):
            r = u.post(f"{BASE}/upgrade", json={"session_id": sid, "bet_amount": bet, "target_item": {"id": GLOVE_CASE}})
            if r.status_code != 200:
                pytest.fail(f"/upgrade failed {r.status_code}: {r.text[:300]}")
            ok += 1
        assert ok == 60

        ups = list(db.upgrades.find({"session_id": sid}, {"_id": 0}))
        assert len(ups) == 60
        paid = sum(float(x["target_item"]["price"]) for x in ups if x.get("win"))
        deposits = 50 * 0.8
        cap = max(deposits, 20) * 2.0 + 0.3 * deposits + 1e-6
        assert paid <= cap, f"paid {paid} exceeds cap {cap}"

        forced_player = [x for x in ups if x.get("forced_reason") == "player"]
        assert forced_player, "no forced_reason='player' rows produced in 60 upgrades"
        for x in forced_player:
            assert x["win"] is False
            assert x["forced_loss"] is True
            assert abs(x["roll"] * 360 - 180) >= x["chance"] * 180 - 1e-9, f"forced loss roll inside win zone: {x['roll']} {x['chance']}"
            assert "player" in (x.get("protection") or {}), x.get("protection")
            assert "p" in x["protection"]["player"]
        # all forced rows must carry a reason, non-forced must not
        for x in ups:
            if x.get("forced_loss"):
                assert x.get("forced_reason") in ("bank", "rtp", "player", "lock", "error")
            else:
                assert x.get("forced_reason") is None

    def test_small_wins_still_pass(self, admin, db):
        for c in ["users", "deposits", "upgrades", "drops", "withdrawals", "item_history", "bank_state", "bank_ledger"]:
            db[c].delete_many({})
        sid, u = make_player(db, admin, rap=1000, balance=3000)
        assert admin.post(f"{BASE}/admin/bank/adjust", json={"amount": 50000, "note": "TEST_it7 topup2"}).status_code == 200
        bet = round(GLOVE_PRICE * 0.75, 2)
        for _ in range(40):
            r = u.post(f"{BASE}/upgrade", json={"session_id": sid, "bet_amount": bet, "target_item": {"id": GLOVE_CASE}})
            assert r.status_code == 200, r.text
        ups = list(db.upgrades.find({"session_id": sid}, {"_id": 0}))
        wins = [x for x in ups if x.get("win")]
        forced_player = [x for x in ups if x.get("forced_reason") == "player"]
        print(f"small-win sim: games={len(ups)} wins={len(wins)} forced_player={len(forced_player)} forced_total={sum(1 for x in ups if x.get('forced_loss'))}")
        assert len(wins) > 0, "no natural wins paid for a small-ratio player"
        assert len(forced_player) <= len(wins), f"player-throttle denials ({len(forced_player)}) exceed natural wins ({len(wins)})"
        self._sid = sid

    def test_profile_hides_protection_fields(self, db):
        sid = db.upgrades.find_one({}, sort=[("created_at", -1)])["session_id"]
        u = user_session(sid)
        r = u.get(f"{BASE}/profile")
        assert r.status_code == 200, r.text
        games = r.json()["games"]
        assert games, "profile has no games"
        blocked = {"forced_loss", "forced_reason", "protection", "roll"}
        for g in games:
            leaked = blocked & set(g)
            assert not leaked, f"profile leaks {leaked}"
        assert "'_id'" not in str(r.json()).replace("session_id", "sid")
