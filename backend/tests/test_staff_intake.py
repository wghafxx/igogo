"""End-to-end backend tests for staff skin-intake module.

Runs against the public preview REACT_APP_BACKEND_URL. Uses seeded staff and player tokens plus
extra users inserted directly in Mongo. Cleans up test data at teardown.
"""
import asyncio
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
UA = "staff-intake-test-agent/1.0"
ADMIN_SEED = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]

_mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _jwt_user(session_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": session_id, "role": "user", "exp": now + timedelta(days=30), "iat": now, "sv": 0}, JWT_SECRET, algorithm="HS256")


def _tiny_png() -> bytes:
    # 1x1 red PNG
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
    r = http.post(f"{API}/admin/login", json={"phrases": ADMIN_SEED}, headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"headers": {"Authorization": f"Bearer {token}", "User-Agent": UA}}


@pytest.fixture(scope="module")
def seeded():
    """Ensure seed staff + seed player exist and return their tokens."""
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
    return {
        "staff_token": _jwt_user("seed-staff-1"),
        "player_token": _jwt_user("seed-player-1"),
        "staff_session": "seed-staff-1",
        "player_session": "seed-player-1",
    }


@pytest.fixture(scope="module")
def staff_row(seeded, admin, http):
    """Make sure seed staff is registered in /admin/staff (created via API)."""
    r = http.get(f"{API}/admin/staff", headers=admin["headers"])
    assert r.status_code == 200, r.text
    for row in r.json():
        if row.get("session_id") == "seed-staff-1":
            return row
    # add if missing
    r = http.post(f"{API}/admin/staff", json={
        "discord_id": "900000000000000001", "roblox_display_name": "Staff Receiver",
        "roblox_nick": "staff_receiver", "roblox_link": "https://www.roblox.com/users/111/profile"
    }, headers={**admin["headers"], "Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return r.json()


def _fresh_player(prefix="test"):
    sid = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}"
    did = f"9{int(time.time()*1000) % 10**17:017d}"
    _mongo.users.insert_one({
        "session_id": sid, "discord_id": did, "nickname": f"{prefix}_{sid[-6:]}",
        "roblox_display_name": prefix.title(), "roblox_nick": f"{prefix}_{sid[-6:]}",
        "roblox_link": f"https://www.roblox.com/users/{did[-6:]}/profile",
        "roblox_nick_normalized": f"{prefix}_{sid[-6:]}".lower(),
        "balance": 0.0, "skins": [], "created_at": datetime.now(timezone.utc)
    })
    return {"session_id": sid, "discord_id": did, "token": _jwt_user(sid)}


def _new_deposit(http, player_token, expected_rap=300):
    r = http.post(f"{API}/chats", json={"kind": "deposit", "expected_rap": expected_rap},
                  headers={"Authorization": f"Bearer {player_token}", "Content-Type": "application/json", "User-Agent": UA})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    # response may embed deposit id under different keys; fall back to Mongo
    dep_id = body.get("deposit_id") or (body.get("deposit") or {}).get("id")
    if not dep_id:
        # find in mongo — latest pending deposit for this session
        doc = _mongo.deposits.find({"status": "pending"}).sort("created_at", -1)
        for d in doc:
            if d.get("chat_id") == body.get("id") or d.get("chat_id") == body.get("chat_id"):
                dep_id = d["id"]
                break
    assert dep_id, f"no deposit id in {body}"
    return dep_id


def _upload_ev(http, staff_token, purpose, deposit_id=None):
    data = {"purpose": purpose}
    if deposit_id:
        data["deposit_id"] = deposit_id
    r = http.post(f"{API}/staff/evidence", data=data,
                  files={"file": ("shot.png", PNG, "image/png")},
                  headers={"Authorization": f"Bearer {staff_token}", "User-Agent": UA})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------- module-level cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    # Delete deposits/reports/moves/chats for TEST_ users
    test_sessions = [u["session_id"] for u in _mongo.users.find({"session_id": {"$regex": "^TEST_"}}, {"session_id": 1})]
    if test_sessions:
        dep_ids = [d["id"] for d in _mongo.deposits.find({"session_id": {"$in": test_sessions}}, {"id": 1})]
        if dep_ids:
            _mongo.staff_reports.delete_many({"deposit_id": {"$in": dep_ids}})
            _mongo.staff_moves.delete_many({"deposit_id": {"$in": dep_ids}})
        _mongo.deposits.delete_many({"session_id": {"$in": test_sessions}})
        _mongo.chats.delete_many({"session_id": {"$in": test_sessions}})
    _mongo.users.delete_many({"session_id": {"$regex": "^TEST_"}})
    # remove extra staff added during tests (discord_id starts with "TESTSTAFF")
    _mongo.staff.delete_many({"discord_id": {"$regex": "^TESTSTAFF"}})


# ---------- tests ----------
class TestAuthorization:
    def test_anon_gets_401_on_staff_routes(self, http):
        assert http.get(f"{API}/staff/queue").status_code == 401
        assert http.get(f"{API}/staff/me").status_code == 401

    def test_player_gets_403_on_staff_routes(self, http, seeded):
        headers = {"Authorization": f"Bearer {seeded['player_token']}", "User-Agent": UA}
        assert http.get(f"{API}/staff/queue", headers=headers).status_code == 403
        assert http.get(f"{API}/staff/me", headers=headers).status_code == 403

    def test_staff_gets_403_on_admin_routes(self, http, seeded):
        headers = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        for path in ("/admin/staff", "/admin/staff-reviews", "/admin/deposits"):
            assert http.get(f"{API}{path}", headers=headers).status_code == 403, path


class TestStaffAdminManagement:
    def test_disable_blocks_staff_access(self, http, admin, staff_row, seeded):
        # disable
        r = http.post(f"{API}/admin/staff/{staff_row['id']}/disable", headers=admin["headers"])
        assert r.status_code == 200, r.text
        # staff now 403
        r2 = http.get(f"{API}/staff/me", headers={"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA})
        assert r2.status_code == 403
        # re-enable
        r3 = http.post(f"{API}/admin/staff/{staff_row['id']}/enable", headers=admin["headers"])
        assert r3.status_code == 200
        r4 = http.get(f"{API}/staff/me", headers={"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA})
        assert r4.status_code == 200, r4.text


class TestQueueAndClaim:
    def test_full_flow_report_approve(self, http, admin, seeded, staff_row):
        player = _fresh_player("claim")
        dep_id = _new_deposit(http, player["token"], expected_rap=300)

        # queue contains deposit
        q = http.get(f"{API}/staff/queue", headers={"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA})
        assert q.status_code == 200
        assert any(d["id"] == dep_id for d in q.json())

        # claim
        headers_staff = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        c = http.post(f"{API}/staff/requests/{dep_id}/claim", headers=headers_staff)
        assert c.status_code == 200, c.text

        # second claim -> 409
        c2 = http.post(f"{API}/staff/requests/{dep_id}/claim", headers=headers_staff)
        assert c2.status_code == 409

        # player cancel before transfer: staff_state=assigned still allows cancel per code
        # (we won't cancel; instead upload + report)
        ev1 = _upload_ev(http, seeded["staff_token"], "intake", dep_id)
        ev2 = _upload_ev(http, seeded["staff_token"], "intake", dep_id)

        report_payload = {
            "items": [{"name": "AK", "qty": 1, "value": 300.0}],
            "evidence": [ev1, ev2], "received": True, "value_checked": True, "note": "ok"
        }
        rep = http.post(f"{API}/staff/requests/{dep_id}/report", json=report_payload,
                        headers={**headers_staff, "Content-Type": "application/json"})
        assert rep.status_code == 201, rep.text
        rj = rep.json()
        assert rj["total_rap"] == 300.0
        # plan credited = total * 0.8 (no promo bonus by default)
        credited = rj["plan"]["credited"]
        assert abs(credited - 240.0) < 0.01, f"credited={credited}"

        # balance unchanged before decision
        u = _mongo.users.find_one({"session_id": player["session_id"]}, {"balance": 1})
        assert (u.get("balance") or 0) == 0

        # old admin route cannot confirm staff deposit
        conf = http.post(f"{API}/admin/deposits/{dep_id}/confirm", json={"rap": 300, "note": ""},
                         headers={**admin["headers"], "Content-Type": "application/json"})
        assert conf.status_code == 409, conf.text

        # player cancel after report -> 409
        can = http.post(f"{API}/deposits/{dep_id}/cancel",
                        headers={"Authorization": f"Bearer {player['token']}", "User-Agent": UA})
        assert can.status_code == 409, can.text

        # reviews list
        rv = http.get(f"{API}/admin/staff-reviews", headers=admin["headers"])
        assert rv.status_code == 200
        assert any(x["id"] == rj["id"] for x in rv.json()["reports"])

        # approve twice — second is idempotent
        ap1 = http.post(f"{API}/admin/staff-reports/{rj['id']}/approve", headers=admin["headers"])
        assert ap1.status_code == 200, ap1.text
        ap2 = http.post(f"{API}/admin/staff-reports/{rj['id']}/approve", headers=admin["headers"])
        assert ap2.status_code == 200, ap2.text
        assert ap2.json().get("already") is True or ap2.json()["report"]["status"] == "approved"

        # balance credited exactly once — total credited on deposit doc == 240
        dep_doc = _mongo.deposits.find_one({"id": dep_id}, {"credited": 1, "status": 1, "staff_state": 1})
        assert dep_doc["status"] == "confirmed", dep_doc
        assert dep_doc["staff_state"] == "approved", dep_doc
        assert abs(float(dep_doc.get("credited") or 0) - 240.0) < 0.5, dep_doc

    def test_concurrent_claim_only_one_wins(self, http, seeded, staff_row):
        # Create a 2nd staff user
        p2 = _fresh_player("staff2")
        _mongo.users.update_one({"session_id": p2["session_id"]}, {"$set": {"discord_id": "TESTSTAFF" + p2["session_id"][-6:]}})
        r = http.post(f"{API}/admin/staff", json={
            "discord_id": "TESTSTAFF" + p2["session_id"][-6:], "roblox_display_name": "Second",
            "roblox_nick": "second_staff", "roblox_link": "https://www.roblox.com/users/999/profile",
        }, headers={"Authorization": http.headers.get("Authorization", ""), **{"User-Agent": UA, "Content-Type": "application/json"}})
        # need admin headers
        admin_r = http.post(f"{API}/admin/login", json={"phrases": ADMIN_SEED}, headers={"Content-Type": "application/json", "User-Agent": UA})
        adm_h = {"Authorization": f"Bearer {admin_r.json()['token']}", "User-Agent": UA, "Content-Type": "application/json"}
        r = http.post(f"{API}/admin/staff", json={
            "discord_id": "TESTSTAFF" + p2["session_id"][-6:], "roblox_display_name": "Second",
            "roblox_nick": "second_staff", "roblox_link": "https://www.roblox.com/users/999/profile",
        }, headers=adm_h)
        assert r.status_code in (201, 409), r.text

        staff2_token = p2["token"]

        player = _fresh_player("race")
        dep_id = _new_deposit(http, player["token"], expected_rap=300)

        h1 = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        h2 = {"Authorization": f"Bearer {staff2_token}", "User-Agent": UA}

        results = [None, None]

        def do_claim(idx, headers):
            results[idx] = http.post(f"{API}/staff/requests/{dep_id}/claim", headers=headers).status_code

        import threading
        t1 = threading.Thread(target=do_claim, args=(0, h1))
        t2 = threading.Thread(target=do_claim, args=(1, h2))
        t1.start(); t2.start(); t1.join(); t2.join()

        assert sorted(results) == [200, 409], results


class TestEvidenceValidation:
    def test_reject_non_image(self, http, seeded):
        player = _fresh_player("evbad")
        dep_id = _new_deposit(http, player["token"], expected_rap=300)
        http.post(f"{API}/staff/requests/{dep_id}/claim",
                  headers={"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA})
        r = http.post(f"{API}/staff/evidence", data={"purpose": "intake", "deposit_id": dep_id},
                      files={"file": ("bad.txt", b"hello world", "text/plain")},
                      headers={"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA})
        assert r.status_code == 400, r.text

    def test_reject_oversize(self, http, seeded):
        player = _fresh_player("evbig")
        dep_id = _new_deposit(http, player["token"], expected_rap=300)
        http.post(f"{API}/staff/requests/{dep_id}/claim",
                  headers={"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA})
        big = PNG + b"\x00" * (5 * 1024 * 1024 + 100)
        r = http.post(f"{API}/staff/evidence", data={"purpose": "intake", "deposit_id": dep_id},
                      files={"file": ("big.png", big, "image/png")},
                      headers={"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA})
        assert r.status_code == 413, r.text

    def test_report_requires_both_checks(self, http, seeded):
        player = _fresh_player("chk")
        dep_id = _new_deposit(http, player["token"], expected_rap=300)
        h = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        http.post(f"{API}/staff/requests/{dep_id}/claim", headers=h)
        ev1 = _upload_ev(http, seeded["staff_token"], "intake", dep_id)
        r = http.post(f"{API}/staff/requests/{dep_id}/report",
                      json={"items": [{"name": "A", "qty": 1, "value": 300}], "evidence": [ev1],
                            "received": True, "value_checked": False},
                      headers={**h, "Content-Type": "application/json"})
        assert r.status_code == 400, r.text

    def test_report_min_rap(self, http, seeded):
        player = _fresh_player("minrap")
        dep_id = _new_deposit(http, player["token"], expected_rap=250)
        h = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        http.post(f"{API}/staff/requests/{dep_id}/claim", headers=h)
        ev1 = _upload_ev(http, seeded["staff_token"], "intake", dep_id)
        r = http.post(f"{API}/staff/requests/{dep_id}/report",
                      json={"items": [{"name": "A", "qty": 1, "value": 150}], "evidence": [ev1],
                            "received": True, "value_checked": True},
                      headers={**h, "Content-Type": "application/json"})
        assert r.status_code == 400, r.text


class TestRevisionAndReject:
    def test_revision_flow(self, http, admin, seeded):
        player = _fresh_player("rev")
        dep_id = _new_deposit(http, player["token"], expected_rap=300)
        h = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        http.post(f"{API}/staff/requests/{dep_id}/claim", headers=h)
        ev1 = _upload_ev(http, seeded["staff_token"], "intake", dep_id)
        r = http.post(f"{API}/staff/requests/{dep_id}/report",
                      json={"items": [{"name": "A", "qty": 1, "value": 300}], "evidence": [ev1],
                            "received": True, "value_checked": True},
                      headers={**h, "Content-Type": "application/json"})
        assert r.status_code == 201, r.text
        v1_id = r.json()["id"]

        # request revision
        rv = http.post(f"{API}/admin/staff-reports/{v1_id}/revision",
                       json={"reason": "please recheck values"},
                       headers={**admin["headers"], "Content-Type": "application/json"})
        assert rv.status_code == 200, rv.text

        # v2 submit
        ev2 = _upload_ev(http, seeded["staff_token"], "intake", dep_id)
        r2 = http.post(f"{API}/staff/requests/{dep_id}/report",
                       json={"items": [{"name": "A", "qty": 1, "value": 320}], "evidence": [ev2],
                             "received": True, "value_checked": True},
                       headers={**h, "Content-Type": "application/json"})
        assert r2.status_code == 201, r2.text
        v2_id = r2.json()["id"]
        assert r2.json()["version"] == 2

        # approving v1 fails
        ap_old = http.post(f"{API}/admin/staff-reports/{v1_id}/approve", headers=admin["headers"])
        assert ap_old.status_code == 409, ap_old.text

        # approve v2 works
        ap_new = http.post(f"{API}/admin/staff-reports/{v2_id}/approve", headers=admin["headers"])
        assert ap_new.status_code == 200, ap_new.text

    def test_reject_then_return(self, http, admin, seeded):
        player = _fresh_player("rej")
        dep_id = _new_deposit(http, player["token"], expected_rap=300)
        h = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        http.post(f"{API}/staff/requests/{dep_id}/claim", headers=h)
        ev1 = _upload_ev(http, seeded["staff_token"], "intake", dep_id)
        r = http.post(f"{API}/staff/requests/{dep_id}/report",
                      json={"items": [{"name": "A", "qty": 1, "value": 300}], "evidence": [ev1],
                            "received": True, "value_checked": True},
                      headers={**h, "Content-Type": "application/json"})
        rid = r.json()["id"]

        # reject
        rj = http.post(f"{API}/admin/staff-reports/{rid}/reject",
                       json={"reason": "fake items"},
                       headers={**admin["headers"], "Content-Type": "application/json"})
        assert rj.status_code == 200, rj.text

        # staff submits return
        ev_r = _upload_ev(http, seeded["staff_token"], "return", dep_id)
        rt = http.post(f"{API}/staff/requests/{dep_id}/return",
                       json={"evidence": [ev_r], "note": "returned"},
                       headers={**h, "Content-Type": "application/json"})
        assert rt.status_code == 201, rt.text
        move_id = rt.json()["id"]

        # admin confirm move
        cf = http.post(f"{API}/admin/staff-moves/{move_id}/confirm", headers=admin["headers"])
        assert cf.status_code == 200, cf.text
        dep = _mongo.deposits.find_one({"id": dep_id}, {"status": 1, "staff_state": 1})
        assert dep["status"] == "rejected"
        assert dep["staff_state"] == "returned"


class TestTransfers:
    def test_pending_transfer_then_confirm(self, http, admin, seeded):
        h = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        ev1 = _upload_ev(http, seeded["staff_token"], "transfer", None)
        tr = http.post(f"{API}/staff/transfers",
                       json={"items": [{"name": "AK", "qty": 1, "value": 300}], "evidence": [ev1], "note": "tx"},
                       headers={**h, "Content-Type": "application/json"})
        assert tr.status_code == 201, tr.text
        move_id = tr.json()["id"]
        # admin confirm
        cf = http.post(f"{API}/admin/staff-moves/{move_id}/confirm", headers=admin["headers"])
        assert cf.status_code == 200
        # idempotent
        cf2 = http.post(f"{API}/admin/staff-moves/{move_id}/confirm", headers=admin["headers"])
        assert cf2.status_code == 409


class TestShifts:
    def test_shift_start_pause_resume_end(self, http, seeded):
        h = {"Authorization": f"Bearer {seeded['staff_token']}", "User-Agent": UA}
        # ensure closed first
        cur = http.get(f"{API}/staff/shift", headers=h).json()
        if cur:
            http.post(f"{API}/staff/shift/end", headers=h)
        s = http.post(f"{API}/staff/shift/start", headers=h)
        assert s.status_code == 200, s.text
        # second start -> 409
        s2 = http.post(f"{API}/staff/shift/start", headers=h)
        assert s2.status_code == 409, s2.text
        # pause -> resume -> end
        assert http.post(f"{API}/staff/shift/pause", headers=h).status_code == 200
        assert http.post(f"{API}/staff/shift/resume", headers=h).status_code == 200
        assert http.post(f"{API}/staff/shift/end", headers=h).status_code == 200

    def test_stats_range_validation(self, http, admin, staff_row):
        r = http.get(f"{API}/admin/staff/{staff_row['id']}/stats",
                     params={"period": "range", "date_from": "not-a-date", "date_to": "2026-01-01"},
                     headers=admin["headers"])
        assert r.status_code == 400
        r2 = http.get(f"{API}/admin/staff/{staff_row['id']}/stats", params={"period": "today"},
                      headers=admin["headers"])
        assert r2.status_code == 200
        assert "stats" in r2.json()
        r3 = http.get(f"{API}/admin/staff/{staff_row['id']}/stats", params={"period": "all"},
                      headers=admin["headers"])
        assert r3.status_code == 200
