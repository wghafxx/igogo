"""Permanent signup attribution and resumable, exactly-once referral credits."""
import asyncio
import logging
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

BONUS_CENTS = 2500
WAGER_REQUIRED = 100
DEPOSIT_RATE = Decimal("0.035")
CODE_PATTERN = re.compile(r"^[a-f0-9]{16}$")
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


async def ensure_indexes(db):
    await db.users.create_index("referral_code", unique=True, partialFilterExpression={"referral_code": {"$type": "string"}})
    await db.users.create_index([("referred_by", 1), ("created_at", -1)])
    await db.referral_rewards.create_index("id", unique=True)
    await db.referral_rewards.create_index([("referrer_id", 1), ("created_at", -1)])
    await db.referral_rewards.create_index([("status", 1), ("created_at", 1)])
    await db.upgrades.create_index([("referral_pending", 1), ("created_at", 1)])
    await db.deposits.create_index([("referral_pending", 1), ("status", 1), ("created_at", 1)])


async def referral_code(db, sid):
    for _ in range(5):
        user = await db.users.find_one({"session_id": sid}, {"referral_code": 1})
        if not user:
            raise HTTPException(401, "Аккаунт не найден")
        if user.get("referral_code"):
            return user["referral_code"]
        code = secrets.token_hex(8)
        try:
            await db.users.update_one({"session_id": sid, "referral_code": {"$exists": False}}, {"$set": {"referral_code": code}})
        except DuplicateKeyError:
            continue
    user = await db.users.find_one({"session_id": sid}, {"referral_code": 1})
    if user and user.get("referral_code"):
        return user["referral_code"]
    raise HTTPException(503, "Не удалось создать ссылку. Попробуйте ещё раз")


async def inviter_for_code(db, code):
    if not code or not CODE_PATTERN.fullmatch(code):
        return None
    user = await db.users.find_one({"referral_code": code}, {"session_id": 1})
    return user["session_id"] if user else None


async def signup_fields(db, inviter_id, sid):
    if inviter_id and inviter_id != sid and await db.users.find_one({"session_id": inviter_id}, {"_id": 1}):
        return {"referred_by": inviter_id, "referred_at": now()}
    return {}


async def settle_reward(db, reward):
    """Credit and receipt share one account update; retries cannot repeat a credit."""
    if reward["referrer_id"] == reward["invitee_id"]:
        raise HTTPException(409, "Нельзя начислить реферальный бонус самому себе")
    amount = reward["amount_cents"] / 100
    result = await db.users.update_one(
        {"session_id": reward["referrer_id"], "referral_receipts": {"$ne": reward["id"]}},
        {"$inc": {"balance": amount, "referral_earned_cents": reward["amount_cents"]},
         "$addToSet": {"referral_receipts": reward["id"]}},
    )
    if not result.matched_count and not await db.users.find_one(
        {"session_id": reward["referrer_id"], "referral_receipts": reward["id"]}, {"_id": 1}
    ):
        raise HTTPException(409, "Аккаунт пригласившего не найден")
    await db.referral_rewards.update_one({"id": reward["id"], "status": "pending"}, {"$set": {"status": "paid", "paid_at": now()}})
    if reward["kind"] == "qualified":
        await db.users.update_one({"session_id": reward["invitee_id"], "referral_qualified_at": {"$exists": False}},
                                  {"$set": {"referral_qualified_at": reward["created_at"]}})


async def award(db, reward):
    if reward["amount_cents"] <= 0:
        return
    await db.referral_rewards.update_one({"id": reward["id"]}, {"$setOnInsert": {
        **reward, "status": "pending", "created_at": now(),
    }}, upsert=True)
    saved = await db.referral_rewards.find_one({"id": reward["id"]}, {"_id": 0})
    await settle_reward(db, saved)


async def reward_deposit(db, deposit):
    # A verified settlement must have credited the invited account first.
    user = await db.users.find_one({"session_id": deposit["session_id"], "credited_deposits": deposit["id"]},
                                   {"referred_by": 1})
    inviter = (user or {}).get("referred_by")
    if not inviter or inviter == deposit["session_id"]:
        return
    gross = Decimal(str(deposit["rap"]))
    amount_cents = int((gross * DEPOSIT_RATE * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    await award(db, {"id": f"referral:deposit:{deposit['id']}", "kind": "deposit", "referrer_id": inviter,
                     "invitee_id": deposit["session_id"], "source_id": deposit["id"], "amount_cents": amount_cents,
                     "deposit_rap": float(gross), "rate": float(DEPOSIT_RATE)})


async def wager_totals(db, sids):
    if not sids:
        return {}
    rows = await db.upgrades.aggregate([
        {"$match": {"session_id": {"$in": sids}}},
        {"$group": {"_id": "$session_id", "total": {"$sum": {"$add": [
            {"$ifNull": ["$bet_amount", 0]}, {"$ifNull": ["$items_total", 0]},
        ]}}}},
    ]).to_list(None)
    return {r["_id"]: float(r["total"]) for r in rows}


async def process_deposit(db, deposit):
    await reward_deposit(db, deposit)
    await db.deposits.update_one({"id": deposit["id"]}, {"$unset": {"referral_pending": ""}})


async def reward_wager(db, upgrade):
    sid = upgrade["session_id"]
    user = await db.users.find_one({"session_id": sid}, {"referred_by": 1, "referral_qualified_at": 1})
    inviter = (user or {}).get("referred_by")
    if inviter and inviter != sid and not user.get("referral_qualified_at"):
        total = (await wager_totals(db, [sid])).get(sid, 0)
        if total + 1e-9 >= WAGER_REQUIRED:
            await award(db, {"id": f"referral:qualified:{sid}", "kind": "qualified", "referrer_id": inviter,
                             "invitee_id": sid, "source_id": sid, "amount_cents": BONUS_CENTS})
    # Clear only this event; a concurrent new game must retain its own retry flag.
    await db.upgrades.update_one({"id": upgrade["id"]}, {"$unset": {"referral_pending": ""}})


async def summary(db, sid, app_url):
    code = await referral_code(db, sid)
    users = await db.users.find({"referred_by": sid}, {"_id": 0, "session_id": 1, "nickname": 1,
                                "created_at": 1, "referral_qualified_at": 1}).sort("created_at", -1).to_list(100)
    wagers = await wager_totals(db, [u["session_id"] for u in users])
    totals = await db.referral_rewards.aggregate([
        {"$match": {"referrer_id": sid, "status": "paid"}},
        {"$group": {"_id": "$invitee_id", "amount_cents": {"$sum": "$amount_cents"},
                    "deposit_cents": {"$sum": {"$cond": [{"$eq": ["$kind", "deposit"]}, "$amount_cents", 0]}}}},
    ]).to_list(None)
    earned = {r["_id"]: r["amount_cents"] / 100 for r in totals}
    return {"url": f"{app_url}/?ref={code}", "bonus_rap": BONUS_CENTS / 100,
            "required_wager_rap": WAGER_REQUIRED, "deposit_percent": float(DEPOSIT_RATE * 100),
            "invited_count": await db.users.count_documents({"referred_by": sid}),
            "qualified_count": await db.users.count_documents({"referred_by": sid, "referral_qualified_at": {"$exists": True}}),
            "earned_rap": sum(r["amount_cents"] for r in totals) / 100,
            "deposit_earned_rap": sum(r["deposit_cents"] for r in totals) / 100,
            "invites": [{"nickname": u.get("nickname", "Player"), "joined_at": u.get("created_at"),
                         "wagered_rap": min(WAGER_REQUIRED, round(wagers.get(u["session_id"], 0), 2)),
                         "qualified": bool(u.get("referral_qualified_at")), "earned_rap": earned.get(u["session_id"], 0)} for u in users]}


async def reconcile_once(db):
    for deposit in await db.deposits.find({"referral_pending": True, "status": "confirmed"}, {"_id": 0}).sort("created_at", 1).to_list(100):
        try:
            await process_deposit(db, deposit)
        except Exception:
            logger.exception("Could not process referral deposit %s", deposit["id"])
    for game in await db.upgrades.find({"referral_pending": True}, {"_id": 0, "id": 1, "session_id": 1}).sort("created_at", 1).to_list(100):
        try:
            await reward_wager(db, game)
        except Exception:
            logger.exception("Could not process referral wager %s", game["id"])
    for reward in await db.referral_rewards.find({"status": "pending"}, {"_id": 0}).sort("created_at", 1).to_list(100):
        try:
            await settle_reward(db, reward)
        except Exception:
            logger.exception("Could not settle referral reward %s", reward["id"])


async def reconcile_loop(db):
    while True:
        try:
            from economy_guard import operation
            async with operation(db):
                await reconcile_once(db)
        except Exception:
            logger.exception("Referral reconciliation failed")
        await asyncio.sleep(30)
