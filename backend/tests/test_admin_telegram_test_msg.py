"""Verifies /api/admin/telegram/test auth + the 'da:test:*' simulated callbacks are money-safe.

NOTE: we do NOT call /api/admin/telegram/test with a valid admin token here — the main agent
already sent one real message. We only exercise the unauth path (401/403) and simulate the
inline-button callbacks via /api/telegram/webhook, then confirm nothing in `deposits` or
user balances changed.
"""
import hashlib
import os
import time

import pytest
import requests

pytestmark = pytest.mark.live

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
SEED = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]


def _read_env(key: str) -> str:
    with open("/app/backend/.env") as fh:
        for line in fh:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"{key} missing")


BOT_TOKEN = _read_env("TELEGRAM_BOT_TOKEN")
JWT_SECRET = _read_env("JWT_SECRET")
SECRET = hashlib.sha256(f"{BOT_TOKEN}:{JWT_SECRET}".encode()).hexdigest()[:48]
ADMIN_ID = int(_read_env("TELEGRAM_ADMIN_ID"))


def _cb(uid, data):
    return {"update_id": uid,
            "callback_query": {"id": f"q{uid}", "from": {"id": ADMIN_ID}, "data": data,
                               "message": {"message_id": 1, "chat": {"id": ADMIN_ID}}}}


# -------- auth on /admin/telegram/test --------

def test_admin_telegram_test_requires_admin():
    r = requests.post(f"{BASE}/api/admin/telegram/test", timeout=15)
    assert r.status_code in (401, 403), r.text


def test_admin_telegram_test_bad_token_rejected():
    r = requests.post(f"{BASE}/api/admin/telegram/test",
                      headers={"Authorization": "Bearer not-a-real-token"}, timeout=15)
    assert r.status_code in (401, 403), r.text


def test_admin_login_works():
    """Verify seed login still returns a token (regression) but we never hit /telegram/test with it."""
    r = requests.post(f"{BASE}/api/admin/login", json={"phrases": SEED}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("token")


# -------- webhook secret regression --------

def test_webhook_403_without_secret():
    r = requests.post(f"{BASE}/api/telegram/webhook", json={"update_id": 800000001}, timeout=15)
    assert r.status_code == 403


def test_webhook_200_with_secret():
    r = requests.post(f"{BASE}/api/telegram/webhook",
                      headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                      json={"update_id": 800000002}, timeout=15)
    assert r.status_code == 200


# -------- simulated 'da:test:*' inline buttons never touch money --------

def _snapshot():
    """Return (deposits_count, sum_of_user_balances) from Mongo."""
    import asyncio as _a
    from motor.motor_asyncio import AsyncIOMotorClient as _C

    async def go():
        db = _C("mongodb://localhost:27017").test_database
        deposits = await db.deposits.count_documents({})
        users = await db.users.find({}, {"balance": 1, "_id": 0}).to_list(10000)
        bal = sum(float(u.get("balance") or 0) for u in users)
        # Also make sure no phantom "test0000..." deposit was materialised
        phantom = await db.deposits.count_documents({"id": "test0000-0000-0000-0000-000000000000"})
        return deposits, round(bal, 4), phantom
    return _a.run(go())


@pytest.mark.parametrize("action", ["ask", "ok", "rej", "no", "amt"])
def test_da_test_callback_is_money_safe(action):
    before = _snapshot()
    uid = 850000000 + int(time.time() * 1000) % 100000
    r = requests.post(f"{BASE}/api/telegram/webhook",
                      headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                      json=_cb(uid + hash(action) % 1000, f"da:test:{action}"), timeout=15)
    assert r.status_code == 200, r.text
    # tiny grace — the handler is sync w.r.t. Mongo but callback is fire-and-forget for Telegram HTTP
    time.sleep(0.3)
    after = _snapshot()
    assert after[0] == before[0], f"deposits count changed for da:test:{action}: {before[0]} -> {after[0]}"
    assert after[1] == before[1], f"user balances changed for da:test:{action}: {before[1]} -> {after[1]}"
    assert after[2] == 0, f"phantom TEST_DEP was materialised in deposits for da:test:{action}"
