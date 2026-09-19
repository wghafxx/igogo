"""Simulation: many players with different behaviour; verify casino stays in profit, no player drains bank, yet small wins happen."""
import asyncio
import os
import random
import uuid
from collections import defaultdict
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


async def main():
    mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mc[os.environ["DB_NAME"]]
    for c in ["users", "deposits", "upgrades", "drops", "withdrawals", "item_history", "bank_state", "bank_ledger", "bank_settings", "luck_cycles"]:
        await db[c].delete_many({})
    async with httpx.AsyncClient(base_url=API, timeout=60) as h:
        A = {"Authorization": f"Bearer {(await h.post('/admin/login', json={'phrases': SEED})).json()['token']}"}
        shop = (await h.get("/shop", params={"sort": "price_asc"})).json()["items"]
        players = []
        for i in range(12):
            sid = f"discord_sim_{i}_{uuid.uuid4().hex[:4]}"
            await db.users.insert_one({"session_id": sid, "balance": 0.0, "nickname": f"Sim{i}", "skins": [], "discord_id": str(i), "roblox_nick": f"Sim{i}Rbx", "roblox_link": "https://www.roblox.com/share?code=sim", "created_at": datetime.now(timezone.utc)})
            U = {"Authorization": f"Bearer {tok(sid)}"}
            dep = (await h.post("/deposits", json={"description": "sim", "expected_rap": 100, "receiver_id": "ysrent1"}, headers=U)).json()
            rap = random.choice([50, 100, 200, 500])
            r = await h.post(f"/admin/deposits/{dep['id']}/confirm", json={"rap": rap}, headers=A)
            assert r.status_code == 200, r.text
            players.append({"sid": sid, "U": U, "dep": rap * 0.8, "style": random.choice(["small", "small", "greedy", "mixed"])})

        results = defaultdict(lambda: {"games": 0, "wins": 0})
        for rnd in range(25):
            for p in players:
                me = (await h.get("/auth/me", headers=p["U"])).json()
                bal = me["balance"]
                if bal < 5:
                    continue
                if p["style"] == "small":
                    cands = [s for s in shop if s["price"] <= p["dep"]] or shop[:1]
                elif p["style"] == "greedy":
                    cands = [s for s in shop if s["price"] > p["dep"]] or shop[-2:]
                else:
                    cands = shop
                t = random.choice(cands)
                bet = round(min(bal * 0.4, t["price"] * random.choice([0.25, 0.5, 0.75])), 2)
                if bet / t["price"] < 0.01:
                    continue
                r = await h.post("/upgrade", json={"session_id": p["sid"], "bet_amount": bet, "target_item": {"id": t["id"]}}, headers=p["U"])
                if r.status_code == 200:
                    results[p["sid"]]["games"] += 1
                    results[p["sid"]]["wins"] += int(r.json()["win"])
                    if r.json()["win"] and random.random() < 0.5:
                        me = (await h.get("/auth/me", headers=p["U"])).json()
                        if me["skins"]:
                            await h.post("/skins/sell", json={"uids": [me["skins"][0]["uid"]]}, headers=p["U"])

        bank = (await h.get("/admin/bank", headers=A)).json()
        rows = (await h.get("/admin/players", headers=A)).json()
        print(f"bank={bank['bank']:.0f} liabilities={bank['liabilities']['total']:.0f} net={bank['net']:.0f} rtp={bank['rtp']['rtp']:.2f} games={bank['games']['total']} wins={bank['games']['wins']} forced={bank['games']['forced_by']}")
        assert bank["net"] >= 0, "CASINO IN LOSS"
        winners = [r for r in rows if r["net"] > 0]
        print(f"players={len(rows)} with_wins={sum(1 for r in rows if r['wins'] > 0)} in_profit={len(winners)} max_take={max((r['net'] for r in rows), default=0):.0f}")
        for r in rows:
            print(f"  {r['nickname']:6} dep={r['deposits']:6.0f} wagered={r['wagered']:7.0f} paid={r['paid']:7.0f} rtp={r['rtp']:.2f} games={r['games']:3} wins={r['wins']:2} forced={r['forced']:2} net={r['net']:+7.0f} fate={r['cycle']}")
            if r["cycle"]:
                assert r["cycle"]["paid"] <= r["cycle"]["allowance"] * 1.3 + r["deposits"] * 0.15 + 1e-6, f"{r['nickname']} exceeded fate allowance"
        kinds = [r["cycle"]["kind"] for r in rows if r["cycle"]]
        mults = sorted(set(r["cycle"]["multiplier"] for r in rows if r["cycle"] and r["cycle"]["kind"] == "win"))
        print(f"fates: drains={kinds.count('drain')} wins={kinds.count('win')} multipliers={mults}")
        assert sum(1 for r in rows if r["wins"] > 0) >= len(rows) * 0.2, "too few players ever win — not interesting"
        print("SIMULATION OK")


asyncio.run(main())
