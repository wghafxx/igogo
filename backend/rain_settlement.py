"""Return a closed luck reserve once, including retries after interruption."""
from datetime import datetime, timezone

from pymongo import ReturnDocument


async def refund_rain(db, rain):
    if "slices" in rain:
        left = sum(float(s.get("amount") or 0) for s in rain["slices"] if not s.get("session_id"))
    else:
        left = float(rain.get("left") or 0)
    amount = round(max(0.0, left), 2)
    await db.bank_state.update_one({"id": "main"}, {"$setOnInsert": {"bank": 0.0, "pool": 0.0}}, upsert=True)
    # The money and its receipt are written together. A restart between this
    # write and finishing the rain cannot return the same reserve a second time.
    await db.bank_state.update_one(
        {"id": "main", "rain_returns": {"$ne": rain["id"]}},
        {"$inc": {"pool": amount}, "$addToSet": {"rain_returns": rain["id"]}},
    )
    await db.rains.update_one({"id": rain["id"], "return_pending": True}, {"$set": {
        "returned_amount": amount, "left": 0.0, "return_pending": False,
    }})
    return {**rain, "returned_amount": amount, "left": 0.0, "return_pending": False}


async def resume_rain_returns(db):
    async for rain in db.rains.find({"status": "closed", "return_pending": True}, {"_id": 0}):
        await refund_rain(db, rain)


async def close_rain(db, conditions=None):
    rain = await db.rains.find_one_and_update(
        {"status": "active", **(conditions or {})},
        {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc), "return_pending": True}},
        return_document=ReturnDocument.AFTER,
    )
    return await refund_rain(db, rain) if rain else None
