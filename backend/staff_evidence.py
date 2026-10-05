"""Private staff screenshots in MongoDB GridFS (PNG/JPEG, up to 5 MB each)."""
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, UploadFile
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

BUCKET = "staff_evidence"
MAX_BYTES = 5 * 1024 * 1024
MAX_FILES = 6
UPLOADS_PER_HOUR = 120
PURPOSES = ("intake", "return", "transfer")
SIGNATURES = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"))


def bucket(db):
    return AsyncIOMotorGridFSBucket(db, bucket_name=BUCKET)


def sniff(data: bytes):
    return next((ct for sig, ct in SIGNATURES if data.startswith(sig)), None)


async def ensure_indexes(db):
    await db[f"{BUCKET}.files"].create_index([("metadata.staff_id", 1), ("uploadDate", -1)])


async def save(db, staff_id: str, deposit_id, purpose: str, file: UploadFile) -> dict:
    if purpose not in PURPOSES:
        raise HTTPException(400, "Неверное назначение файла")
    recent = await db[f"{BUCKET}.files"].count_documents({
        "metadata.staff_id": staff_id, "uploadDate": {"$gt": datetime.now(timezone.utc) - timedelta(hours=1)}})
    if recent >= UPLOADS_PER_HOUR:
        raise HTTPException(429, "Слишком много загрузок за час")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Файл больше 5 МБ")
    content_type = sniff(data)
    if not content_type:
        raise HTTPException(400, "Нужен скриншот PNG или JPEG")
    ext = "png" if content_type == "image/png" else "jpg"
    file_id = await bucket(db).upload_from_stream(f"evidence.{ext}", data, metadata={
        "staff_id": staff_id, "deposit_id": deposit_id, "purpose": purpose, "content_type": content_type})
    return {"id": str(file_id), "content_type": content_type, "size": len(data)}


def _oid(file_id: str) -> ObjectId:
    try:
        return ObjectId(file_id)
    except (InvalidId, TypeError):
        raise HTTPException(404, "Файл не найден") from None


async def meta(db, file_id: str):
    return await db[f"{BUCKET}.files"].find_one({"_id": _oid(file_id)})


async def read(db, file_id: str) -> tuple:
    doc = await meta(db, file_id)
    if not doc:
        raise HTTPException(404, "Файл не найден")
    stream = await bucket(db).open_download_stream(doc["_id"])
    return await stream.read(), doc["metadata"]


async def validate(db, ids, staff_id: str, deposit_id, purpose: str) -> list:
    ids = list(dict.fromkeys(str(i) for i in ids or []))
    if not 1 <= len(ids) <= MAX_FILES:
        raise HTTPException(400, f"Приложите от 1 до {MAX_FILES} скриншотов")
    for file_id in ids:
        doc = await meta(db, file_id)
        m = (doc or {}).get("metadata") or {}
        if not doc or m.get("staff_id") != staff_id or m.get("deposit_id") != deposit_id or m.get("purpose") != purpose:
            raise HTTPException(400, "Скриншот не найден или относится к другой заявке")
    return ids
