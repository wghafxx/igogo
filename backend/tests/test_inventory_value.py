"""Iteration: inventory value + per-item sell/withdraw (skins endpoints)."""
import os
import subprocess
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base.rstrip("/")
BACKEND_ENV = dotenv_values("/app/backend/.env")


def mint_token(sub="discord_test_1", role="user"):
    return jwt.encode(
        {"sub": sub, "role": role, "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        BACKEND_ENV["JWT_SECRET"],
        algorithm="HS256",
    )


def reseed():
    subprocess.run(["python3", "/app/backend/tests/setup_test_user.py"], check=True, capture_output=True)


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {mint_token()}"})
    return s


@pytest.fixture(autouse=True)
def fresh_user():
    reseed()
    yield


class TestSkinsSellWithdraw:
    def test_auth_me_has_skins(self, client):
        r = client.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200, r.text
        u = r.json()
        assert "_id" not in u
        assert len(u["skins"]) == 3
        assert all("uid" in s and "price" in s for s in u["skins"])

    def test_sell_single_skin(self, client):
        u = client.get(f"{BASE_URL}/api/auth/me").json()
        skin = u["skins"][0]
        bal0 = u["balance"]
        r = client.post(f"{BASE_URL}/api/skins/sell", json={"uids": [skin["uid"]]})
        assert r.status_code == 200, r.text
        nu = r.json()
        assert "_id" not in nu
        assert len(nu["skins"]) == 2
        assert skin["uid"] not in [s["uid"] for s in nu["skins"]]
        assert nu["balance"] == pytest.approx(bal0 + skin["price"], abs=0.01)
        # persistence
        fresh = client.get(f"{BASE_URL}/api/auth/me").json()
        assert len(fresh["skins"]) == 2
        assert fresh["balance"] == pytest.approx(bal0 + skin["price"], abs=0.01)
        # history
        prof = client.get(f"{BASE_URL}/api/profile").json()
        assert any(h.get("kind") == "sold" for h in prof.get("item_history", []))

    def test_withdraw_single_skin(self, client):
        u = client.get(f"{BASE_URL}/api/auth/me").json()
        skin = u["skins"][0]
        bal0 = u["balance"]
        r = client.post(f"{BASE_URL}/api/skins/withdraw", json={"uids": [skin["uid"]]})
        assert r.status_code == 200, r.text
        nu = r.json()
        assert len(nu["skins"]) == 2
        assert nu["balance"] == pytest.approx(bal0, abs=0.01)
        fresh = client.get(f"{BASE_URL}/api/auth/me").json()
        assert skin["uid"] not in [s["uid"] for s in fresh["skins"]]
        prof = client.get(f"{BASE_URL}/api/profile").json()
        assert any(h.get("kind") == "withdrawn" for h in prof.get("item_history", []))
        assert prof["stats"]["withdrawn_count"] >= 1

    def test_sell_all(self, client):
        u = client.get(f"{BASE_URL}/api/auth/me").json()
        total = sum(s["price"] for s in u["skins"])
        uids = [s["uid"] for s in u["skins"]]
        r = client.post(f"{BASE_URL}/api/skins/sell", json={"uids": uids})
        assert r.status_code == 200, r.text
        nu = r.json()
        assert nu["skins"] == []
        assert nu["balance"] == pytest.approx(u["balance"] + total, abs=0.01)

    def test_sell_unknown_uid(self, client):
        r = client.post(f"{BASE_URL}/api/skins/sell", json={"uids": ["does-not-exist"]})
        assert r.status_code in (200, 400, 404), r.text
        if r.status_code == 200:
            assert len(r.json()["skins"]) == 3

    def test_sell_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/skins/sell", json={"uids": ["x"]})
        assert r.status_code in (401, 403), r.text

    def test_sell_invalid_payload(self, client):
        r = client.post(f"{BASE_URL}/api/skins/sell", json={})
        assert r.status_code == 422, r.text

    def test_double_sell_same_uid(self, client):
        u = client.get(f"{BASE_URL}/api/auth/me").json()
        uid = u["skins"][0]["uid"]
        price = u["skins"][0]["price"]
        client.post(f"{BASE_URL}/api/skins/sell", json={"uids": [uid]})
        r = client.post(f"{BASE_URL}/api/skins/sell", json={"uids": [uid]})
        assert r.status_code in (200, 400, 404), r.text
        fresh = client.get(f"{BASE_URL}/api/auth/me").json()
        # balance must not be credited twice
        assert fresh["balance"] == pytest.approx(u["balance"] + price, abs=0.01)
