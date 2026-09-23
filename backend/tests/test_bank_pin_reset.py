"""Backend tests for PIN-protected bank ops + factory reset (iteration).

Tests:
- POST /api/admin/login (10-word phrase, UA-bound session)
- PUT /api/admin/bank/settings PIN behaviour (no pin -> 422, wrong -> 403, right -> 200)
- POST /api/admin/bank/pool  ( +500 with PIN, wrong -> 403, missing -> 422 )
- POST /api/admin/bank/adjust ( +300 with PIN, wrong -> 403, missing -> 422 )
- Full economy reset: see isolated test_economy_reset.py
"""
import os
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path("/app/backend/.env"))
load_dotenv(Path("/app/frontend/.env"))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
UA = "BloxGradeTester/1.0 (pytest bank-pin-reset)"
SEED = "alpha bravo charlie delta echo foxtrot golf hotel india juliet".split()
PIN = "1001"


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
    r = s.post(f"{BASE_URL}/api/admin/login", json={"phrases": SEED})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    token = r.json().get("token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ---------- RTP settings PIN ----------
class TestBankSettingsPin:
    def test_no_pin_422(self, admin):
        r = admin.put(f"{BASE_URL}/api/admin/bank/settings", json={"rtp_target": 0.9})
        assert r.status_code == 422

    def test_wrong_pin_403(self, admin):
        r = admin.put(f"{BASE_URL}/api/admin/bank/settings", json={"rtp_target": 0.9, "pin": "0000"})
        assert r.status_code == 403
        assert "PIN" in r.json().get("detail", "")

    def test_correct_pin_persists(self, admin):
        try:
            r = admin.put(f"{BASE_URL}/api/admin/bank/settings", json={"rtp_target": 0.9, "pin": PIN})
            assert r.status_code == 200, r.text
            g = admin.get(f"{BASE_URL}/api/admin/bank")
            assert g.status_code == 200
            assert abs(float(g.json()["settings"]["rtp_target"]) - 0.9) < 1e-9
        finally:
            # Restore to 0.85
            admin.put(f"{BASE_URL}/api/admin/bank/settings", json={"rtp_target": 0.85, "pin": PIN})


# ---------- Pool + Adjust PIN ----------
class TestPoolAndAdjustPin:
    def test_pool_missing_pin_422(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/bank/pool", json={"amount": 500, "note": "test"})
        assert r.status_code == 422

    def test_pool_wrong_pin_403(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/bank/pool", json={"amount": 500, "note": "test", "pin": "0000"})
        assert r.status_code == 403

    def test_pool_correct_pin_increases_by_exact_amount(self, admin):
        before = float(admin.get(f"{BASE_URL}/api/admin/bank").json()["pool"])
        r = admin.post(f"{BASE_URL}/api/admin/bank/pool", json={"amount": 500, "note": "test", "pin": PIN})
        assert r.status_code == 200, r.text
        after = float(admin.get(f"{BASE_URL}/api/admin/bank").json()["pool"])
        assert round(after - before, 2) == 500.0

    def test_adjust_missing_pin_422(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/bank/adjust", json={"amount": 300, "note": "test"})
        assert r.status_code == 422

    def test_adjust_wrong_pin_403(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/bank/adjust", json={"amount": 300, "note": "test", "pin": "0000"})
        assert r.status_code == 403

    def test_adjust_correct_pin_increases_by_exact_amount(self, admin):
        before = float(admin.get(f"{BASE_URL}/api/admin/bank").json()["bank"])
        r = admin.post(f"{BASE_URL}/api/admin/bank/adjust", json={"amount": 300, "note": "test", "pin": PIN})
        assert r.status_code == 200, r.text
        after = float(admin.get(f"{BASE_URL}/api/admin/bank").json()["bank"])
        assert round(after - before, 2) == 300.0


# Full reset is covered only in test_economy_reset.py with disposable databases.
# Never exercise the destructive economy reset through this shared BASE_URL suite.
