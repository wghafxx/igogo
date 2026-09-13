"""Payment flow with isolated MongoDB and a fake provider; no real payments."""
import asyncio
import copy
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from mongomock.collection import Collection

BASE = "/api/payments/xrocket"
SECRET = "test-webhook-secret"
run = asyncio.run


def signed(raw, timestamp=None):
    timestamp = str(timestamp or int(time.time() * 1000))
    signature = hmac.new(SECRET.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return {"Signature": signature, "Signature-Timestamp": timestamp, "Signature-Version": "v1"}


@pytest.fixture
def payment_api(isolated_server, monkeypatch):
    server = isolated_server
    server.db = db = AsyncMongoMockClient()["payment_test"]
    xp = server.xp
    gateway = server.xrocket = xp.XrocketGateway("test-api-token", SECRET)
    invoices, calls = {}, []

    async def setup():
        await xp.ensure_indexes(db)
        await db.user_locks.create_index("session_id", unique=True)
        await db.bank_state.create_index("id", unique=True)
        await db.bank_ledger.create_index("id", unique=True)
        # No active promo on these users: refresh_user_promo does not need seeding.
        await db.users.insert_many([{"session_id": f"discord_{i}", "discord_id": str(i),
                                     "nickname": f"Player {i}", "balance": 0, "skins": []} for i in (1, 2)])

    run(setup())

    async def provider(db, method, path, **kwargs):
        calls.append((method, path, copy.deepcopy(kwargs)))
        if method == "POST":
            body = kwargs["json"]
            key = body["clientInvoiceId"]
            if key in invoices:
                raise xp.ProviderError(409, "client_id_already_taken")
            invoices[key] = {"id": f"inv-{len(invoices)}", "clientInvoiceId": key,
                             "priceAmount": body["priceAmount"], "priceCurrency": body["priceCurrency"],
                             "status": "active", "expiresAt": (xp.now() + timedelta(hours=1)).isoformat(),
                             "links": {"telegramBotLink": "https://t.me/xRocket?start=invoice-test"}}
        else:
            key = kwargs["params"]["clientInvoiceId"]
        if key not in invoices:
            raise xp.ProviderError(404)
        return copy.deepcopy(invoices[key])

    monkeypatch.setattr(gateway, "request", provider)

    async def send(method, path, who="discord_1", **kwargs):
        headers = kwargs.pop("headers", {})
        if who:
            headers["Authorization"] = f"Bearer {server.make_token(who)}"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await client.request(method, path, headers=headers, **kwargs)

    def request(method, path, **kwargs):
        return run(send(method, path, **kwargs))

    def create(**kwargs):
        payload = {"request_id": str(uuid.uuid4()), "amount_rub": 35, "currency": "USDT", **kwargs}
        response = request("POST", BASE + "/invoices", json=payload)
        assert response.status_code == 200, response.text
        return response.json()

    def webhook(doc, event_id="event-1", **kwargs):
        event = {"id": event_id, "type": "invoice", "data": {"event": "invoice_status_changed", "invoice": invoices[doc["id"]]}}
        raw = json.dumps(event).encode()
        return request("POST", BASE + "/webhook", who=None, content=raw, headers=signed(raw), **kwargs)

    return SimpleNamespace(server=server, db=db, xp=xp, gateway=gateway, invoices=invoices,
                           calls=calls, provider=provider, send=send, request=request, create=create, webhook=webhook)


@pytest.mark.parametrize("currency", ["GRAM", "USDT", "USDC", "BTC", "ETH", "TRX", "SOL", "BNB"])
def test_invoice_contract_and_zero_site_fee(payment_api, currency):
    api = payment_api
    doc = api.create(currency=currency)
    body = api.calls[0][2]["json"]
    assert body["priceAmount"] == "35.00" and body["priceCurrency"] == "rub"
    assert body["payoutCurrency"] == currency and body["payCurrencies"] == [currency]
    assert body["isFeePaidByUser"] is True and body["numPayments"] == 1
    assert body["expiresIn"] == 3_600_000
    assert body["callback"]["callbackUrl"] == "http://test/api/payments/xrocket/webhook"
    assert doc["expected_rap"] == doc["quoted_rap"] == 70
    assert doc["status"] == "awaiting_payment"
    assert "session_id" not in doc and "provider_invoice_id" not in doc
    assert run(api.db.users.find_one({"session_id": "discord_1"}))["balance"] == 0


@pytest.mark.parametrize("changes", [{"amount_rub": 34.99}, {"amount_rub": -1}, {"amount_rub": 35.001},
                                      {"amount_rub": 1000001}, {"currency": "FAKE"}, {"request_id": "invalid"}])
def test_invalid_input_never_calls_provider(payment_api, changes):
    payload = {"request_id": str(uuid.uuid4()), "amount_rub": 35, "currency": "USDT", **changes}
    assert payment_api.request("POST", BASE + "/invoices", json=payload).status_code == 422
    assert payment_api.calls == []


def test_idempotency_and_account_ownership(payment_api):
    api = payment_api
    key = str(uuid.uuid4())
    doc = api.create(request_id=key)
    assert api.create(request_id=key)["id"] == doc["id"]
    assert len(api.calls) == 1
    payload = {"request_id": key, "amount_rub": 36, "currency": "USDT"}
    assert api.request("POST", BASE + "/invoices", json=payload).status_code == 409
    payload["amount_rub"] = 35
    assert api.request("POST", BASE + "/invoices", who="discord_2", json=payload).status_code == 409
    for method, suffix in (("GET", ""), ("POST", "/refresh")):
        assert api.request(method, BASE + "/invoices/" + doc["id"] + suffix, who="discord_2").status_code == 404
    assert api.request("GET", BASE + "/invoices", who="discord_2").json() == []
    assert api.request("GET", BASE + "/invoices", who=None).status_code == 401
    # Browser polling reads local state only.
    assert api.request("GET", BASE + "/invoices/" + doc["id"]).status_code == 200
    assert len(api.calls) == 1


def test_timeout_recovers_original_invoice(payment_api, monkeypatch):
    api = payment_api

    async def interrupted(*args, **kwargs):
        await api.provider(*args, **kwargs)
        raise api.xp.ProviderError(503)

    monkeypatch.setattr(api.gateway, "request", interrupted)
    payload = {"request_id": str(uuid.uuid4()), "amount_rub": 35, "currency": "USDT"}
    assert api.request("POST", BASE + "/invoices", json=payload).status_code == 503
    monkeypatch.setattr(api.gateway, "request", api.provider)
    assert api.request("POST", BASE + "/invoices", json=payload).json()["status"] == "awaiting_payment"
    assert [call[0] for call in api.calls] == ["POST", "GET"]
    assert len(api.invoices) == run(api.db.deposits.count_documents({})) == 1


def test_paid_invoice_credits_once_and_freezes_promo(payment_api):
    api = payment_api
    run(api.db.promo_codes.insert_one({"id": "p", "code": "PELMEN", "percent": 10, "deleted": False}))
    run(api.db.users.update_one({"session_id": "discord_1"}, {"$set": {"promo_id": "p", "promo_code": "PELMEN", "promo_bonus": .1}}))
    doc = api.create()
    assert doc["quoted_rap"] == 77
    run(api.db.promo_codes.update_one({"id": "p"}, {"$set": {"percent": 30}}))
    api.invoices[doc["id"]]["status"] = "paid"
    assert api.webhook(doc).status_code == 200
    assert api.webhook(doc).status_code == 200
    assert api.webhook(doc, "event-2").status_code == 200
    response = api.request("POST", BASE + "/invoices/" + doc["id"] + "/refresh")
    assert response.json()["status"] == "confirmed" and response.json()["credited"] == 77
    user = run(api.db.users.find_one({"session_id": "discord_1"}))
    assert user["balance"] == 77 and user["skins"] == [] and user["credited_deposits"] == [doc["id"]]
    assert run(api.db.bank_state.find_one({"id": "main"}))["bank"] == 70
    assert run(api.db.bank_ledger.count_documents({})) == 1
    saved = run(api.db.deposits.find_one({"id": doc["id"]}))
    assert saved["fee"] == 0 and saved["bonus_applied"] == .1 and saved["balance_credited"] == 77


@pytest.mark.parametrize("status", ["active", "partially_paid", "expired", "cancelled"])
def test_only_authoritative_full_payment_credits(payment_api, status):
    api = payment_api
    doc = api.create()
    api.invoices[doc["id"]]["status"] = status
    # Even a signed event that claims 'paid' is not the source of monetary truth.
    event = {"id": "evt", "type": "invoice", "data": {"event": "payment_status_changed",
             "invoice": {**api.invoices[doc["id"]], "status": "paid"}}}
    raw = json.dumps(event).encode()
    assert api.request("POST", BASE + "/webhook", who=None, content=raw, headers=signed(raw)).status_code == 200
    assert run(api.db.users.find_one({"session_id": "discord_1"}))["balance"] == 0
    assert run(api.db.bank_ledger.count_documents({})) == 0


@pytest.mark.parametrize("field,value", [("priceAmount", "35.001"), ("priceAmount", "350"),
                                           ("priceCurrency", "USDT"), ("clientInvoiceId", "other"), ("id", "other")])
def test_invoice_mismatch_never_credits(payment_api, field, value):
    api = payment_api
    doc = api.create()
    api.invoices[doc["id"]].update(status="paid", **{field: value})
    assert api.request("POST", BASE + "/invoices/" + doc["id"] + "/refresh").status_code == 409
    assert run(api.db.users.find_one({"session_id": "discord_1"}))["balance"] == 0


@pytest.mark.parametrize("mode", ["missing", "tampered", "expired", "future", "version", "unicode"])
def test_webhook_signature_enforced(payment_api, mode):
    raw = b'{"id":"event","type":"invoice"}'
    headers = signed(raw)
    if mode == "missing":
        headers = {}
    elif mode == "tampered":
        raw += b" "
    elif mode in ("expired", "future"):
        headers = signed(raw, int(time.time() * 1000) + (-600000 if mode == "expired" else 600000))
    elif mode == "version":
        headers["Signature-Version"] = "v2"
    else:
        # Check directly: HTTP itself rejects non-ASCII header values.
        assert not payment_api.gateway.verify_signature(raw, {"signature-version": "v1", "signature-timestamp": "１２３"})
        return
    assert payment_api.request("POST", BASE + "/webhook", who=None, content=raw, headers=headers).status_code == 401
    assert payment_api.calls == []


def test_malformed_webhook_and_oversize_body(payment_api):
    for raw, status in ((b"{", 400), (b"x" * 65537, 413)):
        assert payment_api.request("POST", BASE + "/webhook", who=None, content=raw, headers=signed(raw)).status_code == status


def test_interrupted_credit_resumes_without_double_credit(payment_api, monkeypatch):
    api = payment_api
    doc = api.create()
    api.invoices[doc["id"]]["status"] = "paid"
    original = Collection.update_one
    failed = False

    def fail_once(collection, *args, **kwargs):
        nonlocal failed
        if collection.name == "bank_ledger" and not failed:
            failed = True
            raise RuntimeError("simulated write outage")
        return original(collection, *args, **kwargs)

    monkeypatch.setattr(Collection, "update_one", fail_once)
    with pytest.raises(RuntimeError, match="simulated write"):
        api.webhook(doc)
    saved = run(api.db.deposits.find_one({"id": doc["id"]}))
    assert saved["status"] == "processing"
    assert run(api.db.users.find_one({"session_id": "discord_1"}))["balance"] == 70
    # Recovery uses the already verified persisted plan without another API request.
    run(api.xp.synchronize(api.db, api.gateway, saved))
    assert api.webhook(doc).status_code == 200
    assert run(api.db.users.find_one({"session_id": "discord_1"}))["balance"] == 70
    assert run(api.db.bank_state.find_one({"id": "main"}))["bank"] == 70
    assert run(api.db.bank_ledger.count_documents({})) == 1


def test_manual_confirmation_blocked_and_missing_keys_disable(payment_api):
    api = payment_api
    doc = api.create()
    from deposit_settlement import confirm_deposit
    with pytest.raises(HTTPException) as error:
        run(confirm_deposit(api.db, doc["id"], 1000, ""))
    assert error.value.status_code == 409
    api.gateway.token = ""
    assert api.request("GET", BASE + "/info", who=None).json()["enabled"] is False
    assert api.request("POST", BASE + "/invoices", json={"request_id": str(uuid.uuid4()), "amount_rub": 35, "currency": "BTC"}).status_code == 503


def test_gateway_rate_limit_and_official_host_only(payment_api):
    api = payment_api
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(429, json={"type": "https://test/rate_limited"}, headers={"Retry-After": "120"})

    gateway = api.xp.XrocketGateway("mock-token", SECRET, transport=httpx.MockTransport(transport))
    for _ in range(2):
        with pytest.raises(api.xp.ProviderError) as error:
            run(gateway.request(api.db, "GET", "/api/v1/invoice"))
        assert error.value.status == 429
    assert len(requests) == 1 and requests[0].headers["Authorization"] == "Bearer mock-token"
    assert run(api.db.xrocket_api_slots.find_one({}))["next_at"] > api.xp.now().replace(tzinfo=None) + timedelta(seconds=110)
    with pytest.raises(ValueError):
        api.xp.XrocketGateway("mock-token", SECRET, "https://untrusted.example")


def test_unexpected_provider_shapes_and_links_rejected(payment_api):
    api = payment_api
    doc = api.create()
    for value in (None, [], "bad"):
        with pytest.raises(HTTPException) as error:
            api.xp.validate_invoice(doc, value)
        assert error.value.status_code == 502
    for link in ("https://evil.example/pay", "javascript:alert(1)", "https://t.me/someone_else", 12):
        with pytest.raises(HTTPException):
            api.xp.invoice_link({"links": {"telegramBotLink": link}})


def test_background_recovery_without_webhook_or_browser(payment_api, monkeypatch):
    api = payment_api
    doc = api.create()
    api.invoices[doc["id"]]["status"] = "paid"
    run(api.db.deposits.update_one({"id": doc["id"]}, {"$set": {"next_check_at": api.xp.now() - timedelta(minutes=2)}}))
    ticks = 0

    async def one_tick(_):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(api.xp, "asyncio", SimpleNamespace(sleep=one_tick))
    with pytest.raises(asyncio.CancelledError):
        run(api.xp.reconcile_loop(api.db, api.gateway))
    assert run(api.db.users.find_one({"session_id": "discord_1"}))["balance"] == 70
    assert run(api.db.deposits.find_one({"id": doc["id"]}))["status"] == "confirmed"
