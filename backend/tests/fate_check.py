"""Fate check: with a healthy bank, a player whose fate is x4 can really reach ~x4; a 'drain' player ends near 0."""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
API = os.environ.get("TEST_API", "http://localhost:8001/api")
SEED = ["0u1o0gyxz", "bg7gw7mnt", "zm7pcp8ip", "5hccvev8s", "7i59vojax", "q8bheol0k", "di8ihi1wr", "g5bkbe61g", "kiulp6xqy", "5mdyfh6hp"]


def tok(sid):
    return jwt.encode({"sub": sid, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, os.environ["JWT_SECRET"], algorithm="HS256")


async def play(h, db, sid, U, item, rounds=300):
    peak = 0.0
    for _ in range(rounds):
        me = (await h.get("/auth/me", headers=U)).json()
        for sk in me["skins"]:
            await h.post("/skins/sell", json={"uids": [sk["uid"]]}, headers=U)
        me = (await h.get("/auth/me", headers=U)).json()
        peak = max(peak, me["balance"])
        bet = round(min(me["balance"], max(1.0, me["balance"] * 0.2), item["price"] * 0.75), 2)
        if bet / item["price"] < 0.01:
            break
        r = await h.post("/upgrade", json={"session_id": sid, "bet_amount": bet, "target_item": {"id": item["id"]}}, headers=U)
        assert r.status_code == 200, r.text
    return peak, (await h.get("/auth/me", headers=U)).json()["balance"]


async def main():
    mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mc[os.environ["DB_NAME"]]
    for c in ["users", "deposits", "upgrades", "drops", "withdrawals", "item_history", "bank_state", "bank_ledger", "bank_settings", "luck_cycles"]:
        await db[c].delete_many({})
    async with httpx.AsyncClient(base_url=API, timeout=60) as h:
        A = {"Authorization": f"Bearer {(await h.post('/admin/login', json={'phrases': SEED})).json()['token']}"}
        await h.post("/admin/bank/adjust", json={"amount": 100000, "note": "healthy bank"}, headers=A)
        await h.put("/admin/bank/settings", json={"rtp_target": 1.0}, headers=A)
        # pre-existing losses so global RTP is not the limiting factor
        await db.upgrades.insert_many([{"id": str(uuid.uuid4()), "session_id": "ghost", "bet_amount": 500.0, "items_total": 0, "win": False, "target_item": {"price": 1000}, "created_at": datetime.now(timezone.utc)} for _ in range(40)])
        item = (await h.get("/shop", params={"sort": "price_asc"})).json()["items"][0]

        async def make(nick, fate_kind, mult):
            sid = f"discord_fate_{nick}_{uuid.uuid4().hex[:4]}"
            await db.users.insert_one({"session_id": sid, "balance": 0.0, "nickname": nick, "skins": [], "discord_id": nick, "roblox_nick": nick, "roblox_link": "https://www.roblox.com/x", "created_at": datetime.now(timezone.utc)})
            U = {"Authorization": f"Bearer {tok(sid)}"}
            dep = (await h.post("/deposits", json={"description": "fate skin", "expected_rap": 125, "receiver_id": "ysrent1"}, headers=U)).json()
            r = await h.post(f"/admin/deposits/{dep['id']}/confirm", json={"rap": 125}, headers=A)
            assert r.status_code == 200 and r.json()["credited"] == 100.0
            cyc = await db.luck_cycles.find_one({"session_id": sid, "active": True})
            assert cyc and cyc["kind"] in ("drain", "win"), cyc
            await db.luck_cycles.update_one({"id": cyc["id"]}, {"$set": {"kind": fate_kind, "multiplier": mult, "allowance": round(100 * mult, 2)}})
            return sid, U

        sid, U = await make("Lucky", "win", 4.0)
        peak, final = await play(h, db, sid, U, item)
        forced_inside = await db.upgrades.count_documents({"session_id": sid, "forced_loss": True, "protection.player.p": 0.0})
        forced_total = await db.upgrades.count_documents({"session_id": sid, "forced_loss": True})
        paid = sum(u["target_item"]["price"] for u in await db.upgrades.find({"session_id": sid, "win": True}).to_list(10000))
        print(f"Lucky x4: peak balance {peak:.0f} (allowance 400) final {final:.0f} paid={paid:.0f} forced={forced_total} forced_inside_allowance={forced_inside}")
        assert forced_inside == 0, "roulette must be honest inside the allowance"
        assert paid <= 400 * 1.3 + 43 + 1e-6, "x4 player paid beyond allowance"

        sid, U = await make("Doomed", "drain", 0.3)
        peak, final = await play(h, db, sid, U, item)
        print(f"Doomed drain: peak {peak:.0f} (allowance 30) final {final:.0f}")
        assert final < 20

        bank = (await h.get("/admin/bank", headers=A)).json()
        assert bank["net"] >= 0
        rows = (await h.get("/admin/players", headers=A)).json()
        assert all(r["cycle"] for r in rows if r["session_id"] != "ghost")
        print("FATE CHECK OK")


asyncio.run(main())
