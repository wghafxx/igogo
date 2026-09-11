"""Windows client coordinates and interruptible safety checks. No input at import."""
import ctypes
from ctypes import wintypes as wt
from dataclasses import dataclass
from pathlib import PureWindowsPath
import sys
import time

user32 = kernel32 = None
if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    for name, args, result in (
        ("GetForegroundWindow", [], wt.HWND),
        ("IsWindow", [wt.HWND], wt.BOOL),
        ("IsWindowVisible", [wt.HWND], wt.BOOL),
        ("IsIconic", [wt.HWND], wt.BOOL),
        ("GetWindowTextW", [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int),
        ("GetWindowThreadProcessId", [wt.HWND, ctypes.POINTER(wt.DWORD)], wt.DWORD),
        ("GetClientRect", [wt.HWND, ctypes.POINTER(wt.RECT)], wt.BOOL),
        ("ClientToScreen", [wt.HWND, ctypes.POINTER(wt.POINT)], wt.BOOL),
        ("EnumWindows", [ENUMPROC, wt.LPARAM], wt.BOOL),
        ("SetForegroundWindow", [wt.HWND], wt.BOOL),
        ("ShowWindow", [wt.HWND, ctypes.c_int], wt.BOOL),
        ("GetAsyncKeyState", [ctypes.c_int], ctypes.c_short),
        ("WindowFromPoint", [wt.POINT], wt.HWND),
        ("GetAncestor", [wt.HWND, wt.UINT], wt.HWND),
        ("GetCursorPos", [ctypes.POINTER(wt.POINT)], wt.BOOL),
        ("GetSystemMetrics", [ctypes.c_int], ctypes.c_int),
    ):
        fn = getattr(user32, name)
        fn.argtypes, fn.restype = args, result
    for name, args, result in (
        ("OpenProcess", [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
        ("QueryFullProcessImageNameW", [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)], wt.BOOL),
        ("CloseHandle", [wt.HANDLE], wt.BOOL),
        ("CreateMutexW", [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR], wt.HANDLE),
    ):
        fn = getattr(kernel32, name)
        fn.argtypes, fn.restype = args, result
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def require_windows():
    if user32 is None:
        raise RuntimeError("Захват Roblox и ввод мыши требуют Windows 10/11. Здесь доступны только офлайн-тесты")


def check_stop():
    if user32 is not None and user32.GetAsyncKeyState(0x77) & 0x8001:
        raise KeyboardInterrupt("F8")


def pause(seconds):
    deadline = time.monotonic() + seconds
    while True:
        check_stop()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.025, remaining))


def process_id(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def is_roblox(hwnd):
    if user32 is None or not hwnd or not user32.IsWindow(hwnd):
        return False
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, len(title))
    if title.value.strip().lower() != "roblox":
        return False
    handle = kernel32.OpenProcess(0x1000, False, process_id(hwnd))
    if not handle:
        return False
    try:
        size = wt.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            return False
        return PureWindowsPath(image.value).name.lower() in {
            "robloxplayerbeta.exe", "robloxplayer.exe", "windows10universal.exe"}
    finally:
        kernel32.CloseHandle(handle)


def foreground_is_roblox():
    return user32 is not None and is_roblox(user32.GetForegroundWindow())


def roblox_window():
    require_windows()
    foreground = user32.GetForegroundWindow()
    if is_roblox(foreground):
        return foreground
    found = []

    @ENUMPROC
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and is_roblox(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(visit, 0)
    if len(found) > 1:
        raise RuntimeError("Открыто несколько Roblox. Выведи нужный аккаунт на передний план")
    return found[0] if found else None


def activate_roblox(hwnd=None):
    require_windows()
    hwnd = hwnd or roblox_window()
    if not hwnd or not is_roblox(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    if user32.GetForegroundWindow() != hwnd:
        user32.SetForegroundWindow(hwnd)
        pause(0.3)
    return user32.GetForegroundWindow() == hwnd and is_roblox(hwnd)


@dataclass(frozen=True)
class ClientRect:
    left: int
    top: int
    width: int
    height: int

    def contains(self, x, y):
        return self.left <= x < self.left + self.width and self.top <= y < self.top + self.height


def client_rect(hwnd):
    require_windows()
    if not is_roblox(hwnd) or user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
        raise RuntimeError("Выбранное окно Roblox закрыто/свёрнуто")
    rect, origin = wt.RECT(), wt.POINT(0, 0)
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)) or not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise RuntimeError("Не удалось получить игровую область")
    if rect.right < 100 or rect.bottom < 100:
        raise RuntimeError("Игровая область слишком мала")
    return ClientRect(origin.x, origin.y, rect.right, rect.bottom)


def guard_target(hwnd, rect, x, y):
    check_stop()
    if user32.GetForegroundWindow() != hwnd or client_rect(hwnd) != rect or not rect.contains(x, y):
        return False
    target = user32.WindowFromPoint(wt.POINT(int(x), int(y)))
    return user32.GetAncestor(target, 2) == hwnd


class SingleInstance:
    """Prevent concurrent bots/calibrators controlling the same desktop."""
    def __enter__(self):
        require_windows()
        ctypes.set_last_error(0)
        self.handle = kernel32.CreateMutexW(None, False, "Local\\TradePlazaReceiver")
        if not self.handle:
            raise RuntimeError("Не удалось создать блокировку запуска")
        if ctypes.get_last_error() == 183:
            kernel32.CloseHandle(self.handle)
            raise RuntimeError("Другой бот или калибровщик уже запущен")
        return self

    def __exit__(self, *_):
        kernel32.CloseHandle(self.handle)