"""Payments in any currency via DonationAlerts, approved only by the owner's Telegram account.

Flow: player creates a request -> chat gets exact instructions -> player presses "I paid" once ->
the bot sends the request to TELEGRAM_ADMIN_ID -> the owner confirms the received RUB amount (two taps) or rejects.
Crediting reuses deposit_settlement.confirm_deposit unchanged (same path as the admin panel).
"""

import asyncio
import hashlib
import html
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal, InvalidOperation

import httpx
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import live_chat as chat
from chat_texts import CURRENCIES, tr
from cryptobot_payments import RAP_RUB_RATE
from da_phrases import pick_phrase
from deposit_settlement import confirm_deposit

logger = logging.getLogger(__name__)
METHOD = "donationalerts"
MAX_RUB = Decimal("500000")
MIN_AMOUNTS = {"KZT": Decimal("500")}


def now():
    return datetime.now(timezone.utc)


def rap_for_rub(rub: Decimal) -> Decimal:
    return (rub / RAP_RUB_RATE).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def fmt(value) -> str:
    d = Decimal(str(value)).quantize(Decimal("0.01"))
    return f"{d:f}".rstrip("0").rstrip(".") if "." in f"{d:f}" else f"{d:f}"


class TelegramBot:
    def __init__(self, token, admin_id, jwt_secret):
        self.token = token or ""
        self.admin_id = int(admin_id) if str(admin_id or "").strip().lstrip("-").isdigit() else None
        self.secret = hashlib.sha256(f"{self.token}:{jwt_secret}".encode()).hexdigest()[:48]

    @property
    def enabled(self):
        return bool(self.token and self.admin_id)

    async def call(self, method, payload=None, files=None):
        async with httpx.AsyncClient(timeout=15) as client:
            url = f"https://api.telegram.org/bot{self.token}/{method}"
            r = await client.post(url, data=payload, files=files) if files else await client.post(url, json=payload or {})
        body = r.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method}: {body.get('description')}")
        return body["result"]


def bot_from_env(jwt_secret):
    return TelegramBot(os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_ADMIN_ID"), jwt_secret)


def da_url():
    return os.environ.get("DONATIONALERTS_URL") or ""


async def ensure_indexes(db):
    await db.telegram_updates.create_index("created_at", expireAfterSeconds=7 * 24 * 3600)
    await db.telegram_prompts.create_index("created_at", expireAfterSeconds=24 * 3600)
    await db.deposits.create_index([("payment_method", 1), ("status", 1), ("tg_notified", 1)])


def parse_amount(value) -> Decimal:
    try:
        amount = Decimal(str(value).replace(",", ".").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "Неверная сумма") from None
    if amount <= 0 or amount > Decimal("100000000"):
        raise HTTPException(400, "Неверная сумма")
    return amount


async def create_request(db, user, currency, amount, lang, receiver):
    if not da_url():
        raise HTTPException(409, "Оплата через DonationAlerts временно недоступна")
    currency = str(currency or "").upper()
    if currency not in CURRENCIES:
        raise HTTPException(400, "Неподдерживаемая валюта")
    amount = parse_amount(amount)
    minimum = MIN_AMOUNTS.get(currency)
    if minimum and amount < minimum:
        raise HTTPException(400, f"Минимальная сумма оплаты картой — {fmt(minimum)} {currency}")
    code = "BG-" + secrets.token_hex(3).upper()
    phrase = await pick_phrase(db, secrets.choice)
    rub_rap = float(rap_for_rub(amount)) if currency == "RUB" else None
    dep = {
        "id": str(uuid.uuid4()), "session_id": user["session_id"], "nickname": user.get("nickname"), "discord_id": user.get("discord_id"),
        "roblox_nick": user.get("roblox_nick"), "roblox_display_name": user.get("roblox_display_name"), "roblox_link": user.get("roblox_link"),
        "description": f"DonationAlerts · {fmt(amount)} {currency} · «{phrase}»",
        "expected_rap": rub_rap, "receiver_id": receiver["id"], "receiver_nick": receiver["nickname"],
        "promo_id": user.get("promo_id"), "promo_code": user.get("promo_code"), "promo_bonus": float(user.get("promo_bonus") or 0),
        "status": "pending", "amount": None, "created_at": now(), "resolved_at": None, "via_chat": True,
        "payment_method": METHOD, "declared_amount": float(amount), "declared_currency": currency, "da_code": code, "da_phrase": phrase,
    }
    profile = {**user, "registered": True}
    found = await chat.create_chat(db, user["session_id"], profile, "support", None, None, lang)
    dep["chat_id"] = found["id"]
    await db.deposits.insert_one(dict(dep))
    lang = chat.lang_of(found)
    await db.chats.update_one({"id": found["id"]}, {"$set": {"deposit_id": dep["id"], "expected_rap": rub_rap}})
    await chat.post_message(db, found, "user", tr("da_request", lang, amount=fmt(amount), currency=currency),
                            {"kind": "da_request", "deposit_id": dep["id"]})
    await chat.post_message(db, found, "admin", tr("da_instructions", lang, url=da_url(), currency=currency, amount=fmt(amount),
                                                   nick=user.get("roblox_nick") or "-", phrase=f"«{phrase}»", rate=fmt(RAP_RUB_RATE)),
                            {"kind": "da_instructions", "deposit_id": dep["id"], "code": code, "phrase": phrase, "url": da_url(), "paid_claimed": False})
    return {"chat_id": found["id"], "deposit_id": dep["id"], "code": code, "phrase": phrase}


async def claim_paid(db, bot, user, deposit_id):
    res = await db.deposits.update_one(
        {"id": deposit_id, "session_id": user["session_id"], "payment_method": METHOD, "status": "pending", "paid_claimed_at": {"$exists": False}},
        {"$set": {"paid_claimed_at": now(), "tg_notified": False}},
    )
    if not res.modified_count:
        dep = await db.deposits.find_one({"id": deposit_id, "session_id": user["session_id"], "payment_method": METHOD}, {"_id": 0, "status": 1})
        if not dep:
            raise HTTPException(404, "Заявка не найдена")
        raise HTTPException(409, "Оплата уже отправлена на проверку" if dep["status"] == "pending" else "Заявка уже обработана")
    dep = await db.deposits.find_one({"id": deposit_id}, {"_id": 0})
    await db.chat_messages.update_many({"chat_id": dep["chat_id"], "kind": "da_instructions", "deposit_id": deposit_id}, {"$set": {"paid_claimed": True}})
    found = await db.chats.find_one({"id": dep["chat_id"]}, {"_id": 0})
    if found:
        await chat.post_message(db, found, "system", tr("da_claimed", chat.lang_of(found)), {"kind": "da_claimed", "deposit_id": deposit_id})
    await notify_admin(db, bot, dep)
    return {"ok": True}


def _card(dep, extra=""):
    promo = f"{dep.get('promo_code')} (+{float(dep.get('promo_bonus') or 0) * 100:g}%)" if dep.get("promo_code") else "нет"
    e = html.escape
    return (
        "💸 <b>Оплата через DonationAlerts</b>\n\n"
        f"Игрок: <b>{e(str(dep.get('nickname') or '-'))}</b> · Discord {e(str(dep.get('discord_id') or '-'))}\n"
        f"Roblox: <b>@{e(str(dep.get('roblox_nick') or '-'))}</b> ({e(str(dep.get('roblox_display_name') or '-'))})\n"
        f"Профиль: {e(str(dep.get('roblox_link') or '-'))}\n"
        f"Заявлено игроком: <b>{fmt(dep['declared_amount'])} {e(dep['declared_currency'])}</b>\n"
        f"Сообщение доната: <b>«{e(str(dep.get('da_phrase') or '-'))}»</b>\n"
        f"Код заявки: <code>{e(dep['da_code'])}</code>\n"
        f"Промокод: {e(promo)}\n"
        f"Курс сайта: 1 RAP = {fmt(RAP_RUB_RATE)} ₽\n"
        f"Заявка: <code>{dep['id'][:8]}</code>{extra}"
    )


def _main_keyboard(dep):
    rows = []
    if dep["declared_currency"] == "RUB":
        rub = Decimal(str(dep["declared_amount"]))
        rows.append([{"text": f"✅ Пришло {fmt(rub)} ₽ → {fmt(rap_for_rub(rub))} RAP", "callback_data": f"da:ask:{dep['id']}:{int(rub * 100)}"}])
    rows.append([{"text": "✏️ Ввести полученную сумму в ₽", "callback_data": f"da:amt:{dep['id']}"}])
    rows.append([{"text": "❌ Отклонить", "callback_data": f"da:rej:{dep['id']}"}])
    return {"inline_keyboard": rows}


async def notify_admin(db, bot, dep):
    if not bot.enabled:
        return False
    try:
        msg = await bot.call("sendMessage", {"chat_id": bot.admin_id, "text": _card(dep), "parse_mode": "HTML",
                                             "disable_web_page_preview": True, "reply_markup": _main_keyboard(dep)})
        shot = await db.chat_attachments.find_one({"chat_id": dep["chat_id"], "expires_at": {"$gt": now()}}, sort=[("created_at", -1)])
        if shot:
            ext = shot["content_type"].split("/")[1]
            await bot.call("sendPhoto", {"chat_id": str(bot.admin_id), "caption": f"Скриншот игрока · заявка {dep['id'][:8]}",
                                         "reply_to_message_id": str(msg["message_id"])},
                           files={"photo": (f"shot.{ext}", bytes(shot["data"]), shot["content_type"])})
    except Exception:
        logger.exception("Telegram notification failed for deposit %s; will retry", dep["id"])
        return False
    await db.deposits.update_one({"id": dep["id"]}, {"$set": {"tg_notified": True, "tg_message_id": msg["message_id"]}})
    return True


async def retry_loop(db, bot):
    while True:
        try:
            for dep in await db.deposits.find({"payment_method": METHOD, "status": "pending", "tg_notified": False}, {"_id": 0}).to_list(20):
                await notify_admin(db, bot, dep)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("DonationAlerts Telegram retry failed")
        await asyncio.sleep(60)


async def setup_webhook(bot, public_url):
    url = f"{public_url.rstrip('/')}/api/telegram/webhook"
    await bot.call("setWebhook", {"url": url, "secret_token": bot.secret, "allowed_updates": ["message", "callback_query"]})
    return url


async def _edit(bot, message, text, keyboard=None):
    payload = {"chat_id": message["chat"]["id"], "message_id": message["message_id"], "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    payload["reply_markup"] = keyboard or {"inline_keyboard": []}
    try:
        await bot.call("editMessageText", payload)
    except Exception:
        logger.warning("editMessageText failed", exc_info=True)


async def _answer(bot, query_id, text=""):
    try:
        await bot.call("answerCallbackQuery", {"callback_query_id": query_id, "text": text[:190]})
    except Exception:
        logger.warning("answerCallbackQuery failed", exc_info=True)


async def _confirm_prompt(bot, dep, rub, message=None):
    rap = rap_for_rub(rub)
    text = _card(dep, f"\n\n❓ Зачислить <b>{fmt(rap)} RAP</b> (получено {fmt(rub)} ₽) игроку <b>@{html.escape(str(dep.get('roblox_nick') or '-'))}</b>?"
                      + (" Промокод добавится автоматически." if dep.get("promo_code") else ""))
    keyboard = {"inline_keyboard": [[{"text": f"✅ Да, зачислить {fmt(rap)} RAP", "callback_data": f"da:ok:{dep['id']}:{int(rub * 100)}"}],
                                    [{"text": "↩️ Назад", "callback_data": f"da:back:{dep['id']}"}]]}
    if message:
        await _edit(bot, message, text, keyboard)
    else:
        await bot.call("sendMessage", {"chat_id": bot.admin_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": keyboard})


async def _credit(db, bot, dep, rub, message):
    rap = rap_for_rub(rub)
    if rap < 1:
        return await _edit(bot, message, _card(dep, "\n\n⚠️ Сумма слишком мала"), _main_keyboard(dep))
    result = await confirm_deposit(db, dep["id"], float(rap), f"DonationAlerts · {fmt(rub)} ₽ · Telegram")
    found = await db.chats.find_one({"id": dep["chat_id"]}, {"_id": 0})
    if found and not result.get("already_confirmed"):
        await chat.post_message(db, found, "system", tr("deposit_confirmed", chat.lang_of(found), credited=float(result.get("credited") or 0)))
    await db.deposits.update_one({"id": dep["id"]}, {"$set": {"received_rub": float(rub)}})
    note = "уже было зачислено ранее" if result.get("already_confirmed") else "зачислено"
    await _edit(bot, message, _card(dep, f"\n\n✅ <b>{note}: {float(result.get('credited') or 0):.2f} RAP</b> (получено {fmt(rub)} ₽)"))


async def _reject(db, bot, dep, message, notify_rejected):
    res = await db.deposits.update_one({"id": dep["id"], "status": "pending"},
                                       {"$set": {"status": "rejected", "rejection_reason": "payment_not_found", "resolved_at": now()}})
    if res.modified_count:
        await notify_rejected(dep, "payment_not_found")
    await _edit(bot, message, _card(dep, "\n\n❌ <b>Отклонено</b>" if res.modified_count else "\n\nℹ️ Заявка уже обработана"))


TEST_DEP = {"id": "test0000-0000-0000-0000-000000000000", "nickname": "Тестовый игрок", "discord_id": "000000000000000000",
            "roblox_nick": "test_player", "roblox_display_name": "Test Player", "roblox_link": "https://www.roblox.com/users/1/profile",
            "declared_amount": 250.0, "declared_currency": "RUB", "da_code": "BG-TEST00", "da_phrase": "го ещё катку", "promo_code": None}


async def send_test(bot):
    """Sample top-up card: same layout and buttons, but pressing them never touches deposits or balances."""
    text = "🧪 <b>ПРОВЕРОЧНОЕ СООБЩЕНИЕ</b> — деньги не зачисляются\n\n" + _card(TEST_DEP)
    keyboard = {"inline_keyboard": [[{"text": "✅ Пришло 250 ₽ → 500 RAP", "callback_data": "da:test:ask"}],
                                    [{"text": "✏️ Ввести полученную сумму в ₽", "callback_data": "da:test:amt"}],
                                    [{"text": "❌ Отклонить", "callback_data": "da:test:rej"}]]}
    return await bot.call("sendMessage", {"chat_id": bot.admin_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": keyboard})


async def _handle_test(bot, query, message, action):
    await _answer(bot, query["id"], "Проверка: кнопка работает")
    head = "🧪 <b>ПРОВЕРОЧНОЕ СООБЩЕНИЕ</b> — деньги не зачисляются\n\n"
    if action == "ask":
        await _edit(bot, message, head + _card(TEST_DEP, "\n\n❓ Зачислить <b>500 RAP</b> (получено 250 ₽) игроку <b>@test_player</b>?"),
                    {"inline_keyboard": [[{"text": "✅ Да, зачислить 500 RAP", "callback_data": "da:test:ok"}], [{"text": "↩️ Назад", "callback_data": "da:test:back"}]]})
    elif action == "rej":
        await _edit(bot, message, head + _card(TEST_DEP, "\n\n❓ Отклонить заявку (платёж не найден)?"),
                    {"inline_keyboard": [[{"text": "❌ Да, отклонить", "callback_data": "da:test:no"}], [{"text": "↩️ Назад", "callback_data": "da:test:back"}]]})
    elif action == "back":
        await send_test(bot)
    else:
        result = {"ok": "✅ Так будет выглядеть зачисление: 500 RAP игроку @test_player", "no": "❌ Так будет выглядеть отклонение",
                  "amt": "✏️ В настоящей заявке бот попросит ответить суммой в рублях и пересчитает её в RAP"}.get(action, "Проверка завершена")
        await _edit(bot, message, head + _card(TEST_DEP, f"\n\n<b>{result}</b>\n(проверка — ничего не зачислено)"))
    return None


async def handle_update(db, bot, update, notify_rejected):
    try:
        await db.telegram_updates.insert_one({"_id": int(update.get("update_id", 0)), "created_at": now()})
    except DuplicateKeyError:
        return  # Telegram re-delivered an update we already processed
    query = update.get("callback_query")
    if query:
        if (query.get("from") or {}).get("id") != bot.admin_id:
            return await _answer(bot, query["id"], "Нет доступа")
        parts = str(query.get("data") or "").split(":")
        message = query.get("message") or {}
        if parts[:2] == ["da", "test"]:
            return await _handle_test(bot, query, message, parts[2] if len(parts) > 2 else "")
        dep = await db.deposits.find_one({"id": parts[2] if len(parts) > 2 else "", "payment_method": METHOD}, {"_id": 0}) if parts[0] == "da" else None
        if not dep:
            return await _answer(bot, query["id"], "Заявка не найдена")
        action = parts[1]
        if dep["status"] != "pending" and action not in ("ok",):
            await _answer(bot, query["id"], "Заявка уже обработана")
            return await _edit(bot, message, _card(dep, f"\n\nℹ️ Статус: {dep['status']}"))
        await _answer(bot, query["id"])
        try:
            if action == "ask":
                await _confirm_prompt(bot, dep, Decimal(parts[3]) / 100, message)
            elif action == "ok":
                await _credit(db, bot, dep, Decimal(parts[3]) / 100, message)
            elif action == "amt":
                prompt = await bot.call("sendMessage", {"chat_id": bot.admin_id, "reply_markup": {"force_reply": True, "input_field_placeholder": "например 250"},
                                                        "text": f"Ответьте на это сообщение суммой в рублях, которая пришла на DonationAlerts с сообщением «{dep.get('da_phrase') or dep['da_code']}»:"})
                await db.telegram_prompts.insert_one({"_id": prompt["message_id"], "deposit_id": dep["id"], "created_at": now()})
            elif action == "rej":
                await _edit(bot, message, _card(dep, "\n\n❓ Отклонить заявку (платёж не найден)?"),
                            {"inline_keyboard": [[{"text": "❌ Да, отклонить", "callback_data": f"da:rejok:{dep['id']}"}],
                                                 [{"text": "↩️ Назад", "callback_data": f"da:back:{dep['id']}"}]]})
            elif action == "rejok":
                await _reject(db, bot, dep, message, notify_rejected)
            elif action == "back":
                await _edit(bot, message, _card(dep), _main_keyboard(dep))
        except HTTPException as error:
            await bot.call("sendMessage", {"chat_id": bot.admin_id, "text": f"⚠️ {error.detail}"})
        return None
    message = update.get("message") or {}
    if (message.get("from") or {}).get("id") != bot.admin_id or (message.get("chat") or {}).get("id") != bot.admin_id:
        return None
    reply = message.get("reply_to_message") or {}
    prompt = await db.telegram_prompts.find_one({"_id": reply.get("message_id")}) if reply else None
    if not prompt:
        if (message.get("text") or "").startswith("/start"):
            await bot.call("sendMessage", {"chat_id": bot.admin_id, "text": "Бот BloxGrade на связи: сюда приходят оплаты DonationAlerts на проверку."})
        return None
    dep = await db.deposits.find_one({"id": prompt["deposit_id"]}, {"_id": 0})
    try:
        rub = Decimal((message.get("text") or "").replace(",", ".").replace("₽", "").strip()).quantize(Decimal("0.01"))
    except InvalidOperation:
        rub = Decimal("0")
    if not dep or dep["status"] != "pending":
        return await bot.call("sendMessage", {"chat_id": bot.admin_id, "text": "Заявка уже обработана"})
    if rub <= 0 or rub > MAX_RUB:
        return await bot.call("sendMessage", {"chat_id": bot.admin_id, "text": "Не понял сумму. Ответьте на сообщение числом, например 250"})
    await _confirm_prompt(bot, dep, rub)
    return None
