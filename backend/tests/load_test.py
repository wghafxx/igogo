"""Load test with a raw asyncio HTTP client (httpx is too slow to saturate the server).
Creates qa_raw_* users, runs concurrent spins, prints throughput/latency, deletes everything it created."""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

PLAYERS = int(sys.argv[1]) if len(sys.argv) > 1 else 100
SPINS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
PREFIX = "qa_raw_"


async def player(i, results):
    sid = f"{PREFIX}{i}"
    tok = jwt.encode({"sub": sid, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, os.environ["JWT_SECRET"], algorithm="HS256")
    body = json.dumps({"session_id": sid, "bet_amount": 5, "bet_items": [], "target_item": {"id": "case-chrysalis"}, "chance": 0.1}).encode()
    req = (f"POST /api/upgrade HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {tok}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: keep-alive\r\n\r\n").encode() + body
    r, w = await asyncio.open_connection("127.0.0.1", 8001)
    for _ in range(SPINS):
        t = time.perf_counter()
        w.write(req)
        await w.drain()
        hdr = await r.readuntil(b"\r\n\r\n")
        status = int(hdr.split(b" ")[1])
        cl = int([line for line in hdr.split(b"\r\n") if line.lower().startswith(b"content-length")][0].split(b":")[1])
        await r.readexactly(cl)
        results.append((time.perf_counter() - t, status))
    w.close()


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.users.insert_many([{"session_id": f"{PREFIX}{i}", "nickname": f"Raw{i}", "balance": 100.0, "skins": [], "discord_id": f"{PREFIX}{i}"} for i in range(PLAYERS)])
    results = []
    try:
        t0 = time.perf_counter()
        await asyncio.gather(*(player(i, results) for i in range(PLAYERS)))
        wall = time.perf_counter() - t0
        lat = sorted(r[0] for r in results)
        codes = {}
        for _, s in results:
            codes[s] = codes.get(s, 0) + 1
        n = len(lat)
        print(f"players={PLAYERS} spins={n} wall={wall:.2f}s throughput={n / wall:.0f} spins/s")
        print(f"latency p50={lat[n // 2] * 1000:.0f}ms p95={lat[int(n * 0.95)] * 1000:.0f}ms max={lat[-1] * 1000:.0f}ms codes={codes}")
        wins = await db.upgrades.count_documents({"session_id": {"$regex": "^" + PREFIX}, "win": True})
        forced = await db.upgrades.count_documents({"session_id": {"$regex": "^" + PREFIX}, "forced_loss": True})
        print(f"wins={wins} forced_losses={forced} (expected win rate ~{5 / 44 * 0.9:.3f})")
    finally:
        for col in ["users", "upgrades", "drops", "presence", "item_history"]:
            await db[col].delete_many({"session_id": {"$regex": "^" + PREFIX}})
        print("cleaned")


asyncio.run(main())
