"""Seed preview data for the staff intake flow: a staff user, a player with a pending skin request, and JWTs.

Usage: python tests/seed_staff.py  -> prints tokens (writes nothing outside MongoDB)."""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def token(sid):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sid, "role": "user", "exp": now + timedelta(days=30), "iat": now, "sv": 0}, os.environ["JWT_SECRET"], algorithm="HS256")


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    users = {
        "staff": {"session_id": "seed-staff-1", "discord_id": "900000000000000001", "nickname": "StaffTester",
                  "roblox_display_name": "Staff Receiver", "roblox_nick": "staff_receiver", "roblox_link": "https://www.roblox.com/users/111/profile"},
        "player": {"session_id": "seed-player-1", "discord_id": "900000000000000002", "nickname": "PlayerTester",
                   "roblox_display_name": "Player One", "roblox_nick": "player_one", "roblox_link": "https://www.roblox.com/users/222/profile"},
    }
    for u in users.values():
        await db.users.update_one({"session_id": u["session_id"]}, {"$setOnInsert": {**u, "balance": 0.0, "skins": [], "created_at": datetime.now(timezone.utc),
                                                                                     "roblox_nick_normalized": u["roblox_nick"].lower()}}, upsert=True)
    for name, u in users.items():
        print(f"{name.upper()}_TOKEN={token(u['session_id'])}")
    print("STAFF_DISCORD_ID=900000000000000001")
    print(f"NEW_REQUEST_HINT=POST /api/chats {{kind:'deposit', expected_rap:300}} with PLAYER_TOKEN (id {uuid.uuid4().hex[:4]})")


asyncio.run(main())
