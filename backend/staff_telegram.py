"""Separate Telegram bot for staff intake reviews: album + decision card, durable outbox, owner-only callbacks."""
import asyncio
import html
import json
import logging
import os
import uuid
from datetime import timedelta

import httpx
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import staff_core as core
import staff_evidence as ev

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 40


class StaffBot:
    def __init__(self):
        self.token = os.environ.get("STAFF_TG_BOT_TOKEN") or ""
        owner = str(os.environ.get("STAFF_TG_OWNER_ID") or "").strip()
        self.owner_id = int(owner) if owner.isdigit() else None
        self.secret = os.environ.get("STAFF_TG_WEBHOOK_SECRET") or ""

    @property
    def shared(self):
        # Same token as the DonationAlerts bot: updates arrive via /api/telegram/webhook and are delegated here.
        return bool(self.token) and self.token == (os.environ.get("TELEGRAM_BOT_TOKEN") or "")

    @property
    def enabled(self):
        return bool(self.token and self.owner_id and (self.secret or self.shared))

    async def call(self, method, payload=None, files=None):
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"https://api.telegram.org/bot{self.token}/{method}"
            r = await client.post(url, data=payload, files=files) if files else await client.post(url, json=payload or {})
        body = r.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method}: {body.get('description')}")
        return body["result"]


async def ensure_indexes(db):
    await db.staff_tg_outbox.create_index("id", unique=True)
    await db.staff_tg_outbox.create_index([("status", 1), ("next_at", 1)])
    await db.staff_tg_updates.create_index("created_at", expireAfterSeconds=14 * 24 * 3600)
    await db.staff_tg_prompts.create_index("created_at", expireAfterSeconds=24 * 3600)


def _num(v):
    return f"{float(v):,.2f}".replace(",", " ").rstrip("0").rstrip(".")


def card(rep, extra=""):
    e = lambda v: html.escape(str(v if v not in (None, "") else "-"))  # noqa: E731
    p, r, plan = rep["player"], rep["receiver"], rep["plan"]
    rap = float(rep["total_rap"])
    fee = rap * core.FEE
    bonus = float(plan["credited"]) - (rap - fee)
    lines = [f"🧾 <b>Заявка #{e(rep['deposit_id'][:8])}</b> · версия {rep['version']}",
             f"Сотрудник: <b>{e(rep.get('staff_nick'))}</b> · приём на @{e(r.get('roblox_nick'))}",
             f"Игрок: <b>{e(p.get('nickname'))}</b> · Discord {e(p.get('discord_id'))}",
             f"Roblox: {e(p.get('roblox_display_name'))} (@{e(p.get('roblox_nick'))})", f"Профиль: {e(p.get('roblox_link'))}", "", "<b>Предметы:</b>"]
    lines += [f"• {e(i['name'])} × {i['qty']} — {_num(i['value'])} RAP" + (f" (= {_num(i['qty'] * i['value'])})" if i["qty"] > 1 else "") for i in rep["items"]]
    promo = f"{e(rep.get('promo_code'))} +{rep['promo_bonus'] * 100:g}% (+{_num(bonus)} RAP)" if rep.get("promo_code") and bonus > 0 else "нет"
    skins = ", ".join(f"{e(s['name'])} {_num(s['price'])}" for s in plan["issued_skins"]) or "—"
    lines += ["", f"Общая оценка: <b>{_num(rap)} RAP</b> ({rep['items_count']} шт.)", f"Комиссия 20%: −{_num(fee)} RAP", f"Промобонус: {promo}",
              f"К выдаче: <b>{_num(plan['credited'])} RAP</b> = скины {len(plan['issued_skins'])} шт. на {_num(plan['skins_total'])} RAP + баланс {_num(plan['balance_credited'])} RAP",
              f"Виртуальные скины: {skins}", "Отметки: ✅ Скины получил · ✅ Стоимость проверил"]
    if rep.get("note"):
        lines.append(f"Комментарий: {e(rep['note'])}")
    return "\n".join(lines) + extra


def keyboard(rid):
    return {"inline_keyboard": [[{"text": "✅ Подтвердить", "callback_data": f"sr:ok:{rid}"}],
                                [{"text": "🛠 На доработку", "callback_data": f"sr:rev:{rid}"}, {"text": "❌ Отклонить", "callback_data": f"sr:rej:{rid}"}]]}


async def enqueue(db, bot, rep):
    box = {"id": str(uuid.uuid4()), "report_id": rep["id"], "status": "pending", "attempts": 0, "media_sent": False,
           "next_at": core.now(), "lease_until": core.now() - timedelta(seconds=1), "created_at": core.now()}
    await db.staff_tg_outbox.insert_one(dict(box))
    if bot.enabled:
        asyncio.create_task(_safe_deliver(db, bot, box["id"]))
    return box


async def _safe_deliver(db, bot, box_id):
    try:
        await deliver(db, bot, box_id)
    except Exception:
        logger.exception("Staff Telegram delivery crashed")


async def deliver(db, bot, box_id):
    now = core.now()
    box = await db.staff_tg_outbox.find_one_and_update(
        {"id": box_id, "status": "pending", "next_at": {"$lte": now}, "lease_until": {"$lt": now}},
        {"$set": {"lease_until": now + timedelta(seconds=90)}}, projection={"_id": 0})
    if not box:
        return False
    rep = await db.staff_reports.find_one({"id": box["report_id"]}, {"_id": 0})
    if not rep or rep["status"] != "submitted":
        await db.staff_tg_outbox.update_one({"id": box_id}, {"$set": {"status": "cancelled"}})
        return False
    try:
        if not box.get("media_sent"):
            files, media = {}, []
            for n, fid in enumerate(rep["evidence"]):
                data, meta = await ev.read(db, fid)
                files[f"f{n}"] = (f"shot{n}.{'png' if meta['content_type'] == 'image/png' else 'jpg'}", data, meta["content_type"])
                media.append({"type": "photo", "media": f"attach://f{n}"})
            caption = f"Скриншоты · заявка #{rep['deposit_id'][:8]} · v{rep['version']}"
            try:
                await _send_album(bot, files, media, caption, "photo")
            except RuntimeError as error:
                if "PHOTO" not in str(error).upper() and "IMAGE" not in str(error).upper():
                    raise
                # Very tall/wide screenshots are refused as photos; files keep full quality.
                await _send_album(bot, files, media, caption, "document")
            await db.staff_tg_outbox.update_one({"id": box_id}, {"$set": {"media_sent": True}})
        msg = await bot.call("sendMessage", {"chat_id": bot.owner_id, "text": card(rep), "parse_mode": "HTML",
                                             "disable_web_page_preview": True, "reply_markup": keyboard(rep["id"])})
    except Exception as error:
        attempts = box.get("attempts", 0) + 1
        await db.staff_tg_outbox.update_one({"id": box_id}, {"$set": {
            "status": "failed" if attempts >= MAX_ATTEMPTS else "pending",
            "attempts": attempts, "last_error": str(error)[:300], "lease_until": core.now() - timedelta(seconds=1),
            "next_at": core.now() + timedelta(seconds=min(900, 20 * 2 ** min(attempts, 6)))}})
        logger.warning("Staff Telegram delivery failed (attempt %s): %s", attempts, error)
        return False
    await db.staff_tg_outbox.update_one({"id": box_id}, {"$set": {"status": "sent", "sent_at": core.now()}})
    await db.staff_reports.update_one({"id": rep["id"]}, {"$set": {"tg_card": {"chat_id": bot.owner_id, "message_id": msg["message_id"]}}})
    return True


async def _send_album(bot, files, media, caption, kind):
    chat_id = str(bot.owner_id)
    if len(media) == 1:
        method = "sendPhoto" if kind == "photo" else "sendDocument"
        return await bot.call(method, {"chat_id": chat_id, "caption": caption}, files={kind: files["f0"]})
    items = [{**m, "type": kind} for m in media]
    items[0] = {**items[0], "caption": caption}
    return await bot.call("sendMediaGroup", {"chat_id": chat_id, "media": json.dumps(items)}, files=files)


async def owns(db, update) -> bool:
    """In shared-bot mode: is this update meant for staff reviews rather than DonationAlerts?"""
    data = str(((update.get("callback_query") or {}).get("data")) or "")
    if data.startswith(("sr:", "srt:")):
        return True
    reply = ((update.get("message") or {}).get("reply_to_message") or {}).get("message_id")
    return bool(reply and await db.staff_tg_prompts.find_one({"_id": reply}, {"_id": 1}))


async def retry_loop(db, bot):
    while True:
        try:
            for box in await db.staff_tg_outbox.find({"status": "pending", "next_at": {"$lte": core.now()}}, {"_id": 0, "id": 1}).to_list(20):
                await deliver(db, bot, box["id"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Staff Telegram retry loop failed")
        await asyncio.sleep(30)


async def mark_card(db, bot, report_id, suffix):
    """Remove buttons from the Telegram card after a decision made anywhere (Telegram or /admin)."""
    rep = await db.staff_reports.find_one({"id": report_id}, {"_id": 0})
    if not bot.enabled or not rep or not rep.get("tg_card"):
        return
    try:
        await bot.call("editMessageText", {"chat_id": rep["tg_card"]["chat_id"], "message_id": rep["tg_card"]["message_id"], "text": card(rep, suffix),
                                           "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": {"inline_keyboard": []}})
    except Exception:
        logger.warning("Could not update staff Telegram card", exc_info=True)


def decision_suffix(rep):
    d = rep.get("decision") or {}
    via = "Telegram" if d.get("via") == "telegram" else "панель"
    if rep["status"] == "approved":
        return f"\n\n✅ <b>Подтверждено ({via}): зачислено {_num(rep.get('credited') or rep['plan']['credited'])} RAP</b>"
    if rep["status"] == "revision":
        return f"\n\n🛠 <b>На доработке ({via}):</b> {html.escape(d.get('reason') or '')}"
    if rep["status"] == "rejected":
        return f"\n\n❌ <b>Отклонено ({via}):</b> {html.escape(d.get('reason') or '')}"
    return f"\n\nℹ️ Статус: {rep['status']}"


async def setup_webhook(bot, public_url):
    url = f"{public_url.rstrip('/')}/api/staff-telegram/webhook"
    await bot.call("setWebhook", {"url": url, "secret_token": bot.secret, "allowed_updates": ["message", "callback_query"], "drop_pending_updates": False})
    return url


async def send_test(bot):
    text = "🧪 <b>ПРОВЕРОЧНОЕ СООБЩЕНИЕ</b> — ничего не зачисляется.\nТак будут выглядеть карточки отчётов сотрудников. Кнопки ниже только проверяют связь."
    kb = {"inline_keyboard": [[{"text": "✅ Подтвердить", "callback_data": "srt:ok"}],
                              [{"text": "🛠 На доработку", "callback_data": "srt:rev"}, {"text": "❌ Отклонить", "callback_data": "srt:rej"}]]}
    return await bot.call("sendMessage", {"chat_id": bot.owner_id, "text": text, "parse_mode": "HTML", "reply_markup": kb})


async def _answer(bot, qid, text=""):
    try:
        await bot.call("answerCallbackQuery", {"callback_query_id": qid, "text": text[:190]})
    except Exception:
        logger.warning("answerCallbackQuery failed", exc_info=True)


async def _edit(bot, message, text, kb=None):
    try:
        await bot.call("editMessageText", {"chat_id": message["chat"]["id"], "message_id": message["message_id"], "text": text,
                                           "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": kb or {"inline_keyboard": []}})
    except Exception:
        logger.warning("editMessageText failed", exc_info=True)


async def handle_update(db, bot, update):
    try:
        await db.staff_tg_updates.insert_one({"_id": int(update.get("update_id", 0)), "created_at": core.now()})
    except DuplicateKeyError:
        return  # re-delivered update
    query = update.get("callback_query")
    if query:
        return await _callback(db, bot, query)
    message = update.get("message") or {}
    sender, chat_id = (message.get("from") or {}).get("id"), (message.get("chat") or {}).get("id")
    if sender != bot.owner_id or chat_id != bot.owner_id:
        if (message.get("text") or "").startswith("/start") and sender:
            await bot.call("sendMessage", {"chat_id": chat_id, "text": f"Ваш Telegram ID: {sender}. Решения по заявкам принимаются только от владельца."})
        return
    reply = message.get("reply_to_message") or {}
    prompt = await db.staff_tg_prompts.find_one_and_delete({"_id": reply.get("message_id")}) if reply else None
    if not prompt:
        if (message.get("text") or "").startswith("/start"):
            await bot.call("sendMessage", {"chat_id": bot.owner_id, "text": "Бот проверки заявок сотрудников BloxGrade на связи."})
        return
    reason = (message.get("text") or "").strip()
    try:
        rep = await core.decide(db, prompt["report_id"], prompt["action"], reason, "owner", "telegram")
        await mark_card(db, bot, rep["id"], decision_suffix(rep))
        await bot.call("sendMessage", {"chat_id": bot.owner_id, "text": "Готово: " + ("отправлено на доработку" if prompt["action"] == "revision" else "заявка отклонена")})
    except HTTPException as error:
        await bot.call("sendMessage", {"chat_id": bot.owner_id, "text": f"⚠️ {error.detail}"})


async def _callback(db, bot, query):
    message = query.get("message") or {}
    if (query.get("from") or {}).get("id") != bot.owner_id or (message.get("chat") or {}).get("id") != bot.owner_id:
        return await _answer(bot, query["id"], "Нет доступа")
    parts = str(query.get("data") or "").split(":")
    if parts[0] == "srt":
        return await _answer(bot, query["id"], "Проверка: кнопка работает, ничего не изменено")
    if parts[0] != "sr" or len(parts) != 3:
        return await _answer(bot, query["id"], "Неизвестная кнопка")
    action, rid = parts[1], parts[2]
    rep = await db.staff_reports.find_one({"id": rid}, {"_id": 0})
    dep = await db.deposits.find_one({"id": rep["deposit_id"]}, {"_id": 0, "staff_report_id": 1, "staff_state": 1}) if rep else None
    if not rep or rep["status"] != "submitted" or not dep or dep.get("staff_report_id") != rid or dep.get("staff_state") != "review":
        await _answer(bot, query["id"], "Кнопка устарела: заявка изменена или уже решена")
        if rep:
            await _edit(bot, message, card(rep, decision_suffix(rep) if rep["status"] != "submitted" else "\n\nℹ️ Устаревшая версия"))
        return
    await _answer(bot, query["id"])
    if action == "ok":
        kb = {"inline_keyboard": [[{"text": f"✅ Да, зачислить {_num(rep['plan']['credited'])} RAP", "callback_data": f"sr:okc:{rid}"}],
                                  [{"text": "↩️ Назад", "callback_data": f"sr:back:{rid}"}]]}
        return await _edit(bot, message, card(rep, f"\n\n❓ Зачислить игроку <b>{_num(rep['plan']['credited'])} RAP</b>?"), kb)
    if action == "back":
        return await _edit(bot, message, card(rep), keyboard(rid))
    if action == "okc":
        try:
            result = await core.approve(db, rid, "owner", "telegram")
            return await _edit(bot, message, card(result["report"], decision_suffix(result["report"])))
        except HTTPException as error:
            return await bot.call("sendMessage", {"chat_id": bot.owner_id, "text": f"⚠️ {error.detail}"})
    if action in ("rev", "rej"):
        kind = "revision" if action == "rev" else "reject"
        prompt = await bot.call("sendMessage", {"chat_id": bot.owner_id, "reply_markup": {"force_reply": True, "input_field_placeholder": "Причина"},
                                                "text": f"Ответьте на это сообщение причиной ({'на доработку' if kind == 'revision' else 'отклонения'}) для заявки #{rep['deposit_id'][:8]} v{rep['version']}:"})
        await db.staff_tg_prompts.insert_one({"_id": prompt["message_id"], "report_id": rid, "action": kind, "created_at": core.now()})
