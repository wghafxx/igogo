"""Live support chat: users (including guests) talk to an operator from the admin panel."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pymongo.errors import BulkWriteError, DuplicateKeyError

from chat_texts import norm_lang, tr

MAX_TEXT = 2000
MAX_MESSAGES = 200
TOGGLE_COOLDOWN = 180
STATUSES = ("open", "active", "closed")
WELCOME_MESSAGE = tr("welcome", "ru")


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


def lang_of(chat):
    return norm_lang((chat or {}).get("lang"))


def public_chat(doc):
    return {k: v for k, v in doc.items() if k != "_id"}


async def ensure_indexes(db):
    await db.chats.create_index("id", unique=True)
    await db.chats.create_index([("owner", 1), ("updated_at", -1)])
    # One chat per owner for chats created from now on (older duplicates keep working).
    await db.chats.create_index("owner_unique", unique=True, partialFilterExpression={"owner_unique": {"$type": "string"}})
    await db.chat_messages_archive.create_index([("chat_id", 1), ("created_at", 1)])
    await db.chats.create_index([("status", 1), ("updated_at", -1)])
    await db.chat_messages.create_index("id", unique=True)
    await db.chat_messages.create_index([("chat_id", 1), ("created_at", 1)])
    await db.chat_messages.create_index([("chat_id", 1), ("created_at", -1), ("_id", -1)])


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
    await trim_messages(db, chat["id"])
    return msg


async def create_chat(db, owner, profile, kind, text=None, deposit=None, lang=None):
    if kind not in ("support", "deposit", "withdrawal"):
        raise HTTPException(400, "Неверный тип чата")
    chat = await db.chats.find_one({"owner": owner}, {"_id": 0}, sort=[("updated_at", -1)])
    created = None
    if not chat:
        created = {
            "id": str(uuid.uuid4()), "owner": owner, "owner_unique": owner, "kind": "support", "status": "open",
            "nickname": profile.get("nickname") or "Гость", "avatar": profile.get("avatar"),
            "discord_id": profile.get("discord_id"), "roblox_nick": profile.get("roblox_nick"),
            "guest": not profile.get("registered"), "lang": norm_lang(lang),
            "deposit_id": None, "expected_rap": None,
            "user_unread": 0, "admin_unread": 0,
            "created_at": now(), "updated_at": now(), "last_message": None, "accepted_at": None, "closed_at": None, "toggle_at": now(),
        }
        try:
            await db.chats.insert_one(dict(created))
        except DuplicateKeyError:
            # A parallel request created the owner's chat first: continue with that one.
            created = None
            chat = await db.chats.find_one({"owner": owner}, {"_id": 0}, sort=[("updated_at", -1)])
    if created:
        chat = created
        await post_message(db, chat, "admin", tr("welcome", lang_of(chat)), {"kind": "welcome"})
    else:
        if lang:
            chat["lang"] = norm_lang(lang)
        if chat["status"] == "closed":
            require_cooldown(chat)
            await clear_messages(db, chat["id"])
            await db.chats.update_one({"id": chat["id"]}, {"$set": {"status": "open", "closed_at": None, "toggle_at": now(), "updated_at": now()}})
            chat["status"] = "open"
            await post_message(db, chat, "admin", tr("welcome", lang_of(chat)), {"kind": "welcome"})
            await post_message(db, chat, "system", tr("reopened", lang_of(chat)))
        profile_fields = {"lang": lang_of(chat), "nickname": profile.get("nickname") or chat["nickname"], "avatar": profile.get("avatar"), "discord_id": profile.get("discord_id"), "roblox_nick": profile.get("roblox_nick"), "guest": not profile.get("registered")}
        await db.chats.update_one({"id": chat["id"]}, {"$set": profile_fields})
    if deposit:
        await db.chats.update_one({"id": chat["id"]}, {"$set": {"deposit_id": deposit["id"], "expected_rap": deposit["expected_rap"]}})
        await post_message(db, chat, "user", tr("deposit_request", lang_of(chat), rap=deposit["expected_rap"]), {"kind": "deposit_request", "expected_rap": deposit["expected_rap"], "deposit_id": deposit["id"]})
        await post_message(db, chat, "system", tr("deposit_created", lang_of(chat)))
    if text and text.strip():
        await post_message(db, chat, "user", text)
    return await db.chats.find_one({"id": chat["id"]}, {"_id": 0})


async def post_withdrawal_request(db, chat, withdrawals):
    total = round(sum(float((w.get("item") or {}).get("price") or 0) for w in withdrawals), 2)
    lang = lang_of(chat)
    names = ", ".join(str((w.get("item") or {}).get("name") or "skin") for w in withdrawals[:5])
    if len(withdrawals) > 5:
        names += tr("withdrawal_more", lang, n=len(withdrawals) - 5)
    await post_message(db, chat, "user", tr("withdrawal_request", lang, names=names, count=len(withdrawals), total=total),
                       {"kind": "withdrawal_request", "count": len(withdrawals), "total": total})
    await post_message(db, chat, "system", tr("withdrawal_created", lang))


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
    await post_message(db, chat, "system", tr("user_closed", lang_of(chat)))
    await db.chats.update_one({"id": chat["id"]}, {"$set": {"status": "closed", "closed_at": now(), "toggle_at": now()}})
    return await db.chats.find_one({"id": chat["id"]}, {"_id": 0})


async def user_reopen(db, chat):
    if chat["status"] != "closed":
        return chat
    require_cooldown(chat)
    await clear_messages(db, chat["id"])
    await db.chats.update_one({"id": chat["id"]}, {"$set": {"status": "open", "closed_at": None, "toggle_at": now(), "updated_at": now()}})
    chat["status"] = "open"
    await post_message(db, chat, "admin", tr("welcome", lang_of(chat)), {"kind": "welcome"})
    await post_message(db, chat, "system", tr("reopened", lang_of(chat)))
    return await db.chats.find_one({"id": chat["id"]}, {"_id": 0})


async def get_owned_chat(db, chat_id, owner):
    chat = await db.chats.find_one({"id": chat_id, "owner": owner}, {"_id": 0})
    if not chat:
        raise HTTPException(404, "Чат не найден")
    return chat


async def archive_messages(db, query):
    # Conversations leave the live window but stay restorable in chat_messages_archive.
    rows = await db.chat_messages.find(query).to_list(None)
    if not rows:
        return
    try:
        await db.chat_messages_archive.insert_many(rows, ordered=False)
    except BulkWriteError:
        pass  # rows archived by an earlier interrupted attempt
    await db.chat_messages.delete_many({"_id": {"$in": [r["_id"] for r in rows]}})


async def clear_messages(db, chat_id):
    # Keep payment records separately; the previous conversation is archived, not shown again.
    await archive_messages(db, {"chat_id": chat_id})
    await db.chats.update_one({"id": chat_id}, {"$set": {"user_unread": 0, "admin_unread": 0, "last_message": None}})


async def trim_messages(db, chat_id):
    oldest = await db.chat_messages.find({"chat_id": chat_id}, {"_id": 1, "created_at": 1}).sort([("created_at", -1), ("_id", -1)]).skip(MAX_MESSAGES - 1).limit(1).to_list(1)
    if oldest:
        row = oldest[0]
        await archive_messages(db, {"chat_id": chat_id, "$or": [
            {"created_at": {"$lt": row["created_at"]}},
            {"created_at": row["created_at"], "_id": {"$lt": row["_id"]}},
        ]})


async def messages(db, chat_id, after=None, limit=MAX_MESSAGES):
    query = {"chat_id": chat_id}
    if after:
        # Inclusive: messages sharing the cursor's millisecond are not lost; clients dedupe by id.
        query["created_at"] = {"$gte": after}
    # Select the newest window first, then return it in reading order.
    limit = min(MAX_MESSAGES, max(1, limit))
    rows = await db.chat_messages.find(query, {"_id": 0}).sort([("created_at", -1), ("_id", -1)]).limit(limit).to_list(limit)
    return list(reversed(rows))


async def mark_read(db, chat_id, side):
    await db.chats.update_one({"id": chat_id, f"{side}_unread": {"$gt": 0}}, {"$set": {f"{side}_unread": 0}})


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


async def admin_list(db, status="open", q=None, offset=0, limit=100, scope=None):
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
    if scope:
        query = {"$and": [query, scope]} if query else scope
    order = 1 if status == "open" else -1
    page = await db.chats.find(query, {"_id": 0}).sort([("updated_at", order), ("id", 1)]).skip(offset).limit(limit + 1).to_list(limit + 1)
    has_more = len(page) > limit
    rows = await enrich_chats(db, page[:limit])
    if status != "closed":
        far = now()
        rows.sort(key=lambda r: (0, r["waiting_since"]) if r["waiting_since"] else (1, far - _utc(r["updated_at"])))
    return {"items": rows, "has_more": has_more, "offset": offset, "total": await db.chats.count_documents(query)}


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


async def admin_summary(db, scope=None):
    rows = await db.chats.aggregate([
        {"$match": {"status": {"$ne": "closed"}, **(scope or {})}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}, "unread": {"$sum": {"$ifNull": ["$admin_unread", 0]}}}},
    ]).to_list(None)
    by = {r["_id"]: r for r in rows}
    return {
        "open": int(by.get("open", {}).get("n", 0)),
        "active": int(by.get("active", {}).get("n", 0)),
        "unread": int(sum(r["unread"] for r in rows)),
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
    if chat["status"] == "closed":
        await clear_messages(db, chat_id)
    await db.chats.update_one({"id": chat_id}, {"$set": {"status": "active", "accepted_at": now(), "operator": operator, "closed_at": None}})
    chat["status"] = "active"
    await post_message(db, chat, "system", tr("operator_joined", lang_of(chat)))
    return await db.chats.find_one({"id": chat_id}, {"_id": 0})


async def close(db, chat_id):
    chat = await require_chat(db, chat_id)
    if chat["status"] == "closed":
        return chat
    await post_message(db, chat, "system", tr("operator_closed", lang_of(chat)))
    await db.chats.update_one({"id": chat_id}, {"$set": {"status": "closed", "closed_at": now(), "toggle_at": now()}})
    return await db.chats.find_one({"id": chat_id}, {"_id": 0})


def _text(text, chat):
    # Callers may pass a plain string or a (key, params) pair translated to the chat language.
    return tr(text[0], lang_of(chat), **text[1]) if isinstance(text, tuple) else text


async def notify_owner(db, owner, text):
    chat = await db.chats.find_one({"owner": owner}, {"_id": 0}, sort=[("updated_at", -1)])
    if chat:
        await post_message(db, chat, "system", _text(text, chat))


async def notify_deposit(db, deposit, text):
    if deposit and deposit.get("chat_id"):
        chat = await db.chats.find_one({"id": deposit["chat_id"]}, {"_id": 0})
        if chat:
            await post_message(db, chat, "system", _text(text, chat))
