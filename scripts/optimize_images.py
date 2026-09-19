"""Download catalog skin images once, store them as small WebP files, and pre-blur the site background."""
import concurrent.futures
import io
import pathlib
import re
import sys

import requests
from PIL import Image, ImageEnhance, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "items"
OUT.mkdir(parents=True, exist_ok=True)
SRC = "https://bloxstrike.net/items/bloxstrike-live"
SIZE = 256

ids = set()
for f in [ROOT / "backend" / "server.py", ROOT / "frontend" / "src" / "lib" / "rarity.js"]:
    ids.update(re.findall(r"/(\d{10,})\.png", f.read_text()))


def convert(item_id):
    target = OUT / f"{item_id}.webp"
    if target.exists():
        return item_id, "cached"
    r = requests.get(f"{SRC}/{item_id}.png", timeout=30)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert("RGBA")
    im.thumbnail((SIZE, SIZE), Image.LANCZOS)
    im.save(target, "WEBP", quality=82, method=6)
    return item_id, f"{target.stat().st_size // 1024}KB"


with concurrent.futures.ThreadPoolExecutor(8) as pool:
    for item_id, status in pool.map(convert, sorted(ids)):
        print(item_id, status)

bg_src = ROOT / "frontend" / "src" / "assets" / "bg-dust2.webp"
bg_out = ROOT / "frontend" / "src" / "assets" / "bg-dust2-blur.webp"
bg = Image.open(bg_src).convert("RGB")
# Same look as the old runtime `blur(7px) saturate(1.15) brightness(1.02)` + `saturate(1.1)` overlay, baked in once.
bg = bg.filter(ImageFilter.GaussianBlur(6))
bg = ImageEnhance.Color(bg).enhance(1.32)
bg = ImageEnhance.Brightness(bg).enhance(1.04)
bg = ImageEnhance.Contrast(bg).enhance(1.05)
bg.save(bg_out, "WEBP", quality=78, method=6)
print("background", bg.size, bg_out.stat().st_size // 1024, "KB")
sys.exit(0)
