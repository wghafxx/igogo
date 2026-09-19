"""Iteration 14 isolated regression: allocation conservation, confirm idempotency, admin auth, public checks."""

import asyncio
import os
import re
import sys
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
import requests
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.append("/app/backend")

from deposit_allocation import allocation, cents  # noqa: E402
from deposit_settlement import confirm_deposit  # noqa: E402
import server  # noqa: E402


frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"


def _admin_phrase_words():
    raw = open("/app/memory/test_credentials.md", encoding="utf-8").read()
    m = re.search(r"Current owner-provided admin phrase:\s*`([^`]+)`", raw)
    if not m:
        pytest.skip("Admin seed phrase missing in /app/memory/test_credentials.md")
    words = [w.strip() for w in m.group(1).split() if w.strip()]
    if len(words) != 10:
        pytest.skip("Admin seed phrase malformed")
    return words


def _user_token(session_id: str) -> str:
    return jwt.encode(
        {"sub": session_id, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(hours=2)},
        backend_env["JWT_SECRET"],
        algorithm="HS256",
    )


def _calc_net(rap: float, promo: float) -> int:
    rap_cents = Decimal(cents(rap))
    bonus = min(Decimal("0.5"), max(Decimal("0"), Decimal(str(promo or 0.0))))
    return int((rap_cents * Decimal("0.8") * (Decimal("1") + bonus)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@pytest.fixture(scope="module")
async def isolated_db():
    # Isolated Mongo DB for admin/deposit auth-financial tests only.
    test_db_name = f"{backend_env['DB_NAME']}_it14_{uuid.uuid4().hex[:8]}"
    client = AsyncIOMotorClient(backend_env["MONGO_URL"])
    db = client[test_db_name]
    await db.shop_items.insert_many([
        {"id": "case-finishline", "type": "Case", "name": "Finishline Case", "price": 39.0, "rarity": "red", "image": "x"},
        {"id": "case-lionheart", "type": "Case", "name": "Lionheart", "price": 40.0, "rarity": "red", "image": "x"},
        {"id": "driver-gator", "type": "Driver Gloves", "name": "Gator", "price": 1699.0, "rarity": "gold", "image": "x"},
        {"id": "gut-rusted", "type": "Gut", "name": "Rusted", "price": 1773.0, "rarity": "gold", "image": "x"},
        {"id": "flip-rusted", "type": "Flip", "name": "Rusted", "price": 2000.0, "rarity": "gold", "image": "x"},
        {"id": "skeleton-safari", "type": "Skeleton", "name": "Safari", "price": 2200.0, "rarity": "gold", "image": "x"},
        {"id": "butterfly-safari", "type": "Butterfly", "name": "Safari", "price": 3000.0, "rarity": "gold", "image": "x"},
        {"id": "karambit-safari", "type": "Karambit", "name": "Safari", "price": 3500.0, "rarity": "gold", "image": "x"},
        {"id": "reinforced", "type": "Operator Gloves", "name": "Reinforced", "price": 3600.0, "rarity": "gold", "image": "x"},
        {"id": "aztec", "type": "Hand Wraps", "name": "Aztec", "price": 4250.0, "rarity": "gold", "image": "x"},
        {"id": "imperial", "type": "Sports Gloves", "name": "Imperial", "price": 11299.0, "rarity": "gold", "image": "x"},
    ])
    # Mirror critical production unique indexes for concurrency/idempotency checks.
    await db.users.create_index("session_id", unique=True)
    await db.bank_ledger.create_index("id", unique=True)
    await db.bank_state.create_index("id", unique=True)
    await db.item_history.create_index("id", unique=True)
    try:
        yield db
    finally:
        await client.drop_database(test_db_name)
        client.close()


@pytest.fixture(scope="module")
async def isolated_client(isolated_db):
    # Isolated app DB binding; never touches live admin sessions.
    original_db = server.db
    server.db = isolated_db
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    server.db = original_db


# ---------- Money conservation allocation tests ----------
class TestAllocationInvariants:
    def test_property_style_amounts(self):
        catalog = [
            {"id": "dup", "type": "Case", "name": "A", "price": 39},
            {"id": "dup", "type": "Case", "name": "A2", "price": 40},
            {"id": "b", "type": "Case", "name": "B", "price": 40},
            {"id": "c", "type": "Case", "name": "C", "price": 1699},
            {"id": "d", "type": "Case", "name": "D", "price": 1773},
            {"id": "e", "type": "Case", "name": "E", "price": 2000},
            {"id": "f", "type": "Case", "name": "F", "price": 2200},
            {"id": "g", "type": "Case", "name": "G", "price": 3000},
            {"id": "h", "type": "Case", "name": "H", "price": 3500},
            {"id": "i", "type": "Case", "name": "I", "price": 3600},
        ]
        amounts = [20, 49, 50, 100, 200, 625, 1000, 10000, 30000, 1_000_000]
        promos = [0, 0.067, 0.10, 0.5]
        for rap in amounts:
            for promo in promos:
                plan = allocation(rap, promo, catalog)
                ids = [s["id"] for s in plan["issued_skins"]]
                spent = sum(cents(s["price"]) for s in plan["issued_skins"])
                rem = cents(plan["balance_credited"])
                net = _calc_net(rap, promo)
                assert len(ids) <= 5
                assert len(ids) == len(set(ids))
                assert spent + rem == net
                assert rem >= 0

    def test_empty_and_sparse_catalog(self):
        p1 = allocation(50, 0.1, [])
        assert p1["issued_skins"] == []
        assert cents(p1["balance_credited"]) == _calc_net(50, 0.1)

        p2 = allocation(200, 0, [{"id": "huge", "name": "X", "type": "X", "price": 9999999}])
        assert p2["issued_skins"] == []
        assert cents(p2["balance_credited"]) == _calc_net(200, 0)


@pytest.mark.anyio
class TestDepositSettlementWorkflow:
    async def _seed(self, db, status="pending", rap=625, promo=0.1):
        sid = f"qa_dep_{uuid.uuid4().hex[:8]}"
        dep_id = str(uuid.uuid4())
        await db.users.insert_one({"session_id": sid, "nickname": "QA", "balance": 0.0, "skins": [], "credited_deposits": []})
        await db.deposits.insert_one({
            "id": dep_id,
            "session_id": sid,
            "nickname": "QA",
            "discord_id": "123",
            "description": "qa",
            "expected_rap": rap,
            "promo_bonus": promo,
            "status": status,
            "created_at": datetime.now(timezone.utc),
            "resolved_at": None,
        })
        return sid, dep_id

    async def test_pending_preview_confirm_once(self, isolated_db):
        sid, dep_id = await self._seed(isolated_db)
        before = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})
        assert before["balance"] == 0 and before["skins"] == []

        out = await confirm_deposit(isolated_db, dep_id, 625, "qa")
        assert out["ok"] is True
        user = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})
        dep = await isolated_db.deposits.find_one({"id": dep_id}, {"_id": 0})
        assert dep["status"] == "confirmed"
        issued = sum(cents(s["price"]) for s in user["skins"])
        rem = cents(user["balance"])
        assert issued + rem == cents(dep["credited"])

    async def test_preview_readonly_and_consistent_with_confirm(self, isolated_db, isolated_client):
        sid, dep_id = await self._seed(isolated_db, rap=625, promo=0.1)
        words = _admin_phrase_words()
        login = await isolated_client.post("/api/admin/login", json={"phrases": words}, headers={"User-Agent": "qa-ua-preview"})
        assert login.status_code == 200
        ah = {"Authorization": f"Bearer {login.json()['token']}", "User-Agent": "qa-ua-preview"}

        before = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})
        p1 = await isolated_client.post(f"/api/admin/deposits/{dep_id}/preview", json={"rap": 625, "note": "x"}, headers=ah)
        p2 = await isolated_client.post(f"/api/admin/deposits/{dep_id}/preview", json={"rap": 625, "note": "y"}, headers=ah)
        assert p1.status_code == 200 and p2.status_code == 200
        assert p1.json()["issued_skins"] == p2.json()["issued_skins"]
        assert p1.json()["balance_credited"] == p2.json()["balance_credited"]

        after_preview = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})
        assert after_preview["balance"] == before["balance"]
        assert after_preview["skins"] == before["skins"]

        cf = await isolated_client.post(f"/api/admin/deposits/{dep_id}/confirm", json={"rap": 625, "note": "confirm"}, headers=ah)
        assert cf.status_code == 200
        dep = await isolated_db.deposits.find_one({"id": dep_id}, {"_id": 0})
        assert sorted([i["id"] for i in dep["issued_skins"]]) == sorted([i["id"] for i in p1.json()["issued_skins"]])
        assert cents(dep["balance_credited"]) == cents(p1.json()["balance_credited"])

    async def test_repeat_and_concurrent_confirm_no_extra_credit(self, isolated_db):
        sid, dep_id = await self._seed(isolated_db, rap=1000, promo=0)
        first = await confirm_deposit(isolated_db, dep_id, 1000, "first")
        assert first["ok"]
        user_first = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})

        rep = await confirm_deposit(isolated_db, dep_id, 1000, "repeat")
        assert rep.get("already_confirmed") is True
        assert cents(rep["credited"]) == cents(first["credited"])

        vals = await asyncio.gather(*[confirm_deposit(isolated_db, dep_id, 1000, "c") for _ in range(3)])
        assert all(v.get("already_confirmed") for v in vals)
        user_after = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})
        assert user_after["balance"] == pytest.approx(user_first["balance"])
        assert sorted(s["uid"] for s in user_after["skins"]) == sorted(s["uid"] for s in user_first["skins"])

    async def test_pending_concurrent_confirm_three_requests_single_allocation(self, isolated_db):
        sid, dep_id = await self._seed(isolated_db, rap=625, promo=0.1)
        state_before = await isolated_db.bank_state.find_one({"id": "main"}, {"_id": 0})
        bank_before = cents((state_before or {}).get("bank", 0))

        vals = await asyncio.gather(*[confirm_deposit(isolated_db, dep_id, 625, "race") for _ in range(3)])
        assert all(v.get("ok") for v in vals)

        dep = await isolated_db.deposits.find_one({"id": dep_id}, {"_id": 0})
        user = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})

        assert dep["status"] == "confirmed"
        assert user["credited_deposits"].count(dep_id) == 1

        # Exactly one allocation persisted to the user and all totals are conserved.
        user_dep_skins = [s for s in user["skins"] if s.get("deposit_id") == dep_id]
        assert len(user_dep_skins) == len(dep.get("issued_skins", []))
        assert sorted(s["uid"] for s in user_dep_skins) == sorted(s["uid"] for s in dep.get("issued_skins", []))
        issued = sum(cents(s["price"]) for s in user_dep_skins)
        rem = cents(dep.get("balance_credited", 0))
        assert issued + rem == cents(dep["credited"])
        assert cents(user["balance"]) == rem

        assert await isolated_db.bank_ledger.count_documents({"id": f"deposit:{dep_id}"}) == 1
        assert await isolated_db.item_history.count_documents({"deposit_id": dep_id}) == len(dep.get("issued_skins", []))

        state = await isolated_db.bank_state.find_one({"id": "main"}, {"_id": 0})
        receipts = [r for r in state.get("deposit_receipts", []) if r.get("id") == dep_id]
        assert len(receipts) == 1
        assert cents(state.get("bank", 0)) - bank_before == cents(dep["rap"])

    async def test_retry_after_simulated_partial_credit_state(self, isolated_db):
        sid, dep_id = await self._seed(isolated_db, rap=200, promo=0)
        plan = allocation(200, 0, await isolated_db.shop_items.find({}, {"_id": 0}).to_list(None))
        plan["issued_skins"] = [{**item, "uid": str(uuid.uuid4()), "deposit_id": dep_id} for item in plan["issued_skins"]]
        await isolated_db.deposits.update_one({"id": dep_id}, {"$set": {**plan, "status": "processing", "planned_at": datetime.now(timezone.utc)}})
        await isolated_db.users.update_one(
            {"session_id": sid},
            {"$inc": {"balance": plan["balance_credited"]}, "$push": {"skins": {"$each": plan["issued_skins"]}}, "$addToSet": {"credited_deposits": dep_id}},
        )

        out = await confirm_deposit(isolated_db, dep_id, 200, "retry")
        assert out["ok"]
        user = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})
        assert user["credited_deposits"].count(dep_id) == 1
        assert await isolated_db.bank_ledger.count_documents({"id": f"deposit:{dep_id}"}) == 1

    async def test_retry_after_bank_write_does_not_double_book(self, isolated_db):
        sid, dep_id = await self._seed(isolated_db, rap=200, promo=0)
        plan = allocation(200, 0, await isolated_db.shop_items.find({}, {"_id": 0}).to_list(None))
        plan["issued_skins"] = [{**item, "uid": str(uuid.uuid4()), "deposit_id": dep_id} for item in plan["issued_skins"]]
        planned_at = datetime.now(timezone.utc)

        await isolated_db.deposits.update_one(
            {"id": dep_id},
            {"$set": {**plan, "status": "processing", "planned_at": planned_at}},
        )

        # Simulate crash after bank write but before user credit and final status update.
        await isolated_db.bank_state.update_one(
            {"id": "main"},
            {"$set": {"bank": 200.0, "deposit_receipts": [{"id": dep_id, "bank_after": 200.0}]}},
            upsert=True,
        )

        out = await confirm_deposit(isolated_db, dep_id, 200, "retry-bank")
        assert out["ok"] is True

        user = await isolated_db.users.find_one({"session_id": sid}, {"_id": 0})
        dep = await isolated_db.deposits.find_one({"id": dep_id}, {"_id": 0})
        state = await isolated_db.bank_state.find_one({"id": "main"}, {"_id": 0})

        assert dep["status"] == "confirmed"
        assert user["credited_deposits"].count(dep_id) == 1
        assert await isolated_db.bank_ledger.count_documents({"id": f"deposit:{dep_id}"}) == 1

        receipts = [r for r in state.get("deposit_receipts", []) if r.get("id") == dep_id]
        assert len(receipts) == 1
        assert cents(state["bank"]) == cents(200)

    async def test_rejected_cancelled_and_missing_user(self, isolated_db):
        _, dep_rej = await self._seed(isolated_db, status="rejected", rap=100)
        with pytest.raises(Exception):
            await confirm_deposit(isolated_db, dep_rej, 100, "x")

        _, dep_can = await self._seed(isolated_db, status="cancelled", rap=100)
        with pytest.raises(Exception):
            await confirm_deposit(isolated_db, dep_can, 100, "x")

        dep_id = str(uuid.uuid4())
        await isolated_db.deposits.insert_one({
            "id": dep_id,
            "session_id": "qa_missing",
            "nickname": "qa",
            "discord_id": "qa",
            "description": "qa",
            "expected_rap": 100,
            "promo_bonus": 0,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        })
        with pytest.raises(Exception):
            await confirm_deposit(isolated_db, dep_id, 100, "x")
        assert await isolated_db.bank_ledger.count_documents({"id": f"deposit:{dep_id}"}) == 0


@pytest.mark.anyio
class TestAdminAuthIsolated:
    async def test_seed_hash_format(self):
        seed_hash = backend_env.get("ADMIN_SEED_HASH", "")
        assert seed_hash.startswith("sha256$")
        assert seed_hash[7:].startswith("$2b$")

    async def test_login_last_word_change_old_phrase_fail(self, isolated_client):
        words = _admin_phrase_words()
        ok = await isolated_client.post("/api/admin/login", json={"phrases": words}, headers={"User-Agent": "qa-ua-1"})
        assert ok.status_code == 200

        bad_words = list(words)
        bad_words[-1] = bad_words[-1] + "x"
        bad = await isolated_client.post("/api/admin/login", json={"phrases": bad_words}, headers={"User-Agent": "qa-ua-1"})
        assert bad.status_code == 403

        old = await isolated_client.post(
            "/api/admin/login",
            json={"phrases": ["bloxgrade", "admin", "test", "old", "seed", "phrase", "for", "qa", "flow", "fail"]},
            headers={"User-Agent": "qa-ua-1"},
        )
        assert old.status_code in (403, 422)

    async def test_role_isolation_and_user_agent_binding(self, isolated_client):
        words = _admin_phrase_words()
        login = await isolated_client.post("/api/admin/login", json={"phrases": words}, headers={"User-Agent": "qa-ua-2"})
        assert login.status_code == 200
        token = login.json()["token"]

        s1 = await isolated_client.get("/api/admin/session", headers={"Authorization": f"Bearer {token}", "User-Agent": "qa-ua-2"})
        s2 = await isolated_client.get("/api/admin/session", headers={"Authorization": f"Bearer {token}", "User-Agent": "qa-ua-3"})
        assert s1.status_code == 200
        assert s2.status_code == 403

        user_token = _user_token("discord_qa_role")
        as_user = await isolated_client.get("/api/admin/session", headers={"Authorization": f"Bearer {user_token}", "User-Agent": "qa-ua-2"})
        assert as_user.status_code == 403

    async def test_seed_version_rejects_tampered_token(self, isolated_client):
        words = _admin_phrase_words()
        login = await isolated_client.post("/api/admin/login", json={"phrases": words}, headers={"User-Agent": "qa-ua-4"})
        assert login.status_code == 200
        tok = login.json()["token"]
        data = jwt.decode(tok, backend_env["JWT_SECRET"], algorithms=["HS256"])
        data["seed_version"] = "invalid"
        tampered = jwt.encode(data, backend_env["JWT_SECRET"], algorithm="HS256")
        res = await isolated_client.get("/api/admin/session", headers={"Authorization": f"Bearer {tampered}", "User-Agent": "qa-ua-4"})
        assert res.status_code == 403

    async def test_bruteforce_lockout_after_five_fails(self, isolated_client, isolated_db):
        await isolated_db.login_attempts.delete_many({})
        statuses = []
        for _ in range(6):
            r = await isolated_client.post("/api/admin/login", json={"phrases": ["x"] * 10}, headers={"User-Agent": "qa-ua-lock"})
            statuses.append(r.status_code)
        assert statuses[:5] == [403, 403, 403, 403, 403]
        assert statuses[5] == 429


# ---------- Live public read-only checks ----------
class TestPublicLiveEndpoints:
    def test_shop_items_and_search_safety(self):
        r = requests.get(f"{API}/shop", timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 24
        got = {(i["name"], float(i["price"])) for i in items}
        expected = {
            ("Lionheart", 40.0), ("Finishline Case", 39.0), ("Imperial", 11299.0), ("Aztec", 4250.0),
            ("Reinforced", 3600.0), ("Bumblebee", 3050.0), ("Gator", 1699.0), ("Safari", 3500.0),
            ("Safari", 3000.0), ("Safari", 2200.0), ("Rusted", 2000.0), ("Rusted", 1773.0),
            ("Typhon", 110.0), ("Railgun", 152.0), ("Orchids", 242.0), ("Aniki", 299.0),
        }
        assert expected.issubset(got)
        assert requests.get(f"{API}/shop", params={"q": "["}, timeout=30).status_code == 200
        assert requests.get(f"{API}/shop", params={"q": "Safari", "rarity": "gold"}, timeout=30).status_code == 200

    def test_discord_public_redirect_cookie_state(self):
        r = requests.get(f"{API}/auth/discord/login", allow_redirects=False, timeout=30)
        assert r.status_code in (302, 307)
        loc = r.headers.get("location", "")
        assert "discord.com/oauth2/authorize" in loc
        assert "scope=identify" in loc
        assert f"client_id={backend_env['DISCORD_CLIENT_ID']}" in loc
        set_cookie = r.headers.get("set-cookie", "")
        assert "bg_oauth_state=" in set_cookie
        assert "Max-Age=600" in set_cookie

    def test_discord_callback_missing_mismatch_and_replay_state_denied(self):
        s = requests.Session()
        login = s.get(f"{API}/auth/discord/login", allow_redirects=False, timeout=30)
        assert login.status_code in (302, 307)
        qs = parse_qs(urlparse(login.headers.get("location", "")).query)
        state = (qs.get("state") or [None])[0]
        assert state

        missing = s.get(f"{API}/auth/discord/callback?code=dummy", allow_redirects=False, timeout=30)
        assert missing.status_code in (302, 307)
        assert "auth_error=state" in missing.headers.get("location", "")

        mismatch = s.get(f"{API}/auth/discord/callback?code=dummy&state=wrong{state}", allow_redirects=False, timeout=30)
        assert mismatch.status_code in (302, 307)
        assert "auth_error=state" in mismatch.headers.get("location", "")

        first = s.get(f"{API}/auth/discord/callback?code=dummy&state={state}", allow_redirects=False, timeout=30)
        assert first.status_code in (302, 307)
        assert "auth_error=state" not in first.headers.get("location", "")

        replay = s.get(f"{API}/auth/discord/callback?code=dummy&state={state}", allow_redirects=False, timeout=30)
        assert replay.status_code in (302, 307)
        assert "auth_error=state" in replay.headers.get("location", "")
