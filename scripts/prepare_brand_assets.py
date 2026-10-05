"""Prepare web assets from the user's original logo files (no font substitution)."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "brand"
OUTPUT = ROOT / "frontend" / "public" / "brand"
OUTPUT.mkdir(parents=True, exist_ok=True)

wordmark = Image.open(SOURCE / "wordmark-original.png").convert("RGBA")
wordmark = wordmark.crop(wordmark.getchannel("A").getbbox())
wordmark.save(OUTPUT / "bloxgrade-wordmark.png", optimize=True)

avatar = Image.open(SOURCE / "avatar-original.png").convert("RGB")
for size, name in [(32, "favicon-32.png"), (180, "apple-touch-icon.png"),
                   (192, "icon-192.png"), (512, "icon-512.png")]:
    avatar.resize((size, size), Image.Resampling.LANCZOS).save(OUTPUT / name, optimize=True)
avatar.resize((512, 512), Image.Resampling.LANCZOS).save(
    OUTPUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
print(f"Prepared original wordmark {wordmark.size} and five icon variants in {OUTPUT}")