"""Immutable client frames, colour-aware template matching and strict OCR."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import time
import unicodedata

import cv2
import numpy as np
import desktop

_tpl_cache = {}


def _load_tpl(path):
    path = Path(path)
    if not path.is_file():
        return None
    key = (str(path.resolve()), path.stat().st_mtime_ns)
    if key not in _tpl_cache:
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or min(image.shape[:2]) < 5 or max(image.std(axis=(0, 1))) < 3:
            return None
        _tpl_cache[key] = image
    return _tpl_cache[key]


def save_image(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise OSError(f"Не удалось записать изображение: {path}")
    encoded.tofile(path)


def hover_colours_match(candidate, template):
    """Allow brightness changes, NOT active-green -> disabled-gray/red recolouring."""
    original = template.astype(np.float32)
    current = candidate.astype(np.float32)
    # Remove brightness only; preserve per-pixel chroma and visible content.
    original_chroma = original-original.mean(axis=2, keepdims=True)
    current_chroma = current-current.mean(axis=2, keepdims=True)
    if np.mean(np.abs(original_chroma-current_chroma)) > 24:
        return False
    hsv_before = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
    hsv_after = cv2.cvtColor(candidate, cv2.COLOR_BGR2HSV)
    coloured = (hsv_before[:, :, 1] > 70) & (hsv_before[:, :, 2] > 45)
    if np.mean(coloured) >= 0.05:
        hue_delta = np.abs(hsv_before[:, :, 0].astype(float)-hsv_after[:, :, 0])
        hue_delta = np.minimum(hue_delta, 180-hue_delta)
        saturated = hsv_after[:, :, 1] >= np.maximum(45, hsv_before[:, :, 1].astype(float)*0.45)
        if np.mean((hue_delta[coloured] <= 10) & saturated[coloured]) < 0.9:
            return False
    elif np.mean(hsv_after[:, :, 1] > 70) > 0.15:
        return False
    return True


def match_image(image, template, thr=0.85, scales=None, hover=False):
    if template is None or image is None or not image.size:
        return None
    best = None
    scales = scales or ((1.0, 0.96, 1.04, 0.92, 1.08, 0.9, 1.1) if hover else (1.0, 0.96, 1.04))
    for scale in scales:
        h, w = template.shape[:2]
        w, h = round(w * scale), round(h * scale)
        if min(w, h) < 5 or w > image.shape[1] or h > image.shape[0]:
            continue
        tpl = template if scale == 1 else cv2.resize(template, (w, h))
        if max(tpl.std(axis=(0, 1))) < 3:
            continue
        scores = cv2.matchTemplate(image, tpl, cv2.TM_CCOEFF_NORMED)
        # Evaluate a few peaks: the strongest correlation may have the wrong colour.
        for _ in range(3):
            _, score, _, (x, y) = cv2.minMaxLoc(scores)
            if not np.isfinite(score) or score < thr:
                break
            candidate = image[y:y+h, x:x+w]
            colour_error = np.mean(np.abs(candidate.astype(np.float32)-tpl.astype(np.float32)))
            colour_ok = hover_colours_match(candidate, tpl) if hover else colour_error <= 32
            if colour_ok and (best is None or score > best[2]):
                best = (x + w//2, y + h//2, float(score))
            scores[max(0, y-h//2):y+h//2+1, max(0, x-w//2):x+w//2+1] = -1
    return best


@dataclass
class Frame:
    image: np.ndarray
    left: int = 0
    top: int = 0
    captured_at: float = field(default_factory=time.monotonic)

    @property
    def w(self):
        return self.image.shape[1]

    @property
    def h(self):
        return self.image.shape[0]

    def bounds(self, region):
        if region is None:
            return 0, 0, self.w, self.h
        x1, y1, x2, y2 = region
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("Область за границей игрового окна")
        bounds = (round(x1*self.w), round(y1*self.h), round(x2*self.w), round(y2*self.h))
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise ValueError("Пустая область распознавания")
        return bounds

    def grab(self, region=None):
        x1, y1, x2, y2 = self.bounds(region)
        return self.image[y1:y2, x1:x2]

    def find(self, template_path, region=None, thr=0.85, hover=False):
        hit = match_image(self.grab(region), _load_tpl(template_path), thr, hover=hover)
        if hit is None:
            return None
        x, y, *_ = self.bounds(region)
        return self.left + x + hit[0], self.top + y + hit[1], hit[2]


class Screen:
    def __init__(self, hwnd=None):
        desktop.require_windows()
        self.hwnd = hwnd or desktop.roblox_window()
        if not self.hwnd:
            raise RuntimeError("Окно клиента Roblox не найдено")
        self.pid = desktop.process_id(self.hwnd)
        self.rect = desktop.client_rect(self.hwnd)
        from mss import mss
        self.sct = mss()

    def snapshot(self):
        desktop.check_stop()
        rect = desktop.client_rect(self.hwnd)
        if desktop.process_id(self.hwnd) != self.pid or desktop.user32.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("Потерян фокус выбранного Roblox; снимок отменён")
        image = np.asarray(self.sct.grab({"left": rect.left, "top": rect.top,
                                        "width": rect.width, "height": rect.height}))
        if desktop.client_rect(self.hwnd) != rect or desktop.user32.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("Окно изменилось во время снимка")
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        if float(image.std()) < 1:
            raise RuntimeError("Получен пустой/однотонный снимок. Попробуй оконный режим Roblox")
        self.rect = rect
        return Frame(image, rect.left, rect.top)

    def grab(self, region=None):
        return self.snapshot().grab(region)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.sct.close()


def expand(region, k=0.08):
    x1, y1, x2, y2 = region
    dx, dy = (x2-x1)*k, (y2-y1)*k
    return [max(0, x1-dx), max(0, y1-dy), min(1, x2+dx), min(1, y2+dy)]


def _get_ocr(tesseract_cmd=""):
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd or "tesseract"
    return pytesseract


def check_ocr(tesseract_cmd="", lang="eng"):
    try:
        ocr = _get_ocr(tesseract_cmd)
        version = str(ocr.get_tesseract_version())
        missing = set(lang.split("+")) - set(ocr.get_languages(config=""))
        if missing:
            raise RuntimeError("Нет языков Tesseract: " + ", ".join(sorted(missing)))
        return version
    except Exception as exc:
        raise RuntimeError(f"OCR недоступен: {exc}. Проверь tesseract_cmd и ocr_lang") from exc


def _prep_ocr(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if gray.mean() < 127:
        gray = 255-gray
    return cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)


def ocr_text(image, whitelist=None, psm=7, tesseract_cmd="", lang="eng"):
    desktop.check_stop()
    options = f"--psm {psm}"
    if whitelist:
        options += f" -c tessedit_char_whitelist={whitelist}"
    try:
        text = _get_ocr(tesseract_cmd).image_to_string(_prep_ocr(image), lang=lang, config=options, timeout=2)
    except RuntimeError as exc:
        if "timeout" not in str(exc).lower():
            raise
        return None
    desktop.check_stop()
    return text.strip()


def norm_nick(nick):
    if not isinstance(nick, str):
        return ""
    nick = nick.strip().removeprefix("@")
    return nick.lower() if re.fullmatch(r"[A-Za-z0-9_]{3,20}", nick) else ""


def ocr_nick(image, tesseract_cmd="", lang="eng"):
    # No character whitelist: stripping punctuation can turn a different name into an allowed one.
    return norm_nick(ocr_text(image, None, 7, tesseract_cmd, lang))


def norm_display_name(text):
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text).strip()
    if not text or len(text) > 50 or "@" in text or any(c in text for c in "\r\n\t"):
        return ""
    return " ".join(text.split()).casefold()


def ocr_display_name(image, tesseract_cmd="", lang="eng"):
    return norm_display_name(ocr_text(image, None, 7, tesseract_cmd, lang))


def nick_matches(nick, allowed):
    name = norm_nick(nick)
    return name if name and name in {norm_nick(item) for item in allowed} else None


def parse_number(text):
    if not isinstance(text, str):
        return None
    text = text.strip()
    if re.fullmatch(r"[0-9]{1,12}", text):
        return int(text)
    # Only complete integers with consistent thousands separators. Never strip K/M, signs or labels.
    if re.fullmatch(r"[0-9]{1,3}(?P<sep>[, .\u00a0\u202f])[0-9]{3}(?:(?P=sep)[0-9]{3}){0,2}", text):
        return int(re.sub(r"[, .\u00a0\u202f]", "", text))
    return None


def ocr_number(image, tesseract_cmd=""):
    return parse_number(ocr_text(image, None, 7, tesseract_cmd))


def slot_empty(slot_img, plus_template_path, thr=0.8):
    template = _load_tpl(plus_template_path)
    hit = match_image(slot_img, template, thr)
    if hit is None:
        return False
    h, w = slot_img.shape[:2]
    return abs(hit[0]-w/2) <= w*0.18 and abs(hit[1]-h/2) <= h*0.18


def visuals_equal(a, b, tolerance=20, changed_fraction=0.01):
    if a is None or b is None or a.shape != b.shape or not a.size:
        return False
    delta = np.max(np.abs(a.astype(np.int16)-b.astype(np.int16)), axis=2)
    return float(np.mean(delta > tolerance)) <= changed_fraction


def wait_until(fn, timeout, poll=0.25, stop=desktop.check_stop):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stop()
        result = fn()
        if result:
            return result
        desktop.pause(min(poll, max(0, deadline-time.monotonic())))
    return None