"""Iteration 8 seed: user WITH roblox (discord_test_1) and user WITHOUT roblox (TEST_it8_norbx).
Clears their deposits + resets promo so the UI flow starts clean. Prints JWTs."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app/backend")
import jwt
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from pymongo import MongoClient  # noqa: E402

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def mint(sid):
    return jwt.encode({"sub": sid, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                      os.environ["JWT_SECRET"], algorithm="HS256")


db.users.update_one({"session_id": "discord_test_1"}, {"$set": {
    "session_id": "discord_test_1", "balance": 5000.0, "nickname": "Tester", "discord_id": "1",
    "avatar": "https://cdn.discordapp.com/embed/avatars/0.png",
    "roblox_nick": "TesterRBX", "roblox_link": "https://www.roblox.com/users/1/profile",
}, "$unset": {"promo_code": "", "promo_bonus": ""}}, upsert=True)
db.users.update_one({"session_id": "TEST_it8_norbx"}, {"$set": {
    "session_id": "TEST_it8_norbx", "balance": 1000.0, "nickname": "NoRbx", "discord_id": "2",
    "avatar": "https://cdn.discordapp.com/embed/avatars/1.png", "skins": [],
}, "$unset": {"roblox_nick": "", "roblox_link": "", "promo_code": "", "promo_bonus": ""}}, upsert=True)
db.deposits.delete_many({"session_id": {"$in": ["discord_test_1", "TEST_it8_norbx"]}})
db.login_attempts.delete_many({})
print("WITH_ROBLOX", mint("discord_test_1"))
print("NO_ROBLOX", mint("TEST_it8_norbx"))
