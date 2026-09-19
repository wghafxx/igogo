"""Live support chat: users (including guests) talk to an operator from the admin panel."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

MAX_TEXT = 2000
TOGGLE_COOLDOWN = 180
STATUSES = ("open", "active", "closed")
WELCOME_MESSAGE = (
    "Здравствуйте! Это чат поддержки. Здесь вы сможете быстро пополнить баланс деньгами или скинами.\n\n"
    "Доступна оплата в следующих валютах:\n"
    "BYN — белорусский рубль\n"
    "EUR — евро\n"
    "KZT — казахстанский тенге\n"
    "RUB — российский рубль\n"
    "UAH — украинская гривна\n"
    "USD — доллар США\n"
    "BRL — бразильский реал\n"
    "TRY — турецкая лира\n"
    "PLN — польский злотый\n"
    "UZS — узбекский сум\n\n"
    "Также вы можете решить здесь свой вопрос — просто задайте его."
)


def now():
    return datetime.now(timezone.utc)


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def cooldown_left(chat):
    t = _utc(chat.get("toggle_at")) if chat else None
    if not t:
        return 0
    left = TOGGLE_COOLDOWN - (now() - t).total_seconds()
    return max(0, int(left + 0.999))


def require_cooldown(chat):
    left = cooldown_left(chat)
    if left:
        raise HTTPException(429, f"Подождите {left} сек — чат можно открыть или закрыть раз в {TOGGLE_COOLDOWN // 60} минуты", headers={"Retry-After": str(left)})


def public_chat(doc):
    return {k: v for k, v in doc.items() if k != "_id"}


async def ensure_indexes(db):
    await db.chats.create_index("id", unique=True)
    await db.chats.create_index([("owner", 1), ("updated_at", -1)])
    await db.chats.create_index([("status", 1), ("updated_at", -1)])
    await db.chat_messages.create_index("id", unique=True)
    await db.chat_messages.create_index([("chat_id", 1), ("created_at", 1)])


def _message(chat_id, sender, text, extra=None):
    return {"id": str(uuid.uuid4()), "chat_id": chat_id, "sender": sender, "text": text, "created_at": now(), **(extra or {})}


async def post_message(db, chat, sender, text, extra=None):
    text = text.strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")
    if len(text) > MAX_TEXT:
        raise HTTPException(400, f"Сообщение длиннее {MAX_TEXT} символов")
    msg = _message(chat["id"], sender, text, extra)
    await db.chat_messages.insert_one(dict(msg))
    changes = {"updated_at": msg["created_at"], "last_message": {"text": text[:140], "sender": sender, "created_at": msg["created_at"]}}
    inc = {}
    if sender == "user":
        inc["admin_unread"] = 1
        if chat["status"] == "closed":
            changes["status"] = "open"
    elif sender in ("admin", "system"):
        inc["user_unread"] = 1
    update = {"$set": changes}
    if inc:
        update["$inc"] = inc
    await db.chats.update_one({"id": chat["id"]}, update)
    return msg


async def create_chat(db, owner, profile, kind, text=None, deposit=None):
    if kind not in ("support", "deposit", "withdrawal"):
        raise HTTPException(400, "Неверный тип чата")
    chat = await db.chats.find_one({"owner": owner}, {"_id": 0}, sort=[("updated_at", -1)])
    if chat:
        if chat["status"] == "closed":
            require_cooldown(chat)
            await db.chats.update_one({"id": chat["id"]}, {"$set": {"status": "open", "closed_at": None, "toggle_at": now(), "updated_at": now()}})
            chat["status"] = "open"
            await post_message(db, chat, "system", "Чат открыт заново. Оператор скоро подключится.")
        profile_fields = {"nickname": profile.get("nickname") or chat["nickname"], "avatar": profile.get("avatar"), "discord_id": profile.get("discord_id"), "roblox_nick": profile.get("roblox_nick"), "guest": not profile.get("registered")}
        await db.chats.update_one({"id": chat["id"]}, {"$set": profile_fields})
    else:
        chat = {
            "id": str(uuid.uuid4()), "owner": owner, "kind": "support", "status": "open",
            "nickname": profile.get("nickname") or "Гость", "avatar": profile.get("avatar"),
            "discord_id": profile.get("discord_id"), "roblox_nick": profile.get("roblox_nick"),
            "guest": not profile.get("registered"),
            "deposit_id": None, "expected_rap": None,
            "user_unread": 0, "admin_unread": 0,
            "created_at": now(), "updated_at": now(), "last_message": None, "accepted_at": None, "closed_at": None, "toggle_at": now(),
        }
        await db.chats.insert_one(dict(chat))
        await post_message(db, chat, "admin", WELCOME_MESSAGE, {"kind": "welcome"})
    if deposit:
        await db.chats.update_one({"id": chat["id"]}, {"$set": {"deposit_id": deposit["id"], "expected_rap": deposit["expected_rap"]}})
        await post_message(db, chat, "user", f"Хочу пополнить примерно на {deposit['expected_rap']:.2f} RAP", {"kind": "deposit_request", "expected_rap": deposit["expected_rap"], "deposit_id": deposit["id"]})
        await post_message(db, chat, "system", "Заявка на пополнение создана. Оператор скоро подключится и подскажет, как передать скины.")
    if text and text.strip():
        await post_message(db, chat, "user", text)
    return await db.chats.find_one({"id": chat["id"]}, {"_id": 0})


async def post_withdrawal_request(db, chat, withdrawals):
    total = round(sum(float((w.get("item") or {}).get("price") or 0) for w in withdrawals), 2)
    names = ", ".join(str((w.get("item") or {}).get("name") or "скин") for w in withdrawals[:5])
    if len(withdrawals) > 5:
        names += f" и ещё {len(withdrawals) - 5}"
    await post_message(db, chat, "user", f"Хочу получить скины на вывод: {names} (всего {len(withdrawals)} шт., ≈{total:.2f} RAP)",
                       {"kind": "withdrawal_request", "count": len(withdrawals), "total": total})
    await post_message(db, chat, "system", "Заявка на вывод принята. Оператор скоро подключится и передаст скины через трейд в игре.")


async def my_chats(db, owner):
    rows = await db.chats.find({"owner": owner}, {"_id": 0}).sort("updated_at", -1).to_list(1)
    chat = rows[0] if rows else None
    left = cooldown_left(chat)
    return {"chats": rows, "unread": sum(int(r.get("user_unread") or 0) for r in rows),
            "cooldown_seconds": left, "cooldown_until": (now() + timedelta(seconds=left)) if left else None}


async def user_close(db, chat):
    if chat["status"] == "closed":
        return chat
    require_cooldown(chat)
    await post_message(db, chat, "system", "Вы завершили чат. Открыть его снова можно через 3 минуты")
    await db.chats.update_one({"id": chat["id"]}, {"$set": {"status": "closed", "closed_at": now(), "toggle_at": now()}})
    return await db.chats.find_one({"id": chat["id"]}, {"_id": 0})


async def user_reopen(db, chat):
    if chat["status"] != "closed":
        return chat
    require_cooldown(chat)
    await db.chats.update_one({"id": chat["id"]}, {"$set": {"status": "open", "closed_at": None, "toggle_at": now(), "updated_at": now()}})
    chat["status"] = "open"
    await post_message(db, chat, "system", "Чат открыт заново. Оператор скоро подключится.")
    return await db.chats.find_one({"id": chat["id"]}, {"_id": 0})


async def get_owned_chat(db, chat_id, owner):
    chat = await db.chats.find_one({"id": chat_id, "owner": owner}, {"_id": 0})
    if not chat:
        raise HTTPException(404, "Чат не найден")
    return chat


async def messages(db, chat_id, after=None, limit=200):
    query = {"chat_id": chat_id}
    if after:
        query["created_at"] = {"$gt": after}
    return await db.chat_messages.find(query, {"_id": 0}).sort("created_at", 1).to_list(limit)


async def mark_read(db, chat_id, side):
    await db.chats.update_one({"id": chat_id}, {"$set": {f"{side}_unread": 0}})


async def presence_map(db, owners):
    keys = [o.split("guest:", 1)[1] if o.startswith("guest:") else o for o in owners]
    threshold = now() - timedelta(seconds=120)
    rows = await db.presence.find({"session_id": {"$in": keys}, "last_seen": {"$gte": threshold}}, {"_id": 0, "session_id": 1}).to_list(len(keys) + 1)
    online = {r["session_id"] for r in rows}
    return {o: (o.split("guest:", 1)[1] if o.startswith("guest:") else o) in online for o in owners}


def waiting_since(chat):
    lm = chat.get("last_message") or {}
    if chat.get("status") != "closed" and lm.get("sender") == "user":
        return _utc(lm.get("created_at"))
    return None


async def enrich_chats(db, rows):
    owners = [r["owner"] for r in rows]
    online = await presence_map(db, owners)
    users = {u["session_id"]: u for u in await db.users.find({"session_id": {"$in": owners}}, {"_id": 0, "session_id": 1, "avatar": 1, "nickname": 1, "balance": 1, "skins.price": 1, "roblox_nick": 1, "discord_id": 1}).to_list(len(owners) + 1)}
    for r in rows:
        u = users.get(r["owner"])
        r["online"] = online.get(r["owner"], False)
        ws = waiting_since(r)
        r["waiting_since"] = ws
        r["waiting_seconds"] = int((now() - ws).total_seconds()) if ws else None
        if u:
            r["avatar"] = u.get("avatar") or r.get("avatar")
            r["nickname"] = u.get("nickname") or r.get("nickname")
            r["discord_id"] = u.get("discord_id") or r.get("discord_id")
            r["roblox_nick"] = u.get("roblox_nick") or r.get("roblox_nick")
            r["balance"] = float(u.get("balance") or 0)
            r["skins_total"] = round(sum(float(s.get("price") or 0) for s in (u.get("skins") or [])), 2)
        else:
            r["balance"] = None
            r["skins_total"] = None
    return rows


async def admin_list(db, status="open", q=None):
    if status == "all":
        query = {}
    elif status in STATUSES:
        query = {"status": status}
    else:
        raise HTTPException(400, "Неверный статус")
    q = (q or "").strip()
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        owners = [u["session_id"] for u in await db.users.find(
            {"$or": [{"nickname": rx}, {"discord_id": rx}, {"roblox_nick": rx}, {"roblox_link": rx}]}, {"_id": 0, "session_id": 1}).to_list(200)]
        query = {"$and": [query, {"$or": [{"nickname": rx}, {"discord_id": rx}, {"roblox_nick": rx}, {"owner": {"$in": owners}}]}]} if query else {"$or": [{"nickname": rx}, {"discord_id": rx}, {"roblox_nick": rx}, {"owner": {"$in": owners}}]}
    order = 1 if status == "open" else -1
    rows = await enrich_chats(db, await db.chats.find(query, {"_id": 0}).sort("updated_at", order).to_list(200))
    if status == "closed":
        return rows
    far = now()
    rows.sort(key=lambda r: (0, r["waiting_since"]) if r["waiting_since"] else (1, far - _utc(r["updated_at"])))
    return rows


async def search_users(db, q):
    q = (q or "").strip()
    if len(q) < 2:
        return []
    rx = {"$regex": re.escape(q), "$options": "i"}
    users = await db.users.find(
        {"$or": [{"nickname": rx}, {"discord_id": rx}, {"roblox_nick": rx}, {"roblox_link": rx}]},
        {"_id": 0, "session_id": 1, "nickname": 1, "discord_id": 1, "roblox_nick": 1, "roblox_link": 1, "balance": 1, "skins.price": 1, "avatar": 1, "created_at": 1},
    ).to_list(50)
    sids = [u["session_id"] for u in users]
    chats = {c["owner"]: c for c in await db.chats.find({"owner": {"$in": sids}}, {"_id": 0, "id": 1, "owner": 1, "status": 1}).to_list(100)}
    pending = {w["_id"]: w for w in await db.withdrawals.aggregate([
        {"$match": {"session_id": {"$in": sids}, "status": {"$in": ["pending", "cancelling", "paying"]}}},
        {"$group": {"_id": "$session_id", "n": {"$sum": 1}, "total": {"$sum": {"$ifNull": ["$item.price", 0]}}}}]).to_list(100)}
    out = []
    for u in users:
        skins = u.pop("skins", []) or []
        c = chats.get(u["session_id"])
        w = pending.get(u["session_id"])
        out.append({**u, "balance": float(u.get("balance") or 0), "skins_count": len(skins), "skins_total": round(sum(float(s.get("price") or 0) for s in skins), 2),
                    "chat_id": c["id"] if c else None, "chat_status": c["status"] if c else None,
                    "pending_withdrawals": int(w["n"]) if w else 0, "pending_withdrawals_total": round(float(w["total"]), 2) if w else 0})
    return out


async def admin_summary(db):
    rows = await db.chats.find({"status": {"$ne": "closed"}}, {"_id": 0, "status": 1, "admin_unread": 1}).to_list(500)
    return {
        "open": sum(1 for r in rows if r["status"] == "open"),
        "active": sum(1 for r in rows if r["status"] == "active"),
        "unread": sum(int(r.get("admin_unread") or 0) for r in rows),
    }


async def require_chat(db, chat_id):
    chat = await db.chats.find_one({"id": chat_id}, {"_id": 0})
    if not chat:
        raise HTTPException(404, "Чат не найден")
    return chat


async def accept(db, chat_id, operator):
    chat = await require_chat(db, chat_id)
    if chat["status"] == "active":
        return chat
    await db.chats.update_one({"id": chat_id}, {"$set": {"status": "active", "accepted_at": now(), "operator": operator, "closed_at": None}})
    chat["status"] = "active"
    await post_message(db, chat, "system", "Оператор подключился к чату")
    return await db.chats.find_one({"id": chat_id}, {"_id": 0})


async def close(db, chat_id):
    chat = await require_chat(db, chat_id)
    if chat["status"] == "closed":
        return chat
    await post_message(db, chat, "system", "Чат завершён оператором. Напишите снова, если нужна помощь")
    await db.chats.update_one({"id": chat_id}, {"$set": {"status": "closed", "closed_at": now(), "toggle_at": now()}})
    return await db.chats.find_one({"id": chat_id}, {"_id": 0})


async def notify_owner(db, owner, text):
    chat = await db.chats.find_one({"owner": owner}, {"_id": 0}, sort=[("updated_at", -1)])
    if chat:
        await post_message(db, chat, "system", text)


async def notify_deposit(db, deposit, text):
    if deposit and deposit.get("chat_id"):
        chat = await db.chats.find_one({"id": deposit["chat_id"]}, {"_id": 0})
        if chat:
            await post_message(db, chat, "system", text)
