"""Explicit input backend; guards before movement/down, unconditional release."""
import ctypes
from ctypes import wintypes as wt
import desktop

_ic = None
_mode = None
_pressed = False
HOVER_DELAY, HOLD_DELAY = 0.18, 0.12


class ClickCancelled(RuntimeError):
    pass


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16), ("wParamH", ctypes.c_uint16)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", ctypes.c_uint32), ("data", INPUTUNION)]


def cursor_pos():
    desktop.require_windows()
    point = wt.POINT()
    if not desktop.user32.GetCursorPos(ctypes.byref(point)):
        raise RuntimeError("Не читается положение курсора")
    return point.x, point.y


def screen_size():
    desktop.require_windows()
    return desktop.user32.GetSystemMetrics(0), desktop.user32.GetSystemMetrics(1)


def is_admin():
    return bool(ctypes.windll.shell32.IsUserAnAdmin()) if desktop.user32 is not None else False


def configure(backend="interception", allow_sendinput=False, device=None):
    global _ic, _mode
    desktop.require_windows()
    close()
    _ic, _mode = None, None
    if backend == "sendinput":
        if not allow_sendinput:
            raise RuntimeError("SendInput требует allow_sendinput: true")
        _mode = "sendinput"
    elif backend == "interception":
        try:
            import interception
            if device is None:
                interception.auto_capture_devices(keyboard=False, mouse=True)
            else:
                interception.set_devices(mouse=device)
            interception.get_mouse()
            _ic, _mode = interception, "interception"
        except Exception as exc:
            raise RuntimeError(f"Interception недоступен: {exc}. Проверь драйвер; автоматической смены способа ввода нет") from exc
    else:
        raise ValueError("mouse_backend: interception или sendinput")


def _send(flags, dx=0, dy=0):
    event = INPUT(type=0, data=INPUTUNION(mi=MOUSEINPUT(dx, dy, 0, flags, 0, 0)))
    fn = desktop.user32.SendInput
    fn.argtypes, fn.restype = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int], wt.UINT
    if fn(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise RuntimeError("Windows заблокировала SendInput. Проверь одинаковые права игры и Python")


def _move(x, y):
    if _mode == "interception":
        # Library absolute movement only supports the primary monitor.
        width, height = screen_size()
        if not (0 <= x < width and 0 <= y < height):
            raise RuntimeError("Для Interception помести игру и курсор на основной монитор")
        _ic.move_to(x, y, allow_global_params=False)
    elif _mode == "sendinput":
        left, top, width, height = [desktop.user32.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
        if not (left <= x < left + width and top <= y < top + height):
            raise RuntimeError("Точка вне рабочего стола")
        _send(0x0001 | 0x8000 | 0x4000, round((x-left)*65535/(width-1)), round((y-top)*65535/(height-1)))
    else:
        raise RuntimeError("Мышь не настроена: сначала configure()")


def _guard(guard):
    desktop.check_stop()
    if guard is None or not guard():
        raise ClickCancelled("Цель клика изменилась/перекрыта или потерян фокус. Ввод отменён")


def move(x, y, duration=0.25, guard=None):
    _guard(guard)
    px, py = cursor_pos()
    steps = max(1, round(duration / 0.025))
    for i in range(1, steps + 1):
        _guard(guard)
        t = i / steps
        t = t * t * (3 - 2 * t)
        _move(round(px + (x-px)*t), round(py + (y-py)*t))
        desktop.pause(duration / steps)
    if max(abs(a-b) for a, b in zip(cursor_pos(), (x, y))) > 2:
        raise ClickCancelled("Курсор не достиг кнопки — проверь устройство мыши. Нажатие отменено")


def _button(down):
    if _mode == "interception":
        (_ic.mouse_down if down else _ic.mouse_up)("left", delay=0.001)
    elif _mode == "sendinput":
        _send(0x0002 if down else 0x0004)
    else:
        raise RuntimeError("Мышь не настроена")


def click(x, y, pre_delay=0.1, post_delay=0.15, *, guard=None, before_press=None, on_press=None):
    global _pressed
    _guard(guard)
    desktop.pause(pre_delay)
    move(x, y, guard=guard)
    desktop.pause(HOVER_DELAY)
    _guard(guard)
    if before_press is None or not before_press():
        raise ClickCancelled("Повторная проверка интерфейса не пройдена; нажатия не было")
    _guard(guard)
    if max(abs(a-b) for a, b in zip(cursor_pos(), (x, y))) > 2:
        raise ClickCancelled("Курсор смещён пользователем; нажатия не было")
    if on_press:
        on_press()  # Durable ACCEPT intent BEFORE possibly sending input.
    _guard(guard)
    try:
        _pressed = True  # Release even if a backend throws after partial delivery.
        _button(True)
        desktop.pause(HOLD_DELAY)
    finally:
        close()
    desktop.pause(post_delay)
    return True


def close():
    global _pressed
    if _pressed:
        _button(False)
        _pressed = False


def mode():
    return _mode or "не настроена (ввод не выполнялся)"


def using_interception():
    return _mode == "interception"