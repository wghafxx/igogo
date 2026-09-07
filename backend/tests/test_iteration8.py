"""Iteration 8 — deposit request wizard backend: /api/deposit/info receivers,
POST /api/deposits (roblox gate, validation, cooldown, pending cap), cancel, admin deposits filters."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
UA = "iteration8-tester/1.0"

SEED = [
    "0u1o0gyxz", "bg7gw7mnt", "zm7pcp8ip", "5hccvev8s", "7i59vojax",
    "q8bheol0k", "di8ihi1wr", "g5bkbe61g", "kiulp6xqy", "5mdyfh6hp",
]


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


def mint(session_id: str) -> str:
    return jwt.encode(
        {"sub": session_id, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        os.environ["JWT_SECRET"], algorithm="HS256",
    )


def make_user(db, suffix, roblox=True, promo=None):
    sid = f"TEST_it8_{suffix}_{uuid.uuid4().hex[:6]}"
    doc = {"session_id": sid, "balance": 0.0, "nickname": f"TEST_{suffix}", "discord_id": sid, "skins": []}
    if roblox:
        doc["roblox_nick"] = f"TEST_{suffix}_rbx"
        doc["roblox_link"] = "https://www.roblox.com/users/1/profile"
    if promo:
        doc["promo_code"] = promo
        doc["promo_bonus"] = 0.10
    db.users.insert_one(dict(doc))
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {mint(sid)}", "User-Agent": UA})
    return sid, s


@pytest.fixture(scope="module")
def created(mongo):
    sids = []
    yield sids
    if sids:
        mongo.users.delete_many({"session_id": {"$in": sids}})
        mongo.deposits.delete_many({"session_id": {"$in": sids}})


@pytest.fixture(scope="module")
def admin_client(mongo):
    mongo.login_attempts.delete_many({})
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    r = s.post(f"{API}/admin/login", json={"phrases": SEED})
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    yield s
    mongo.login_attempts.delete_many({})


# ---------- deposit info / receiver asset ----------
class TestDepositInfo:
    def test_info_receivers_and_cooldown(self):
        r = requests.get(f"{API}/deposit/info", headers={"User-Agent": UA})
        assert r.status_code == 200
        d = r.json()
        assert d["cooldown"] == 60
        assert d["min_rap"] == 20
        assert d["fee"] == 0.2
        recs = d["receivers"]
        assert isinstance(recs, list) and len(recs) >= 1
        y = next(x for x in recs if x["id"] == "ysrent1")
        assert y["nickname"] == "YSrent1"
        assert y["handle"] == "@YSrent1"
        assert y["avatar"] == "/receivers/ysrent1.png"
        assert "roblox.com" in y["friend_url"]

    def test_receiver_avatar_served(self):
        r = requests.get(f"{BASE_URL}/receivers/ysrent1.png", headers={"User-Agent": UA})
        assert r.status_code == 200, r.status_code
        assert r.headers.get("content-type", "").startswith("image/"), r.headers.get("content-type")
        assert len(r.content) > 500


# ---------- create deposit ----------
class TestCreateDeposit:
    def test_requires_auth(self):
        r = requests.post(f"{API}/deposits", json={"description": "abc", "expected_rap": 50, "receiver_id": "ysrent1"},
                          headers={"User-Agent": UA})
        assert r.status_code == 401

    def test_roblox_gate_then_success(self, mongo, created):
        sid, s = make_user(mongo, "gate", roblox=False)
        created.append(sid)
        payload = {"description": "TEST_ skin one, skin two", "expected_rap": 250, "receiver_id": "ysrent1"}
        r = s.post(f"{API}/deposits", json=payload)
        assert r.status_code == 400, r.text
        assert "Roblox" in r.json()["detail"]

        rb = s.post(f"{API}/profile/roblox", json={"roblox_nick": "TEST_nick", "roblox_link": "https://www.roblox.com/users/5/profile"})
        assert rb.status_code == 200, rb.text
        assert rb.json()["roblox_nick"] == "TEST_nick"

        r = s.post(f"{API}/deposits", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["expected_rap"] == 250
        assert d["receiver_id"] == "ysrent1"
        assert d["receiver_nick"] == "YSrent1"
        assert d["roblox_nick"] == "TEST_nick"
        assert d["status"] == "pending"
        assert d["promo_bonus"] == 0
        assert "_id" not in d
        assert isinstance(d["id"], str)

        my = s.get(f"{API}/deposits/my")
        assert my.status_code == 200
        rows = my.json()
        assert any(x["id"] == d["id"] and x["status"] == "pending" for x in rows)
        assert all("_id" not in x for x in rows)

    def test_promo_bonus_persisted(self, mongo, created):
        sid, s = make_user(mongo, "promo", promo="SINZUKU")
        created.append(sid)
        r = s.post(f"{API}/deposits", json={"description": "TEST_ promo dep", "expected_rap": 100, "receiver_id": "ysrent1"})
        assert r.status_code == 200, r.text
        assert r.json()["promo_bonus"] == 0.10
        assert r.json()["promo_code"] == "SINZUKU"

    def test_rate_limit_429(self, mongo, created):
        sid, s = make_user(mongo, "rate")
        created.append(sid)
        p = {"description": "TEST_ first", "expected_rap": 50, "receiver_id": "ysrent1"}
        assert s.post(f"{API}/deposits", json=p).status_code == 200
        r2 = s.post(f"{API}/deposits", json={**p, "description": "TEST_ second"})
        assert r2.status_code == 429, r2.text
        assert "сек" in r2.json()["detail"]

    def test_min_rap_validation(self, mongo, created):
        sid, s = make_user(mongo, "min")
        created.append(sid)
        r = s.post(f"{API}/deposits", json={"description": "TEST_ low", "expected_rap": 10, "receiver_id": "ysrent1"})
        assert r.status_code == 422, r.text

    def test_short_description_validation(self, mongo, created):
        sid, s = make_user(mongo, "desc")
        created.append(sid)
        r = s.post(f"{API}/deposits", json={"description": "a", "expected_rap": 50, "receiver_id": "ysrent1"})
        assert r.status_code == 422, r.text

    def test_unknown_receiver(self, mongo, created):
        sid, s = make_user(mongo, "recv")
        created.append(sid)
        r = s.post(f"{API}/deposits", json={"description": "TEST_ bad receiver", "expected_rap": 50, "receiver_id": "nobody"})
        assert r.status_code == 400, r.text
        assert "не найден" in r.json()["detail"]

    def test_max_five_pending(self, mongo, created):
        sid, s = make_user(mongo, "cap")
        created.append(sid)
        # insert 5 pending directly (bypass cooldown) then attempt a 6th via API
        old = datetime.now(timezone.utc) - timedelta(seconds=600)
        mongo.deposits.insert_many([{
            "id": str(uuid.uuid4()), "session_id": sid, "status": "pending", "expected_rap": 50,
            "receiver_id": "ysrent1", "receiver_nick": "YSrent1", "description": "TEST_ seeded",
            "created_at": old, "resolved_at": None, "amount": None,
        } for _ in range(5)])
        r = s.post(f"{API}/deposits", json={"description": "TEST_ sixth", "expected_rap": 50, "receiver_id": "ysrent1"})
        assert r.status_code == 400, r.text
        assert "5 заявок" in r.json()["detail"]


# ---------- cancel ----------
class TestCancelDeposit:
    def test_cancel_own_pending_and_idempotency(self, mongo, created):
        sid, s = make_user(mongo, "cancel")
        created.append(sid)
        r = s.post(f"{API}/deposits", json={"description": "TEST_ cancel me", "expected_rap": 250, "receiver_id": "ysrent1"})
        assert r.status_code == 200, r.text
        dep_id = r.json()["id"]

        c = s.post(f"{API}/deposits/{dep_id}/cancel")
        assert c.status_code == 200, c.text
        assert c.json()["ok"] is True

        rows = s.get(f"{API}/deposits/my").json()
        row = next(x for x in rows if x["id"] == dep_id)
        assert row["status"] == "cancelled"
        assert row["resolved_at"]

        again = s.post(f"{API}/deposits/{dep_id}/cancel")
        assert again.status_code == 404, again.text

    def test_cannot_cancel_other_users_deposit(self, mongo, created):
        sid_a, sa = make_user(mongo, "owner")
        sid_b, sb = make_user(mongo, "thief")
        created.extend([sid_a, sid_b])
        r = sa.post(f"{API}/deposits", json={"description": "TEST_ mine", "expected_rap": 60, "receiver_id": "ysrent1"})
        assert r.status_code == 200, r.text
        dep_id = r.json()["id"]
        c = sb.post(f"{API}/deposits/{dep_id}/cancel")
        assert c.status_code == 404, c.text
        assert mongo.deposits.find_one({"id": dep_id})["status"] == "pending"

    def test_unknown_id_404(self, mongo, created):
        sid, s = make_user(mongo, "unk")
        created.append(sid)
        assert s.post(f"{API}/deposits/{uuid.uuid4()}/cancel").status_code == 404


# ---------- admin ----------
class TestAdminDeposits:
    def test_status_filters(self, admin_client, mongo, created):
        sid, s = make_user(mongo, "adm")
        created.append(sid)
        r = s.post(f"{API}/deposits", json={"description": "TEST_ admin flow", "expected_rap": 250, "receiver_id": "ysrent1"})
        assert r.status_code == 200, r.text
        dep_id = r.json()["id"]

        pend = admin_client.get(f"{API}/admin/deposits", params={"status": "pending"})
        assert pend.status_code == 200
        row = next((x for x in pend.json() if x["id"] == dep_id), None)
        assert row is not None
        assert row["expected_rap"] == 250
        assert row["receiver_nick"] == "YSrent1"

        assert s.post(f"{API}/deposits/{dep_id}/cancel").status_code == 200
        canc = admin_client.get(f"{API}/admin/deposits", params={"status": "cancelled"})
        assert canc.status_code == 200
        assert any(x["id"] == dep_id for x in canc.json())
        assert all("_id" not in x for x in canc.json())

        # admin must not be able to confirm a cancelled deposit
        conf = admin_client.post(f"{API}/admin/deposits/{dep_id}/confirm", json={"rap": 250})
        assert conf.status_code == 404, conf.text
        assert mongo.deposits.find_one({"id": dep_id})["status"] == "cancelled"
        assert mongo.users.find_one({"session_id": sid})["balance"] == 0.0

    def test_bogus_status_400(self, admin_client):
        r = admin_client.get(f"{API}/admin/deposits", params={"status": "bogus"})
        assert r.status_code == 400, r.text

    def test_requires_admin_token(self):
        r = requests.get(f"{API}/admin/deposits", params={"status": "cancelled"}, headers={"User-Agent": UA})
        assert r.status_code in (401, 403)
