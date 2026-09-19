"""Seed dedicated rapid-click test user, inventory (>100), and optional live drops.

Usage:
  python /app/backend/tests/seed_iteration1_rapid_user.py
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from pymongo import MongoClient


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    load_dotenv("/app/backend/.env")
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    jwt_secret = os.environ["JWT_SECRET"]

    session_id = "discord_it1_rapid_100hz"
    discord_id = "91001001"

    mongo = MongoClient(mongo_url)
    db = mongo[db_name]

    shop = list(db.shop_items.find({}, {"_id": 0}).sort("price", 1).limit(300))
    if not shop:
        raise RuntimeError("shop_items is empty; cannot seed test inventory")

    target_count = 120
    skins = []
    idx = 0
    while len(skins) < target_count:
        item = dict(shop[idx % len(shop)])
        item["uid"] = str(uuid.uuid4())
        skins.append(item)
        idx += 1

    user_doc = {
        "session_id": session_id,
        "balance": 250000.0,
        "nickname": "RapidClickTester",
        "avatar": "https://cdn.discordapp.com/embed/avatars/2.png",
        "discord_id": discord_id,
        "skins": skins,
        "created_at": now_utc(),
        "last_login": now_utc(),
    }
    db.users.update_one({"session_id": session_id}, {"$set": user_doc}, upsert=True)

    db.drops.delete_many({"session_id": session_id})
    sample = sorted(shop, key=lambda s: float(s.get("price") or 0), reverse=True)[:25]
    if not sample:
        sample = shop[:25]
    for item in sample:
        db.drops.insert_one(
            {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "nickname": user_doc["nickname"],
                "item_name": item.get("name", "Item"),
                "item_type": item.get("type", "Skin"),
                "item_price": float(item.get("price") or 0),
                "item_image": item.get("image"),
                "item_rarity": item.get("rarity"),
                "chance": 0.25,
                "display_chance": 0.29,
                "avatar": user_doc["avatar"],
                "discord_id": discord_id,
                "gold_nick": False,
                "created_at": now_utc(),
            }
        )

    token = jwt.encode(
        {
            "sub": session_id,
            "role": "user",
            "exp": now_utc() + timedelta(days=1),
            "iat": now_utc(),
        },
        jwt_secret,
        algorithm="HS256",
    )

    print(f"SESSION_ID={session_id}")
    print(f"TOKEN={token}")
    print(f"SKINS_COUNT={len(skins)}")
    print("SEEDED_OK=1")


if __name__ == "__main__":
    main()
