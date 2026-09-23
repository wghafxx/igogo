"""Drain API/background operations before a reset, including other workers."""
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def ensure(db):
    await db.economy_control.update_one({"_id": "main"}, {"$setOnInsert": {
        "resetting": False, "active": {},
    }}, upsert=True)


@asynccontextmanager
async def operation(db):
    token = uuid.uuid4().hex
    # Requests are cancelled before their lease can expire. The extra margin
    # allows cleanup after cancellation; crashed workers cannot block forever.
    result = await db.economy_control.update_one(
        {"_id": "main", "resetting": False},
        {"$set": {f"active.{token}": now() + timedelta(seconds=120)}},
    )
    if not result.matched_count:
        raise HTTPException(503, "Идёт полный сброс экономики. Повторите запрос позже", headers={"Retry-After": "5"})
    try:
        async with asyncio.timeout(90):
            yield
    finally:
        await db.economy_control.update_one({"_id": "main"}, {"$unset": {f"active.{token}": ""}})


async def drain(db, seconds=8):
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        control = await db.economy_control.find_one({"_id": "main"})
        if not any(utc(expires) > now() for expires in control.get("active", {}).values()):
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise HTTPException(409, "Есть незавершённые операции. Повторите сброс через несколько секунд")
        await asyncio.sleep(0.05)
