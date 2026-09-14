"""A bounded activity feed derived from durable deposit and withdrawal records."""
import asyncio
from datetime import datetime, timezone


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def operation_notifications(db, user, limit=50):
    # Query creations and resolutions independently: an old request completed today
    # must still appear ahead of recently created requests. Each source is bounded.
    projection = {"_id": 0, "id": 1, "status": 1, "created_at": 1, "resolved_at": 1,
                  "credited": 1, "amount": 1, "expected_rap": 1, "rap": 1,
                  "item.name": 1, "item.price": 1, "rejection_reason": 1,
                  "cancellation_reason": 1}
    query = {"session_id": user["session_id"]}
    batches = await asyncio.gather(*(
        collection.find({**query, **({"resolved_at": {"$ne": None}} if field == "resolved_at" else {})}, projection)
        .sort([(field, -1), ("id", -1)]).to_list(limit)
        for collection in (db.deposits, db.withdrawals)
        for field in ("created_at", "resolved_at")
    ))
    read_at = utc(user.get("notifications_read_at") or datetime.min.replace(tzinfo=timezone.utc))
    events = []
    for kind, batches_for_kind in (("deposit", batches[:2]), ("withdrawal", batches[2:])):
        records = {doc["id"]: doc for batch in batches_for_kind for doc in batch}
        for doc in records.values():
            created_at = doc.get("created_at")
            if not created_at:
                continue
            item = doc.get("item") or {}
            amount = (item.get("price") if kind == "withdrawal" else
                      doc.get("expected_rap", doc.get("rap")))

            def append(event, timestamp, event_amount, reason=None):
                timestamp = utc(timestamp)
                events.append({"id": f"{kind}:{doc['id']}:{event}", "type": f"{kind}_{event}",
                               "created_at": timestamp, "amount": event_amount,
                               "item_name": item.get("name"), "reason": reason,
                               "read": timestamp <= read_at})

            # A failed invoice creation is not a submitted payment request.
            if doc.get("status") not in ("creating", "payment_error"):
                append("requested", created_at, amount)
            status = doc.get("status")
            if kind == "deposit" and status in ("confirmed", "cancelled", "rejected", "expired"):
                credited = doc.get("credited", doc.get("amount")) if status == "confirmed" else amount
                append(status, doc.get("resolved_at") or created_at, credited, doc.get("rejection_reason"))
            elif kind == "withdrawal" and status in ("done", "cancelled"):
                append(status, doc.get("resolved_at") or created_at, amount, doc.get("cancellation_reason"))
    events.sort(key=lambda event: (event["created_at"], event["id"]), reverse=True)
    items = events[:limit]
    return {"items": items, "unread_count": sum(not item["read"] for item in items),
            "read_through": items[0]["created_at"] if items else None}
