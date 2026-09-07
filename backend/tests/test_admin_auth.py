"""Admin auth hardening tests: /api/admin/login, /admin/logout, /admin/session, require_admin, lockout."""
import os
import uuid
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
BASE_URL = base_url.rstrip("/") + "/api"
JWT_SECRET = backend_env["JWT_SECRET"]
MONGO_URL = backend_env["MONGO_URL"].strip('"')
DB_NAME = backend_env["DB_NAME"].strip('"')

GOOD = ["0u1o0gyxz", "bg7gw7mnt", "zm7pcp8ip", "5hccvev8s", "7i59vojax",
        "q8bheol0k", "di8ihi1wr", "g5bkbe61g", "kiulp6xqy", "5mdyfh6hp"]
UA = "BloxgradeQA/1.0"
UA2 = "BloxgradeQA-Other/2.0"


def clear_attempts():
    MongoClient(MONGO_URL)[DB_NAME].login_attempts.delete_many({})


@pytest.fixture(autouse=True, scope="module")
def _clean():
    clear_attempts()
    yield
    clear_attempts()


def post_login(phrases, ua=UA):
    return requests.post(f"{BASE_URL}/admin/login", json={"phrases": phrases},
                         headers={"User-Agent": ua, "Content-Type": "application/json"}, timeout=30)


def login_token(ua=UA):
    clear_attempts()
    r = post_login(GOOD, ua)
    assert r.status_code == 200, r.text
    return r.json()["token"]


class TestAdminLoginPositive:
    def test_login_correct(self):
        clear_attempts()
        r = post_login(GOOD)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["token"], str) and len(d["token"]) > 20
        assert "expires_at" in d
        claims = jwt.decode(d["token"], JWT_SECRET, algorithms=["HS256"])
        assert claims["role"] == "admin" and claims["type"] == "admin" and claims["jti"]
        exp = datetime.fromtimestamp(claims["exp"], timezone.utc)
        assert timedelta(hours=3, minutes=50) < exp - datetime.now(timezone.utc) < timedelta(hours=4, minutes=5)

    def test_login_case_and_whitespace_insensitive(self):
        clear_attempts()
        messy = [f"  {w.upper()} " for w in GOOD]
        r = post_login(messy)
        assert r.status_code == 200, r.text
        assert "token" in r.json()

    def test_session_endpoint(self):
        token = login_token()
        r = requests.get(f"{BASE_URL}/admin/session", headers={"Authorization": f"Bearer {token}", "User-Agent": UA}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True and r.json()["expires_at"]


class TestAdminLoginNegative:
    def test_wrong_order(self):
        clear_attempts()
        r = post_login(GOOD[::-1])
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "Неверная сид-фраза"

    def test_nine_words_422(self):
        clear_attempts()
        r = post_login(GOOD[:9])
        assert r.status_code == 422, r.text

    def test_eleven_words_422(self):
        clear_attempts()
        r = post_login(GOOD + ["extra"])
        assert r.status_code == 422, r.text

    def test_all_wrong_words_generic_message(self):
        clear_attempts()
        r = post_login([f"wrong{i}" for i in range(10)])
        assert r.status_code == 403
        detail = r.json()["detail"]
        assert detail == "Неверная сид-фраза"
        for w in GOOD:
            assert w not in detail.lower()

    def test_one_wrong_word_generic(self):
        clear_attempts()
        bad = list(GOOD)
        bad[4] = "zzzzzzzzz"
        r = post_login(bad)
        assert r.status_code == 403
        assert r.json()["detail"] == "Неверная сид-фраза"
        assert "5" not in r.json()["detail"]

    def test_empty_word(self):
        clear_attempts()
        bad = list(GOOD)
        bad[0] = ""
        r = post_login(bad)
        assert r.status_code in (403, 422), r.text

    def test_missing_body(self):
        clear_attempts()
        r = requests.post(f"{BASE_URL}/admin/login", json={}, headers={"User-Agent": UA}, timeout=30)
        assert r.status_code == 422


class TestTokenSecurity:
    def test_different_user_agent_rejected(self):
        token = login_token(UA)
        h = {"Authorization": f"Bearer {token}", "User-Agent": UA2}
        assert requests.get(f"{BASE_URL}/admin/session", headers=h, timeout=30).status_code == 403
        assert requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30).status_code == 403

    def test_logout_revokes_token(self):
        token = login_token()
        h = {"Authorization": f"Bearer {token}", "User-Agent": UA}
        assert requests.post(f"{BASE_URL}/admin/logout", headers=h, timeout=30).status_code == 200
        assert requests.get(f"{BASE_URL}/admin/session", headers=h, timeout=30).status_code == 403
        assert requests.get(f"{BASE_URL}/admin/deposits", headers=h, timeout=30).status_code == 403
        # second logout with revoked token must fail
        assert requests.post(f"{BASE_URL}/admin/logout", headers=h, timeout=30).status_code == 403

    def test_forged_admin_jwt_without_jti(self):
        forged = jwt.encode({"sub": "admin", "role": "admin",
                             "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, JWT_SECRET, algorithm="HS256")
        h = {"Authorization": f"Bearer {forged}", "User-Agent": UA}
        assert requests.get(f"{BASE_URL}/admin/session", headers=h, timeout=30).status_code == 403
        assert requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30).status_code == 403

    def test_forged_admin_jwt_with_random_jti(self):
        forged = jwt.encode({"sub": "admin", "role": "admin", "type": "admin", "jti": str(uuid.uuid4()),
                             "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, JWT_SECRET, algorithm="HS256")
        h = {"Authorization": f"Bearer {forged}", "User-Agent": UA}
        assert requests.get(f"{BASE_URL}/admin/session", headers=h, timeout=30).status_code == 403

    def test_user_jwt_rejected(self):
        user_tok = jwt.encode({"sub": "discord_test_1", "role": "user",
                               "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, JWT_SECRET, algorithm="HS256")
        h = {"Authorization": f"Bearer {user_tok}", "User-Agent": UA}
        for ep in ("/admin/session", "/admin/deposits", "/admin/withdrawals", "/admin/bank"):
            assert requests.get(f"{BASE_URL}{ep}", headers=h, timeout=30).status_code == 403, ep

    def test_expired_admin_token(self):
        token = login_token()
        jti = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["jti"]
        expired = jwt.encode({"sub": "admin", "role": "admin", "type": "admin", "jti": jti,
                              "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, JWT_SECRET, algorithm="HS256")
        h = {"Authorization": f"Bearer {expired}", "User-Agent": UA}
        assert requests.get(f"{BASE_URL}/admin/session", headers=h, timeout=30).status_code == 403

    def test_no_token_and_garbage(self):
        assert requests.get(f"{BASE_URL}/admin/session", headers={"User-Agent": UA}, timeout=30).status_code == 403
        h = {"Authorization": "Bearer not.a.jwt", "User-Agent": UA}
        assert requests.get(f"{BASE_URL}/admin/session", headers=h, timeout=30).status_code == 403

    def test_wrong_secret_signature(self):
        forged = jwt.encode({"sub": "admin", "role": "admin", "type": "admin", "jti": "x",
                             "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "othersecret", algorithm="HS256")
        h = {"Authorization": f"Bearer {forged}", "User-Agent": UA}
        assert requests.get(f"{BASE_URL}/admin/session", headers=h, timeout=30).status_code == 403


class TestAdminEndpoints:
    @pytest.fixture(scope="class")
    def h(self):
        token = login_token()
        return {"Authorization": f"Bearer {token}", "User-Agent": UA, "Content-Type": "application/json"}

    def test_deposits_withdrawals(self, h):
        for ep in ("/admin/deposits", "/admin/withdrawals"):
            r = requests.get(f"{BASE_URL}{ep}", headers=h, timeout=30)
            assert r.status_code == 200, (ep, r.text)
            assert isinstance(r.json(), list)

    def test_deposits_bad_status(self, h):
        r = requests.get(f"{BASE_URL}/admin/deposits", headers=h, params={"status": "bogus"}, timeout=30)
        assert r.status_code == 400

    def test_bank_get(self, h):
        r = requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "rtp_target" in d["settings"]
        assert isinstance(d["bank"], (int, float))
        assert "liabilities" in d and "net" in d
        # no raw mongo ObjectId keys leaked
        assert '"_id"' not in r.text and "'_id'" not in r.text

    def test_bank_settings_and_adjust(self, h):
        cur = requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30).json()
        original = float(cur["settings"]["rtp_target"])
        r = requests.put(f"{BASE_URL}/admin/bank/settings", json={"rtp_target": 0.91}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        got = requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30).json()["settings"]["rtp_target"]
        assert abs(float(got) - 0.91) < 1e-6
        r = requests.put(f"{BASE_URL}/admin/bank/settings", json={"rtp_target": original}, headers=h, timeout=30)
        assert r.status_code == 200
        assert abs(float(requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30).json()["settings"]["rtp_target"]) - original) < 1e-6

        before = float(requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30).json()["bank"])
        r = requests.post(f"{BASE_URL}/admin/bank/adjust", json={"amount": 100, "note": "TEST_adjust"}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        after = float(requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30).json()["bank"])
        assert abs(after - (before + 100)) < 1e-6
        r = requests.post(f"{BASE_URL}/admin/bank/adjust", json={"amount": -100, "note": "TEST_revert"}, headers=h, timeout=30)
        assert r.status_code == 200
        final = float(requests.get(f"{BASE_URL}/admin/bank", headers=h, timeout=30).json()["bank"])
        assert abs(final - before) < 1e-6

    def test_deposit_confirm_reject_unknown_id(self, h):
        r = requests.post(f"{BASE_URL}/admin/deposits/{uuid.uuid4()}/confirm", json={"rap": 100}, headers=h, timeout=30)
        assert r.status_code == 404, r.text
        r = requests.post(f"{BASE_URL}/admin/deposits/{uuid.uuid4()}/reject", json={}, headers=h, timeout=30)
        assert r.status_code == 404, r.text

    def test_confirm_validation(self, h):
        r = requests.post(f"{BASE_URL}/admin/deposits/{uuid.uuid4()}/confirm", json={"rap": -5}, headers=h, timeout=30)
        assert r.status_code == 422, r.text


class TestLockout:
    """Runs last: exhausts per-IP fails then verifies 429 even with the correct phrase."""

    def test_lockout_after_five_fails(self):
        clear_attempts()
        for i in range(5):
            r = post_login([f"bad{i}{j}" for j in range(10)])
            assert r.status_code == 403, (i, r.status_code, r.text)
        r = post_login([f"badx{j}" for j in range(10)])
        assert r.status_code == 429, r.text
        assert "заблокирован" in r.json()["detail"]
        # correct phrase must also be blocked
        r = post_login(GOOD)
        assert r.status_code == 429, r.text
        clear_attempts()
        r = post_login(GOOD)
        assert r.status_code == 200, r.text
        clear_attempts()
