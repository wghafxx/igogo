"""Smoke tests after removing Emergent dependencies (iteration 3)."""
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://igogo-preview.preview.emergentagent.com").rstrip("/")
UA = "IGOGO-SmokeTest/1.0"
PHRASE = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]


def _s():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Content-Type": "application/json"})
    return s


def test_root():
    r = _s().get(f"{BASE}/api/")
    assert r.status_code == 200
    assert "BLOXGRADE" in r.text.upper()


def test_health():
    r = _s().get(f"{BASE}/api/health")
    assert r.status_code == 200


def test_rarities():
    r = _s().get(f"{BASE}/api/rarities")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_game_config():
    r = _s().get(f"{BASE}/api/game-config")
    assert r.status_code == 200


def test_stats():
    r = _s().get(f"{BASE}/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "online" in data or "onlineCount" in data or isinstance(data, dict)


def test_live_drops():
    r = _s().get(f"{BASE}/api/live-drops")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_shop():
    r = _s().get(f"{BASE}/api/shop")
    assert r.status_code == 200


def test_admin_login_success_and_session():
    s = _s()
    r = s.post(f"{BASE}/api/admin/login", json={"phrases": PHRASE})
    assert r.status_code == 200, r.text
    token = r.json().get("token")
    assert token
    s.headers["Authorization"] = f"Bearer {token}"
    r2 = s.get(f"{BASE}/api/admin/session")
    assert r2.status_code == 200, r2.text


def test_admin_login_wrong_last_word():
    bad = PHRASE[:-1] + ["wrong"]
    r = _s().post(f"{BASE}/api/admin/login", json={"phrases": bad})
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


def test_admin_session_ua_mismatch():
    s = _s()
    r = s.post(f"{BASE}/api/admin/login", json={"phrases": PHRASE})
    assert r.status_code == 200
    token = r.json()["token"]
    s2 = requests.Session()
    s2.headers.update({
        "User-Agent": "DifferentAgent/9.9",
        "Authorization": f"Bearer {token}",
    })
    r2 = s2.get(f"{BASE}/api/admin/session")
    # different UA should not grant access
    assert r2.status_code in (401, 403), f"got {r2.status_code}"
