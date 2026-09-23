"""Validate settings before opening any input device."""
import math
from pathlib import Path

import yaml
from vision import _load_tpl, norm_nick

BASE = Path(__file__).resolve().parent
REQUIRED_TEMPLATES = ("person", "accept", "decline", "close", "list_anchor", "accept_trade", "decline_trade", "trade_anchor", "plus")
REQUIRED_REGIONS = ("person", "row_accept", "row_decline", "close", "row_nick", "accept_trade",
                    "decline_trade", "trade_anchor", "partner_name", "their_total", "our_total", "their_grid", "our_grid",
                    "row_display", "list_anchor")


class ConfigError(ValueError):
    pass


def number(value, key, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigError(f"{key}: требуется конечное число")
    if not low <= value <= high or (integer and int(value) != value):
        raise ConfigError(f"{key}: допустимо {'целое ' if integer else ''}{low}…{high}")
    return int(value) if integer else float(value)


def boolean(data, key, default):
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key}: требуется true/false без кавычек")
    return value


def validate_calibration(data, folder):
    screen, regions = data.get("screen"), data.get("regions")
    if data.get("calibration_version") == 2:
        raise ConfigError("Нужны оба имени и заголовок списка. Обнови только эти области: python calibrate.py --names-only")
    if not isinstance(screen, dict) or screen.get("coordinate_space") != "client" or data.get("calibration_version") != 3:
        raise ConfigError("Старая/отсутствующая калибровка. Выполни python calibrate.py")
    w = number(screen.get("w"), "screen.w", 100, 20000, True)
    h = number(screen.get("h"), "screen.h", 100, 20000, True)
    if not isinstance(regions, dict):
        raise ConfigError("regions должен быть словарём")
    required = set(REQUIRED_REGIONS)
    if boolean(data, "single_page_only", True):
        required.add("pager")
    for key in required:
        if key not in regions:
            raise ConfigError(f"Не выбрана область {key}. Повтори калибровку")
    for key, rect in regions.items():
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            raise ConfigError(f"regions.{key}: нужны 4 координаты")
        x1, y1, x2, y2 = [number(v, f"regions.{key}", 0, 1) for v in rect]
        if round(x2*w)-round(x1*w) < 5 or round(y2*h)-round(y1*h) < 5:
            raise ConfigError(f"regions.{key}: область слишком мала или перевёрнута")
    for key in (*REQUIRED_TEMPLATES, "badge", "success"):
        path = folder / f"{key}.png"
        required_template = key in REQUIRED_TEMPLATES
        if required_template or path.exists() or key in regions:
            template = _load_tpl(path)
            if template is None:
                raise ConfigError(f"Шаблон {key} отсутствует, повреждён или однотонный")
            region_key = "row_" + key if key in ("accept", "decline") else key
            if region_key not in regions:
                raise ConfigError(f"Нет области для шаблона {key}")
            if template.shape[0] > h or template.shape[1] > w:
                raise ConfigError(f"Шаблон {key} больше игрового окна")


class Cfg:
    def __init__(self, path):
        self.path = Path(path).resolve()
        try:
            self.d = yaml.safe_load(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"Не читается {self.path.name}: {exc}") from exc
        if not isinstance(self.d, dict):
            raise ConfigError("Настройки должны быть словарём YAML")
        d = self.d
        names = d.get("only_nicks")
        if not isinstance(names, list) or not names or any(not norm_nick(n) for n in names):
            raise ConfigError("only_nicks: впиши непустой список точных Roblox usernames (3–20 символов)")
        self.only = {norm_nick(n) for n in names}
        values = d.get("whitelist_rap")
        if not isinstance(values, list) or not values:
            raise ConfigError("whitelist_rap: нужен непустой список RAP")
        self.white = {number(v, "whitelist_rap", 1, 10**12, True) for v in values}
        self.min_total = number(d.get("min_total_rap", 35), "min_total_rap", 1, 10**12, True)
        self.max_items = number(d.get("max_items", 6), "max_items", 1, 9, True)
        for attr, key, default in (("strict_page", "single_page_only", True), ("match_total", "check_total_match", True),
                                   ("auto_focus", "auto_focus", True), ("allow_sendinput", "allow_sendinput", False)):
            setattr(self, attr, boolean(d, key, default))
        for attr, key, default, low, high in (
            ("stable", "accept_stable_sec", 4, 1, 120), ("t_items", "wait_items_sec", 180, 5, 3600),
            ("t_window", "wait_window_sec", 15, 1, 120), ("t_close", "wait_close_sec", 30, 3, 300),
            ("poll", "poll_idle_sec", 1, 0.1, 60), ("force", "force_scan_sec", 10, 1, 300),
            ("retry", "retry_backoff_sec", 3, 1, 60),
            ("max_age", "max_observation_age_sec", 5, 0.5, 10)):
            setattr(self, attr, number(d.get(key, default), key, low, high))
        if self.t_items <= self.stable:
            raise ConfigError("wait_items_sec должен превышать accept_stable_sec")
        self.mouse = d.get("mouse_backend", "interception")
        if self.mouse not in {"interception", "sendinput"}:
            raise ConfigError("mouse_backend: interception или sendinput")
        if self.mouse == "sendinput" and not self.allow_sendinput:
            raise ConfigError("Для sendinput явно включи allow_sendinput")
        self.device = d.get("mouse_device")
        if self.device is not None:
            self.device = number(self.device, "mouse_device", 10, 19, True)
        self.thr = d.get("thresholds", {})
        if not isinstance(self.thr, dict):
            raise ConfigError("thresholds должен быть словарём")
        for key, value in self.thr.items():
            number(value, f"thresholds.{key}", 0.6, 1)
        self.tess, self.lang = d.get("tesseract_cmd", ""), d.get("ocr_lang", "eng")
        if not isinstance(self.tess, str) or not isinstance(self.lang, str) or not self.lang:
            raise ConfigError("tesseract_cmd и ocr_lang должны быть строками; ocr_lang непустой")
        folder = d.get("templates_dir", "templates")
        if not isinstance(folder, str) or not folder.strip():
            raise ConfigError("templates_dir: требуется путь")
        self.tpl = (self.path.parent / folder).resolve()
        validate_calibration(d, self.tpl)
        self.reg = d["regions"]
        self.pts = {}

    def T(self, name):
        return self.tpl / f"{name}.png"

    def thr_of(self, name, default=0.85):
        return float(self.thr.get(name, default))

    def check_size(self, frame):
        size = self.d["screen"]
        if (frame.w, frame.h) != (size["w"], size["h"]):
            raise ConfigError(f"Размер игры {frame.w}×{frame.h} изменился. Нужна повторная калибровка; клики запрещены")