"""Trade Plaza receiver. F8/Ctrl+C stops. No website or balance integration."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time

import desktop
import mouse
from configuration import BASE, Cfg, ConfigError
from journal import Journal
from identity import RequestIdentity, read_request
from offer import inspect_offer, same_offer
from vision import Screen, check_ocr, expand, nick_matches, save_image, visuals_equal, wait_until

LOGGER = logging.getLogger("tradebot")
BUTTON_TEMPLATES = {"person", "accept", "decline", "close", "accept_trade", "decline_trade"}
_last_click_diagnostic = -float("inf")


def setup_logging():
    if LOGGER.handlers:
        return
    LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(), RotatingFileHandler(BASE / "bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")):
        handler.setFormatter(formatter)
        LOGGER.addHandler(handler)


def log(*args):
    LOGGER.info(" ".join(map(str, args)))


def capture(screen, cfg):
    desktop.check_stop()
    frame = screen.snapshot()
    cfg.check_size(frame)
    return frame


def locate(frame, cfg, name, region=None):
    key = "row_" + name if name in ("accept", "decline") else name
    roi = region if region is not None else cfg.reg.get(key)
    if roi is None:
        return None
    return frame.find(cfg.T(name), region=expand(roi, 0.12 if name in BUTTON_TEMPLATES else 0.08),
                      thr=cfg.thr_of(name), hover=name in BUTTON_TEMPLATES)


def trade_open(frame, cfg):
    return locate(frame, cfg, "trade_anchor") is not None


def list_open(frame, cfg):
    return not trade_open(frame, cfg) and locate(frame, cfg, "list_anchor") is not None


def outside_trade(frame, cfg):
    return (not trade_open(frame, cfg) and not locate(frame, cfg, "decline_trade")
            and (list_open(frame, cfg) or locate(frame, cfg, "person") is not None))


def guarded_click(screen, cfg, name, hit, condition=None, on_press=None):
    if not hit:
        log(f"Без нажатия: {name}: кнопка не найдена в своей области")
        return False
    rect, hwnd = screen.rect, screen.hwnd
    images = {}

    def require(ok, reason):
        if not ok:
            raise mouse.ClickCancelled(f"{name}: {reason}")

    def before_press():
        frame = capture(screen, cfg)
        images["before"] = frame
        fresh = locate(frame, cfg, name)
        require(fresh is not None, "после наведения не подтверждены форма/цвет кнопки; см. debug/click-before.png")
        require(max(abs(fresh[i]-hit[i]) for i in (0, 1)) <= 4, "кнопка сместилась после наведения")
        require(condition is None or condition(frame), "изменились оба имени/состояние списка/условия предложения")
        require(time.monotonic()-frame.captured_at <= cfg.max_age, "распознавание заняло слишком много времени")
        # OCR can take seconds: compare a NEW frame after OCR, not its stale input.
        latest = capture(screen, cfg)
        images["after"] = latest
        current = locate(latest, cfg, name)
        require(current is not None, "кнопка исчезла/стала неактивной после OCR")
        require(max(abs(current[i]-hit[i]) for i in (0, 1)) <= 4, "кнопка сместилась во время OCR")
        if name in ("accept", "decline"):
            keys = ("row_nick", "row_display")
            require(list_open(latest, cfg), "список больше не открыт")
        elif name == "accept_trade":
            keys = ("partner_name", "our_total", "their_total", "our_grid", "their_grid", "pager")
            require(trade_open(latest, cfg) and not locate(latest, cfg, "success"), "трейд закрыт или видно старое уведомление успеха")
        else:
            keys = ("row_nick", "row_display") if name == "close" else ()
            if name == "person" and (list_open(latest, cfg) or trade_open(latest, cfg)):
                require(False, "список или трейд уже открыт; повторное открытие не нужно")
            if name == "close" and not list_open(latest, cfg):
                require(False, "список уже закрыт")
            if name == "close" and (locate(latest, cfg, "accept") or locate(latest, cfg, "decline")):
                require(False, "появился новый запрос — список оставлен открытым")
            if name == "decline_trade" and not trade_open(latest, cfg):
                require(False, "трейд уже закрыт")
        for key in keys:
            if key in cfg.reg:
                require(visuals_equal(frame.grab(cfg.reg[key]), latest.grab(cfg.reg[key]), changed_fraction=0.002),
                        f"область {key} изменилась во время OCR")
        return True

    try:
        sent = mouse.click(hit[0], hit[1], guard=lambda: desktop.guard_target(hwnd, rect, hit[0], hit[1]),
                           before_press=before_press, on_press=on_press)
        if sent:
            log(f"Клик отправлен: {name} ({hit[0]}, {hit[1]}); ожидаю реакцию интерфейса")
        return sent
    except mouse.ClickCancelled as exc:
        log("Без нажатия:", exc)
        save_click_diagnostic(images, name, str(exc))
        # Focus/geometry loss is a hard stop, not a reason to refocus and retry.
        if not desktop.guard_target(hwnd, rect, hit[0], hit[1]):
            raise
        return False


def save_click_diagnostic(images, name, reason):
    global _last_click_diagnostic
    if not images or time.monotonic()-_last_click_diagnostic < 5:
        return
    _last_click_diagnostic = time.monotonic()
    try:
        for stage, frame in images.items():
            save_image(BASE / "debug" / f"click-{stage}.png", frame.image)
        (BASE / "debug" / "click-reason.json").write_text(
            json.dumps({"button": name, "reason": reason, "stages": list(images)}, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log("Не удалось сохранить диагностику клика:", exc)


def wait_state(screen, cfg, predicate, timeout, samples=1):
    consecutive = 0

    def check():
        nonlocal consecutive
        frame = capture(screen, cfg)
        consecutive = consecutive + 1 if predicate(frame) else 0
        return frame if consecutive >= samples else None

    return wait_until(check, timeout, 0.25, stop=desktop.check_stop)


def open_list(screen, cfg):
    for attempt in range(2):
        frame = capture(screen, cfg)
        if list_open(frame, cfg):
            return True
        if trade_open(frame, cfg):
            return False
        hit = locate(frame, cfg, "person")
        if not hit:
            log("Иконка трейдов не найдена. Проверь python debug_vision.py")
            return False
        if not guarded_click(screen, cfg, "person", hit, lambda f: not list_open(f, cfg) and not trade_open(f, cfg)):
            continue
        if wait_state(screen, cfg, lambda f: list_open(f, cfg), 4, samples=2):
            return True
        log(f"Список не открылся, попытка {attempt+1}/2")
    return False


def close_list(screen, cfg):
    frame = capture(screen, cfg)
    if not list_open(frame, cfg):
        return
    if not guarded_click(screen, cfg, "close", locate(frame, cfg, "close"), lambda f: list_open(f, cfg) and row_empty(f, cfg)):
        log("Список оставлен открытым: появился запрос или изменился интерфейс")
        return
    if not wait_state(screen, cfg, lambda f: not list_open(f, cfg), 4, samples=3):
        raise RuntimeError("Список не закрылся; дальнейшие клики остановлены")


def row_empty(frame, cfg, identity=None):
    identity = identity or read_request(frame, cfg)
    return (not locate(frame, cfg, "accept") and not locate(frame, cfg, "decline")
            and not identity.username and not identity.display_name)


def handle_list(screen, cfg):
    """Always re-read row ONE; drain until proven empty, never close on OCR failure."""
    empty_frames = 0
    last_message = None

    def waiting(message):
        nonlocal last_message
        if message != last_message:
            log(message)
            last_message = message
        desktop.pause(cfg.retry)

    while True:
        frame = capture(screen, cfg)
        if not list_open(frame, cfg):
            return "changed"
        acc = locate(frame, cfg, "accept")
        identity = read_request(frame, cfg)
        if row_empty(frame, cfg, identity):
            empty_frames += 1
            if empty_frames >= 3:
                log("Список запросов пуст; все прочитанные строки обработаны")
                return "empty"
            desktop.pause(0.3)
            continue
        empty_frames = 0
        if not identity.complete:
            waiting("Не прочитаны оба имени первой строки; жду читаемый кадр, список НЕ закрываю")
            continue
        matched = nick_matches(identity.username, cfg.only)
        action = "accept" if matched else "decline"
        hit = acc if matched else locate(frame, cfg, "decline")
        if not hit:
            waiting(f"@{identity.username}: кнопка {action.upper()} временно не найдена; список НЕ закрываю")
            continue

        def same_row(fresh):
            return list_open(fresh, cfg) and read_request(fresh, cfg) == identity

        if not guarded_click(screen, cfg, action, hit, same_row):
            waiting(f"@{identity.username}: нажатия не было; повторю распознавание без закрытия списка")
            continue
        last_message = None
        log(f"Первая строка: @{identity.username} / {identity.display_name!r} → {action.upper()}")
        if matched:
            if not wait_state(screen, cfg, lambda f: trade_open(f, cfg), cfg.t_window, samples=2):
                # Only request ACCEPT may retry, and only if the same request is proven still present.
                if not wait_state(screen, cfg, same_row, 2, samples=3):
                    raise RuntimeError("ACCEPT запроса отправлен, результат неясен; дальнейшие клики остановлены")
                waiting("Тот же запрос остался в списке после ACCEPT; повторю с новой проверкой обоих имён")
                continue
            handle_trade(screen, cfg, identity)
            return "trade"

        def row_changed(fresh):
            if not list_open(fresh, cfg):
                return outside_trade(fresh, cfg) or trade_open(fresh, cfg)
            current = read_request(fresh, cfg)
            return (current.complete and current != identity) or row_empty(fresh, cfg, current)

        changed = wait_state(screen, cfg, row_changed, 4, samples=2)
        if not changed:
            waiting("Первая строка не сменилась после DECLINE; повторно проверю её, список НЕ закрываю")


def decline(screen, cfg, reason):
    log(reason, "— DECLINE")
    for _ in range(2):
        frame = capture(screen, cfg)
        if not trade_open(frame, cfg):
            return bool(wait_state(screen, cfg, lambda f: outside_trade(f, cfg), 3, samples=3))
        if not guarded_click(screen, cfg, "decline_trade", locate(frame, cfg, "decline_trade"), lambda f: trade_open(f, cfg)):
            return False
        if wait_state(screen, cfg, lambda f: outside_trade(f, cfg), 4, samples=3):
            return True
    return False


def evaluate(frame, cfg, expected_nick=None):
    observed = inspect_offer(frame, cfg, expected_nick)
    return observed.status, observed.total, observed.message


def handle_trade(screen, cfg, expected_nick):
    if (not isinstance(expected_nick, RequestIdentity) or not expected_nick.complete
            or not nick_matches(expected_nick.username, cfg.only)):
        raise RuntimeError("Нет подтверждённой связки username и верхнего имени; ACCEPT запрещён")
    journal = Journal(cfg.path)
    journal.ensure_clear()
    deadline = time.monotonic()+cfg.t_items
    previous, stable_since, last_message = None, None, None
    while time.monotonic() < deadline:
        frame = capture(screen, cfg)
        if not trade_open(frame, cfg):
            if wait_state(screen, cfg, lambda f: outside_trade(f, cfg), 1.5, samples=3):
                log("Трейд закрыт до ACCEPT; успех не зафиксирован")
                return
            previous, stable_since = None, None
            continue
        observed = inspect_offer(frame, cfg, expected_nick)
        if observed.message != last_message:
            log(observed.message)
            last_message = observed.message
        if observed.status == "decline":
            if not decline(screen, cfg, observed.message):
                raise RuntimeError("Не удалось отменить небезопасный трейд")
            return
        green = locate(frame, cfg, "accept_trade")
        if observed.status != "ok" or not green or time.monotonic()-frame.captured_at > cfg.max_age:
            previous, stable_since = None, None
        elif not same_offer(previous, observed):
            previous, stable_since = observed, time.monotonic()
        elif time.monotonic()-stable_since >= cfg.stable:
            if locate(frame, cfg, "success"):
                raise RuntimeError("Старое уведомление успеха ещё видно. ACCEPT отменён")

            def final_check(fresh):
                return (trade_open(fresh, cfg) and not locate(fresh, cfg, "success")
                        and same_offer(previous, inspect_offer(fresh, cfg, expected_nick)))

            pressed = guarded_click(screen, cfg, "accept_trade", green, final_check,
                                    on_press=lambda: journal.begin(expected_nick.username, observed.total, expected_nick.display_name))
            if pressed:
                log(f"ACCEPT отправлен один раз; сумма={observed.total}. Жду подтверждение")
                return await_result(screen, cfg, observed.total, journal)
            journal.ensure_clear()  # Ambiguous delivery never retries automatically.
            previous, stable_since = None, None
        desktop.pause(0.3)
    if not decline(screen, cfg, "Истекло время ожидания безопасного стабильного предложения"):
        raise RuntimeError("Не удалось закрыть трейд после таймаута")


def await_result(screen, cfg, total, journal=None):
    deadline = time.monotonic()+cfg.t_close
    closed_frames = success_frames = 0
    success_seen = False
    while time.monotonic() < deadline:
        frame = capture(screen, cfg)
        success_frames = success_frames+1 if locate(frame, cfg, "success") else 0
        success_seen = success_seen or success_frames >= 2
        closed_frames = closed_frames+1 if outside_trade(frame, cfg) else 0
        if closed_frames >= 3 and success_seen:
            if journal:
                journal.complete("ui_success")
            log(f"ПРИНЯТО: подтверждение интерфейса, сумма={total}. На сайте зачислений нет")
            return True
        # Allow delayed success banners; window disappearance alone is not success.
        desktop.pause(0.25)
    raise RuntimeError("После ACCEPT успех НЕ ПОДТВЕРЖДЁН. Остановка без повторного клика; проверь результат вручную")


def focus(cfg):
    desktop.require_windows()
    if not desktop.foreground_is_roblox() and not (cfg.auto_focus and desktop.activate_roblox()):
        raise RuntimeError("Выведи нужное окно Roblox на передний план")


def run(cfg):
    check_ocr(cfg.tess, cfg.lang)
    Journal(cfg.path).ensure_clear()
    focus(cfg)
    with Screen() as screen:
        capture(screen, cfg)
        mouse.configure(cfg.mouse, cfg.allow_sendinput, cfg.device)
        log("Мышь:", mouse.mode(), "| админ:", mouse.is_admin(), "| F8 — стоп | usernames:", sorted(cfg.only))
        last_force, misses, next_scan = -float("inf"), 0, 0
        try:
            while True:
                frame = capture(screen, cfg)
                if trade_open(frame, cfg):
                    if not decline(screen, cfg, "Открытый трейд без подтверждённой строки — сброс"):
                        raise RuntimeError("Не удалось сбросить открытый трейд")
                elif list_open(frame, cfg):
                    result = handle_list(screen, cfg)
                    if result == "empty":
                        close_list(screen, cfg)
                        last_force = time.monotonic()
                    else:
                        last_force = -float("inf")
                elif time.monotonic() >= next_scan and (locate(frame, cfg, "badge") or time.monotonic()-last_force >= cfg.force):
                    last_force = time.monotonic()
                    if open_list(screen, cfg):
                        misses = 0
                        next_scan = 0
                        result = handle_list(screen, cfg)
                        if result == "empty":
                            close_list(screen, cfg)
                            last_force = time.monotonic()
                        else:
                            last_force = -float("inf")
                    else:
                        misses += 1
                        next_scan = time.monotonic()+cfg.force
                        log(f"Список пока не открылся ({misses}); повтор через {cfg.force:g}с с новым снимком")
                desktop.pause(cfg.poll)
        except Exception:
            try:
                if desktop.user32.GetForegroundWindow() == screen.hwnd and desktop.foreground_is_roblox():
                    save_image(BASE / "debug" / "last_error.png", screen.grab())
            except Exception:
                pass
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Приёмщик трейдов. F8 / Ctrl+C — остановка")
    parser.add_argument("--config", type=Path, default=BASE / "config.yaml")
    parser.add_argument("--expected-username", help="Для --dry-run: нижний @username исходного запроса")
    parser.add_argument("--expected-display-name", help="Для --dry-run: верхнее имя исходного запроса")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Проверить настройки/OCR/окно без движения мыши и кликов")
    modes.add_argument("--dry-run", action="store_true", help="Проверить один кадр открытого трейда БЕЗ ввода")
    modes.add_argument("--resolve-pending", action="store_true", help="После ручной проверки результата разрешить следующий запуск (трейд должен быть закрыт)")
    args = parser.parse_args(argv)
    if (bool(args.expected_username) != bool(args.expected_display_name)
            or ((args.expected_username or args.expected_display_name) and not args.dry_run)):
        parser.error("Оба --expected-* задаются вместе и только с --dry-run")
    setup_logging()
    try:
        cfg = Cfg(args.config)
        with desktop.SingleInstance():
            if args.check or args.dry_run or args.resolve_pending:
                focus(cfg)
                with Screen() as screen:
                    frame = capture(screen, cfg)
                    if args.resolve_pending:
                        if not wait_state(screen, cfg, lambda f: outside_trade(f, cfg), 3, samples=3):
                            raise RuntimeError("Сначала вручную закрой трейд. Сброс ожидания запрещён")
                        Journal(cfg.path).complete("manually_reviewed_unknown_result")
                        log("Результат отмечен как проверенный вручную; автоматический успех НЕ записан")
                    elif args.check:
                        log("Настройки и шаблоны: OK | Tesseract:", check_ocr(cfg.tess, cfg.lang))
                        log("Окно:", screen.rect, "| ожидающий ACCEPT:", bool(Journal(cfg.path).read().get("pending")))
                        log("Шаблон успеха:", "есть" if cfg.T("success").is_file() else "нет — после ACCEPT потребуется ручная проверка")
                    else:
                        check_ocr(cfg.tess, cfg.lang)
                        if not trade_open(frame, cfg):
                            raise RuntimeError("Для --dry-run открой окно трейда")
                        identity = RequestIdentity(args.expected_username, args.expected_display_name)
                        result = inspect_offer(frame, cfg, identity)
                        log("БЕЗ КЛИКОВ:", result.status, result.message)
                return 0
            run(cfg)
        return 0
    except KeyboardInterrupt:
        log("Остановлено пользователем. Новые клики не отправляются")
        return 0
    except (ConfigError, RuntimeError, OSError, ValueError) as exc:
        log("СТОП:", exc)
        return 2
    except Exception:
        LOGGER.exception("СТОП: непредвиденная ошибка; дальнейший ввод запрещён")
        return 3
    finally:
        mouse.close()


if __name__ == "__main__":
    raise SystemExit(main())