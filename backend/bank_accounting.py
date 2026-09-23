"""The 20% skin-deposit fee is reserved inside the bank, outside player funds."""
from decimal import Decimal, ROUND_HALF_UP

from deposit_allocation import cents


def deposit_commission(deposit):
    # Crypto payments have no site fee. Never infer a fee from a promo-adjusted
    # credit or from RTP: only the recorded 20% skin-deposit commission qualifies.
    if deposit.get("payment_method") in ("xrocket", "cryptobot") or deposit.get("fee") != 0.20:
        return 0.0
    value = (Decimal(cents(deposit["rap"])) * Decimal("0.20")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(value / 100)


def spendable_bank_expr():
    return {"$subtract": [{"$ifNull": ["$bank", 0]}, {"$ifNull": ["$commission_profit", 0]}]}


async def bank_funds(db):
    state = await db.bank_state.find_one({"id": "main"}, {"bank": 1, "commission_profit": 1}) or {}
    bank = float(state.get("bank") or 0)
    profit = float(state.get("commission_profit") or 0)
    return {"bank": bank, "commission_profit": profit, "available_bank": round(bank - profit, 2)}


async def reserve_legacy_commission(db, deposit):
    amount = deposit_commission(deposit)
    if not amount:
        return
    dep_id = deposit["id"]
    # An interrupted deposit may already be in the bank even before its status
    # becomes confirmed. Require a bank receipt/journal entry before reserving it.
    posted = await db.bank_state.find_one({"id": "main", "deposit_receipts.id": dep_id}, {"_id": 1})
    if not posted:
        posted = await db.bank_ledger.find_one({"kind": "deposit", "ref_id": dep_id}, {"_id": 1})
    if not posted:
        return
    await db.bank_state.update_one(
        {"id": "main", "commission_deposits": {"$ne": dep_id}},
        {"$inc": {"commission_profit": amount}, "$addToSet": {"commission_deposits": dep_id}},
    )


async def reserve_historical_commissions(db):
    if await db.bank_state.find_one({"id": "main", "commission_backfill_version": 1}, {"_id": 1}):
        return
    # Preserve existing user balances and inventory. If old commissions have
    # already been spent, the available-bank deficit remains visible to admins.
    async for deposit in db.deposits.find({"status": "confirmed", "fee": 0.20}, {"_id": 0}):
        await reserve_legacy_commission(db, deposit)
    await db.bank_state.update_one(
        {"id": "main"}, {"$set": {"commission_backfill_version": 1}}, upsert=True,
    )
