"""Manual coin credits, with an immutable operation log and atomic user receipt."""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

# Storage uses doubles throughout the application. Above this magnitude even a
# single cent cannot reliably be represented. This is not a grant/bank budget.
MAX_BALANCE = 2 ** 45
COINS_PER_RUB = 2


def now():
    return datetime.now(timezone.utc)


def public(row):
    return {k: row.get(k) for k in ("id", "amount", "amount_rub", "note", "status", "created_at", "completed_at")}


async def ensure_indexes(db):
    await db.admin_coin_grants.create_index("id", unique=True)
    await db.admin_coin_grants.create_index([("session_id", 1), ("created_at", -1)])


async def settle(db, op):
    if op["status"] == "reset":
        raise HTTPException(409, "Начисление отменено полным сбросом экономики. Создайте новый запрос")
    if op["status"] == "rejected":
        raise HTTPException(400, "Сумма выходит за технический диапазон баланса")
    if op["status"] != "completed":
        result = await db.users.update_one({
            "session_id": op["session_id"], "admin_coin_receipts": {"$ne": op["id"]},
            "$expr": {"$lte": [{"$add": [{"$ifNull": ["$balance", 0]}, op["amount"]]}, MAX_BALANCE]},
        }, {"$inc": {"balance": op["amount"]}, "$addToSet": {"admin_coin_receipts": op["id"]}})
        if not result.matched_count:
            user = await db.users.find_one({"session_id": op["session_id"]}, {"admin_coin_receipts": 1})
            if not user:
                raise HTTPException(404, "Игрок не найден")
            if op["id"] not in user.get("admin_coin_receipts", []):
                await db.admin_coin_grants.update_one({"id": op["id"], "status": "pending"}, {"$set": {"status": "rejected"}})
                raise HTTPException(400, "Сумма выходит за технический диапазон баланса")
        # Retrying after a crash between these two writes finds the user receipt.
        await db.admin_coin_grants.update_one({"id": op["id"], "status": "pending"}, {"$set": {
            "status": "completed", "completed_at": now(),
        }})
    row = await db.admin_coin_grants.find_one({"id": op["id"]})
    user = await db.users.find_one({"session_id": op["session_id"]}, {"balance": 1})
    return {**public(row), "balance": float(user.get("balance") or 0)}


async def credit(db, session_id, request_id, amount, note, admin, amount_rub=None):
    user = await db.users.find_one({"session_id": session_id}, {"nickname": 1})
    if not user or session_id.startswith("guest:"):
        raise HTTPException(404, "Игрок не найден")
    op = {"id": request_id, "session_id": session_id, "nickname": user.get("nickname"),
          "amount": float(amount), "note": note, "admin_jti": admin, "status": "pending", "created_at": now()}
    if amount_rub is not None:
        op["amount_rub"] = float(amount_rub)
    try:
        await db.admin_coin_grants.insert_one(dict(op))
    except DuplicateKeyError:
        op = await db.admin_coin_grants.find_one({"id": request_id})
        rubles = float(amount_rub) if amount_rub is not None else None
        if (op["session_id"], op["amount"], op["note"], op.get("amount_rub")) != (session_id, float(amount), note, rubles):
            raise HTTPException(409, "Этот запрос уже использован для другого начисления")
    return await settle(db, op)


async def resume_pending(db):
    async for op in db.admin_coin_grants.find({"status": "pending"}):
        try:
            await settle(db, op)
        except Exception:
            logging.getLogger(__name__).exception("Could not resume manual credit %s", op["id"])
