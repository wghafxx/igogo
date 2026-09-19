"""BLOXGRADE backend regression tests: deposits/fee/promo, casino bank ledger,
payout protection, server-side chance, withdrawals, admin bank endpoints."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

pytest.skip("Retired live-mutating legacy suite. Use test_iteration14_isolated.py; never mutate the owner's database.", allow_module_level=True)
SID = "discord_test_1"
JWT_SECRET = backend_env["JWT_SECRET"]

mongo = MongoClient(backend_env["MONGO_URL"])
db = mongo[backend_env["DB_NAME"]]


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def user_token():
    return jwt.encode(
        {"sub": SID, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
def uh(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture(scope="session")
def admin_token():
    pytest.skip("Retired legacy single-phrase login contract")


@pytest.fixture(scope="session")
def ah(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session", autouse=True)
def seed_user():
    db.users.update_one({"session_id": SID}, {"$set": {
        "session_id": SID, "nickname": "Tester", "discord_id": "1",
        "balance": 1000.0, "skins": [], "promo_bonus": 0.0, "promo_code": None,
    }}, upsert=True)
    yield


def set_balance(v):
    db.users.update_one({"session_id": SID}, {"$set": {"balance": float(v)}})


def get_user():
    return db.users.find_one({"session_id": SID}, {"_id": 0})


def bank():
    d = db.bank_state.find_one({"id": "main"}) or {}
    return float(d.get("bank") or 0)


def liabilities():
    bal = sum(float(u.get("balance") or 0) for u in db.users.find({}, {"balance": 1}))
    inv = sum(float(sk.get("price") or 0) for u in db.users.find({}, {"skins": 1}) for sk in (u.get("skins") or []))
    pend = sum(float((w.get("item") or {}).get("price") or 0) for w in db.withdrawals.find({"status": "pending"}))
    return bal + inv + pend


def rtp_stats():
    wagered = sum(float(u.get("bet_amount") or 0) + float(u.get("items_total") or 0) for u in db.upgrades.find({}))
    paid = sum(float((u.get("target_item") or {}).get("price") or 0) for u in db.upgrades.find({"win": True}))
    return wagered, paid


def item(name):
    return db.shop_items.find_one({"name": name}, {"_id": 0})


# ---------- health / auth ----------
class TestBasics:
    def test_root(self):
        r = requests.get(f"{BASE}/", timeout=30)
        assert r.status_code == 200 and "message" in r.json()

    def test_bank_requires_admin(self, uh):
        assert requests.get(f"{BASE}/admin/bank", timeout=30).status_code == 403
        assert requests.get(f"{BASE}/admin/bank", headers=uh, timeout=30).status_code == 403

    def test_admin_bank_shape(self, ah):
        r = requests.get(f"{BASE}/admin/bank", headers=ah, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("bank", "settings", "liabilities", "net", "rtp", "games", "ledger"):
            assert k in d, f"missing {k}"
        assert "rtp_target" in d["settings"]
        for k in ("balances", "inventory", "pending_withdrawals", "total"):
            assert k in d["liabilities"]
        for k in ("wagered", "paid", "rtp"):
            assert k in d["rtp"]
        for k in ("total", "wins", "forced_losses"):
            assert k in d["games"]
        assert isinstance(d["ledger"], list)
        assert abs(d["net"] - (d["bank"] - d["liabilities"]["total"])) < 0.01


# ---------- deposits: fee + promo + bank ----------
class TestDeposits:
    def _create(self):
        pass

    def test_deposit_with_promo(self, uh, ah):
        db.deposits.delete_many({"session_id": SID, "status": "pending"})
        r = requests.post(f"{BASE}/promo/apply", json={"code": "SINZUKU"}, headers=uh, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["promo_bonus"] == 0.10

        dep = requests.post(f"{BASE}/deposits", json={"description": "TEST_promo deposit"}, headers=uh, timeout=30)
        assert dep.status_code == 200, dep.text
        dep_id = dep.json()["id"]
        assert dep.json()["promo_bonus"] == 0.10

        bal_before = float(get_user()["balance"])
        bank_before = bank()

        low = requests.post(f"{BASE}/admin/deposits/{dep_id}/confirm", json={"rap": 10}, headers=ah, timeout=30)
        assert low.status_code == 400, f"rap=10 should be rejected, got {low.status_code}"

        ok = requests.post(f"{BASE}/admin/deposits/{dep_id}/confirm", json={"rap": 100, "note": "TEST"}, headers=ah, timeout=30)
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["credited"] == 88.0, body
        assert abs(body["bank"] - (bank_before + 100)) < 0.01

        assert abs(float(get_user()["balance"]) - (bal_before + 88.0)) < 0.01
        led = db.bank_ledger.find_one({"ref_id": dep_id, "kind": "deposit"})
        assert led and abs(led["amount"] - 100) < 0.01

        again = requests.post(f"{BASE}/admin/deposits/{dep_id}/confirm", json={"rap": 100}, headers=ah, timeout=30)
        assert again.status_code == 404, again.status_code

    def test_deposit_without_promo(self, uh, ah):
        db.users.update_one({"session_id": SID}, {"$set": {"promo_bonus": 0.0, "promo_code": None}})
        dep = requests.post(f"{BASE}/deposits", json={"description": "TEST_no promo"}, headers=uh, timeout=30)
        assert dep.status_code == 200, dep.text
        dep_id = dep.json()["id"]
        assert dep.json()["promo_bonus"] == 0.0
        bal_before = float(get_user()["balance"])
        ok = requests.post(f"{BASE}/admin/deposits/{dep_id}/confirm", json={"rap": 50}, headers=ah, timeout=30)
        assert ok.status_code == 200, ok.text
        assert ok.json()["credited"] == 40.0, ok.json()
        assert abs(float(get_user()["balance"]) - (bal_before + 40.0)) < 0.01


# ---------- bank settings + adjust ----------
class TestBankAdmin:
    def test_settings_validation(self, ah):
        bad = requests.put(f"{BASE}/admin/bank/settings", json={"rtp_target": 0.3}, headers=ah, timeout=30)
        assert bad.status_code == 422, bad.status_code
        ok = requests.put(f"{BASE}/admin/bank/settings", json={"rtp_target": 0.85}, headers=ah, timeout=30)
        assert ok.status_code == 200 and ok.json()["rtp_target"] == 0.85
        # restore default
        requests.put(f"{BASE}/admin/bank/settings", json={"rtp_target": 0.90}, headers=ah, timeout=30)
        assert requests.get(f"{BASE}/admin/bank", headers=ah, timeout=30).json()["settings"]["rtp_target"] == 0.90

    def test_adjust(self, ah):
        zero = requests.post(f"{BASE}/admin/bank/adjust", json={"amount": 0, "note": "TEST_zero"}, headers=ah, timeout=30)
        assert zero.status_code == 400, zero.status_code
        before = bank()
        note = f"TEST_adjust_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE}/admin/bank/adjust", json={"amount": 100, "note": note}, headers=ah, timeout=30)
        assert r.status_code == 200, r.text
        assert abs(r.json()["bank"] - (before + 100)) < 0.01
        assert abs(bank() - (before + 100)) < 0.01
        led = db.bank_ledger.find_one({"note": note})
        assert led and led["kind"] == "adjust" and abs(led["amount"] - 100) < 0.01

    def test_adjust_requires_note(self, ah):
        r = requests.post(f"{BASE}/admin/bank/adjust", json={"amount": 10}, headers=ah, timeout=30)
        assert r.status_code == 422, r.status_code


# ---------- upgrade validation / server-side chance ----------
class TestUpgradeValidation:
    def test_min_chance_rejected(self, uh):
        it = item("Anodized Red")
        set_balance(5000)
        r = requests.post(f"{BASE}/upgrade", json={
            "session_id": SID, "bet_amount": 1, "bet_items": [], "target_item": it, "chance": 0.5,
        }, headers=uh, timeout=60)
        assert r.status_code == 400, f"expected 400 for chance<1%, got {r.status_code} {r.text[:200]}"

    def test_chance_is_server_side(self, uh):
        it = item("Anodized Red")
        set_balance(5000)
        r = requests.post(f"{BASE}/upgrade", json={
            "session_id": SID, "bet_amount": 20, "bet_items": [], "target_item": it, "chance": 0.74,
        }, headers=uh, timeout=60)
        assert r.status_code == 200, r.text
        assert abs(r.json()["chance"] - 20 / it["price"]) < 1e-9, r.json()

    def test_bet_above_75pct_rejected(self, uh):
        it = item("Anodized Red")
        set_balance(5000)
        r = requests.post(f"{BASE}/upgrade", json={
            "session_id": SID, "bet_amount": it["price"] * 0.76, "bet_items": [], "target_item": it,
        }, headers=uh, timeout=60)
        assert r.status_code == 400, r.status_code

    def test_session_mismatch_401(self, uh):
        it = item("Glove Case")
        r = requests.post(f"{BASE}/upgrade", json={
            "session_id": "someone_else", "bet_amount": 30, "bet_items": [], "target_item": it,
        }, headers=uh, timeout=60)
        assert r.status_code == 401, r.status_code

    def test_upgrade_requires_auth(self):
        it = item("Glove Case")
        r = requests.post(f"{BASE}/upgrade", json={"session_id": SID, "bet_amount": 30, "target_item": it}, timeout=60)
        assert r.status_code == 401


# ---------- payout protection invariants ----------
class TestPayoutProtection:
    def test_invariants_under_load(self, uh, ah):
        it = item("Glove Case")
        price, bet = it["price"], round(it["price"] * 0.75, 2)
        # make wins possible: small player balance, well funded bank
        set_balance(500)
        needed = liabilities() + price * 20 - bank()
        if needed > 0:
            r = requests.post(f"{BASE}/admin/bank/adjust", json={"amount": round(needed + 1000, 2), "note": "TEST_fund bank"}, headers=ah, timeout=30)
            assert r.status_code == 200, r.text
        target = requests.get(f"{BASE}/admin/bank", headers=ah, timeout=30).json()["settings"]["rtp_target"]

        def one(_):
            if float(get_user()["balance"]) < bet:
                set_balance(500)
            return requests.post(f"{BASE}/upgrade", json={
                "session_id": SID, "bet_amount": bet, "bet_items": [], "target_item": it, "chance": 0.75,
            }, headers=uh, timeout=60)

        codes = []
        for i in range(30):
            codes.append(one(i).status_code)
        with ThreadPoolExecutor(max_workers=6) as ex:
            codes += [r.status_code for r in ex.map(one, range(12))]
        bad = [c for c in codes if c not in (200, 400)]
        assert not bad, f"unexpected upgrade status codes: {bad}"
        assert codes.count(200) >= 30, f"only {codes.count(200)} successful upgrades"

        # solvency invariant
        b, li = bank(), liabilities()
        assert b + 0.01 >= li, f"bank {b} < liabilities {li} — solvency broken"
        # rtp invariant
        wagered, paid = rtp_stats()
        assert wagered > 0
        assert paid / wagered <= target + 1e-6, f"rtp {paid / wagered:.4f} > target {target}"

    def test_forced_losses_consistent(self):
        forced = list(db.upgrades.find({"forced_loss": True}, {"_id": 0}))
        assert forced, "no forced losses recorded — protection may not be triggering"
        for u in forced:
            assert u["win"] is False, f"forced loss {u['id']} marked as win"
            assert abs(u["roll"] * 360 - 180) >= u["chance"] * 180 - 1e-9, f"forced loss roll inside win zone: {u['id']}"
            assert db.drops.count_documents({"session_id": u["session_id"], "created_at": u["created_at"]}) == 0

    def test_drops_match_wins(self):
        wins = db.upgrades.count_documents({"win": True})
        drops = db.drops.count_documents({})
        assert drops == wins, f"drops {drops} != wins {wins}"

    def test_profile_hides_protection_fields(self, uh):
        r = requests.get(f"{BASE}/profile", headers=uh, timeout=30)
        assert r.status_code == 200, r.text
        games = r.json()["games"]
        assert games, "no games in profile"
        leaked = [k for g in games for k in ("forced_loss", "forced_reason", "protection", "roll") if k in g]
        assert not leaked, f"profile leaks protection fields: {set(leaked)}"


# ---------- withdrawal -> bank decrease ----------
class TestWithdrawal:
    def test_withdraw_and_admin_done(self, uh, ah):
        it = item("Glove Case")
        skin = {**it, "uid": str(uuid.uuid4())}
        db.users.update_one({"session_id": SID}, {"$push": {"skins": skin}})
        r = requests.post(f"{BASE}/skins/withdraw", json={"uids": [skin["uid"]]}, headers=uh, timeout=30)
        assert r.status_code == 200, r.text
        assert all(s["uid"] != skin["uid"] for s in r.json()["skins"])

        pending = requests.get(f"{BASE}/admin/withdrawals", headers=ah, timeout=30)
        assert pending.status_code == 200
        rows = [w for w in pending.json() if (w.get("item") or {}).get("uid") == skin["uid"]]
        assert rows, "withdrawal not visible to admin"
        wid = rows[0]["id"]
        assert rows[0]["user"] and rows[0]["user"]["session_id"] == SID

        before = bank()
        done = requests.post(f"{BASE}/admin/withdrawals/{wid}/done", headers=ah, timeout=30)
        assert done.status_code == 200, done.text
        assert abs(done.json()["bank"] - (before - it["price"])) < 0.01
        led = db.bank_ledger.find_one({"ref_id": wid})
        assert led and led["kind"] == "withdrawal" and abs(led["amount"] + it["price"]) < 0.01
        assert requests.post(f"{BASE}/admin/withdrawals/{wid}/done", headers=ah, timeout=30).status_code == 404


# ---------- protection triggered by insolvency (reason=bank) ----------
class TestBankReasonProtection:
    def test_low_bank_forces_losses(self, uh, ah):
        it = item("Glove Case")
        bet = round(it["price"] * 0.75, 2)
        set_balance(2000)
        li = liabilities()
        # drain bank below liabilities so no payout can be allowed
        drain = round(bank() - li + 5000, 2)
        assert requests.post(f"{BASE}/admin/bank/adjust", json={"amount": -drain, "note": "TEST_drain"}, headers=ah, timeout=30).status_code == 200
        assert bank() < li, (bank(), li)
        before_forced = db.upgrades.count_documents({"forced_loss": True})
        wins = 0
        for _ in range(25):
            if float(get_user()["balance"]) < bet:
                set_balance(2000)
            r = requests.post(f"{BASE}/upgrade", json={
                "session_id": SID, "bet_amount": bet, "bet_items": [], "target_item": it, "chance": 0.75,
            }, headers=uh, timeout=60)
            assert r.status_code == 200, r.text
            if r.json()["win"]:
                wins += 1
        assert wins == 0, f"{wins} wins paid out while bank is insolvent"
        new_forced = list(db.upgrades.find({"forced_loss": True}, {"_id": 0}).sort("created_at", -1).limit(25))
        assert db.upgrades.count_documents({"forced_loss": True}) > before_forced, "no forced losses recorded"
        assert any(u.get("forced_reason") == "bank" for u in new_forced), \
            f"expected forced_reason=bank, got {[u.get('forced_reason') for u in new_forced][:5]}"
        # restore bank
        requests.post(f"{BASE}/admin/bank/adjust", json={"amount": drain, "note": "TEST_restore"}, headers=ah, timeout=30)
