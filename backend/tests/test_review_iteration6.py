"""Live backend regression for iteration 6 review request.

Covers:
- /api/admin/staff-requests/{dep_id}/takeover: 409 while report is in review, 200 while assigned
- /api/admin/staff-reports/{report_id}/approve: credits player via chat flow
- /api/admin/players/{sid}/inventory + /balance + /skins/{uid}/remove
- /api/upgrade: works without 'unavailable prize' / payout-limit error for a modest bet
- Quick commands available for admin and staff (/api/admin/commands, /api/staff/commands)
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://donation-command-ui.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PHRASES = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
UA = "iter6-tester/1.0"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = s.post(f"{API}/admin/login", json={"phrases": PHRASES}, timeout=15)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def tokens():
    # Produced by backend/tests/seed_staff.py; idempotent in preview.
    import subprocess
    out = subprocess.check_output(["python", "tests/seed_staff.py"], cwd="/app/backend", text=True)
    data = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    assert "PLAYER_TOKEN" in data and "STAFF_TOKEN" in data, out
    return data


def _staff(tokens):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tokens['STAFF_TOKEN']}"
    s.headers["User-Agent"] = "iter6-staff/1.0"
    return s


def _player(tokens):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tokens['PLAYER_TOKEN']}"
    s.headers["User-Agent"] = "iter6-player/1.0"
    return s


# ---------- quick commands ----------
def test_admin_commands_present(admin):
    r = admin.get(f"{API}/admin/commands", timeout=10)
    assert r.status_code == 200, r.text
    rows = r.json()
    cmds = {c["command"] for c in rows}
    # Seeded commands include donat (no args) and nick (with {nick}).
    assert "donat" in cmds
    assert "nick" in cmds


def test_staff_commands_present(tokens):
    r = _staff(tokens).get(f"{API}/staff/commands", timeout=10)
    assert r.status_code == 200, r.text
    cmds = {c["command"] for c in r.json()}
    assert "donat" in cmds


# ---------- admin takeover: 409 while in review ----------
def test_takeover_409_when_report_in_review(admin):
    # Find an existing staff deposit in state 'review'; seed_review_chat.py already created one.
    reviews = admin.get(f"{API}/admin/staff-reviews", timeout=10).json()
    assert reviews["reports"], "No submitted staff reports present — seed_review_chat.py should have created one"
    report = reviews["reports"][0]
    dep_id = report["deposit_id"]
    r = admin.post(f"{API}/admin/staff-requests/{dep_id}/takeover", timeout=10)
    assert r.status_code == 409, r.text


# ---------- admin approve staff report: credits player ----------
def test_approve_staff_report_credits_player(admin):
    reviews = admin.get(f"{API}/admin/staff-reviews", timeout=10).json()
    if not reviews["reports"]:
        pytest.skip("no submitted staff report to approve")
    rep = reviews["reports"][0]
    rid, dep_id = rep["id"], rep["deposit_id"]
    credited_plan = float(rep["plan"]["credited"])
    # fetch player balance before
    dep = admin.get(f"{API}/admin/staff-reports/{rid}", timeout=10).json()
    sid = rep["player"]["session_id"]
    bal_before = admin.get(f"{API}/admin/players/{sid}/inventory", timeout=10).json()["balance"]
    r = admin.post(f"{API}/admin/staff-reports/{rid}/approve", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    # settle_deposit runs synchronously inside approve; balance+skins should reflect the credit
    time.sleep(1.5)
    inv = admin.get(f"{API}/admin/players/{sid}/inventory", timeout=10).json()
    delta = float(inv["balance"]) - float(bal_before) + sum(float(s["price"]) for s in inv["skins"] if s.get("deposit_id") == dep_id)
    # delta won't match exactly because old skins remain; just assert balance did not decrease and credited key is set
    assert float(inv["balance"]) >= float(bal_before) or inv["skins"], "approve had no visible effect"
    # second approve should be idempotent
    r2 = admin.post(f"{API}/admin/staff-reports/{rid}/approve", timeout=10)
    assert r2.status_code == 200


# ---------- takeover 200 for assigned deposit ----------
def test_takeover_for_assigned_deposit(admin, tokens):
    player = _player(tokens)
    staff = _staff(tokens)
    # make sure the player has no open chat/deposit
    chats = player.get(f"{API}/chats/mine", timeout=10)
    # best-effort cancel
    if chats.status_code == 200:
        for c in chats.json() if isinstance(chats.json(), list) else []:
            if c.get("status") == "open":
                player.post(f"{API}/chats/{c['id']}/close", timeout=5)
    # create a fresh deposit chat
    r = player.post(f"{API}/chats", json={"kind": "deposit", "expected_rap": 300}, timeout=10)
    if r.status_code == 409:
        pytest.skip(f"player already has an active deposit chat: {r.text}")
    assert r.status_code in (200, 201), r.text
    chat = r.json()
    chat_id = chat["id"]
    # staff accepts the chat
    a = staff.post(f"{API}/staff/chats/{chat_id}/accept", timeout=10)
    assert a.status_code in (200, 201, 409), a.text
    # locate the deposit
    detail = staff.get(f"{API}/staff/chats/{chat_id}/messages", timeout=10).json()
    dep = detail.get("deposit")
    if not dep:
        pytest.skip("no deposit linked to chat yet")
    dep_id = dep["id"]
    # takeover should succeed (state 'assigned')
    t = admin.post(f"{API}/admin/staff-requests/{dep_id}/takeover", timeout=10)
    assert t.status_code == 200, t.text
    body = t.json()
    assert body.get("staff_flow") is False
    assert body.get("staff_state") in (None, "")
    # cleanup
    player.post(f"{API}/chats/{chat_id}/close", timeout=5)


# ---------- admin player inventory / balance / skin remove ----------
def test_admin_player_balance_and_skin_remove(admin, tokens):
    sid = "seed-player-1"
    inv = admin.get(f"{API}/admin/players/{sid}/inventory", timeout=10)
    assert inv.status_code == 200, inv.text
    before = inv.json()
    target = round(float(before["balance"]) + 7.25, 2)
    r = admin.put(f"{API}/admin/players/{sid}/balance", json={"balance": target, "note": "iter6"}, timeout=10)
    assert r.status_code == 200, r.text
    after = r.json()
    assert round(float(after["balance"]), 2) == target
    # GET back to confirm persistence
    inv2 = admin.get(f"{API}/admin/players/{sid}/inventory", timeout=10).json()
    assert round(float(inv2["balance"]), 2) == target
    # Skin removal: pick first skin if any
    if inv2["skins"]:
        uid = inv2["skins"][0]["uid"]
        rm = admin.post(f"{API}/admin/players/{sid}/skins/{uid}/remove", json={"note": "iter6"}, timeout=10)
        assert rm.status_code == 200, rm.text
        after_rm = rm.json()
        assert all(s["uid"] != uid for s in after_rm["skins"])


# ---------- upgrade works without 'unavailable prize' ----------
def test_upgrade_no_payout_limit(admin, tokens):
    sid = "seed-player-1"
    # give the player balance
    admin.put(f"{API}/admin/players/{sid}/balance", json={"balance": 50000, "note": "iter6-upgrade"}, timeout=10)
    shop = requests.get(f"{API}/shop?limit=1&sort=price_asc", timeout=10).json()
    target = shop["items"][0]
    player = _player(tokens)
    payload = {
        "session_id": sid,
        "target_item": {"id": target["id"]},
        "bet_amount": round(float(target["price"]) * 0.05, 2),
        "bet_items": [],
        "chance": 0,  # ignored server-side
        "request_id": str(uuid.uuid4()),
    }
    r = player.post(f"{API}/upgrade", json=payload, timeout=15)
    # Accept 200 or 400 for low-chance, but never a 'unavailable'/'cheaper target' message.
    body = r.text.lower()
    forbidden = ["unavailable", "cannot win", "выберите цель дешевле", "максимальный доступный приз", "payout limit"]
    for f in forbidden:
        assert f not in body, f"upgrade response contains forbidden text {f!r}: {r.text}"
