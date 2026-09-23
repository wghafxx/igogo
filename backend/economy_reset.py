"""Resumable full economy reset; public upgrade count and account identities survive."""
import asyncio
import uuid
from datetime import timedelta

from fastapi import HTTPException
from pymongo import ReturnDocument

from economy_guard import now, drain
import staff_core

ZERO_BANK = {
    "bank": 0.0, "pool": 0.0, "commission_profit": 0.0,
    "deposit_receipts": [], "withdrawal_receipts": [], "commission_deposits": [], "rain_returns": [],
    "commission_backfill_version": 1,
}
WIPE = (
    "upgrades", "drops", "item_history", "luck_cycles", "rains", "bank_ledger",
    "deposits", "withdrawals", "promo_gifts", "promo_gift_ops", "promo_activations",
    "referral_rewards", "user_locks",
)


async def upgrade_count(db):
    totals = await db.economy_totals.find_one({"_id": "main"}) or {}
    return int(totals.get("upgrades_before_reset", 0)) + await db.upgrades.estimated_document_count()


async def clear_data(db, journal):
    # Preserve old invoice IDs so a delayed retry cannot recreate a paid invoice.
    async for dep in db.deposits.find({"payment_method": {"$in": ["xrocket", "cryptobot"]}}, {"id": 1}):
        await db.retired_payment_orders.update_one({"_id": dep["id"]}, {"$setOnInsert": {"reset_id": journal["_id"]}}, upsert=True)
    # Keep only purchase ID tombstones; never restore historical purchased skins.
    async for user in db.users.find({"shop_receipts.0": {"$exists": True}}, {"shop_receipts.id": 1}):
        ids = [r["id"] for r in user.get("shop_receipts", [])]
        if ids:
            await db.users.update_one({"_id": user["_id"]}, {"$addToSet": {"retired_shop_orders": {"$each": ids}}})
    await db.users.update_many({}, {"$set": {
        "balance": 0.0, "skins": [], "gold_nick": False, "referral_earned_cents": 0,
        "promo_id": None, "promo_code": None, "promo_bonus": 0.0,
    }, "$unset": {key: "" for key in (
        "credited_deposits", "claimed_promo_gifts", "admin_coin_receipts", "shop_receipts",
        "referral_receipts", "referral_qualified_at", "referred_by", "referral_joined_at",
        "cancelled_withdrawals", "returned_withdrawals",
    )}})
    # Retain immutable request IDs to reject retries, but hide reset grants from history.
    await db.admin_coin_grants.update_many({"status": {"$ne": "reset"}}, {"$set": {"status": "reset", "reset_id": journal["_id"]}})
    await db.promo_codes.update_many({}, {"$set": {"reserved_count": 0, "reserved_keys": [], "used_count": 0}})
    await db.chats.update_many({}, {"$set": {"deposit_id": None, "expected_rap": None}})
    await staff_core.on_economy_reset(db, journal)
    for name in WIPE:
        await db[name].delete_many({})
    await db.economy_totals.update_one({"_id": "main"}, {"$set": {
        "upgrades_before_reset": journal["upgrades_total"],
    }}, upsert=True)
    await db.bank_state.replace_one({"id": "main"}, {
        "id": "main", **ZERO_BANK, "reset_at": journal["created_at"],
    }, upsert=True)
    await db.admin_audit.update_one({"id": f"economy-reset:{journal['_id']}"}, {"$setOnInsert": {
        "event": "economy_reset", "jti": journal["admin_jti"], "created_at": journal["created_at"],
        "upgrades_total_preserved": journal["upgrades_total"],
    }}, upsert=True)


async def reset(db, request_id, admin):
    previous = await db.economy_resets.find_one({"_id": request_id})
    if previous and previous["status"] == "completed":
        await db.economy_control.update_one({"_id": "main", "reset_id": request_id}, {"$set": {"resetting": False, "reset_id": None}})
        return previous["result"]
    token = uuid.uuid4().hex
    control = await db.economy_control.find_one_and_update({
        "_id": "main", "$and": [
            {"$or": [{"resetting": False}, {"lock_until": {"$lt": now()}}]},
            {"$or": [{"resetting": False}, {"reset_id": request_id}]},
        ],
    }, {"$set": {"resetting": True, "reset_id": request_id, "owner": token, "lock_until": now() + timedelta(seconds=120)}}, return_document=ReturnDocument.AFTER)
    if not control:
        raise HTTPException(409, "Сброс уже выполняется. Повторите этот запрос позже")
    started = bool(previous)
    completed = False
    try:
        async with asyncio.timeout(90):
            previous = await db.economy_resets.find_one({"_id": request_id})
            if previous and previous["status"] == "completed":
                completed = True
                return previous["result"]
            started = bool(previous)
            await drain(db)
            # Persist the absolute counter BEFORE deleting games. Retrying a partial
            # reset must not add the same historical count twice.
            if not previous:
                previous = {"_id": request_id, "status": "running", "created_at": now(),
                            "admin_jti": admin, "upgrades_total": await upgrade_count(db)}
                await db.economy_resets.insert_one(dict(previous))
                started = True
            await clear_data(db, previous)
            result = {"ok": True, "bank": 0.0, "pool": 0.0, "commission_profit": 0.0,
                      "upgrades_total": previous["upgrades_total"]}
            await db.economy_resets.update_one({"_id": request_id}, {"$set": {"status": "completed", "result": result, "completed_at": now()}})
            completed = True
            return result
    finally:
        # A partially cleared database stays closed to ordinary requests until
        # a retry/startup finishes the same journalled reset.
        changes = {"lock_until": now() - timedelta(seconds=1)}
        if completed or not started:
            changes.update({"resetting": False, "reset_id": None})
        await db.economy_control.update_one({"_id": "main", "owner": token}, {"$set": changes, "$unset": {"owner": ""}})


async def resume(db):
    while True:
        control = await db.economy_control.find_one({"_id": "main"})
        if not control or not control.get("resetting"):
            return
        request_id = control["reset_id"]
        journal = await db.economy_resets.find_one({"_id": request_id})
        if journal and journal["status"] == "completed":
            await db.economy_control.update_one({"_id": "main", "reset_id": request_id}, {"$set": {"resetting": False, "reset_id": None}})
            return
        try:
            await reset(db, request_id, (journal or {}).get("admin_jti", "startup-recovery"))
        except HTTPException as error:
            if error.status_code != 409:
                raise
            await asyncio.sleep(1)
