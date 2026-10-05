"""Backend tests for iteration 6:
- Staff reject via chat: skin request rejection (no report yet), DonationAlerts money rejection
- Reject refused when: report submitted, paid_claimed, chat not accepted, wrong staff, player token
- DonationAlerts KZT min 500 enforcement (< 500 -> 400, >= 500 -> 201)
"""
import os
import uuid
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
JWT_SECRET = os.environ["JWT_SECRET"]
UA = "staff-reject-min-test/1.0"
ADMIN_SEED = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]

_mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _jwt_user(sid):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sid, "role": "user", "exp": now + timedelta(days=30), "iat": now, "sv": 0},
                      JWT_SECRET, algorithm="HS256")


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    return s


@pytest.fixture(scope="module")
def admin(http):
    r = http.post(f"{API}/admin/login", json={"phrases": ADMIN_SEED},
                  headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    return {"headers": {"Authorization": f"Bearer {r.json()['token']}", "User-Agent": UA}}


@pytest.fixture(scope="module")
def seeded(admin, http):
    users = {
        "staff": {"session_id": "seed-staff-1", "discord_id": "900000000000000001", "nickname": "StaffTester",
                  "roblox_display_name": "Staff Receiver", "roblox_nick": "staff_receiver",
                  "roblox_link": "https://www.roblox.com/users/111/profile"},
    }
    for u in users.values():
        _mongo.users.update_one({"session_id": u["session_id"]}, {"$setOnInsert": {
            **u, "balance": 0.0, "skins": [], "created_at": datetime.now(timezone.utc),
            "roblox_nick_normalized": u["roblox_nick"].lower()}}, upsert=True)
    r = http.get(f"{API}/admin/staff", headers=admin["headers"])
    if not any(row.get("session_id") == "seed-staff-1" for row in r.json()):
        http.post(f"{API}/admin/staff", json={
            "discord_id": "900000000000000001", "roblox_display_name": "Staff Receiver",
            "roblox_nick": "staff_receiver", "roblox_link": "https://www.roblox.com/users/111/profile"
        }, headers={**admin["headers"], "Content-Type": "application/json"})
    return {
        "staff_h": {"Authorization": f"Bearer {_jwt_user('seed-staff-1')}", "User-Agent": UA},
    }


@pytest.fixture(scope="module")
def second_staff(admin, http):
    sid = f"TEST_staff2_{uuid.uuid4().hex[:8]}"
    did = f"TESTSTAFF{sid[-6:]}"
    unique_nick = f"second_{sid[-6:]}"
    _mongo.users.insert_one({
        "session_id": sid, "discord_id": did, "nickname": "SecondStaff",
        "roblox_display_name": "Second Staff", "roblox_nick": unique_nick,
        "roblox_link": "https://www.roblox.com/users/999/profile",
        "roblox_nick_normalized": unique_nick.lower(), "balance": 0.0, "skins": [],
        "session_version": 0, "created_at": datetime.now(timezone.utc),
    })
    r = http.post(f"{API}/admin/staff", json={
        "discord_id": did, "roblox_display_name": "Second Staff",
        "roblox_nick": unique_nick, "roblox_link": "https://www.roblox.com/users/999/profile",
    }, headers={**admin["headers"], "Content-Type": "application/json"})
    assert r.status_code in (201, 409), r.text
    return {"session_id": sid, "h": {"Authorization": f"Bearer {_jwt_user(sid)}", "User-Agent": UA}}


def _fresh_player(prefix="rjp"):
    sid = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}"
    did = f"9{int(time.time()*1000) % 10**16:016d}"
    nick = f"{prefix}_{sid[-6:]}"
    _mongo.users.insert_one({
        "session_id": sid, "discord_id": did, "nickname": nick,
        "roblox_display_name": prefix.title(), "roblox_nick": nick,
        "roblox_link": "https://www.roblox.com/users/12345/profile",
        "roblox_nick_normalized": nick.lower(),
        "balance": 0.0, "skins": [], "session_version": 0,
        "created_at": datetime.now(timezone.utc),
    })
    tok = _jwt_user(sid)
    return {"session_id": sid, "discord_id": did, "token": tok,
            "h": {"Authorization": f"Bearer {tok}", "User-Agent": UA, "X-Session-Id": sid}}


def _create_chat(http, player, kind="support"):
    body = {"kind": kind}
    r = http.post(f"{API}/chats", json=body,
                  headers={**player["h"], "Content-Type": "application/json"})
    assert r.status_code in (200, 201), r.text
    return r.json()


# ---------- cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    sessions = [u["session_id"] for u in _mongo.users.find({"session_id": {"$regex": "^TEST_"}}, {"session_id": 1})]
    if sessions:
        dep_ids = [d["id"] for d in _mongo.deposits.find({"session_id": {"$in": sessions}}, {"id": 1})]
        if dep_ids:
            _mongo.staff_reports.delete_many({"deposit_id": {"$in": dep_ids}})
            _mongo.staff_moves.delete_many({"deposit_id": {"$in": dep_ids}})
        _mongo.deposits.delete_many({"session_id": {"$in": sessions}})
        _mongo.chats.delete_many({"owner": {"$in": sessions}})
    _mongo.users.delete_many({"session_id": {"$regex": "^TEST_"}})
    _mongo.staff.delete_many({"discord_id": {"$regex": "^TESTSTAFF"}})


# ---------- Staff reject skin request ----------
class TestStaffRejectSkin:
    def _accept(self, http, staff_h, chat_id):
        r = http.post(f"{API}/staff/chats/{chat_id}/accept", headers=staff_h)
        assert r.status_code == 200, r.text

    def _open_deposit(self, http, staff_h, chat_id):
        # upload intake evidence -> auto-creates deposit
        # actually we need a deposit first; use evidence-intake which creates on demand
        # Alternative: fetch chat/messages to get deposit
        r = http.get(f"{API}/staff/chats/{chat_id}/messages", headers=staff_h)
        assert r.status_code == 200, r.text
        dep = r.json().get("deposit")
        if dep:
            return dep["id"]
        # trigger creation by uploading a tiny evidence
        import struct, zlib
        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        iend = chunk(b"IEND", b"")
        png = sig + ihdr + idat + iend
        r = http.post(f"{API}/staff/chats/{chat_id}/evidence", data={"purpose": "intake"},
                      files={"file": ("s.png", png, "image/png")}, headers=staff_h)
        assert r.status_code == 201, r.text
        return r.json()["deposit_id"]

    def test_reject_skin_in_assigned_state(self, http, seeded):
        player = _fresh_player("rjas")
        ch = _create_chat(http, player)
        chat_id = ch["id"]
        self._accept(http, seeded["staff_h"], chat_id)
        dep_id = self._open_deposit(http, seeded["staff_h"], chat_id)
        # reject
        r = http.post(f"{API}/staff/chats/{chat_id}/reject",
                      json={"deposit_id": dep_id, "reason": "long_wait"},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code == 200, r.text
        dep = _mongo.deposits.find_one({"id": dep_id},
                                       {"status": 1, "rejection_reason": 1, "rejected_by": 1, "resolved_at": 1})
        assert dep["status"] == "rejected"
        assert dep["rejection_reason"] == "long_wait"
        assert dep["rejected_by"].startswith("staff:")

    def test_reject_with_custom_reason(self, http, seeded):
        player = _fresh_player("rjfree")
        ch = _create_chat(http, player)
        chat_id = ch["id"]
        self._accept(http, seeded["staff_h"], chat_id)
        dep_id = self._open_deposit(http, seeded["staff_h"], chat_id)
        r = http.post(f"{API}/staff/chats/{chat_id}/reject",
                      json={"deposit_id": dep_id, "reason": "Игрок сам передумал"},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code == 200, r.text
        dep = _mongo.deposits.find_one({"id": dep_id}, {"rejection_reason": 1})
        assert dep["rejection_reason"] == "Игрок сам передумал"

    def test_reject_blocked_after_report_submitted(self, http, seeded):
        player = _fresh_player("rjrep")
        ch = _create_chat(http, player)
        chat_id = ch["id"]
        self._accept(http, seeded["staff_h"], chat_id)
        dep_id = self._open_deposit(http, seeded["staff_h"], chat_id)
        # Get an evidence id from the first upload
        import struct, zlib
        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        iend = chunk(b"IEND", b"")
        png = sig + ihdr + idat + iend
        ev = http.post(f"{API}/staff/chats/{chat_id}/evidence", data={"purpose": "intake"},
                       files={"file": ("s.png", png, "image/png")}, headers=seeded["staff_h"])
        # submit report
        rp = http.post(f"{API}/staff/chats/{chat_id}/report",
                       json={"items": [{"name": "AK", "qty": 1, "value": 300}], "evidence": [ev.json()["id"]],
                             "received": True, "value_checked": True, "note": ""},
                       headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert rp.status_code == 201, rp.text
        # now try reject -> 409
        r = http.post(f"{API}/staff/chats/{chat_id}/reject",
                      json={"deposit_id": dep_id, "reason": "long_wait"},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code == 409, r.text

    def test_reject_requires_chat_accepted(self, http, seeded, second_staff):
        # A chat owned by staff #1; second staff tries to reject -> 404 (chat not in scope)
        player = _fresh_player("rjscope")
        ch = _create_chat(http, player)
        chat_id = ch["id"]
        self._accept(http, seeded["staff_h"], chat_id)
        dep_id = self._open_deposit(http, seeded["staff_h"], chat_id)
        r = http.post(f"{API}/staff/chats/{chat_id}/reject",
                      json={"deposit_id": dep_id, "reason": "long_wait"},
                      headers={**second_staff["h"], "Content-Type": "application/json"})
        assert r.status_code == 404, r.text

    def test_reject_free_chat_needs_accept(self, http, seeded, second_staff):
        # A free chat: second_staff (not yet accepted) tries to reject -> 409 "Сначала примите чат"
        player = _fresh_player("rjfree2")
        ch = _create_chat(http, player)
        chat_id = ch["id"]
        # No accept by anyone: chat is free
        r = http.post(f"{API}/staff/chats/{chat_id}/reject",
                      json={"deposit_id": "does-not-matter", "reason": "long_wait"},
                      headers={**second_staff["h"], "Content-Type": "application/json"})
        assert r.status_code == 409, r.text
        assert "прим" in r.json().get("detail", "").lower()

    def test_reject_empty_reason_422(self, http, seeded):
        player = _fresh_player("rjer")
        ch = _create_chat(http, player)
        chat_id = ch["id"]
        self._accept(http, seeded["staff_h"], chat_id)
        dep_id = self._open_deposit(http, seeded["staff_h"], chat_id)
        r = http.post(f"{API}/staff/chats/{chat_id}/reject",
                      json={"deposit_id": dep_id, "reason": ""},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code in (400, 422), r.text

    def test_reject_player_token_forbidden(self, http, seeded):
        player = _fresh_player("rjpl")
        ch = _create_chat(http, player)
        r = http.post(f"{API}/staff/chats/{ch['id']}/reject",
                      json={"deposit_id": "x", "reason": "long_wait"},
                      headers={**player["h"], "Content-Type": "application/json"})
        assert r.status_code == 403, r.text


# ---------- Staff reject DonationAlerts money ----------
class TestStaffRejectMoney:
    def _seed_da_deposit(self, chat_id, session_id, paid=False):
        dep_id = str(uuid.uuid4())
        doc = {
            "id": dep_id, "session_id": session_id, "status": "pending",
            "payment_method": "donationalerts",
            "declared_amount": 300.0, "declared_currency": "RUB",
            "da_code": "BG-TEST", "da_phrase": "test phrase",
            "chat_id": chat_id, "via_chat": True,
            "created_at": datetime.now(timezone.utc),
        }
        if paid:
            doc["paid_claimed_at"] = datetime.now(timezone.utc)
        _mongo.deposits.insert_one(doc)
        return dep_id

    def test_reject_unpaid_da(self, http, seeded):
        player = _fresh_player("mnrj")
        ch = _create_chat(http, player)
        chat_id = ch["id"]
        r = http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        assert r.status_code == 200
        dep_id = self._seed_da_deposit(chat_id, player["session_id"], paid=False)
        r = http.post(f"{API}/staff/chats/{chat_id}/reject",
                      json={"deposit_id": dep_id, "reason": "no_reason"},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code == 200, r.text
        dep = _mongo.deposits.find_one({"id": dep_id}, {"status": 1, "rejection_reason": 1})
        assert dep["status"] == "rejected"
        assert dep["rejection_reason"] == "no_reason"

    def test_reject_blocked_after_paid_claim(self, http, seeded):
        player = _fresh_player("mnpd")
        ch = _create_chat(http, player)
        chat_id = ch["id"]
        r = http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        assert r.status_code == 200
        dep_id = self._seed_da_deposit(chat_id, player["session_id"], paid=True)
        r = http.post(f"{API}/staff/chats/{chat_id}/reject",
                      json={"deposit_id": dep_id, "reason": "no_reason"},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code == 409, r.text


# ---------- DonationAlerts KZT min ----------
class TestDonationAlertsMinKZT:
    def test_kzt_below_500_rejected(self, http):
        player = _fresh_player("kzt")
        r = http.post(f"{API}/donationalerts/requests",
                      json={"currency": "KZT", "amount": 499},
                      headers={**player["h"], "Content-Type": "application/json"})
        assert r.status_code == 400, r.text
        assert "500" in r.json().get("detail", "")
        assert "KZT" in r.json().get("detail", "")

    def test_kzt_at_500_ok(self, http):
        player = _fresh_player("kzt2")
        r = http.post(f"{API}/donationalerts/requests",
                      json={"currency": "KZT", "amount": 500},
                      headers={**player["h"], "Content-Type": "application/json"})
        # DONATIONALERTS_URL is set in preview .env for these tests -> should succeed 201
        assert r.status_code == 201, r.text
        body = r.json()
        assert "chat_id" in body and "deposit_id" in body

    def test_usd_no_min_applies(self, http):
        # USD not in MIN_AMOUNTS: 1 USD should pass
        player = _fresh_player("usd")
        r = http.post(f"{API}/donationalerts/requests",
                      json={"currency": "USD", "amount": 1},
                      headers={**player["h"], "Content-Type": "application/json"})
        assert r.status_code == 201, r.text
