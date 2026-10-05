"""Player bonuses: a one-time chain of four deposit gifts and a weekly Roblox display-name bonus."""
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

TZ = ZoneInfo("Asia/Qyzylorda")
GIFTS = [
    {"id": "g1", "kind": "percent", "pct": 0.15, "min_rap": 500},
    {"id": "g2", "kind": "skin", "item_id": "case-glove-case", "min_rap": 200},
    {"id": "g3", "kind": "skin", "item_id": "awp-railgun", "min_rap": 500},
    {"id": "g4", "kind": "skin", "item_id": "ak47-aniki", "min_rap": 2000},
]
WEEKLY_AMOUNT = 20.0
WEEKLY_MIN_GAMES = 10
WEEKLY_NAME = "bloxgrade"


def now():
    return datetime.now(timezone.utc)


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def week_bounds():
    local = now().astimezone(TZ)
    start = datetime(local.year, local.month, local.day, tzinfo=TZ) - timedelta(days=local.weekday())
    return start.astimezone(timezone.utc), (start + timedelta(days=7)).astimezone(timezone.utc), start.strftime("%G-W%V")


def _net(dep):
    return round(float(dep.get("rap") or 0) * (1 - float(dep.get("fee") or 0)), 2)


async def _qualifying(db, session_id, gift, since, used):
    if not since:
        return None
    return await db.deposits.find_one(
        {"session_id": session_id, "status": "confirmed", "rap": {"$gte": gift["min_rap"]},
         "resolved_at": {"$gt": since}, "id": {"$nin": used}},
        {"_id": 0, "id": 1, "rap": 1, "fee": 1, "resolved_at": 1}, sort=[("resolved_at", 1)])


async def state(db, user):
    bonus = user.get("bonus") or {}
    claims = bonus.get("claims") or {}
    used = [c.get("deposit_id") for c in claims.values()]
    items = {i["id"]: i for i in await db.shop_items.find({"id": {"$in": [g["item_id"] for g in GIFTS if g.get("item_id")]}}, {"_id": 0}).to_list(10)}
    gifts, anchor, prev_done = [], _utc(bonus.get("started_at")), True
    for g in GIFTS:
        out = {**g, "item": items.get(g.get("item_id"))}
        claim = claims.get(g["id"])
        if claim:
            out.update(status="claimed", claimed_at=claim["at"], amount=claim.get("amount"))
            anchor = _utc(claim["at"])
        elif not prev_done:
            out["status"] = "locked"
        elif g["id"] == "g1" and not anchor:
            out["status"] = "inactive"
        else:
            dep = await _qualifying(db, user["session_id"], g, anchor, used)
            out["status"] = "claimable" if dep else "waiting"
            if dep:
                out.update(deposit_id=dep["id"], deposit_rap=float(dep["rap"]), amount=round(_net(dep) * g["pct"], 2) if g["kind"] == "percent" else None)
        prev_done = bool(claim)
        gifts.append(out)
    start, end, key = week_bounds()
    games = await db.upgrades.count_documents({"session_id": user["session_id"], "created_at": {"$gte": start, "$lt": end}})
    name_ok = WEEKLY_NAME in (user.get("roblox_display_name") or "").lower()
    weekly = {"amount": WEEKLY_AMOUNT, "min_games": WEEKLY_MIN_GAMES, "games": games, "access": bool(user.get("weekly_bonus_access")),
              "name_ok": name_ok, "display_name": user.get("roblox_display_name"), "claimed": user.get("weekly_claimed_week") == key,
              "resets_at": end}
    weekly["can_claim"] = weekly["access"] and name_ok and games >= WEEKLY_MIN_GAMES and not weekly["claimed"]
    return {"gifts": gifts, "weekly": weekly}


async def activate(db, user):
    await db.users.update_one({"session_id": user["session_id"], "bonus.started_at": {"$exists": False}}, {"$set": {"bonus.started_at": now()}})
    return await state(db, await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0}))


async def claim_gift(db, user, gift_id):
    current = next((g for g in (await state(db, user))["gifts"] if g["id"] == gift_id), None)
    if not current:
        raise HTTPException(404, "Подарок не найден")
    if current["status"] != "claimable":
        raise HTTPException(409, "Подарок пока недоступен")
    claim = {"at": now(), "deposit_id": current["deposit_id"]}
    if current["kind"] == "percent":
        claim["amount"] = current["amount"]
        change = {"$inc": {"balance": current["amount"]}}
    else:
        if not current["item"]:
            raise HTTPException(409, "Предмет подарка сейчас недоступен. Напишите в поддержку")
        skin = {**current["item"], "uid": str(uuid.uuid4())}
        claim.update(amount=float(skin.get("price") or 0), skin_uid=skin["uid"])
        change = {"$push": {"skins": skin}}
    change.setdefault("$set", {})[f"bonus.claims.{gift_id}"] = claim
    res = await db.users.update_one({"session_id": user["session_id"], f"bonus.claims.{gift_id}": {"$exists": False}}, change)
    if not res.modified_count:
        raise HTTPException(409, "Подарок уже получен")
    await db.bonus_claims.insert_one({"id": str(uuid.uuid4()), "session_id": user["session_id"], "kind": gift_id, **claim})
    if current["kind"] == "skin":
        await db.item_history.insert_one({"id": str(uuid.uuid4()), "session_id": user["session_id"], "kind": "bonus", "item": skin,
                                          "price": claim["amount"], "created_at": claim["at"]})
    return await state(db, await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0}))


async def claim_weekly(db, user):
    st = (await state(db, user))["weekly"]
    if not st["access"]:
        raise HTTPException(403, "Доступ к бонусу выдаёт поддержка после проверки аккаунта")
    if not st["name_ok"]:
        raise HTTPException(409, "Display Name в Roblox должен быть bloxgrade")
    if st["games"] < WEEKLY_MIN_GAMES:
        raise HTTPException(409, f"Нужно минимум {WEEKLY_MIN_GAMES} игр за неделю")
    _, _, key = week_bounds()
    res = await db.users.update_one({"session_id": user["session_id"], "weekly_bonus_access": True, "weekly_claimed_week": {"$ne": key}},
                                    {"$set": {"weekly_claimed_week": key}, "$inc": {"balance": WEEKLY_AMOUNT}})
    if not res.modified_count:
        raise HTTPException(409, "Бонус за эту неделю уже получен")
    await db.bonus_claims.insert_one({"id": str(uuid.uuid4()), "session_id": user["session_id"], "kind": "weekly", "week": key,
                                      "amount": WEEKLY_AMOUNT, "at": now()})
    return await state(db, await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0}))
