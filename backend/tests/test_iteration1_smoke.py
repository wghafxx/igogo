"""Iteration 1 smoke tests: public config/shop + guest presence + seeded auth user."""

import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values


frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = BASE_URL.rstrip("/") + "/api"


def _auth_headers(session_id: str) -> dict:
    secret = backend_env.get("JWT_SECRET")
    if not secret:
        pytest.skip("JWT_SECRET missing in backend/.env")
    token = jwt.encode(
        {
            "sub": session_id,
            "role": "user",
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "iat": datetime.now(timezone.utc),
        },
        secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class TestIteration1Smoke:
    """Critical endpoint smoke checks for current rapid-click regression iteration."""

    def test_game_config_shape(self):
        response = requests.get(f"{API}/game-config", timeout=20)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("rtp"), (float, int))
        assert isinstance(data.get("min_chance"), (float, int))
        assert isinstance(data.get("max_chance"), (float, int))
        assert isinstance(data.get("max_bet_ratio"), (float, int))

    def test_shop_has_items(self):
        response = requests.get(
            f"{API}/shop",
            params={"page": 1, "limit": 25, "sort": "price_desc"},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("items"), list)
        assert data.get("total", 0) >= len(data.get("items", []))
        assert data.get("page") == 1
        if data["items"]:
            first = data["items"][0]
            assert isinstance(first.get("id"), str)
            assert isinstance(first.get("name"), str)
            assert isinstance(first.get("price"), (float, int))

    def test_guest_presence(self):
        payload = {"session_id": "TEST_guest_presence_it1"}
        response = requests.post(f"{API}/presence", json=payload, timeout=20)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("online"), int)
        assert isinstance(data.get("upgrades"), int)

    def test_seeded_user_and_auth_me(self):
        session_id = "discord_it1_rapid_100hz"
        user_response = requests.get(f"{API}/user/{session_id}", headers=_auth_headers(session_id), timeout=20)
        assert user_response.status_code == 200
        user_data = user_response.json()
        assert user_data.get("session_id") == session_id
        assert isinstance(user_data.get("skins"), list)
        assert len(user_data.get("skins", [])) >= 100

        me_response = requests.get(f"{API}/auth/me", headers=_auth_headers(session_id), timeout=20)
        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data.get("session_id") == session_id
        assert me_data.get("discord_id") == "91001001"
