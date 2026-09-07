"""Full production reset: wipes all players, games, bank, deposits, withdrawals. Keeps shop_items only."""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

WIPE = [
    "users", "upgrades", "drops", "item_history", "luck_cycles", "presence",
    "deposits", "withdrawals", "bank_ledger", "bank_settings",
    "admin_sessions", "admin_audit", "login_attempts", "oauth_states",
]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for c in WIPE:
        r = await db[c].delete_many({})
        print(f"{c:16} -{r.deleted_count}")
    await db.bank_state.update_one({"id": "main"}, {"$set": {"bank": 0.0}}, upsert=True)
    await db.bank_lock.update_one({"id": "main"}, {"$set": {"locked_until": __import__("datetime").datetime(2000, 1, 1)}}, upsert=True)
    print("bank_state      ", await db.bank_state.find_one({"id": "main"}, {"_id": 0}))
    print("shop_items kept ", await db.shop_items.count_documents({}))


asyncio.run(main())
