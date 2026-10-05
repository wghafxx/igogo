"""Preview seed: staff request in review inside an admin chat. Usage: python tests/seed_review_chat.py"""
import io
import os
import struct
import zlib
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
API = "http://localhost:8001/api"
PHRASE = os.environ.get("TEST_ADMIN_PHRASE", "alpha bravo charlie delta echo foxtrot golf hotel india juliet").split()


def png():
    raw = b"\x00\xff\x00\x00"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def main():
    lines = dict(l.split("=", 1) for l in os.popen("python tests/seed_staff.py").read().split() if "=" in l and "_TOKEN" in l)
    st, pl = {"Authorization": f"Bearer {lines['STAFF_TOKEN']}"}, {"Authorization": f"Bearer {lines['PLAYER_TOKEN']}"}
    ad = {"Authorization": f"Bearer {requests.post(f'{API}/admin/login', json={'phrases': PHRASE}).json()['token']}"}
    requests.post(f"{API}/admin/staff", headers=ad, json={"discord_id": "900000000000000001", "roblox_display_name": "Staff Receiver",
                                                         "roblox_nick": "staff_receiver", "roblox_link": "https://www.roblox.com/users/111/profile"})
    chat = requests.post(f"{API}/chats", headers=pl, json={"kind": "deposit", "expected_rap": 300}).json()
    print("chat", chat.get("id"), chat.get("detail"))
    cid = chat["id"]
    print("take", requests.post(f"{API}/staff/chats/{cid}/accept", headers=st).status_code)
    ev = requests.post(f"{API}/staff/chats/{cid}/evidence", headers=st, files={"file": ("t.png", io.BytesIO(png()), "image/png")}, data={"purpose": "intake"}).json()
    print("evidence", ev)
    rep = requests.post(f"{API}/staff/chats/{cid}/report", headers=st, json={"items": [{"name": "Glove Case", "qty": 2, "value": 150}],
                        "evidence": [ev["id"]], "received": True, "value_checked": True, "note": ""})
    print("report", rep.status_code, rep.text[:200])
    print("admin chat deposit (expected 409):", requests.post(f"{API}/admin/chats/{cid}/deposit", headers=ad, json={"rap": 300}).status_code)
    for c in ("donat", "wait"):
        requests.post(f"{API}/admin/commands", headers=ad, json={"command": c, "text": "Пополнение через DonationAlerts: ссылка в профиле" if c == "donat" else "Подождите пару минут"})


main()
