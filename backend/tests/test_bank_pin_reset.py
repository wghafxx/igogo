"""Backend tests for PIN-protected bank ops + factory reset (iteration).

Tests:
- POST /api/admin/login (10-word phrase, UA-bound session)
- PUT /api/admin/bank/settings PIN behaviour (no pin -> 422, wrong -> 403, right -> 200)
- POST /api/admin/bank/pool  ( +500 with PIN, wrong -> 403, missing -> 422 )
- POST /api/admin/bank/adjust ( +300 with PIN, wrong -> 403, missing -> 422 )
- POST /api/admin/bank/reset (factory zero; games/wagered unchanged; Mongo state clean;
    pool topup after reset does NOT get back-filled from history)
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


# ---------- Full bank reset ----------
class TestBankReset:
    def test_wrong_pin_reset_forbidden_and_no_change(self, admin, db):
        before_state = db.bank_state.find_one({"id": "main"}, {"_id": 0}) or {}
        before_ledger = db.bank_ledger.count_documents({})
        r = admin.post(f"{BASE_URL}/api/admin/bank/reset", json={"pin": "0000"})
        assert r.status_code == 403
        after_state = db.bank_state.find_one({"id": "main"}, {"_id": 0}) or {}
        assert float(after_state.get("bank") or 0) == float(before_state.get("bank") or 0)
        assert float(after_state.get("pool") or 0) == float(before_state.get("pool") or 0)
        assert db.bank_ledger.count_documents({}) == before_ledger

    def test_reset_missing_pin_422(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/bank/reset", json={})
        assert r.status_code == 422

    def test_reset_correct_pin_resets_everything(self, admin, db):
        before_bank = admin.get(f"{BASE_URL}/api/admin/bank").json()
        games_total_before = int(before_bank["games"]["total"])
        rtp_wagered_before = float(before_bank["rtp"]["wagered"])

        r = admin.post(f"{BASE_URL}/api/admin/bank/reset", json={"pin": PIN})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"ok": True, "bank": 0.0, "pool": 0.0, "commission_profit": 0.0}

        g = admin.get(f"{BASE_URL}/api/admin/bank").json()
        # Zeros
        assert g["bank"] == 0
        assert g["pool"] == 0
        assert g["commission_profit"] == 0
        assert g["available_bank"] == 0
        assert g["deposits_total"] == 0
        # Explicit not -0
        import math
        assert g["withdrawals_total"] == 0
        assert not math.copysign(1, g["withdrawals_total"]) < 0, "withdrawals_total must not be -0"
        assert g["adjustments_total"] == 0
        # Ledger has exactly 1 row: 'reset' with bank_after 0
        assert len(g["ledger"]) == 1
        row = g["ledger"][0]
        assert row["kind"] == "reset"
        assert float(row["bank_after"]) == 0.0
        # Games untouched
        assert g["games"]["total"] == games_total_before
        assert float(g["rtp"]["wagered"]) == rtp_wagered_before

        # Mongo direct verification
        state = db.bank_state.find_one({"id": "main"}, {"_id": 0})
        assert state["bank"] == 0
        assert state["pool"] == 0
        assert state["commission_profit"] == 0
        assert state["deposit_receipts"] == []
        assert state["withdrawal_receipts"] == []
        assert state["commission_deposits"] == []
        assert state["rain_returns"] == []
        assert state["commission_backfill_version"] == 1
        assert db.bank_ledger.count_documents({}) == 1

    def test_pool_topup_after_reset_not_backfilled(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/bank/pool", json={"amount": 100, "note": "post-reset", "pin": PIN})
        assert r.status_code == 200, r.text
        g = admin.get(f"{BASE_URL}/api/admin/bank").json()
        # Must be exactly 100 - not back-filled from history
        assert round(float(g["pool"]), 2) == 100.0
