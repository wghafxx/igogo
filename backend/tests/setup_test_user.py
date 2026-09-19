"""Seed the discord_test_1 test user with balance + 3 skins copied from shop_items."""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    shop = await db.shop_items.find({}, {"_id": 0}).sort("price", 1).to_list(200)
    print("shop items:", len(shop))
    if len(shop) < 4:
        print("NOT ENOUGH SHOP ITEMS")
    cheap = shop[:3]
    skins = [{**it, "uid": str(uuid.uuid4())} for it in cheap]
    await db.users.update_one(
        {"session_id": "discord_test_1"},
        {"$set": {
            "session_id": "discord_test_1",
            "balance": 999000.0,
            "nickname": "Tester",
            "avatar": "https://cdn.discordapp.com/embed/avatars/0.png",
            "discord_id": "1",
            "skins": skins,
        }},
        upsert=True,
    )
    u = await db.users.find_one({"session_id": "discord_test_1"}, {"_id": 0})
    print("balance", u["balance"], "skins", len(u["skins"]), "prices", [s["price"] for s in u["skins"]])
    print("expensive targets:", [(s["name"], s["price"]) for s in shop[-3:]])


asyncio.run(main())
