"""Resumable skin returns, with an atomic per-account receipt for each withdrawal."""
from datetime import datetime, timezone

from fastapi import HTTPException


async def resolve_history(db, withdrawal, kind, **fields):
    # Older withdrawals had no ID in item_history. Match their original timestamp
    # as well as the UID so withdrawing a returned skin cannot change an older row.
    query = {"session_id": withdrawal["session_id"], "$or": [
        {"withdrawal_id": withdrawal["id"]},
        {"withdrawal_id": {"$exists": False}, "kind": "withdraw_requested",
         "item.uid": withdrawal["item"]["uid"], "created_at": withdrawal["created_at"]},
    ]}
    changes = {"kind": kind, "withdrawal_id": withdrawal["id"], **fields}
    result = await db.item_history.update_one(query, {"$set": changes})
    if not result.matched_count:
        await db.item_history.update_one({"id": f"withdrawal:{withdrawal['id']}"}, {"$set": changes, "$setOnInsert": {
            "session_id": withdrawal["session_id"], "item": withdrawal["item"],
            "price": withdrawal["item"].get("price", 0), "created_at": withdrawal["created_at"],
        }}, upsert=True)


async def finish_cancellation(db, withdrawal):
    wid, sid = withdrawal["id"], withdrawal["session_id"]
    result = await db.users.update_one(
        {"session_id": sid, "returned_withdrawals": {"$ne": wid}},
        {"$push": {"skins": withdrawal["item"]}, "$addToSet": {"returned_withdrawals": wid}},
    )
    if not result.matched_count and not await db.users.find_one(
        {"session_id": sid, "returned_withdrawals": wid}, {"_id": 1}
    ):
        raise HTTPException(409, "Аккаунт игрока не найден. Возврат скина не выполнен")
    resolved_at = withdrawal["cancelled_at"]
    await resolve_history(db, withdrawal, "withdraw_cancelled",
                          cancellation_reason=withdrawal["cancellation_reason"], resolved_at=resolved_at)
    await db.withdrawals.update_one({"id": wid, "status": "cancelling"}, {"$set": {
        "status": "cancelled", "resolved_at": resolved_at,
    }})
    return {"ok": True}


async def cancel_withdrawal(db, withdrawal_id, reason):
    # Claim before returning the skin: the concurrent "done" action can no longer win.
    await db.withdrawals.update_one(
        {"id": withdrawal_id, "status": "pending"}, {"$set": {
            "status": "cancelling", "cancellation_reason": reason,
            "cancelled_at": datetime.now(timezone.utc),
        }},
    )
    withdrawal = await db.withdrawals.find_one({"id": withdrawal_id}, {"_id": 0})
    if not withdrawal or withdrawal["status"] not in ("cancelling", "cancelled"):
        raise HTTPException(404, "Заявка не найдена или вывод уже выполнен")
    if withdrawal["status"] == "cancelled":
        return {"ok": True}
    return await finish_cancellation(db, withdrawal)
