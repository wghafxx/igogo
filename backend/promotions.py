"""Persistent promo codes and one activation record per account and promo."""

from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError


DEFAULT_PROMOS = (
    ("SINZUKU", 10, False),
    ("XYIPACHOSIK", 6.7, True),
    ("PELMEN", 10, False),
    ("INKAB00M", 9, False),
)


def promo_fields(promo):
    return {
        "promo_id": promo["id"] if promo else None,
        "promo_code": promo["code"] if promo else None,
        "promo_bonus": round(promo["percent"] / 100, 6) if promo else 0.0,
    }


def account_key(user):
    # Discord login always uses discord_<id>; older deposits may omit discord_id.
    discord_id = user.get("discord_id")
    sid = user.get("session_id") or ""
    if not discord_id and sid.startswith("discord_"):
        discord_id = sid[len("discord_"):]
    return f"discord:{discord_id}" if discord_id else f"session:{sid}" if sid else None


async def record_activation(db, promo_id, user):
    key = account_key(user)
    if key is None:
        return
    query = {"promo_id": promo_id, "account_key": key}
    try:
        await db.promo_activations.update_one(query, {"$setOnInsert": {
            **query, "created_at": datetime.now(timezone.utc),
        }}, upsert=True)
    except DuplicateKeyError:
        # A simultaneous activation of this same promo/account already recorded it.
        pass


async def refresh_user_promo(db, user):
    """Resolve current terms; cached user fields cannot revive a deleted bonus."""
    if not user.get("promo_id") and not user.get("promo_code"):
        return user
    query = {"id": user["promo_id"]} if user.get("promo_id") else {"code": user["promo_code"].upper()}
    promo = await db.promo_codes.find_one({**query, "deleted": False}, {"_id": 0})
    return {**user, **promo_fields(promo)}


async def ensure_promotions(db):
    await db.promo_codes.create_index("id", unique=True)
    await db.promo_codes.create_index("code", unique=True, partialFilterExpression={"deleted": False})
    await db.promo_activations.create_index([("promo_id", 1), ("account_key", 1)], unique=True)
    await db.users.create_index("promo_id")
    for code, percent, gold_nick in DEFAULT_PROMOS:
        # Stable seed IDs and tombstones preserve admin edits/deletions on restart.
        await db.promo_codes.update_one({"id": f"default-{code.lower()}"}, {"$setOnInsert": {
            "id": f"default-{code.lower()}", "code": code, "percent": percent,
            "gold_nick": gold_nick, "deleted": False, "created_at": datetime.now(timezone.utc),
        }}, upsert=True)

    migration_id = "promo-activation-history-v1"
    if await db.migrations.find_one({"_id": migration_id}):
        return
    promos = {p["code"]: p async for p in db.promo_codes.find({"deleted": False})}
    # Recover all available evidence, including previous codes in deposit history.
    # Activations overwritten before this migration with no deposit are unknowable.
    for collection in (db.users, db.deposits):
        async for row in collection.find({"promo_code": {"$type": "string"}}, {
            "session_id": 1, "discord_id": 1, "promo_code": 1,
        }):
            promo = promos.get(row["promo_code"].strip().upper())
            if promo:
                await record_activation(db, promo["id"], row)
    async for user in db.users.find({"promo_code": {"$type": "string"}, "promo_id": {"$exists": False}}):
        promo = promos.get(user["promo_code"].strip().upper())
        if promo:
            await db.users.update_one({"_id": user["_id"], "promo_code": user["promo_code"]}, {"$set": promo_fields(promo)})
    await db.migrations.update_one({"_id": migration_id}, {"$setOnInsert": {
        "completed_at": datetime.now(timezone.utc),
    }}, upsert=True)
