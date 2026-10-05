"""Encode the supplied already-blurred artwork once, not in the browser."""
from pathlib import Path
from PIL import Image, ImageOps

root = Path(__file__).resolve().parents[1]
source = root / "assets/backgrounds/train-soft-original.png"
output = root / "frontend/src/assets"
image = Image.open(source).convert("RGB")
image.save(output / "bg-train-soft.webp", "WEBP", quality=78, method=6)
ImageOps.fit(image, (640, 1100), method=Image.Resampling.LANCZOS).save(
    output / "bg-train-soft-mobile.webp", "WEBP", quality=76, method=6)