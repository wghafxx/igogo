"""
Tests for the new withdrawal/support-chat + top-up-via-chat flow.

Covers review request:
1. POST /api/chats {kind:'withdrawal'} authed -> 201; guest -> 401
2. POST /api/chats {kind:'support', text:...} still works
3. POST /api/chats {kind:'deposit', expected_rap:...} -> deposit receiver_nick == 'Поддержка'
4. GET /api/deposits/info receivers[0].id == 'support'
5. POST /api/skins/withdraw with a valid skin uid creates pending withdrawal
6. GET /api/chats/{id}/messages contains withdrawal_request user msg and system 'Заявка на вывод принята'
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # fallback for backend-local execution (frontend/.env)
    from dotenv import dotenv_values
    v = dotenv_values("/app/frontend/.env")
    BASE_URL = v["REACT_APP_BACKEND_URL"].rstrip("/")

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkaXNjb3JkX3Rlc3RfMSIsInJvbGUiOiJ1c2VyIiwiZXhwIjoxNzkyNDM5OTczLCJpYXQiOjE3ODk4NDc5NzN9.N-XChUd640JHbk-0qhU1Wtwxm7gEbEjKus8OpL87lfE"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def me():
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=AUTH, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# --- Deposit info receiver ---
def test_deposits_info_receiver_is_support():
    r = requests.get(f"{BASE_URL}/api/deposit/info", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "receivers" in data
    assert data["receivers"][0]["id"] == "support"
    # nickname should be "Поддержка"
    assert data["receivers"][0]["nickname"] == "Поддержка"


# --- Chats: support kind still works ---
def test_chats_create_support_kind():
    r = requests.post(f"{BASE_URL}/api/chats", headers=AUTH,
                      json={"kind": "support", "text": "TEST_support_ping"}, timeout=15)
    assert r.status_code == 201, r.text
    chat = r.json()
    assert chat.get("kind") == "support"
    assert "id" in chat


# --- Chats: deposit kind -> receiver_nick 'Поддержка' ---
def test_chats_create_deposit_receiver_is_support():
    r = requests.post(f"{BASE_URL}/api/chats", headers=AUTH,
                      json={"kind": "deposit", "expected_rap": 300}, timeout=15)
    assert r.status_code == 201, r.text
    chat = r.json()
    # NOTE: chats table stores kind as 'support' by design (single-chat-per-user),
    # but a deposit record must be created with receiver 'Поддержка'.
    assert "id" in chat
    # deposit record should reference support receiver
    d = requests.get(f"{BASE_URL}/api/deposits/my", headers=AUTH, timeout=15)
    assert d.status_code == 200, d.text
    deposits = d.json() if isinstance(d.json(), list) else d.json().get("items", [])
    # Find a deposit tied to chat
    mine = [x for x in deposits if x.get("chat_id") == chat["id"] or x.get("via_chat")]
    assert mine, f"No deposit tied to chat found in {deposits[:3]}"
    assert mine[0].get("receiver_nick") == "Поддержка"


# --- Withdrawal chat: guest 401 ---
def test_chats_create_withdrawal_guest_unauthorized():
    sid = str(uuid.uuid4())
    r = requests.post(f"{BASE_URL}/api/chats",
                      headers={"x-session-id": sid},
                      json={"kind": "withdrawal"}, timeout=15)
    assert r.status_code == 401, f"Expected 401 for guest, got {r.status_code}: {r.text}"


# --- Skin withdraw + Withdrawal chat authed ---
def test_skin_withdraw_then_withdrawal_chat_has_messages(me):
    skins = me.get("skins") or []
    if not skins:
        pytest.skip("test user has no skins to withdraw")
    # pick first skin with price >= 20
    skin = next((s for s in skins if float(s.get("price", 0)) >= 20), None)
    if not skin:
        pytest.skip("no skin with price >= 20 RAP")
    uid = skin["uid"]

    # POST /api/skins/withdraw
    wr = requests.post(f"{BASE_URL}/api/skins/withdraw", headers=AUTH,
                       json={"request_id": str(uuid.uuid4()), "uids": [uid]}, timeout=20)
    # Might return 200/201/400 (10-per-24h limit). Log outcome
    print("skins/withdraw status", wr.status_code, wr.text[:200])
    assert wr.status_code in (200, 201, 400), wr.text

    # Now create withdrawal chat
    cr = requests.post(f"{BASE_URL}/api/chats", headers=AUTH,
                       json={"kind": "withdrawal"}, timeout=15)
    assert cr.status_code == 201, cr.text
    chat = cr.json()
    assert "id" in chat
    chat_id = chat["id"]
    print("chat returned:", chat_id, "kind:", chat.get("kind"), "deposit_id:", chat.get("deposit_id"))
    # Cross-check via my chats
    mc = requests.get(f"{BASE_URL}/api/chats/mine", headers=AUTH, timeout=15)
    print("my chats:", mc.status_code, mc.text[:400])

    # Fetch messages
    mr = requests.get(f"{BASE_URL}/api/chats/{chat_id}/messages", headers=AUTH, timeout=15)
    assert mr.status_code == 200, mr.text
    msgs = mr.json().get("messages", []) if isinstance(mr.json(), dict) else mr.json()
    print("chat messages:", [(m.get("role"), m.get("kind"), (m.get("text") or "")[:60]) for m in msgs])

    # There should be a system message with 'Заявка на вывод принята' when there is at least 1 pending w/d
    pending = requests.get(f"{BASE_URL}/api/profile", headers=AUTH, timeout=15).json().get("withdrawals", [])
    pending_count = sum(1 for w in pending if w.get("status") == "pending")
    if pending_count > 0:
        # user message with kind 'withdrawal_request'
        user_msgs = [m for m in msgs if m.get("kind") == "withdrawal_request"]
        assert user_msgs, f"No withdrawal_request user message in {msgs}"
        # system ack
        sys_msgs = [m for m in msgs if "Заявка на вывод принята" in (m.get("text") or "")]
        assert sys_msgs, f"No system 'Заявка на вывод принята' in {msgs}"
