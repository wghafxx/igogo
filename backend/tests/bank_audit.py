"""Bank protection audit: solvency + RTP invariants must never be violated."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
API = os.environ.get("TEST_API", "http://localhost:8001/api")
SEED = ["0u1o0gyxz", "bg7gw7mnt", "zm7pcp8ip", "5hccvev8s", "7i59vojax", "q8bheol0k", "di8ihi1wr", "g5bkbe61g", "kiulp6xqy", "5mdyfh6hp"]


def user_token(sid):
    return jwt.encode({"sub": sid, "role": "user", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, os.environ["JWT_SECRET"], algorithm="HS256")


async def invariants(db):
    bank = float(((await db.bank_state.find_one({"id": "main"})) or {}).get("bank") or 0)
    bal = sum(float(u.get("balance") or 0) for u in await db.users.find({}).to_list(10000))
    inv = sum(float(s.get("price") or 0) for u in await db.users.find({}).to_list(10000) for s in u.get("skins", []))
    pend = sum(float(w["item"].get("price") or 0) for w in await db.withdrawals.find({"status": "pending"}).to_list(10000))
    ups = await db.upgrades.find({}).to_list(100000)
    wagered = sum(float(u.get("bet_amount") or 0) + float(u.get("items_total") or 0) for u in ups)
    paid = sum(float(u["target_item"]["price"]) for u in ups if u.get("win"))
    return bank, bal + inv + pend, wagered, paid


async def main():
    mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mc[os.environ["DB_NAME"]]
    for c in ["users", "deposits", "upgrades", "drops", "withdrawals", "item_history", "bank_state", "bank_ledger", "bank_settings", "luck_cycles"]:
        await db[c].delete_many({})

    async with httpx.AsyncClient(base_url=API, timeout=30) as h:
        admin = (await h.post("/admin/login", json={"phrases": SEED})).json()["token"]
        A = {"Authorization": f"Bearer {admin}"}
        sid = f"discord_audit_{uuid.uuid4().hex[:6]}"
        U = {"Authorization": f"Bearer {user_token(sid)}"}
        await db.users.insert_one({"session_id": sid, "balance": 0.0, "nickname": "Audit", "skins": [], "discord_id": "9", "roblox_nick": "AuditRbx", "roblox_link": "https://www.roblox.com/share?code=audit", "created_at": datetime.now(timezone.utc)})

        # promo then deposit: 100 RAP -> 80 -> 88
        assert (await h.post("/promo/apply", json={"code": "sinzuku"}, headers=U)).status_code == 200
        dep = (await h.post("/deposits", json={"description": "audit skin", "expected_rap": 100, "receiver_id": "ysrent1"}, headers=U)).json()
        assert dep.get("id"), dep
        r = await h.post("/deposits", json={"description": "spam", "expected_rap": 100, "receiver_id": "ysrent1"}, headers=U)
        assert r.status_code == 429, r.text
        r = await h.post("/deposits", json={"description": "bad", "expected_rap": 10, "receiver_id": "ysrent1"}, headers=U)
        assert r.status_code == 422, r.text
        r = await h.post(f"/admin/deposits/{dep['id']}/confirm", json={"rap": 10}, headers=A)
        assert r.status_code == 400, r.text
        r = await h.post(f"/admin/deposits/{dep['id']}/confirm", json={"rap": 100}, headers=A)
        assert r.status_code == 200 and r.json()["credited"] == 88.0 and r.json()["bank"] == 100.0, r.text
        r = await h.post(f"/admin/deposits/{dep['id']}/confirm", json={"rap": 100}, headers=A)
        assert r.status_code == 404
        me = (await h.get("/auth/me", headers=U)).json()
        assert me["balance"] == 88.0, me
        print("OK deposit: 100 RAP -> 88 credited, bank 100")

        shop = (await h.get("/shop", params={"sort": "price_asc"})).json()["items"]
        cheap = shop[0]  # Glove Case 43
        big = shop[-1]   # 1580

        # client-chosen chance must be ignored; bet over 75% rejected
        r = await h.post("/upgrade", json={"session_id": sid, "bet_amount": 1, "target_item": {"id": big["id"]}, "chance": 0.75}, headers=U)
        assert r.status_code == 400, r.text  # 1/1580 < 1% min chance
        r = await h.post("/upgrade", json={"session_id": sid, "bet_amount": 20, "target_item": {"id": big["id"]}, "chance": 0.75}, headers=U)
        assert r.status_code == 200 and abs(r.json()["chance"] - 20 / big["price"]) < 1e-9, r.text
        assert r.json()["win"] is False
        r = await h.post("/upgrade", json={"session_id": sid, "bet_amount": 40, "target_item": {"id": cheap["id"]}}, headers=U)
        assert r.status_code == 400
        r = await h.post("/upgrade", json={"session_id": sid, "bet_amount": 0, "bet_items": [{"uid": "fake"}], "target_item": {"id": cheap["id"]}}, headers=U)
        assert r.status_code == 400
        r = await h.post("/upgrade", json={"session_id": sid, "bet_amount": -5, "target_item": {"id": cheap["id"]}}, headers=U)
        assert r.status_code == 422
        r = await h.post("/upgrade", json={"session_id": "discord_other", "bet_amount": 1, "target_item": {"id": cheap["id"]}}, headers=U)
        assert r.status_code == 401
        print("OK validation: chance server-side, limits, foreign session rejected")

        # hammer upgrades (sequential + concurrent) and verify invariants after each batch
        wins = forced = 0
        for _ in range(40):
            bal = (await h.get("/auth/me", headers=U)).json()["balance"]
            if bal < 40:
                await db.users.update_one({"session_id": sid}, {"$inc": {"balance": 100.0}})
                await h.post("/admin/bank/adjust", json={"amount": 100, "note": "audit top-up"}, headers=A)
                bal += 100
            bet = round(min(bal, cheap["price"] * 0.75), 2)
            rs = await asyncio.gather(*[h.post("/upgrade", json={"session_id": sid, "bet_amount": round(bet / 3, 2), "target_item": {"id": cheap["id"]}}, headers=U) for _ in range(3)])
            for r in rs:
                if r.status_code == 200 and r.json()["win"]:
                    wins += 1
            bank, liab, wagered, paid = await invariants(db)
            assert bank + 1e-6 >= liab, f"SOLVENCY BROKEN bank={bank} liabilities={liab}"
            assert wagered == 0 or paid / wagered <= 0.90 + 1e-9, f"RTP BROKEN {paid}/{wagered}"
        forced = await db.upgrades.count_documents({"forced_loss": True})
        nat = await db.upgrades.count_documents({"win": True})
        bank, liab, wagered, paid = await invariants(db)
        print(f"OK {await db.upgrades.count_documents({})} games: wins={nat} forced_losses={forced} bank={bank:.2f} liabilities={liab:.2f} rtp={paid / wagered:.3f}")
        # every forced loss must have a losing roll and no skin awarded
        for u in await db.upgrades.find({"forced_loss": True}).to_list(1000):
            assert abs(u["roll"] * 360 - 180) >= u["chance"] * 180, "forced loss roll inside win zone"
            assert u["win"] is False
        assert await db.drops.count_documents({}) == nat

        # withdrawal reduces bank
        me = (await h.get("/auth/me", headers=U)).json()
        if me["skins"]:
            sk = me["skins"][0]
            await h.post("/skins/withdraw", json={"uids": [sk["uid"]]}, headers=U)
            w = (await h.get("/admin/withdrawals", headers=A)).json()[0]
            before = (await h.get("/admin/bank", headers=A)).json()["bank"]
            after = (await h.post(f"/admin/withdrawals/{w['id']}/done", headers=A)).json()["bank"]
            assert abs(before - after - sk["price"]) < 1e-6
            print(f"OK withdrawal: bank {before:.2f} -> {after:.2f}")

        # settings & adjust
        assert (await h.put("/admin/bank/settings", json={"rtp_target": 0.3}, headers=A)).status_code == 422
        assert (await h.put("/admin/bank/settings", json={"rtp_target": 0.85}, headers=A)).json()["rtp_target"] == 0.85
        assert (await h.post("/admin/bank/adjust", json={"amount": 0, "note": "zero"}, headers=A)).status_code == 400
        assert (await h.get("/admin/bank")).status_code == 403
        assert (await h.get("/admin/bank", headers=U)).status_code == 403
        d = (await h.get("/admin/bank", headers=A)).json()
        assert d["settings"]["rtp_target"] == 0.85 and d["games"]["forced_losses"] == forced and len(d["ledger"]) > 0
        # forced_loss must not leak to the player
        prof = (await h.get("/profile", headers=U)).json()
        assert all("forced_loss" not in g for g in prof["games"])
        print("OK admin bank endpoints, RTP settings, no leak to player")
        print("ALL AUDIT CHECKS PASSED")


asyncio.run(main())
