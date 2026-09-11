"""Transactional client-window calibration; cancellation never retains stale regions."""
import argparse
import os
from pathlib import Path
import shutil
import uuid

import cv2
import yaml

import desktop
from configuration import BASE, validate_calibration
from vision import Screen, save_image


class CalibrationCancelled(Exception):
    pass


def snap(screen, prompt):
    print(f"\n>>> {prompt}")
    input("Подготовь игру и нажми Enter здесь. Снимок игры сделается автоматически... ")
    if not desktop.activate_roblox(screen.hwnd):
        raise RuntimeError("Не удалось активировать выбранное окно Roblox. Не переключай аккаунты")
    desktop.pause(0.6)
    frame = screen.snapshot()
    print(f"Игровая область: {frame.w}×{frame.h}, начало ({frame.left}, {frame.top})")
    return frame


def ask_roi(image, key, hint, required=True):
    print(f"\n[{key}] {hint}\nОбведи область, Enter — принять. Esc — {'ОТМЕНИТЬ калибровку' if required else 'пропустить'}.")
    height, width = image.shape[:2]
    scale = min(1.0, 1280/width, 720/height)
    preview = cv2.resize(image, (round(width*scale), round(height*scale)))
    sx, sy = preview.shape[1]/width, preview.shape[0]/height
    while True:
        desktop.check_stop()
        x, y, rw, rh = cv2.selectROI(key, preview, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(key)
        if rw == 0 or rh == 0:
            if required:
                raise CalibrationCancelled(f"Не выбрана обязательная область {key}")
            return None
        x1, y1 = max(0, round(x/sx)), max(0, round(y/sy))
        x2, y2 = min(width, round((x+rw)/sx)), min(height, round((y+rh)/sy))
        if min(x2-x1, y2-y1) >= 5:
            return x1, y1, x2-x1, y2-y1
        print("Область слишком мала — выдели её заново")


def frac(rect, width, height):
    x, y, w, h = rect
    return [x/width, y/height, min(1, (x+w)/width), min(1, (y+h)/height)]


def select(frame, cfg, folder, key, hint, template=False, required=True):
    while True:
        rect = ask_roi(frame.image, key, hint, required)
        if rect is None:
            return
        x, y, width, height = rect
        crop = frame.image[y:y+height, x:x+width]
        if template and max(crop.std(axis=(0, 1))) < 3:
            print("Однотонная область не подходит. Захвати текст, контур или значок кнопки")
            continue
        region_key = "row_" + key if key in ("accept", "decline") else key
        cfg["regions"][region_key] = frac(rect, frame.w, frame.h)
        if template:
            save_image(folder / f"{key}.png", crop)
        return


def atomic_config(path, cfg):
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    backup_tmp = temporary.with_suffix(".bak.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(cfg, stream, allow_unicode=True, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            shutil.copy2(path, backup_tmp)
            os.replace(backup_tmp, path.with_suffix(path.suffix + ".bak"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
        backup_tmp.unlink(missing_ok=True)


def calibrate(path):
    desktop.require_windows()
    path = Path(path).resolve()
    source = path if path.exists() else BASE / "config.example.yaml"
    cfg = yaml.safe_load(source.read_text(encoding="utf-8-sig"))
    if not isinstance(cfg, dict):
        raise ValueError("Настройки должны быть словарём YAML")
    cfg["regions"], cfg["points"] = {}, {}
    configured = Path(cfg.get("templates_dir", "templates"))
    root = configured.parent if configured.name.startswith("calibration-") else configured
    folder = path.parent / root / f"calibration-{uuid.uuid4().hex[:12]}"
    folder.mkdir(parents=True, exist_ok=False)
    saved = False
    try:
        if not desktop.activate_roblox():
            raise RuntimeError("Окно Roblox не найдено/не активируется")
        with Screen() as screen:
            main_frame = snap(screen, "ШАГ 1/4: Trade Plaza без меню и трейдов")
            size = (main_frame.w, main_frame.h)
            cfg["screen"] = {"w": size[0], "h": size[1], "coordinate_space": "client"}
            select(main_frame, cfg, folder, "person", "Иконка открытия списка трейдов", template=True)
            select(main_frame, cfg, folder, "badge", "Бейдж уведомления (необязательно)", template=True, required=False)

            def shot(prompt):
                frame = snap(screen, prompt)
                if (frame.w, frame.h) != size:
                    raise RuntimeError("Размер игры изменился между шагами — начни заново")
                return frame

            listing = shot("ШАГ 2/4: СПИСОК ТРЕЙДОВ с входящим запросом")
            for key, hint in (("accept", "ЗЕЛЁНАЯ ACCEPT первой строки, вместе с текстом"),
                              ("decline", "КРАСНАЯ DECLINE первой строки, вместе с текстом"),
                              ("close", "Кнопка закрытия именно СПИСКА трейдов")):
                select(listing, cfg, folder, key, hint, template=True)
            select(listing, cfg, folder, "list_anchor", "Постоянный заголовок: Select Player To Accept Or Decline Trades (без кнопок и имён)", template=True)
            select(listing, cfg, folder, "row_nick", "Точный @username первой строки. НЕ Display Name; без других подписей")
            select(listing, cfg, folder, "row_display", "ВЕРХНЕЕ имя первой строки, над @username; только имя")
            trade = shot("ШАГ 3/4: ОКНО ТРЕЙДА, зелёная активная ACCEPT, наша сетка пустая")
            for key, hint in (("accept_trade", "ЗЕЛЁНАЯ активная ACCEPT в ТРЕЙДЕ, включая текст"),
                              ("decline_trade", "КРАСНАЯ DECLINE в ТРЕЙДЕ, включая текст"),
                              ("trade_anchor", "Постоянный ЗАГОЛОВОК/ЗНАЧОК трейда, не ник/сумма/кнопка"),
                              ("plus", "ПЛЮС в центре пустого слота")):
                select(trade, cfg, folder, key, hint, template=True)
            for key, hint in (("their_total", "Их Total RAP: только число целиком, без подписи"),
                              ("our_total", "Наш Total RAP: только число целиком, без подписи"),
                              ("partner_name", "Имя партнёра внутри ТРЕЙДА — здесь показывается верхнее имя, не @username"),
                              ("their_grid", "Вся ИХ сетка 3×3 по внешним границам слотов"),
                              ("our_grid", "Вся НАША сетка 3×3 по внешним границам слотов")):
                select(trade, cfg, folder, key, hint)
            select(trade, cfg, folder, "pager", "Пагинация ИХ сетки: вся надпись 1/1", required=cfg.get("single_page_only", True))
            print("\nШАГ 4/4: уведомление УСПЕШНОГО обмена. Без него бот остановится после ACCEPT без подтверждения успеха.")
            if input("Можешь показать уведомление успеха? [y/N]: ").strip().lower() in {"y", "yes", "да", "д"}:
                success = shot("Покажи уникальное уведомление УСПЕХА обмена — не отмену")
                select(success, cfg, folder, "success", "Уникальный текст/значок УСПЕШНОГО обмена", template=True)
        cfg["calibration_version"] = 3
        cfg["templates_dir"] = str(folder.relative_to(path.parent)) if folder.is_relative_to(path.parent) else str(folder)
        validate_calibration(cfg, folder)
        atomic_config(path, cfg)
        saved = True
        print(f"\nКалибровка сохранена: {path}. Предыдущая конфигурация: {path.name}.bak")
        print("Впиши реальные usernames в only_nicks, затем: python bot.py --check")
    finally:
        if not saved:
            shutil.rmtree(folder, ignore_errors=True)
        cv2.destroyAllWindows()


def calibrate_names(path):
    """Migrate v2/v3 names only, preserving other regions and immutable originals."""
    desktop.require_windows()
    path = Path(path).resolve()
    cfg = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if (not isinstance(cfg, dict) or cfg.get("calibration_version") not in (2, 3)
            or cfg.get("screen", {}).get("coordinate_space") != "client"):
        raise ValueError("Нет существующей клиентской калибровки. Выполни python calibrate.py без --names-only")
    source = (path.parent / cfg["templates_dir"]).resolve()
    if not source.is_dir():
        raise ValueError("Старые шаблоны не найдены; нужна полная калибровка")
    folder = path.parent / "templates" / f"calibration-{uuid.uuid4().hex[:12]}"
    folder.mkdir(parents=True, exist_ok=False)
    saved = False
    try:
        for template in source.glob("*.png"):
            shutil.copy2(template, folder / template.name)
        for key in ("list_anchor", "row_nick", "row_display", "partner_name"):
            cfg["regions"].pop(key, None)
        if not desktop.activate_roblox():
            raise RuntimeError("Не удалось активировать Roblox")
        with Screen() as screen:
            def shot(prompt):
                frame = snap(screen, prompt)
                if (frame.w, frame.h) != (cfg["screen"]["w"], cfg["screen"]["h"]):
                    raise ValueError("Размер игры изменился; нужна полная калибровка")
                return frame

            listing = shot("ОБНОВЛЕНИЕ 1/2: открой список с входящим запросом")
            select(listing, cfg, folder, "list_anchor", "Заголовок Select Player To Accept Or Decline Trades, не CLOSE и не имя", template=True)
            select(listing, cfg, folder, "row_display", "ВЕРХНЕЕ имя первой строки, над строкой с @")
            select(listing, cfg, folder, "row_nick", "НИЖНИЙ @username той же первой строки, без RAP")
            trade = shot("ОБНОВЛЕНИЕ 2/2: открой окно обмена с партнёром")
            select(trade, cfg, folder, "partner_name", "Имя ПАРТНЁРА внутри трейда — верхнее имя, не ваше имя")
        cfg["calibration_version"] = 3
        cfg["templates_dir"] = str(folder.relative_to(path.parent))
        validate_calibration(cfg, folder)
        atomic_config(path, cfg)
        saved = True
        print("Области имён и заголовка обновлены. Кнопки/сетки/правила сохранены. Далее: python bot.py --check")
    finally:
        if not saved:
            shutil.rmtree(folder, ignore_errors=True)
        cv2.destroyAllWindows()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Калибровка игровой области Roblox")
    parser.add_argument("--config", type=Path, default=BASE / "config.yaml")
    parser.add_argument("--names-only", action="store_true", help="Обновить только оба имени, имя в трейде и заголовок списка; сохранить остальные области")
    args = parser.parse_args(argv)
    try:
        with desktop.SingleInstance():
            (calibrate_names if args.names_only else calibrate)(args.config.resolve())
        return 0
    except (CalibrationCancelled, KeyboardInterrupt):
        print("Калибровка отменена. Прежние настройки и шаблоны сохранены")
        return 1
    except Exception as exc:
        print(f"Калибровка не сохранена: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())