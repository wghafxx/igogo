"""Owner edits of a player wallet: set exact balance, remove inventory skins. Every change is journaled."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument

import admin_coins


def now():
    return datetime.now(timezone.utc)


def _public(user):
    return {"session_id": user["session_id"], "nickname": user.get("nickname"), "balance": float(user.get("balance") or 0),
            "skins": user.get("skins", []) or [], "weekly_bonus_access": bool(user.get("weekly_bonus_access")),
            "roblox_display_name": user.get("roblox_display_name")}


async def _journal(db, kind, user_before, admin, **details):
    await db.admin_player_edits.insert_one({"id": str(uuid.uuid4()), "kind": kind, "session_id": user_before["session_id"],
                                            "nickname": user_before.get("nickname"), "admin_jti": admin, "created_at": now(), **details})


async def inventory(db, session_id):
    user = await db.users.find_one({"session_id": session_id}, {"_id": 0, "session_id": 1, "nickname": 1, "balance": 1, "skins": 1, "weekly_bonus_access": 1, "roblox_display_name": 1})
    if not user or session_id.startswith("guest:"):
        raise HTTPException(404, "Игрок не найден")
    return _public(user)


async def set_balance(db, session_id, balance, note, admin):
    value = round(float(balance), 2)
    if value < 0 or value > admin_coins.MAX_BALANCE:
        raise HTTPException(400, "Баланс вне допустимого диапазона")
    before = await db.users.find_one_and_update({"session_id": session_id}, {"$set": {"balance": value}},
                                                projection={"_id": 0}, return_document=ReturnDocument.BEFORE)
    if not before or session_id.startswith("guest:"):
        raise HTTPException(404, "Игрок не найден")
    await _journal(db, "balance_set", before, admin, before=float(before.get("balance") or 0), after=value, note=note)
    return await inventory(db, session_id)


async def remove_skin(db, session_id, uid, note, admin):
    before = await db.users.find_one_and_update({"session_id": session_id, "skins.uid": uid}, {"$pull": {"skins": {"uid": uid}}},
                                                projection={"_id": 0}, return_document=ReturnDocument.BEFORE)
    if not before:
        raise HTTPException(404, "Скин уже удалён или игрок не найден")
    skin = next((s for s in before.get("skins", []) if s.get("uid") == uid), None)
    await _journal(db, "skin_remove", before, admin, skin=skin, note=note)
    return await inventory(db, session_id)
