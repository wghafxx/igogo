"""Screenshots in the support chat: stored in MongoDB, removed automatically after 3 days (TTL index).

Budget for a 5 GB database: 1 MB per image, 5 images per player per 24 h, 3-day lifetime
-> at most 15 MB per player; a global cap (default 1 GB) stops uploads before the DB fills up.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

from bson import Binary
from fastapi import HTTPException

MAX_BYTES = 1024 * 1024
DAILY_LIMIT = 5
COOLDOWN_SECONDS = 20
TTL_DAYS = 3
TOTAL_CAP_BYTES = int(os.environ.get("CHAT_ATTACHMENTS_MAX_MB") or 1024) * 1024 * 1024
SIGNATURES = {"image/png": (b"\x89PNG\r\n\x1a\n",), "image/jpeg": (b"\xff\xd8\xff",), "image/webp": (b"RIFF",)}


def sniff(data: bytes):
    for kind, heads in SIGNATURES.items():
        if any(data.startswith(h) for h in heads) and (kind != "image/webp" or data[8:12] == b"WEBP"):
            return kind
    return None


async def ensure_indexes(db):
    await db.chat_attachments.create_index("expires_at", expireAfterSeconds=0)
    await db.chat_attachments.create_index([("owner", 1), ("created_at", -1)])
    await db.chat_attachments.create_index("chat_id")


async def store(db, chat, owner, data: bytes, now):
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Скриншот больше 1 МБ")
    kind = sniff(data)
    if not kind:
        raise HTTPException(400, "Можно прикладывать только изображения PNG, JPEG или WebP")
    last = await db.chat_attachments.find_one({"owner": owner}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
    if last and (now - last["created_at"].replace(tzinfo=now.tzinfo)).total_seconds() < COOLDOWN_SECONDS:
        raise HTTPException(429, f"Подождите {COOLDOWN_SECONDS} сек перед следующим скриншотом")
    if await db.chat_attachments.count_documents({"owner": owner, "created_at": {"$gte": now - timedelta(days=1)}}) >= DAILY_LIMIT:
        raise HTTPException(429, f"Не больше {DAILY_LIMIT} скриншотов в сутки")
    used = await db.chat_attachments.aggregate([{"$group": {"_id": None, "n": {"$sum": "$size"}}}]).to_list(1)
    if used and used[0]["n"] + len(data) > TOTAL_CAP_BYTES:
        raise HTTPException(507, "Хранилище скриншотов временно заполнено, опишите проблему текстом")
    doc = {"_id": str(uuid.uuid4()), "chat_id": chat["id"], "owner": owner, "content_type": kind, "size": len(data),
           "data": Binary(data), "created_at": now, "expires_at": now + timedelta(days=TTL_DAYS)}
    await db.chat_attachments.insert_one(doc)
    return {"id": doc["_id"], "content_type": kind, "size": len(data), "expires_at": doc["expires_at"]}


async def load(db, chat_id, attachment_id):
    doc = await db.chat_attachments.find_one({"_id": attachment_id, "chat_id": chat_id})
    # The TTL monitor runs about once a minute; expired files are hidden immediately.
    if not doc or doc["expires_at"].replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(404, "Скриншот удалён (хранится 3 дня) или не найден")
    return doc
