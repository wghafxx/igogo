"""Balance-to-inventory purchases with atomic debit and retry receipts."""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument

from deposit_allocation import cents


async def purchase_skins(db, user, request_id, lines, expected_total):
    order_id = str(request_id)
    basket = sorted(lines, key=lambda line: line["id"])
    ids = [line["id"] for line in basket]
    if len(set(ids)) != len(ids) or sum(line["quantity"] for line in basket) > 100:
        raise HTTPException(400, "В корзине может быть до 100 предметов; одинаковые скины объедините")

    def receipt_from(account):
        return next((receipt for receipt in account.get("shop_receipts", []) if receipt["id"] == order_id), None)

    receipt = receipt_from(user)
    if receipt is None:
        catalog = {item["id"]: item for item in await db.shop_items.find({"id": {"$in": ids}}, {"_id": 0}).to_list(100)}
        if any(item_id not in catalog for item_id in ids):
            raise HTTPException(400, "Один из скинов больше недоступен. Обновите корзину")
        total_cents = 0
        issued = []
        for line in basket:
            item = catalog[line["id"]]
            price_cents = cents(item["price"])
            if price_cents <= 0:
                raise HTTPException(400, "Этот скин пока недоступен для покупки")
            total_cents += price_cents * line["quantity"]
            clean = {key: item[key] for key in ("id", "name", "type", "rarity", "image") if key in item}
            issued.extend({**clean, "price": price_cents / 100, "uid": str(uuid.uuid4()), "purchase_id": order_id} for _ in range(line["quantity"]))
        if total_cents != cents(expected_total):
            raise HTTPException(409, "Цены изменились. Обновите корзину перед покупкой")
        receipt = {"id": order_id, "items": basket, "total": total_cents / 100, "skins": issued, "created_at": datetime.now(timezone.utc)}
        fresh = await db.users.find_one_and_update(
            {"session_id": user["session_id"], "balance": {"$gte": receipt["total"] - 1e-9}, "shop_receipts.id": {"$ne": order_id}},
            [{"$set": {
                "balance": {"$round": [{"$subtract": ["$balance", receipt["total"]]}, 2]},
                "skins": {"$concatArrays": [{"$ifNull": ["$skins", []]}, {"$literal": issued}]},
                "shop_receipts": {"$concatArrays": [{"$ifNull": ["$shop_receipts", []]}, {"$literal": [receipt]}]},
            }}],
            return_document=ReturnDocument.AFTER, projection={"_id": 0},
        )
        if fresh is None:
            fresh = await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0})
            receipt = receipt_from(fresh or {})
            if receipt is None:
                raise HTTPException(400, "Недостаточно средств на балансе")
        user = fresh
    if receipt["items"] != basket or cents(receipt["total"]) != cents(expected_total):
        raise HTTPException(409, "Номер покупки уже использован для другой корзины")

    # A retry after an interrupted response repairs history without another debit.
    for skin in receipt["skins"]:
        await db.item_history.update_one({"id": f"purchase:{order_id}:{skin['uid']}"}, {"$setOnInsert": {
            "session_id": user["session_id"], "kind": "purchased", "item": skin,
            "price": skin["price"], "purchase_id": order_id, "created_at": receipt["created_at"],
        }}, upsert=True)
    return {"user": user, "purchase_id": order_id, "total": receipt["total"], "count": len(receipt["skins"])}
