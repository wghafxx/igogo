"""Live checks for the mandatory DonationAlerts phrase feature.

- POST /api/donationalerts/requests returns a phrase from da_phrases.PHRASES
- The da_instructions chat message contains that exact phrase in step 4 and exposes a top-level `phrase` field
- The deposit doc has da_phrase and description contains «phrase»
- Issuing many requests in a row never repeats a phrase within the previous 5 issued
- A phrase never equals the phrase of another still-pending DonationAlerts request

After the run we mark all created DA test deposits as cancelled+tg_notified=true so the retry loop
does not spam the owner. The bank / spin / drop code is untouched.
"""
import asyncio
import os
import pathlib

import pytest
import requests
import sys

sys.path.insert(0, "/app/backend")
from da_phrases import PHRASES  # noqa: E402

pytestmark = pytest.mark.live

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TOKEN = pathlib.Path("/root/logs/token.txt").read_text().strip()
TOKEN2 = pathlib.Path("/root/logs/token2.txt").read_text().strip()
H1 = {"Authorization": f"Bearer {TOKEN}"}
H2 = {"Authorization": f"Bearer {TOKEN2}"}


def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient("mongodb://localhost:27017").test_database


async def _cleanup_pending():
    db = _mongo()
    await db.deposits.update_many(
        {"payment_method": "donationalerts", "status": "pending",
         "session_id": {"$in": ["discord_test_1", "discord_test_2"]}},
        {"$set": {"status": "cancelled", "tg_notified": True}},
    )


@pytest.fixture(autouse=True)
def _wipe():
    asyncio.run(_cleanup_pending())
    yield
    asyncio.run(_cleanup_pending())


def _create(headers, currency="USD", amount=5):
    r = requests.post(f"{BASE}/api/donationalerts/requests", headers=headers,
                      json={"currency": currency, "amount": amount}, timeout=15)
    assert r.status_code == 201, r.text
    return r.json()


def test_phrase_in_response_is_from_catalog():
    body = _create(H1)
    assert body["phrase"] in PHRASES
    assert len(body["phrase"]) > 3


def test_chat_instructions_contain_phrase_in_step4_and_have_field():
    body = _create(H1)
    chat_id, dep_id, phrase = body["chat_id"], body["deposit_id"], body["phrase"]
    msgs = requests.get(f"{BASE}/api/chats/{chat_id}/messages", headers=H1, timeout=15).json()["messages"]
    inst = next(m for m in msgs if m.get("kind") == "da_instructions" and m.get("deposit_id") == dep_id)
    # phrase field on the message
    assert inst.get("phrase") == phrase, inst
    # step 4 contains the phrase
    step4 = next((line for line in inst["text"].splitlines() if line.strip().startswith("4.")), "")
    assert phrase in step4, f"phrase not in step 4: {step4!r}"


def test_deposit_has_da_phrase_and_description_contains_phrase():
    body = _create(H1)

    async def read():
        return await _mongo().deposits.find_one({"id": body["deposit_id"]}, {"_id": 0})

    dep = asyncio.run(read())
    assert dep["da_phrase"] == body["phrase"]
    assert f"«{body['phrase']}»" in dep["description"], dep["description"]


def test_phrases_never_repeat_within_last_five_over_many_issues():
    """Issue >30 DonationAlerts requests in a row, rejecting each so a new one can be created.

    Verifies:
      * no repeat within the last 5 issued (sliding window)
      * a phrase never collides with another still-pending DA request (we always reject before next)
    """
    issued = []
    # alternate between the two users so we don't need the reject-before-next dance twice per user
    for i in range(35):
        headers = H1 if i % 2 == 0 else H2
        body = _create(headers, currency="USD", amount=5 + i)
        phrase = body["phrase"]
        # window of last 5
        assert phrase not in issued[-5:], f"repeat within 5 at #{i}: {phrase} vs {issued[-5:]}"
        # not colliding with any other still-pending DA phrase
        async def other_pending():
            return await _mongo().deposits.count_documents(
                {"payment_method": "donationalerts", "status": "pending",
                 "da_phrase": phrase, "id": {"$ne": body["deposit_id"]}}
            )
        assert asyncio.run(other_pending()) == 0
        issued.append(phrase)
        # reject in Mongo so the next create for the same user succeeds (409 rule is per-user pending)
        async def reject():
            await _mongo().deposits.update_one(
                {"id": body["deposit_id"]},
                {"$set": {"status": "rejected", "tg_notified": True, "rejection_reason": "test"}},
            )
        asyncio.run(reject())
    assert len(set(issued)) > 20  # good spread across the 60-phrase catalog


def test_second_da_request_while_pending_returns_409():
    _create(H1)
    r = requests.post(f"{BASE}/api/donationalerts/requests", headers=H1,
                      json={"currency": "USD", "amount": 9}, timeout=15)
    assert r.status_code == 409, r.text
