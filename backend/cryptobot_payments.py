"""CryptoBot (Crypto Pay API) invoices priced in RUB. Credits are fixed by the server."""

import asyncio
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import httpx
from fastapi import HTTPException
from pymongo import ReturnDocument

from deposit_settlement import settle_deposit

logger = logging.getLogger(__name__)
MIN_RUB = Decimal("35")
MAX_RUB = Decimal("1000000")
RAP_RUB_RATE = Decimal("0.50")
ASSETS = ("USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC")
PENDING = ("creating", "awaiting_payment", "processing")
MAINNET_API = "https://pay.crypt.bot/api"
TESTNET_API = "https://testnet-pay.crypt.bot/api"


def now():
    return datetime.now(timezone.utc)


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def public_invoice(doc):
    return {key: doc.get(key) for key in (
        "id", "status", "amount_rub", "currency", "expected_rap", "quoted_rap",
        "promo_code", "promo_bonus", "credited", "invoice_url", "created_at", "expires_at",
        "price_amount", "price_currency", "error_message", "payment_method",
    )}


class ProviderError(Exception):
    def __init__(self, status, code=""):
        self.status, self.code = status, code


def payment_error(error):
    if error.status == 401 or error.code in ("UNAUTHORIZED", "FORBIDDEN"):
        return HTTPException(503, "CryptoBot не принимает ключ приложения. Обратитесь в поддержку сайта")
    if error.status in (400, 403, 404):
        return HTTPException(400, f"CryptoBot не может создать счёт на эту сумму{(' (' + error.code + ')') if error.code else ''}. Измените сумму")
    return HTTPException(503, "Оплата через CryptoBot временно недоступна. Попробуйте позже")


class CryptoBotGateway:
    def __init__(self, token="", testnet=False, transport=None):
        self.token = token.strip()
        self.base_url = TESTNET_API if testnet else MAINNET_API
        self.transport = transport

    @property
    def enabled(self):
        return bool(self.token)

    def verify_signature(self, raw, headers):
        signature = headers.get("crypto-pay-api-signature", "")
        if not self.enabled or len(signature) != 64 or not signature.isascii():
            return False
        secret = hashlib.sha256(self.token.encode()).digest()
        expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def call(self, method, payload=None):
        if not self.enabled:
            raise HTTPException(503, "Оплата через CryptoBot пока не подключена")
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=15, transport=self.transport,
                                         headers={"Crypto-Pay-API-Token": self.token}) as client:
                response = await client.post(f"/{method}", json=payload or {})
        except httpx.HTTPError:
            raise ProviderError(503) from None
        try:
            body = response.json()
        except ValueError:
            raise ProviderError(response.status_code or 503) from None
        if not response.is_success or not body.get("ok"):
            error = body.get("error") if isinstance(body, dict) else None
            code = str(error.get("name", "")) if isinstance(error, dict) else ""
            raise ProviderError(response.status_code if not response.is_success else 400, code)
        return body.get("result")


async def ensure_indexes(db):
    await db.deposits.create_index(
        "id", unique=True, name="cryptobot_order_id",
        partialFilterExpression={"payment_method": "cryptobot"},
    )
    await db.cryptobot_webhooks.create_index("created_at", expireAfterSeconds=30 * 86400)


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def receive_invoice(db, doc, invoice):
    if not isinstance(invoice, dict) or "invoice_id" not in invoice:
        raise HTTPException(502, "Некорректный ответ CryptoBot")
    if invoice.get("payload") and invoice["payload"] != doc["id"]:
        raise HTTPException(409, "Счёт CryptoBot не совпадает с заявкой")
    if doc.get("provider_invoice_id") and str(doc["provider_invoice_id"]) != str(invoice["invoice_id"]):
        raise HTTPException(409, "Счёт CryptoBot не совпадает с заявкой")
    try:
        if money(invoice.get("amount")) != money(doc["amount_rub"]) or str(invoice.get("fiat", "")).upper() != "RUB":
            raise HTTPException(409, "Сумма счёта CryptoBot не совпадает с заявкой")
    except (ArithmeticError, ValueError, TypeError):
        raise HTTPException(502, "Некорректный ответ CryptoBot")
    status = invoice.get("status")
    changes = {"provider_invoice_id": str(invoice["invoice_id"]), "provider_status": status, "last_checked_at": now(), "error_message": None}
    link = invoice.get("bot_invoice_url") or invoice.get("mini_app_invoice_url")
    if isinstance(link, str) and link.startswith("https://t.me/"):
        changes["invoice_url"] = link
    expires = parse_date(invoice.get("expiration_date"))
    if expires:
        changes["expires_at"] = expires
    if status == "paid":
        changes.update(paid_asset=invoice.get("paid_asset"), paid_amount=invoice.get("paid_amount"))
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
        if status == "expired":
            changes.update(status="expired", resolved_at=now())
        elif status == "active":
            changes["status"] = "awaiting_payment"
        await db.deposits.update_one({"id": doc["id"], "status": {"$nin": ["processing", "confirmed"]}}, {"$set": changes})
    return await db.deposits.find_one({"id": doc["id"]}, {"_id": 0})


async def create_invoice(db, gateway, user, request_id, amount_rub, asset, app_url):
    if not gateway.enabled:
        raise HTTPException(503, "Оплата через CryptoBot пока не подключена")
    order_id = f"cryptobot:{request_id}"
    doc = await db.deposits.find_one({"id": order_id}, {"_id": 0})
    if doc and (doc["session_id"] != user["session_id"] or money(doc["amount_rub"]) != amount_rub or doc["currency"] != asset):
        raise HTTPException(409, "Этот запрос уже использован для другого счёта")
    if not doc:
        existing = await db.deposits.find_one({
            "session_id": user["session_id"], "payment_method": "cryptobot", "status": "awaiting_payment",
            "amount_rub": float(amount_rub), "currency": asset, "invoice_url": {"$type": "string"}, "expires_at": {"$gt": now()},
        }, {"_id": 0}, sort=[("created_at", -1)])
        if existing:
            return public_invoice(existing)
        if await db.deposits.count_documents({"session_id": user["session_id"], "payment_method": "cryptobot", "status": {"$in": list(PENDING)}}) >= 5:
            raise HTTPException(429, "У вас уже 5 неоплаченных счетов. Откройте один из них")
        recent = await db.deposits.find_one({"session_id": user["session_id"], "payment_method": "cryptobot", "status": {"$ne": "payment_error"}, "created_at": {"$gt": now() - timedelta(seconds=20)}})
        if recent:
            raise HTTPException(429, "Подождите 20 секунд перед созданием нового счёта")
        bonus = max(Decimal("0"), min(Decimal("0.5"), Decimal(str(user.get("promo_bonus") or 0))))
        rap = money(amount_rub / RAP_RUB_RATE)
        doc = {
            "id": order_id, "payment_method": "cryptobot", "session_id": user["session_id"],
            "nickname": user.get("nickname"), "discord_id": user.get("discord_id"),
            "amount_rub": float(amount_rub), "currency": asset, "status": "creating",
            "price_amount": f"{amount_rub:.2f}", "price_currency": "RUB",
            "expected_rap": float(rap), "quoted_rap": float(money(rap * (1 + bonus))),
            "promo_id": user.get("promo_id"), "promo_code": user.get("promo_code"), "promo_bonus": float(bonus),
            "description": f"CryptoBot · {amount_rub:.2f} ₽ · {asset}", "receiver_nick": "CryptoBot",
            "created_at": now(), "expires_at": now() + timedelta(hours=1), "next_check_at": now() + timedelta(seconds=60),
        }
        await db.deposits.insert_one(dict(doc))
    if doc.get("invoice_url") or doc["status"] in ("processing", "confirmed"):
        return public_invoice(doc)
    try:
        invoice = None
        if doc.get("provider_invoice_id"):
            found = await gateway.call("getInvoices", {"invoice_ids": str(doc["provider_invoice_id"])})
            items = found.get("items") if isinstance(found, dict) else None
            invoice = items[0] if items else None
        if invoice is None:
            invoice = await gateway.call("createInvoice", {
                "currency_type": "fiat", "fiat": "RUB", "amount": f"{amount_rub:.2f}",
                "accepted_assets": doc["currency"], "payload": order_id, "expires_in": 3600,
                "description": f"BLOXGRADE · {doc['quoted_rap']:.2f} RAP",
                "paid_btn_name": "callback", "paid_btn_url": f"{app_url}/profile?payment=cryptobot",
                "allow_comments": False, "allow_anonymous": True,
            })
        result = await receive_invoice(db, doc, invoice)
        if result["status"] == "awaiting_payment" and not result.get("invoice_url"):
            raise HTTPException(502, "CryptoBot не вернул ссылку для оплаты. Повторите запрос")
        return public_invoice(result)
    except ProviderError as error:
        message = payment_error(error)
        changes = {"error_message": message.detail}
        if error.status in (400, 401, 403, 404):
            changes["status"] = "payment_error"
        await db.deposits.update_one({"id": order_id, "status": {"$in": ["creating", "payment_error"]}}, {"$set": changes})
        logger.warning("CryptoBot invoice creation failed: order=%s http=%s code=%s", order_id, error.status, error.code)
        raise message from None


async def synchronize(db, gateway, doc):
    await db.deposits.update_one({"id": doc["id"]}, {"$set": {"next_check_at": now() + timedelta(seconds=60)}})
    if doc["status"] == "confirmed":
        return doc
    if doc["status"] == "processing":
        await settle_deposit(db, doc)
        return await db.deposits.find_one({"id": doc["id"]}, {"_id": 0})
    if not doc.get("provider_invoice_id"):
        await db.deposits.update_one({"id": doc["id"], "status": "creating"}, {"$set": {"status": "payment_error", "error_message": "Счёт не был создан. Нажмите «Повторить создание счёта»"}})
        return await db.deposits.find_one({"id": doc["id"]}, {"_id": 0})
    try:
        found = await gateway.call("getInvoices", {"invoice_ids": str(doc["provider_invoice_id"])})
    except ProviderError as error:
        raise payment_error(error) from None
    items = found.get("items") if isinstance(found, dict) else None
    if not items:
        raise HTTPException(502, "CryptoBot не нашёл счёт")
    return await receive_invoice(db, doc, items[0])


async def handle_event(db, gateway, event):
    if not isinstance(event, dict) or event.get("update_type") != "invoice_paid":
        return
    invoice = event.get("payload")
    update_id = event.get("update_id")
    if not isinstance(invoice, dict) or "invoice_id" not in invoice or update_id is None:
        raise HTTPException(400, "Некорректное событие CryptoBot")
    if await db.cryptobot_webhooks.find_one({"_id": str(update_id), "processed": True}):
        return
    doc = await db.deposits.find_one({"payment_method": "cryptobot", "provider_invoice_id": str(invoice["invoice_id"])}, {"_id": 0})
    if not doc and isinstance(invoice.get("payload"), str):
        doc = await db.deposits.find_one({"payment_method": "cryptobot", "id": invoice["payload"]}, {"_id": 0})
    if not doc:
        return
    await db.cryptobot_webhooks.update_one({"_id": str(update_id)}, {"$setOnInsert": {"order_id": doc["id"], "created_at": now(), "processed": False}}, upsert=True)
    # The signed event is only a trigger: the invoice is re-read from the provider.
    await synchronize(db, gateway, doc)
    await db.cryptobot_webhooks.update_one({"_id": str(update_id)}, {"$set": {"processed": True}})


async def reconcile_loop(db, gateway):
    while True:
        await asyncio.sleep(7)
        try:
            doc = await db.deposits.find_one_and_update(
                {"payment_method": "cryptobot", "status": {"$in": list(PENDING)}, "next_check_at": {"$lte": now()}},
                {"$set": {"next_check_at": now() + timedelta(seconds=60)}},
                sort=[("next_check_at", 1)], return_document=ReturnDocument.AFTER,
            )
            if doc:
                await synchronize(db, gateway, doc)
        except HTTPException as error:
            logger.warning("CryptoBot reconciliation deferred (HTTP %s)", error.status_code)
        except Exception:
            logger.exception("CryptoBot reconciliation failed; will retry")
