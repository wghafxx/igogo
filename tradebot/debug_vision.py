"""Read-only diagnostics for a live client or an existing client screenshot."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

import desktop
from bot import capture, focus, list_open, locate, trade_open
from configuration import BASE, Cfg, REQUIRED_TEMPLATES
from offer import inspect_offer
from identity import RequestIdentity
from vision import Frame, Screen, check_ocr, ocr_display_name, ocr_nick, ocr_number, save_image


def diagnose(frame, cfg, output, expected_nick=None, expected_display_name=None):
    cfg.check_size(frame)
    output.mkdir(parents=True, exist_ok=True)
    overlay = frame.image.copy()
    report = {"screen": {"w": frame.w, "h": frame.h}, "templates": {}, "regions": {}, "ocr": {}}
    for name in (*REQUIRED_TEMPLATES, "badge", "success"):
        hit = locate(frame, cfg, name)
        report["templates"][name] = {"found": hit is not None, "hit": hit, "threshold": cfg.thr_of(name)}
    for key, region in cfg.reg.items():
        save_image(output / f"{key}.png", frame.grab(region))
        x1, y1, x2, y2 = frame.bounds(region)
        cv2.rectangle(overlay, (x1, y1), (x2-1, y2-1), (50, 220, 80), 1)
        cv2.putText(overlay, key, (x1, max(12, y1-3)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 220, 80), 1)
        report["regions"][key] = [x1, y1, x2, y2]
    check_ocr(cfg.tess, cfg.lang)
    report["state"] = "trade" if trade_open(frame, cfg) else "list" if list_open(frame, cfg) else "other"
    report["ocr"]["row_nick"] = ocr_nick(frame.grab(cfg.reg["row_nick"]), cfg.tess, cfg.lang)
    for key in ("row_display", "partner_name"):
        report["ocr"][key] = ocr_display_name(frame.grab(cfg.reg[key]), cfg.tess, cfg.lang)
    for key in ("our_total", "their_total"):
        report["ocr"][key] = ocr_number(frame.grab(cfg.reg[key]), cfg.tess)
    if trade_open(frame, cfg):
        partner = report["ocr"]["partner_name"]
        result = inspect_offer(frame, cfg, RequestIdentity(expected_nick, expected_display_name))
        report["offer"] = {"partner": partner, "status": result.status, "total": result.total, "message": result.message}
    save_image(output / "annotated.png", overlay)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Сохранено: {output}. Ввода не было. Снимки могут содержать usernames — не публикуй без необходимости")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Распознавание БЕЗ кликов; снимок, области и JSON-отчёт")
    parser.add_argument("--config", type=Path, default=BASE / "config.yaml")
    parser.add_argument("--image", type=Path, help="Офлайн-снимок только игровой области (не весь монитор)")
    parser.add_argument("--output", type=Path, default=BASE / "debug")
    parser.add_argument("--expected-nick", "--expected-username", dest="expected_nick", help="Нижний @username исходного запроса")
    parser.add_argument("--expected-display-name", help="Верхнее имя того же исходного запроса")
    args = parser.parse_args(argv)
    try:
        cfg = Cfg(args.config)
        if args.image:
            image = cv2.imdecode(np.fromfile(args.image, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Изображение не читается")
            diagnose(Frame(image), cfg, args.output, args.expected_nick, args.expected_display_name)
        else:
            with desktop.SingleInstance():
                focus(cfg)
                with Screen() as screen:
                    diagnose(capture(screen, cfg), cfg, args.output, args.expected_nick, args.expected_display_name)
        return 0
    except KeyboardInterrupt:
        return 1
    except Exception as exc:
        print("Диагностика не выполнена:", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())