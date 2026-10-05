"""End-to-end backend tests for the NEW staff chat console (/api/staff/chats/*).

Covers:
- chat scope: free chats + chats taken by this staff; another staff's chat -> 404/409
- accept: assigns chat to staff, second staff cannot take (409)
- send message auto-takes free chats
- evidence: creates a deposit on demand; guest chat -> 400; non-assigned -> 409
- report without screenshots -> 4xx; with -> 201 (deposit staff_state=review); owner approve
- staff cannot use withdrawal/coins routes -> 403; /api/staff/transfers POST -> 405
- reject flow via chat: owner rejects, staff submits return in chat, owner confirms move
"""
import io
import os
import struct
import time
import uuid
import zlib
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
UA = "staff-chat-console-test/1.0"
ADMIN_SEED = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]

_mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _jwt_user(sid):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sid, "role": "user", "exp": now + timedelta(days=30), "iat": now, "sv": 0},
                      JWT_SECRET, algorithm="HS256")


def _tiny_png():
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


PNG = _tiny_png()


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
    """Seed staff/player users and ensure staff row exists."""
    users = {
        "staff": {"session_id": "seed-staff-1", "discord_id": "900000000000000001", "nickname": "StaffTester",
                  "roblox_display_name": "Staff Receiver", "roblox_nick": "staff_receiver",
                  "roblox_link": "https://www.roblox.com/users/111/profile"},
        "player": {"session_id": "seed-player-1", "discord_id": "900000000000000002", "nickname": "PlayerTester",
                   "roblox_display_name": "Player One", "roblox_nick": "player_one",
                   "roblox_link": "https://www.roblox.com/users/222/profile"},
    }
    for u in users.values():
        _mongo.users.update_one({"session_id": u["session_id"]}, {"$setOnInsert": {
            **u, "balance": 0.0, "skins": [], "created_at": datetime.now(timezone.utc),
            "roblox_nick_normalized": u["roblox_nick"].lower()}}, upsert=True)
    # ensure staff registered
    r = http.get(f"{API}/admin/staff", headers=admin["headers"])
    assert r.status_code == 200
    if not any(row.get("session_id") == "seed-staff-1" for row in r.json()):
        http.post(f"{API}/admin/staff", json={
            "discord_id": "900000000000000001", "roblox_display_name": "Staff Receiver",
            "roblox_nick": "staff_receiver", "roblox_link": "https://www.roblox.com/users/111/profile"
        }, headers={**admin["headers"], "Content-Type": "application/json"})
    return {
        "staff_token": _jwt_user("seed-staff-1"),
        "player_token": _jwt_user("seed-player-1"),
        "staff_h": {"Authorization": f"Bearer {_jwt_user('seed-staff-1')}", "User-Agent": UA},
    }


def _fresh_player(prefix="chatp"):
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
    return {"session_id": sid, "discord_id": did, "token": _jwt_user(sid),
            "h": {"Authorization": f"Bearer {_jwt_user(sid)}", "User-Agent": UA},
            "sh": {"X-Session-Id": sid}}


def _create_chat(http, player, kind="support", expected_rap=None, session_hdr=True):
    body = {"kind": kind}
    if expected_rap is not None:
        body["expected_rap"] = expected_rap
    headers = {**player["h"], "Content-Type": "application/json"}
    if session_hdr:
        headers["X-Session-Id"] = player["session_id"]
    r = http.post(f"{API}/chats", json=body, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_guest_chat(http):
    """Create an anonymous guest chat (no auth token)."""
    sid = f"guest-{uuid.uuid4().hex[:12]}"
    r = http.post(f"{API}/chats", json={"kind": "support"},
                  headers={"Content-Type": "application/json", "X-Session-Id": sid, "User-Agent": UA})
    assert r.status_code in (200, 201), r.text
    return r.json(), sid


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
    _mongo.chats.delete_many({"owner": {"$regex": "^guest:"}, "kind": "support",
                              "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=1)}})


# ---------- second staff helper ----------
@pytest.fixture(scope="module")
def second_staff(admin, http):
    """Register a second staff member and return their token."""
    sid = f"TEST_staff2_{uuid.uuid4().hex[:8]}"
    did = f"TESTSTAFF{sid[-6:]}"
    unique_nick = f"second_{sid[-6:]}"
    _mongo.users.insert_one({
        "session_id": sid, "discord_id": did, "nickname": "SecondStaff",
        "roblox_display_name": "Second Staff", "roblox_nick": unique_nick,
        "roblox_link": "https://www.roblox.com/users/999/profile",
        "roblox_nick_normalized": unique_nick.lower(), "balance": 0.0, "skins": [],
        "session_version": 0,
        "created_at": datetime.now(timezone.utc),
    })
    r = http.post(f"{API}/admin/staff", json={
        "discord_id": did, "roblox_display_name": "Second Staff",
        "roblox_nick": unique_nick, "roblox_link": "https://www.roblox.com/users/999/profile",
    }, headers={**admin["headers"], "Content-Type": "application/json"})
    assert r.status_code in (201, 409), r.text
    tok = _jwt_user(sid)
    return {"session_id": sid, "token": tok, "h": {"Authorization": f"Bearer {tok}", "User-Agent": UA}}


# ---------- tests ----------
class TestScopeAndListing:
    def test_free_chat_visible_and_accept_assigns(self, http, seeded, second_staff):
        player = _fresh_player("scope")
        ch = _create_chat(http, player, kind="support")
        chat_id = ch["id"]

        # Free chat visible in staff list (status=open)
        r = http.get(f"{API}/staff/chats?status=open", headers=seeded["staff_h"])
        assert r.status_code == 200, r.text
        ids = [c["id"] for c in r.json().get("items", [])]
        assert chat_id in ids

        # Both staff can fetch messages before accept (chat is free)
        m1 = http.get(f"{API}/staff/chats/{chat_id}/messages", headers=seeded["staff_h"])
        assert m1.status_code == 200
        m2 = http.get(f"{API}/staff/chats/{chat_id}/messages", headers=second_staff["h"])
        assert m2.status_code == 200

        # Staff #1 accepts
        acc = http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        assert acc.status_code == 200, acc.text

        # Staff #2 now sees 404 (out of scope)
        m2b = http.get(f"{API}/staff/chats/{chat_id}/messages", headers=second_staff["h"])
        assert m2b.status_code == 404, m2b.text

        # Staff #2 accept -> 409
        acc2 = http.post(f"{API}/staff/chats/{chat_id}/accept", headers=second_staff["h"])
        assert acc2.status_code == 409, acc2.text

        # Staff #2 list with status=all still does not include this chat
        r2 = http.get(f"{API}/staff/chats?status=all", headers=second_staff["h"])
        assert r2.status_code == 200
        assert chat_id not in [c["id"] for c in r2.json().get("items", [])]

    def test_send_auto_takes_free_chat(self, http, seeded):
        player = _fresh_player("auto")
        ch = _create_chat(http, player, kind="support")
        chat_id = ch["id"]
        # send message without explicit accept
        r = http.post(f"{API}/staff/chats/{chat_id}/messages",
                      json={"text": "hi"},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code == 201, r.text
        # chat is now assigned to seeded staff
        c = _mongo.chats.find_one({"id": chat_id}, {"staff_id": 1, "status": 1})
        assert c.get("staff_id") is not None
        assert c["status"] == "active"


class TestCommandsAuth:
    def test_commands_ok_for_staff(self, http, seeded):
        r = http.get(f"{API}/staff/commands", headers=seeded["staff_h"])
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_commands_forbidden_for_player(self, http, seeded):
        # Use seeded player (guaranteed valid user token that isn't a staff member)
        r = http.get(f"{API}/staff/commands",
                     headers={"Authorization": f"Bearer {seeded['player_token']}", "User-Agent": UA})
        assert r.status_code == 403, r.text


class TestEvidenceAndDepositCreation:
    def test_evidence_creates_deposit_for_registered_player(self, http, seeded):
        player = _fresh_player("intake")
        ch = _create_chat(http, player, kind="support")
        chat_id = ch["id"]
        # accept first
        http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        # upload intake evidence
        r = http.post(f"{API}/staff/chats/{chat_id}/evidence",
                      data={"purpose": "intake"},
                      files={"file": ("s.png", PNG, "image/png")},
                      headers=seeded["staff_h"])
        assert r.status_code == 201, r.text
        j = r.json()
        assert "id" in j and "deposit_id" in j
        # deposit should exist and be in staff_state=assigned
        dep = _mongo.deposits.find_one({"id": j["deposit_id"]}, {"staff_state": 1, "status": 1, "staff_id": 1})
        assert dep["status"] == "pending"
        assert dep["staff_state"] == "assigned"

    def test_evidence_rejects_guest_chat(self, http, seeded):
        ch, gsid = _create_guest_chat(http)
        chat_id = ch["id"]
        # accept
        http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        r = http.post(f"{API}/staff/chats/{chat_id}/evidence",
                      data={"purpose": "intake"},
                      files={"file": ("s.png", PNG, "image/png")},
                      headers=seeded["staff_h"])
        assert r.status_code == 400, r.text

    def test_evidence_non_assigned_chat_409(self, http, seeded, second_staff):
        player = _fresh_player("na")
        ch = _create_chat(http, player, kind="support")
        chat_id = ch["id"]
        # staff1 takes it
        http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        # staff2 tries to upload evidence -> 404 (chat out of scope)
        r = http.post(f"{API}/staff/chats/{chat_id}/evidence",
                      data={"purpose": "intake"},
                      files={"file": ("s.png", PNG, "image/png")},
                      headers=second_staff["h"])
        assert r.status_code in (404, 409), r.text


class TestReportViaChatAndApprove:
    def _upload(self, http, staff_h, chat_id):
        r = http.post(f"{API}/staff/chats/{chat_id}/evidence",
                      data={"purpose": "intake"},
                      files={"file": ("s.png", PNG, "image/png")},
                      headers=staff_h)
        assert r.status_code == 201, r.text
        return r.json()

    def test_report_requires_screenshot(self, http, seeded):
        player = _fresh_player("noshot")
        ch = _create_chat(http, player, kind="support")
        chat_id = ch["id"]
        http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        # empty evidence -> 422 from Pydantic (min_length=1)
        r = http.post(f"{API}/staff/chats/{chat_id}/report",
                      json={"items": [{"name": "A", "qty": 1, "value": 300}], "evidence": [],
                            "received": True, "value_checked": True, "note": ""},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code in (400, 422), r.text

    def test_full_report_approve_flow(self, http, admin, seeded):
        player = _fresh_player("apr")
        ch = _create_chat(http, player, kind="support")
        chat_id = ch["id"]
        # accept + evidence + report
        http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        ev1 = self._upload(http, seeded["staff_h"], chat_id)
        rp = http.post(f"{API}/staff/chats/{chat_id}/report",
                       json={"items": [{"name": "AK", "qty": 1, "value": 300}], "evidence": [ev1["id"]],
                             "received": True, "value_checked": True, "note": ""},
                       headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert rp.status_code == 201, rp.text
        report = rp.json()
        assert abs(report["plan"]["credited"] - 240.0) < 0.01

        # deposit state=review
        dep_id = report["deposit_id"]
        dep = _mongo.deposits.find_one({"id": dep_id}, {"staff_state": 1})
        assert dep["staff_state"] == "review"

        # player balance unchanged
        u = _mongo.users.find_one({"session_id": player["session_id"]}, {"balance": 1})
        assert (u.get("balance") or 0) == 0

        # chat detail: deposit present (mine=True)
        d = http.get(f"{API}/staff/chats/{chat_id}/messages", headers=seeded["staff_h"])
        assert d.status_code == 200
        j = d.json()
        assert j["mine"] is True
        assert j.get("deposit") and j["deposit"]["id"] == dep_id

        # owner approves
        ap = http.post(f"{API}/admin/staff-reports/{report['id']}/approve", headers=admin["headers"])
        assert ap.status_code == 200, ap.text

        # after approval: chat has no ACTIVE deposit; a new report starts a new deposit
        d2 = http.get(f"{API}/staff/chats/{chat_id}/messages", headers=seeded["staff_h"])
        assert d2.status_code == 200
        j2 = d2.json()
        assert not j2.get("deposit"), f"expected no active deposit after approval, got {j2.get('deposit')}"

        # new report creates a new deposit
        ev2 = self._upload(http, seeded["staff_h"], chat_id)
        rp2 = http.post(f"{API}/staff/chats/{chat_id}/report",
                        json={"items": [{"name": "M4", "qty": 1, "value": 250}], "evidence": [ev2["id"]],
                              "received": True, "value_checked": True, "note": ""},
                        headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert rp2.status_code == 201, rp2.text
        assert rp2.json()["deposit_id"] != dep_id


class TestForbiddenRoutes:
    def test_transfers_post_removed(self, http, seeded):
        r = http.post(f"{API}/staff/transfers", json={"items": [], "evidence": [], "note": ""},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code in (404, 405), r.text

    def test_staff_cannot_call_admin_withdrawals_done(self, http, seeded):
        r = http.post(f"{API}/admin/chats/dummy/withdrawals/done", headers=seeded["staff_h"])
        assert r.status_code == 403, r.text

    def test_staff_cannot_grant_coins(self, http, seeded):
        r = http.post(f"{API}/admin/players/seed-player-1/coins",
                      json={"request_id": str(uuid.uuid4()), "amount_rub": 10, "note": "test"},
                      headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert r.status_code == 403, r.text


class TestRejectAndReturnViaChat:
    def test_reject_shows_return_form_state(self, http, admin, seeded):
        player = _fresh_player("rjc")
        ch = _create_chat(http, player, kind="support")
        chat_id = ch["id"]
        http.post(f"{API}/staff/chats/{chat_id}/accept", headers=seeded["staff_h"])
        ev = http.post(f"{API}/staff/chats/{chat_id}/evidence",
                       data={"purpose": "intake"},
                       files={"file": ("s.png", PNG, "image/png")},
                       headers=seeded["staff_h"])
        assert ev.status_code == 201, ev.text
        ev_id = ev.json()["id"]
        rp = http.post(f"{API}/staff/chats/{chat_id}/report",
                       json={"items": [{"name": "AK", "qty": 1, "value": 300}], "evidence": [ev_id],
                             "received": True, "value_checked": True, "note": ""},
                       headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert rp.status_code == 201, rp.text
        rid = rp.json()["id"]
        dep_id = rp.json()["deposit_id"]

        # owner rejects
        rj = http.post(f"{API}/admin/staff-reports/{rid}/reject",
                       json={"reason": "fake items"},
                       headers={**admin["headers"], "Content-Type": "application/json"})
        assert rj.status_code == 200, rj.text
        # deposit staff_state -> return_required
        dep = _mongo.deposits.find_one({"id": dep_id}, {"staff_state": 1})
        assert dep["staff_state"] == "return_required"

        # chat detail exposes state so UI shows return form
        d = http.get(f"{API}/staff/chats/{chat_id}/messages", headers=seeded["staff_h"])
        assert d.status_code == 200
        assert d.json()["deposit"]["staff_state"] == "return_required"

        # staff submits return via chat evidence + return endpoint
        ret_ev = http.post(f"{API}/staff/chats/{chat_id}/evidence",
                           data={"purpose": "return"},
                           files={"file": ("r.png", PNG, "image/png")},
                           headers=seeded["staff_h"])
        assert ret_ev.status_code == 201, ret_ev.text
        rt = http.post(f"{API}/staff/chats/{chat_id}/return",
                       json={"evidence": [ret_ev.json()["id"]], "note": ""},
                       headers={**seeded["staff_h"], "Content-Type": "application/json"})
        assert rt.status_code == 201, rt.text
        move_id = rt.json()["id"]

        # owner confirms
        cf = http.post(f"{API}/admin/staff-moves/{move_id}/confirm", headers=admin["headers"])
        assert cf.status_code == 200, cf.text
        dep2 = _mongo.deposits.find_one({"id": dep_id}, {"status": 1, "staff_state": 1})
        assert dep2["status"] == "rejected"
        assert dep2["staff_state"] == "returned"
