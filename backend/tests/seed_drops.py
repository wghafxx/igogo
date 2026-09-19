import asyncio, os, sys, uuid, random
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import httpx

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

async def main(n):
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    async with httpx.AsyncClient() as c:
        items = (await c.get("http://localhost:8001/api/shop?limit=40")).json()["items"]
    now = datetime.now(timezone.utc)
    nicks = ["Builderman", "xX_Pro_Xx", "Nika", "dlb", "Ramzes1337", "kUDesNIk"]
    docs = []
    for i in range(n):
        it = random.choice(items)
        docs.append({"id": str(uuid.uuid4()), "session_id": f"seed-{i}", "nickname": random.choice(nicks), "item_name": it["name"], "item_type": it["type"],
                     "item_price": it["price"], "item_image": it["image"], "item_rarity": it["rarity"], "chance": 0.3, "display_chance": round(random.uniform(0.05, 0.7), 4),
                     "created_at": now - timedelta(seconds=i * 40)})
    await db.drops.insert_many(docs)
    print("inserted", len(docs))

asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 12))
