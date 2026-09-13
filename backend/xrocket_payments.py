"""xRocket Pay API invoices. Amounts and credits are fixed by the server.

Contract: https://pay.api.xrocket.exchange/api/docs/
The payer covers xRocket's fee (isFeePaidByUser); BLOXGRADE takes no fee.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_CEILING
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from deposit_settlement import settle_deposit

logger = logging.getLogger(__name__)
MIN_RUB = Decimal("35")
MAX_RUB = Decimal("1000000")
RAP_RUB_RATE = Decimal("0.50")
CURRENCIES = ("GRAM", "USDT", "USDC", "BTC", "ETH", "TRX", "SOL", "BNB")
PENDING = ("creating", "awaiting_payment", "processing")
PRODUCTION_API = "https://pay.api.xrocket.exchange"
TESTNET_API = "https://pay.api.testnet.xrocket.exchange"


def now():
    return datetime.now(timezone.utc)


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def public_invoice(doc):
    return {key: doc.get(key) for key in (
        "id", "status", "amount_rub", "currency", "expected_rap", "quoted_rap",
        "promo_code", "promo_bonus", "credited", "invoice_url", "created_at", "expires_at",
        "price_amount", "price_currency", "error_message",
    )}


class ProviderError(Exception):
    def __init__(self, status, code="", retry_after=4):
        self.status, self.code, self.retry_after = status, code, retry_after


def payment_error(error):
    if error.status == 429:
        return HTTPException(429, "xRocket занят. Повторите проверку немного позже", headers={"Retry-After": str(error.retry_after)})
    if error.status == 401 or error.code in ("unauthorized", "forbidden"):
        return HTTPException(503, "xRocket не принимает ключ приложения. Обратитесь в поддержку сайта")
    if error.code == "not_implemented":
        return HTTPException(503, "xRocket не поддерживает выбранные параметры счёта. Обратитесь в поддержку сайта")
    if error.status in (400, 403, 404):
        return HTTPException(400, "xRocket не может создать счёт на эту сумму в выбранной валюте. Выберите другую валюту или сумму")
    return HTTPException(503, "Оплата через xRocket временно недоступна. Попробуйте позже")


class XrocketGateway:
    def __init__(self, token="", webhook_secret="", base_url=PRODUCTION_API, transport=None):
        self.token = token.strip()
        self.webhook_secret = webhook_secret.strip()
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        # Never send the API credential to an arbitrary configured host.
        if self.base_url not in (PRODUCTION_API, TESTNET_API):
            raise ValueError("XROCKET_API_BASE_URL must be the official production or testnet API")

    @property
    def enabled(self):
        return bool(self.token and self.webhook_secret)

    async def request(self, db, method, path, **kwargs):
        if not self.enabled:
            raise HTTPException(503, "Оплата через xRocket пока не подключена")
        # xRocket allows 20 requests/minute per endpoint/IP. Coordinate workers
        # through MongoDB; browser status polling never calls the provider.
        slot = f"{method}:{path}"
        for attempt in range(2):
            try:
                await db.xrocket_api_slots.find_one_and_update(
                    {"_id": slot, "next_at": {"$lte": now()}},
                    {"$set": {"next_at": now() + timedelta(seconds=3.2)}}, upsert=True,
                )
                break
            except DuplicateKeyError:
                reservation = await db.xrocket_api_slots.find_one({"_id": slot})
                due = reservation["next_at"].replace(tzinfo=timezone.utc)
                delay = max(0.05, (due - now()).total_seconds() + .05)
                if attempt or delay > 4:
                    raise ProviderError(429, retry_after=max(4, int(delay) + 1)) from None
                await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=15, transport=self.transport,
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            ) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise ProviderError(503) from None
        if not response.is_success:
            try:
                code = str(response.json().get("type", "")).rsplit("/", 1)[-1]
            except (ValueError, AttributeError):
                code = ""
            retry = response.headers.get("Retry-After", "60")
            retry = min(3600, max(4, int(retry))) if retry.isdigit() else 60
            if response.status_code == 429:
                await db.xrocket_api_slots.update_one({"_id": slot}, {"$set": {"next_at": now() + timedelta(seconds=retry)}})
            raise ProviderError(response.status_code, code, retry)
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise ProviderError(503) from None

    def verify_signature(self, raw, headers):
        signature = headers.get("signature", "")
        timestamp = headers.get("signature-timestamp", "")
        if not self.webhook_secret or headers.get("signature-version") != "v1":
            return False
        if len(timestamp) > 16 or not timestamp.isascii() or not timestamp.isdigit():
            return False
        if abs(time.time() * 1000 - int(timestamp)) > 300_000:
            return False
        if len(signature) != 64 or not signature.isascii():
            return False
        expected = hmac.new(self.webhook_secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


async def ensure_indexes(db):
    await db.deposits.create_index(
        "id", unique=True, name="xrocket_order_id",
        partialFilterExpression={"payment_method": "xrocket"},
    )
    await db.deposits.create_index("provider_invoice_id", unique=True, partialFilterExpression={"provider_invoice_id": {"$type": "string"}})
    await db.deposits.create_index([("payment_method", 1), ("status", 1), ("next_check_at", 1)])
    await db.xrocket_webhooks.create_index("created_at", expireAfterSeconds=30 * 86400)


async def quote_crypto(db, gateway, amount_rub, currency):
    # Production rejects RUB/crypto invoices despite the broader OpenAPI schema.
    # Freeze the RUB exchange rate and a single-currency amount BEFORE creation.
    cached = await db.xrocket_rates.find_one({"_id": "RUB", "valid_until": {"$gt": now()}})
    if not cached:
        rates = await gateway.request(db, "GET", "/api/v1/rates", params={"base": "RUB", "assets": list(CURRENCIES)})
        if not isinstance(rates, list):
            raise HTTPException(503, "Не удалось получить курс xRocket. Повторите попытку")
        values = {}
        for row in rates:
            try:
                rate = Decimal(str(row["rate"]))
                if row["currency"] in CURRENCIES and rate.is_finite() and rate > 0:
                    values[row["currency"]] = str(rate)
            except (KeyError, TypeError, InvalidOperation):
                continue
        cached = {"rates": values, "valid_until": now() + timedelta(seconds=30)}
        await db.xrocket_rates.update_one({"_id": "RUB"}, {"$set": cached}, upsert=True)
    if currency not in cached["rates"]:
        raise HTTPException(503, "Курс выбранной валюты временно недоступен. Выберите другую валюту")
    rate = Decimal(cached["rates"][currency])
    # USDT/USDC have six decimals; using more is truncated by the live API.
    # BTC needs eight decimals for ruble-sized payments; other assets accept six.
    step = Decimal("0.00000001" if currency == "BTC" else "0.000001")
    price = (amount_rub / rate).quantize(step, rounding=ROUND_CEILING)
    return {"price_amount": format(price, "f"), "price_currency": currency,
            "rub_rate": str(rate), "price_quoted_at": now()}


def invoice_body(doc, app_url):
    return {
        "priceAmount": doc["price_amount"], "priceCurrency": doc["price_currency"],
        "payoutCurrency": doc["currency"], "payCurrencies": [doc["currency"]],
        "numPayments": 1, "clientInvoiceId": doc["id"], "isFeePaidByUser": True,
        # Verified against production expiresAt: this field is currently seconds.
        "expiresIn": 3600,
        "description": f"BLOXGRADE · {doc['quoted_rap']:.2f} RAP",
        "callback": {"callbackUrl": f"{app_url}/api/payments/xrocket/webhook", "payload": {"order_id": doc["id"]}},
        "url": {"successUrl": f"{app_url}/profile?payment=xrocket", "cancelUrl": f"{app_url}/profile?payment=xrocket"},
    }


def validate_invoice(doc, invoice):
    if not isinstance(invoice, dict):
        raise HTTPException(502, "Некорректный ответ xRocket")
    expected_price = doc.get("price_amount", doc["amount_rub"])
    expected_currency = doc.get("price_currency", "rub")
    try:
        actual_price = Decimal(str(invoice["priceAmount"]))
        valid_amount = actual_price.is_finite() and actual_price > 0 and actual_price == Decimal(str(expected_price))
    except (KeyError, InvalidOperation, ValueError, TypeError):
        valid_amount = False
    if not isinstance(invoice.get("id"), str) or not invoice["id"]:
        raise HTTPException(502, "Некорректный ответ xRocket")
    if (invoice.get("clientInvoiceId") != doc["id"] or
            str(invoice.get("priceCurrency", "")).upper() != expected_currency.upper() or not valid_amount or
            (doc.get("provider_invoice_id") and doc["provider_invoice_id"] != invoice["id"])):
        raise HTTPException(409, "Данные счёта xRocket не совпадают с заявкой")


def invoice_link(invoice):
    links = invoice.get("links")
    link = links.get("telegramBotLink", "") if isinstance(links, dict) else ""
    if not isinstance(link, str):
        raise HTTPException(502, "xRocket не вернул ссылку для оплаты")
    parsed = urlparse(link)
    if parsed.scheme != "https" or parsed.netloc != "t.me" or parsed.path.lower() not in ("/xrocket", "/xrocket_testnet_bot"):
        raise HTTPException(502, "xRocket не вернул ссылку для оплаты")
    return link


async def receive_invoice(db, doc, invoice):
    validate_invoice(doc, invoice)
    provider_status = invoice.get("status")
    changes = {"provider_invoice_id": invoice["id"], "provider_status": provider_status, "last_checked_at": now(), "error_message": None}
    if isinstance(invoice.get("links"), dict) and invoice["links"].get("telegramBotLink"):
        changes["invoice_url"] = invoice_link(invoice)
    if isinstance(invoice.get("expiresAt"), str):
        try:
            changes["expires_at"] = datetime.fromisoformat(invoice["expiresAt"].replace("Z", "+00:00"))
        except ValueError:
            pass
    if provider_status == "paid":
        # Persist the immutable plan before any money moves. Existing settlement
        # deduplicates user AND bank credits and resumes interrupted writes.
        plan = {
            "status": "processing", "settlement_version": 1, "planned_at": now(),
            "rap": doc["expected_rap"], "fee": 0.0, "bonus_applied": doc["promo_bonus"],
            "credited": doc["quoted_rap"], "amount": doc["quoted_rap"],
            "balance_credited": doc["quoted_rap"], "skins_total": 0.0, "issued_skins": [],
        }
        await db.deposits.update_one({"id": doc["id"], "status": {"$nin": ["processing", "confirmed"]}}, {"$set": {**changes, **plan}})
        fresh = await db.deposits.find_one({"id": doc["id"]}, {"_id": 0})
        if fresh["status"] == "processing":
            await settle_deposit(db, fresh)
    else:
        if provider_status in ("expired", "cancelled"):
            changes.update(status=provider_status, resolved_at=now())
        elif provider_status in ("active", "partially_paid"):
            changes["status"] = "awaiting_payment"
        await db.deposits.update_one({"id": doc["id"], "status": {"$nin": ["processing", "confirmed"]}}, {"$set": changes})
    return await db.deposits.find_one({"id": doc["id"]}, {"_id": 0})


async def create_invoice(db, gateway, user, request_id, amount_rub, currency, app_url):
    if not gateway.enabled:
        raise HTTPException(503, "Оплата через xRocket пока не подключена")
    order_id = f"xrocket:{request_id}"
    doc = await db.deposits.find_one({"id": order_id}, {"_id": 0})
    existed = doc is not None
    if doc and (doc["session_id"] != user["session_id"] or money(doc["amount_rub"]) != amount_rub or doc["currency"] != currency):
        raise HTTPException(409, "Этот запрос уже использован для другого счёта")
    if not doc:
        existing = await db.deposits.find_one({
            "session_id": user["session_id"], "payment_method": "xrocket", "status": "awaiting_payment",
            "amount_rub": float(amount_rub), "currency": currency, "invoice_url": {"$type": "string"},
            "expires_at": {"$gt": now()},
        }, {"_id": 0}, sort=[("created_at", -1)])
        if existing:
            return public_invoice(existing)
        if await db.deposits.count_documents({"session_id": user["session_id"], "payment_method": "xrocket", "status": {"$in": list(PENDING)}}) >= 5:
            raise HTTPException(429, "У вас уже 5 неоплаченных счетов. Откройте один из них")
        recent = await db.deposits.find_one({"session_id": user["session_id"], "payment_method": "xrocket", "status": {"$ne": "payment_error"}, "created_at": {"$gt": now() - timedelta(seconds=20)}})
        if recent:
            raise HTTPException(429, "Подождите 20 секунд перед созданием нового счёта")
        bonus = max(Decimal("0"), min(Decimal("0.5"), Decimal(str(user.get("promo_bonus") or 0))))
        rap = money(amount_rub / RAP_RUB_RATE)
        doc = {
            "id": order_id, "payment_method": "xrocket", "session_id": user["session_id"],
            "nickname": user.get("nickname"), "discord_id": user.get("discord_id"),
            "amount_rub": float(amount_rub), "currency": currency, "status": "creating",
            "expected_rap": float(rap), "quoted_rap": float(money(rap * (1 + bonus))),
            "promo_id": user.get("promo_id"), "promo_code": user.get("promo_code"), "promo_bonus": float(bonus),
            "description": f"xRocket · {amount_rub:.2f} ₽ · {currency}", "receiver_nick": "xRocket",
            "created_at": now(), "expires_at": now() + timedelta(hours=1), "next_check_at": now() + timedelta(seconds=60),
        }
        await db.deposits.insert_one(dict(doc))
    if doc.get("invoice_url") or doc["status"] in ("processing", "confirmed"):
        return public_invoice(doc)
    try:
        invoice = None
        # After a timeout the same client ID retrieves the original invoice.
        if existed:
            try:
                invoice = await gateway.request(db, "GET", "/api/v1/invoice", params={"clientInvoiceId": order_id})
            except ProviderError as error:
                if error.status != 404:
                    raise
        if invoice is None:
            if not doc.get("price_amount"):
                quote = await quote_crypto(db, gateway, amount_rub, currency)
                await db.deposits.update_one({"id": order_id, "status": {"$nin": ["processing", "confirmed"]}}, {"$set": quote})
                doc.update(quote)
            try:
                invoice = await gateway.request(db, "POST", "/api/v1/invoices", json=invoice_body(doc, app_url))
            except ProviderError as error:
                if error.code != "client_id_already_taken":
                    raise
                invoice = await gateway.request(db, "GET", "/api/v1/invoice", params={"clientInvoiceId": order_id})
        result = await receive_invoice(db, doc, invoice)
        if result["status"] == "awaiting_payment" and not result.get("invoice_url"):
            raise HTTPException(502, "xRocket не вернул ссылку для оплаты. Повторите запрос")
        return public_invoice(result)
    except ProviderError as error:
        message = payment_error(error)
        changes = {"error_message": message.detail}
        if error.status in (400, 401, 403, 404) or error.code == "not_implemented":
            changes["status"] = "payment_error"
        await db.deposits.update_one({"id": order_id, "status": {"$in": ["creating", "payment_error"]}}, {"$set": changes})
        logger.warning("xRocket invoice creation failed: order=%s http=%s code=%s", order_id, error.status, error.code)
        raise message from None


async def synchronize(db, gateway, doc):
    await db.deposits.update_one({"id": doc["id"]}, {"$set": {"next_check_at": now() + timedelta(seconds=60)}})
    if doc["status"] == "confirmed":
        return doc
    if doc["status"] == "processing":
        await settle_deposit(db, doc)
        return await db.deposits.find_one({"id": doc["id"]}, {"_id": 0})
    try:
        invoice = await gateway.request(db, "GET", "/api/v1/invoice", params={"clientInvoiceId": doc["id"]})
    except ProviderError as error:
        if error.status == 404 and doc["status"] == "creating":
            # No provider invoice was created; let the user retry with a new ID.
            await db.deposits.update_one({"id": doc["id"], "status": "creating"}, {"$set": {"status": "payment_error", "error_message": "Счёт не был создан. Нажмите «Повторить создание счёта»"}})
            return await db.deposits.find_one({"id": doc["id"]}, {"_id": 0})
        raise payment_error(error) from None
    return await receive_invoice(db, doc, invoice)


async def handle_event(db, gateway, event):
    if not isinstance(event, dict) or event.get("type") != "invoice":
        return
    data = event.get("data")
    if not isinstance(data, dict) or data.get("event") not in ("invoice_status_changed", "payment_status_changed"):
        return
    invoice = data.get("invoice")
    if not isinstance(invoice, dict) or not isinstance(event.get("id"), str) or not isinstance(invoice.get("id"), str):
        raise HTTPException(400, "Некорректное событие xRocket")
    if await db.xrocket_webhooks.find_one({"_id": event["id"], "processed": True}):
        return
    # Invoice IDs and our correlation ID must agree when both are supplied.
    query = {"payment_method": "xrocket", "provider_invoice_id": invoice["id"]}
    doc = await db.deposits.find_one(query, {"_id": 0})
    if not doc and invoice.get("clientInvoiceId"):
        doc = await db.deposits.find_one({"payment_method": "xrocket", "id": invoice["clientInvoiceId"]}, {"_id": 0})
    if not doc:
        return
    if ((invoice.get("clientInvoiceId") and invoice["clientInvoiceId"] != doc["id"]) or
            (doc.get("provider_invoice_id") and doc["provider_invoice_id"] != invoice["id"])):
        raise HTTPException(409, "Счёт не совпадает с заявкой")
    await db.xrocket_webhooks.update_one({"_id": event["id"]}, {"$setOnInsert": {"order_id": doc["id"], "created_at": now(), "processed": False}}, upsert=True)
    # Neither redirect parameters nor an unverified status from the browser can credit RAP.
    await synchronize(db, gateway, doc)
    await db.xrocket_webhooks.update_one({"_id": event["id"]}, {"$set": {"processed": True}})


async def reconcile_loop(db, gateway):
    """Recover lost webhooks and interrupted credits even if the payer closes the site."""
    while True:
        await asyncio.sleep(5)
        try:
            doc = await db.deposits.find_one_and_update(
                {"payment_method": "xrocket", "status": {"$in": list(PENDING)}, "next_check_at": {"$lte": now()}},
                {"$set": {"next_check_at": now() + timedelta(seconds=60)}},
                sort=[("next_check_at", 1)], return_document=ReturnDocument.AFTER,
            )
            if doc:
                await synchronize(db, gateway, doc)
        except HTTPException as error:
            logger.warning("xRocket reconciliation deferred (HTTP %s)", error.status_code)
        except Exception:
            logger.exception("xRocket reconciliation failed; will retry")
