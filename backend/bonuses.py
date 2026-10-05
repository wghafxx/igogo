"""Player bonuses funded only from the reserved 20% deposit commission: a gift chain and a weekly display-name bonus."""
import math
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from bank_accounting import deposit_commission

TZ = ZoneInfo("Asia/Qyzylorda")
FEE = 0.20
GIFTS = [
    {"id": "g1", "kind": "percent"},
    {"id": "g2", "kind": "skin", "item_id": "case-glove-case"},
    {"id": "g3", "kind": "skin", "item_id": "awp-railgun"},
    {"id": "g4", "kind": "skin", "item_id": "ak47-aniki"},
]
DEFAULTS = {"g1_pct": 0.15, "g1_min_rap": 500.0, "g2_min_rap": 200.0, "g3_min_rap": 500.0, "g4_min_rap": 2000.0,
            "commission_share": 1.0, "weekly_amount": 20.0, "weekly_min_games": 10, "wager_x": 5.0}
LIMITS = {"g1_pct": (0, 0.25), "g1_min_rap": (1, 1e6), "g2_min_rap": (1, 1e6), "g3_min_rap": (1, 1e6), "g4_min_rap": (1, 1e6),
          "commission_share": (0.05, 1), "weekly_amount": (0, 1000), "weekly_min_games": (1, 1000), "wager_x": (0, 50)}
WEEKLY_NAME = "bloxgrade"
GAME_MIN_STAKE = 1.0
STAKE = {"$add": [{"$ifNull": ["$bet_amount", 0]}, {"$ifNull": ["$items_total", 0]}]}


def now():
    return datetime.now(timezone.utc)


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def week_bounds():
    local = now().astimezone(TZ)
    start = datetime(local.year, local.month, local.day, tzinfo=TZ) - timedelta(days=local.weekday())
    return start.astimezone(timezone.utc), (start + timedelta(days=7)).astimezone(timezone.utc), start.strftime("%G-W%V")


async def settings(db):
    doc = await db.bonus_settings.find_one({"id": "main"}, {"_id": 0, "id": 0, "updated_at": 0}) or {}
    return {**DEFAULTS, **{k: v for k, v in doc.items() if k in DEFAULTS}}


async def save_settings(db, changes):
    clean = {}
    for k, v in changes.items():
        lo, hi = LIMITS[k]
        if v is None or not lo <= float(v) <= hi:
            raise HTTPException(400, f"{k}: допустимо {lo}–{hi}")
        clean[k] = int(v) if k == "weekly_min_games" else round(float(v), 4)
    await db.bonus_settings.update_one({"id": "main"}, {"$set": {**clean, "updated_at": now()}}, upsert=True)
    return await admin_overview(db)


def _min_rap(cfg, gift, value):
    """Deposit threshold is never below the amount whose commission covers the gift value."""
    base = float(cfg[f"{gift['id']}_min_rap"])
    if gift["kind"] == "percent" or not value:
        return base
    return float(max(base, math.ceil(value / (FEE * cfg["commission_share"]))))


def _gift_value(cfg, gift, dep, item):
    budget = deposit_commission(dep) * cfg["commission_share"]
    if gift["kind"] == "percent":
        return round(min(float(dep["rap"]) * (1 - FEE) * cfg["g1_pct"], budget), 2)
    return float(item["price"]) if item and float(item["price"]) <= budget + 1e-9 else 0.0


async def _gifts_catalog(db, cfg):
    items = {i["id"]: i for i in await db.shop_items.find({"id": {"$in": [g["item_id"] for g in GIFTS if g.get("item_id")]}}, {"_id": 0}).to_list(10)}
    out = []
    for g in GIFTS:
        item = items.get(g.get("item_id"))
        out.append({**g, "item": item, "pct": cfg["g1_pct"] if g["kind"] == "percent" else None,
                    "min_rap": _min_rap(cfg, g, float(item["price"]) if item else 0)})
    return out


async def _qualifying(db, session_id, gift, since, used, cfg):
    if not since:
        return None, 0.0
    cursor = db.deposits.find(
        {"session_id": session_id, "status": "confirmed", "fee": FEE, "payment_method": {"$nin": ["xrocket", "cryptobot", "donationalerts"]},
         "rap": {"$gte": gift["min_rap"]}, "resolved_at": {"$gt": since}, "id": {"$nin": used}},
        {"_id": 0, "id": 1, "rap": 1, "fee": 1, "payment_method": 1, "resolved_at": 1}, sort=[("resolved_at", 1)])
    async for dep in cursor:
        value = _gift_value(cfg, gift, dep, gift.get("item"))
        if value > 0:
            return dep, value
    return None, 0.0


async def wager_status(db, session_id, cfg=None):
    """Bonus value x wager_x must be staked in upgrades after the first claim before any withdrawal."""
    cfg = cfg or await settings(db)
    rows = await db.bonus_claims.aggregate([{"$match": {"session_id": session_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "first": {"$min": "$at"}}}]).to_list(1)
    if not rows:
        return {"required": 0.0, "wagered": 0.0, "left": 0.0}
    required = round(float(rows[0]["total"] or 0) * cfg["wager_x"], 2)
    done = await db.upgrades.aggregate([{"$match": {"session_id": session_id, "created_at": {"$gte": rows[0]["first"]}}},
        {"$group": {"_id": None, "s": {"$sum": STAKE}}}]).to_list(1)
    wagered = round(float(done[0]["s"]) if done else 0.0, 2)
    return {"required": required, "wagered": min(wagered, required), "left": round(max(0.0, required - wagered), 2)}


async def require_wagered(db, session_id):
    left = (await wager_status(db, session_id))["left"]
    if left > 0:
        raise HTTPException(400, f"Сначала отыграйте бонус: осталось сделать ставок на {left:.2f} RAP в апгрейдах")


async def _roblox_guard(db, user):
    nick = (user.get("roblox_nick") or "").strip().lower()
    if not nick or not user.get("roblox_link"):
        raise HTTPException(400, "Сначала привяжите Roblox-профиль в профиле сайта")
    other = await db.bonus_claims.find_one({"roblox_nick": nick, "session_id": {"$ne": user["session_id"]}}, {"_id": 1})
    if other:
        raise HTTPException(409, "Бонусы для этого Roblox-аккаунта уже получены на другом аккаунте сайта")
    return nick


async def _take_commission(db, amount, note, session_id):
    """Moves the bonus value out of the reserved commission; refuses if the commission cannot cover it."""
    if amount <= 0:
        return
    res = await db.bank_state.update_one({"id": "main", "commission_profit": {"$gte": amount}}, {"$inc": {"commission_profit": -amount}})
    if not res.modified_count:
        raise HTTPException(409, "Бонусы временно недоступны, попробуйте позже")
    await db.bank_ledger.insert_one({"id": str(uuid.uuid4()), "kind": "bonus", "amount": 0.0, "commission_used": amount,
                                     "note": note, "session_id": session_id, "created_at": now()})


async def _refund_commission(db, amount):
    if amount > 0:
        await db.bank_state.update_one({"id": "main"}, {"$inc": {"commission_profit": amount}})


async def state(db, user):
    cfg = await settings(db)
    bonus = user.get("bonus") or {}
    claims = bonus.get("claims") or {}
    used = [c.get("deposit_id") for c in claims.values()]
    gifts, anchor, prev_done = [], _utc(bonus.get("started_at")), True
    for g in await _gifts_catalog(db, cfg):
        out = dict(g)
        claim = claims.get(g["id"])
        if claim:
            out.update(status="claimed", claimed_at=claim["at"], amount=claim.get("amount"))
            anchor = _utc(claim["at"])
        elif not prev_done:
            out["status"] = "locked"
        elif g["id"] == "g1" and not anchor:
            out["status"] = "inactive"
        else:
            dep, value = await _qualifying(db, user["session_id"], g, anchor, used, cfg)
            out["status"] = "claimable" if dep else "waiting"
            if dep:
                out.update(deposit_id=dep["id"], deposit_rap=float(dep["rap"]), amount=value)
        prev_done = bool(claim)
        gifts.append(out)
    start, end, key = week_bounds()
    games = await db.upgrades.count_documents({"session_id": user["session_id"], "created_at": {"$gte": start, "$lt": end},
                                               "$expr": {"$gte": [STAKE, GAME_MIN_STAKE]}})
    name_ok = WEEKLY_NAME in (user.get("roblox_display_name") or "").lower()
    weekly = {"amount": cfg["weekly_amount"], "min_games": cfg["weekly_min_games"], "games": games, "access": bool(user.get("weekly_bonus_access")),
              "name_ok": name_ok, "display_name": user.get("roblox_display_name"), "claimed": user.get("weekly_claimed_week") == key,
              "resets_at": end}
    weekly["can_claim"] = weekly["access"] and name_ok and games >= cfg["weekly_min_games"] and not weekly["claimed"] and cfg["weekly_amount"] > 0
    return {"gifts": gifts, "weekly": weekly, "wager": {**await wager_status(db, user["session_id"], cfg), "x": cfg["wager_x"]}}


async def _fresh(db, user):
    return await state(db, await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0}))


async def activate(db, user):
    await db.users.update_one({"session_id": user["session_id"], "bonus.started_at": {"$exists": False}}, {"$set": {"bonus.started_at": now()}})
    return await _fresh(db, user)


async def claim_gift(db, user, gift_id):
    current = next((g for g in (await state(db, user))["gifts"] if g["id"] == gift_id), None)
    if not current:
        raise HTTPException(404, "Подарок не найден")
    if current["status"] != "claimable":
        raise HTTPException(409, "Подарок пока недоступен")
    nick = await _roblox_guard(db, user)
    claim = {"at": now(), "deposit_id": current["deposit_id"], "amount": current["amount"]}
    if current["kind"] == "percent":
        change = {"$inc": {"balance": current["amount"]}}
    else:
        skin = {**current["item"], "uid": str(uuid.uuid4()), "bonus": True}
        claim["skin_uid"] = skin["uid"]
        change = {"$push": {"skins": skin}}
    change.setdefault("$set", {})[f"bonus.claims.{gift_id}"] = claim
    await _take_commission(db, claim["amount"], f"Бонус {gift_id} · {user.get('nickname')}", user["session_id"])
    res = await db.users.update_one({"session_id": user["session_id"], f"bonus.claims.{gift_id}": {"$exists": False}}, change)
    if not res.modified_count:
        await _refund_commission(db, claim["amount"])
        raise HTTPException(409, "Подарок уже получен")
    await db.bonus_claims.insert_one({"id": str(uuid.uuid4()), "session_id": user["session_id"], "nickname": user.get("nickname"),
                                      "kind": gift_id, "roblox_nick": nick, **claim})
    if current["kind"] == "skin":
        await db.item_history.insert_one({"id": str(uuid.uuid4()), "session_id": user["session_id"], "kind": "bonus", "item": skin,
                                          "price": claim["amount"], "created_at": claim["at"]})
    return await _fresh(db, user)


async def claim_weekly(db, user):
    st = await state(db, user)
    w = st["weekly"]
    if not w["access"]:
        raise HTTPException(403, "Доступ к бонусу выдаёт поддержка после проверки аккаунта")
    if not w["name_ok"]:
        raise HTTPException(409, "Display Name в Roblox должен быть bloxgrade")
    if w["games"] < w["min_games"]:
        raise HTTPException(409, f"Нужно минимум {w['min_games']} игр за неделю")
    if w["amount"] <= 0:
        raise HTTPException(409, "Еженедельный бонус сейчас выключен")
    nick = await _roblox_guard(db, user)
    _, _, key = week_bounds()
    amount = float(w["amount"])
    await _take_commission(db, amount, f"Еженедельный бонус · {user.get('nickname')}", user["session_id"])
    res = await db.users.update_one({"session_id": user["session_id"], "weekly_bonus_access": True, "weekly_claimed_week": {"$ne": key}},
                                    {"$set": {"weekly_claimed_week": key}, "$inc": {"balance": amount}})
    if not res.modified_count:
        await _refund_commission(db, amount)
        raise HTTPException(409, "Бонус за эту неделю уже получен")
    await db.bonus_claims.insert_one({"id": str(uuid.uuid4()), "session_id": user["session_id"], "nickname": user.get("nickname"),
                                      "kind": "weekly", "week": key, "roblox_nick": nick, "amount": amount, "at": now()})
    return await _fresh(db, user)


async def public(db):
    cfg = await settings(db)
    gifts = [{**g, "status": "inactive" if g["id"] == "g1" else "locked"} for g in await _gifts_catalog(db, cfg)]
    return {"gifts": gifts, "weekly": None, "wager": {"required": 0, "wagered": 0, "left": 0, "x": cfg["wager_x"]}, "weekly_amount": cfg["weekly_amount"]}


async def admin_overview(db):
    cfg = await settings(db)
    bank = await db.bank_state.find_one({"id": "main"}, {"_id": 0, "commission_profit": 1}) or {}
    spent = await db.bonus_claims.aggregate([{"$group": {"_id": None, "s": {"$sum": "$amount"}, "n": {"$sum": 1}}}]).to_list(1)
    recent = await db.bonus_claims.find({}, {"_id": 0, "id": 1, "nickname": 1, "kind": 1, "amount": 1, "at": 1}).sort("at", -1).to_list(30)
    return {"settings": cfg, "gifts": await _gifts_catalog(db, cfg), "commission_left": round(float(bank.get("commission_profit") or 0), 2),
            "spent": round(float(spent[0]["s"]) if spent else 0.0, 2), "claims": spent[0]["n"] if spent else 0, "recent": recent}
