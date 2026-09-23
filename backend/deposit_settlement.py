"""Resumable deposits: atomic credit markers make retries safe on standalone MongoDB."""
from datetime import datetime, timezone
import uuid
import logging
from fastapi import HTTPException
from pymongo import ReturnDocument
from deposit_allocation import allocation, cents
from referrals import process_deposit
from bank_accounting import deposit_commission, reserve_legacy_commission


def now():
    return datetime.now(timezone.utc)


async def plan_deposit(db, dep, rap):
    items = await db.shop_items.find({}, {"_id": 0}).to_list(None)
    return allocation(rap, dep.get("promo_bonus", 0), items)


async def settle_deposit(db, dep):
    """The plan is persisted before any financial writes; each write is idempotent."""
    dep_id, sid = dep["id"], dep["session_id"]
    commission = deposit_commission(dep)
    skins, remainder = dep["issued_skins"], dep["balance_credited"]
    if sum(cents(s["price"]) for s in skins) + cents(remainder) != cents(dep["credited"]) or remainder < 0:
        raise HTTPException(409, "Сумма выдачи не совпадает с депозитом")
    update = {"$inc": {"balance": remainder}, "$addToSet": {"credited_deposits": dep_id}}
    if skins:
        update["$push"] = {"skins": {"$each": skins}}
    result = await db.users.update_one({"session_id": sid, "credited_deposits": {"$ne": dep_id}}, update)
    if not result.matched_count and not await db.users.find_one({"session_id": sid, "credited_deposits": dep_id}, {"_id": 1}):
        raise HTTPException(409, "Аккаунт получателя не найден. Выдача не выполнена")

    await db.bank_state.update_one({"id": "main"}, {"$setOnInsert": {"bank": 0.0}}, upsert=True)
    # Store the original post-credit bank snapshot together with the deduplication marker.
    await db.bank_state.update_one(
        {"id": "main", "deposit_receipts.id": {"$ne": dep_id}},
        [{"$set": {
            "bank": {"$add": [{"$ifNull": ["$bank", 0]}, dep["rap"]]},
            "commission_profit": {"$add": [{"$ifNull": ["$commission_profit", 0]}, commission]},
            "commission_deposits": {"$concatArrays": [
                {"$ifNull": ["$commission_deposits", []]}, [dep_id] if commission else [],
            ]},
        }},
         {"$set": {"deposit_receipts": {"$concatArrays": [
             {"$ifNull": ["$deposit_receipts", []]}, [{"id": dep_id, "bank_after": "$bank", "commission": commission}]
         ]}}}],
    )
    # Recover deposits credited by an older version before the deployment.
    await reserve_legacy_commission(db, dep)
    state = await db.bank_state.find_one({"id": "main"}, {"_id": 0})
    receipt = next(r for r in state["deposit_receipts"] if r["id"] == dep_id)
    await db.bank_ledger.update_one({"id": f"deposit:{dep_id}"}, {"$setOnInsert": {
        "kind": "deposit", "amount": dep["rap"], "bank_after": receipt["bank_after"],
        "commission": commission,
        "note": (f"{dep.get('nickname')}: {'CryptoBot' if dep.get('payment_method') == 'cryptobot' else 'xRocket'}, {dep['amount_rub']} ₽, на баланс {remainder} RAP"
                 if dep.get("payment_method") in ("xrocket", "cryptobot") else
                 f"{dep.get('nickname')}: {len(skins)} скинов ({dep['skins_total']} RAP), остаток {remainder} RAP"),
        "ref_id": dep_id, "session_id": sid, "created_at": dep["planned_at"],
    }}, upsert=True)
    for skin in skins:
        await db.item_history.update_one({"id": f"deposit:{dep_id}:{skin['uid']}"}, {"$setOnInsert": {
            "session_id": sid, "kind": "deposited", "item": skin, "price": skin["price"],
            "deposit_id": dep_id, "created_at": dep["planned_at"],
        }}, upsert=True)
    # The invitation bonus has its own durable retry flag so its failure cannot
    # turn an already credited payment into a payment error for the invited player.
    await db.deposits.update_one({"id": dep_id, "status": "processing"}, {"$set": {
        "status": "confirmed", "resolved_at": now(), "referral_pending": True,
    }})
    try:
        await process_deposit(db, dep)
    except Exception:
        logging.getLogger(__name__).exception("Referral reward deferred for deposit %s", dep_id)
    return {"ok": True, "rap": dep["rap"], "credited": dep["credited"], "skins_total": dep["skins_total"],
            "balance_credited": remainder, "issued_skins": skins, "bank": state["bank"]}


async def confirm_deposit(db, dep_id, rap, note):
    dep = await db.deposits.find_one({"id": dep_id}, {"_id": 0})
    if dep and dep.get("payment_method") in ("xrocket", "cryptobot"):
        raise HTTPException(409, "Платежи xRocket/CryptoBot подтверждаются автоматически платёжной системой")
    if not dep or dep["status"] not in ("pending", "processing", "confirmed"):
        raise HTTPException(404, "Заявка не найдена или уже отклонена/отменена")
    if dep["status"] == "confirmed":
        return {"ok": True, "already_confirmed": True, "credited": dep.get("credited", dep.get("amount", 0)),
                "issued_skins": dep.get("issued_skins", []), "balance_credited": dep.get("balance_credited", dep.get("credited", 0)),
                "skins_total": dep.get("skins_total", 0)}
    if dep["status"] == "pending":
        if not await db.users.find_one({"session_id": dep["session_id"]}, {"_id": 1}):
            raise HTTPException(409, "Аккаунт получателя не найден")
        plan = await plan_deposit(db, dep, rap)
        plan["issued_skins"] = [{**item, "uid": str(uuid.uuid4()), "deposit_id": dep_id} for item in plan["issued_skins"]]
        changes = {**plan, "status": "processing", "note": note, "planned_at": now()}
        dep = await db.deposits.find_one_and_update(
            {"id": dep_id, "status": "pending"}, {"$set": changes},
            return_document=ReturnDocument.AFTER, projection={"_id": 0},
        ) or await db.deposits.find_one({"id": dep_id}, {"_id": 0})
    if dep["status"] not in ("processing", "confirmed"):
        raise HTTPException(409, "Заявка уже отменена или отклонена")
    if cents(dep["rap"]) != cents(rap):
        raise HTTPException(409, "Выдача уже начата на другую сумму. Обновите список заявок")
    return await settle_deposit(db, dep)
