"""Download catalog skin images once and store them as small WebP files (background: scripts/prepare_background.py)."""
import concurrent.futures
import io
import pathlib
import re
import sys

import requests
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "items"
OUT.mkdir(parents=True, exist_ok=True)
SRC = "https://bloxstrike.net/items/bloxstrike-live"
SIZE = 256

ids = set()
for f in [ROOT / "backend" / "catalog.py", ROOT / "frontend" / "src" / "lib" / "rarity.js"]:
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

sys.exit(0)
