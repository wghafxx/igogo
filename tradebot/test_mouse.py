"""Manual mouse diagnostics; never sends input by default or on import."""
import argparse
from pathlib import Path

import desktop
import mouse
from bot import capture, focus, guarded_click, list_open, locate, trade_open
from configuration import BASE, Cfg
from vision import Screen


def main(argv=None):
    parser = argparse.ArgumentParser(description="Диагностика мыши; по умолчанию БЕЗ ввода")
    parser.add_argument("--config", type=Path, default=BASE / "config.yaml")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--move-only", action="store_true", help="Только навести курсор на найденную иконку списка")
    modes.add_argument("--click", action="store_true", help="Один проверенный клик по иконке списка")
    args = parser.parse_args(argv)
    try:
        cfg = Cfg(args.config)
        with desktop.SingleInstance():
            focus(cfg)
            with Screen() as screen:
                frame = capture(screen, cfg)
                print("Окно:", screen.rect, "| админ:", mouse.is_admin(), "| настройка:", cfg.mouse)
                if not args.move_only and not args.click:
                    print("Ввод не выполнялся. Для наведения: --move-only; для одного клика: --click. F8 — стоп")
                    return 0
                if list_open(frame, cfg) or trade_open(frame, cfg):
                    raise RuntimeError("Перед тестом вручную закрой список и окно трейда")
                hit = locate(frame, cfg, "person")
                if not hit:
                    raise RuntimeError("Иконка не найдена; сначала python debug_vision.py")
                mouse.configure(cfg.mouse, cfg.allow_sendinput, cfg.device)
                rect = screen.rect
                print("Режим:", mouse.mode(), "| цель:", hit[:2], "| F8 — стоп")
                if args.move_only:
                    mouse.move(hit[0], hit[1], guard=lambda: desktop.guard_target(screen.hwnd, rect, hit[0], hit[1]))
                elif not guarded_click(screen, cfg, "person", hit, lambda f: not list_open(f, cfg) and not trade_open(f, cfg)):
                    raise RuntimeError("Интерфейс изменился; клик отменён")
                print("Курсор:", mouse.cursor_pos(), "| Команда выполнена; проверь реакцию игры")
        return 0
    except KeyboardInterrupt:
        print("Остановлено; новых кликов нет")
        return 0
    except Exception as exc:
        print("Диагностика остановлена:", exc)
        return 2
    finally:
        mouse.close()


if __name__ == "__main__":
    raise SystemExit(main())