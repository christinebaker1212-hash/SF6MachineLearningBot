"""Thin ctypes layer over the Win32 calls we need. Importable on any OS;
functions raise ``RuntimeError`` when called off Windows.

Verified only as Win32 API usage (documented Microsoft APIs). Behaviour with
SF6 specifically must be validated with ``sf6bot input-test`` in the game.
"""
from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"

# Tag placed in dwExtraInfo of every injected key event, so a future low-level
# keyboard hook (demonstration recorder) can tell bot inputs from human inputs.
INJECT_TAG = 0x5F6B07

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise RuntimeError("This operation requires Windows (the SF6 game PC).")


def set_dpi_aware() -> None:
    """Use physical pixel coordinates. Must run before any window/capture call."""
    if not IS_WINDOWS:
        return
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def send_key_events(events: list[tuple[int, bool, bool]]) -> None:
    """Inject key events atomically in one SendInput call.

    events: list of (scancode, extended, is_down).
    """
    _require_windows()
    if not events:
        return
    arr = (INPUT * len(events))()
    for i, (scan, extended, down) in enumerate(events):
        flags = KEYEVENTF_SCANCODE
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        if not down:
            flags |= KEYEVENTF_KEYUP
        arr[i].type = INPUT_KEYBOARD
        arr[i].u.ki = KEYBDINPUT(0, scan, flags, 0, INJECT_TAG)
    sent = user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
    if sent != len(events):
        err = ctypes.get_last_error()
        raise OSError(f"SendInput injected {sent}/{len(events)} events (GetLastError={err}). "
                      "If SF6 runs as administrator, run this tool as administrator too (UIPI).")


def is_vk_down(vk: int) -> bool:
    _require_windows()
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def foreground_window() -> int:
    _require_windows()
    return int(user32.GetForegroundWindow() or 0)


def is_window(hwnd: int) -> bool:
    _require_windows()
    return bool(user32.IsWindow(hwnd))


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    exe: str
    client_rect: tuple[int, int, int, int]  # screen coords (left, top, right, bottom)
    monitor_rect: tuple[int, int, int, int]


def process_image_path(pid: int) -> str:
    """Full path of a process's executable ("" if not accessible)."""
    _require_windows()
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def _process_exe(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(h)


def window_info(hwnd: int) -> WindowInfo:
    _require_windows()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return WindowInfo(hwnd=int(hwnd), title=buf.value, pid=pid.value, exe=_process_exe(pid.value),
                      client_rect=client_rect_screen(hwnd), monitor_rect=monitor_rect(hwnd))


def client_rect_screen(hwnd: int) -> tuple[int, int, int, int]:
    _require_windows()
    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return (pt.x, pt.y, pt.x + rc.right - rc.left, pt.y + rc.bottom - rc.top)


def monitor_rect(hwnd: int) -> tuple[int, int, int, int]:
    _require_windows()
    MONITOR_DEFAULTTONEAREST = 2
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    r = mi.rcMonitor
    return (r.left, r.top, r.right, r.bottom)


def list_windows() -> list[WindowInfo]:
    _require_windows()
    out: list[WindowInfo] = []

    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            try:
                out.append(window_info(hwnd))
            except Exception:
                pass
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def find_game_window(exe_name: str, title_contains: str) -> WindowInfo | None:
    exe_l, title_l = exe_name.lower(), title_contains.lower()
    for w in list_windows():
        if exe_l and w.exe.lower() == exe_l:
            return w
    for w in list_windows():
        if title_l and title_l in w.title.lower():
            return w
    return None


def make_window_noactivate_topmost(title: str) -> bool:
    """Stop our debug overlay window from stealing focus from the game."""
    if not IS_WINDOWS:
        return False
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    GWL_EXSTYLE = -20
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOPMOST = 0x00000008
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
    HWND_TOPMOST = -1
    SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE = 0x2, 0x1, 0x10
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    # Hide the overlay from screen capture (Windows 10 2004+): it stays visible on the monitor
    # but should not appear in Desktop Duplication frames. Confirm with capture-bench snapshot.png.
    WDA_EXCLUDEFROMCAPTURE = 0x11
    make_window_noactivate_topmost.excluded_from_capture = bool(
        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
    return True


def install_console_ctrl_handler(callback) -> None:
    """Call ``callback()`` on Ctrl+C / Ctrl+Break / console close / logoff / shutdown."""
    if not IS_WINDOWS:
        return
    HANDLER = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def handler(_ctrl_type):
        try:
            callback()
        except Exception:
            pass
        return False  # let default handling continue (KeyboardInterrupt / exit)

    install_console_ctrl_handler._ref = HANDLER(handler)  # keep alive
    kernel32.SetConsoleCtrlHandler(install_console_ctrl_handler._ref, True)


# ---- XInput (controller) kill switch -----------------------------------------
XINPUT_BUTTONS = {"DPAD_UP": 0x0001, "DPAD_DOWN": 0x0002, "DPAD_LEFT": 0x0004, "DPAD_RIGHT": 0x0008,
                  "START": 0x0010, "BACK": 0x0020, "LS": 0x0040, "RS": 0x0080, "LB": 0x0100, "RB": 0x0200,
                  "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000}


class XInputCombo:
    """True while every button in ``combo`` is held on any connected XInput pad.

    Only reads controller state; never sends anything. Disconnected slots are
    rescanned every ``rescan_s`` because polling empty slots is slow."""

    def __init__(self, combo: list[str], rescan_s: float = 2.0) -> None:
        self.mask = 0
        for b in combo:
            self.mask |= XINPUT_BUTTONS[b.upper()]
        self.available = False
        self._connected: list[int] = []
        self._last_scan = -1e9
        self.rescan_s = rescan_s
        if not IS_WINDOWS or not self.mask:
            return
        from ctypes import wintypes as wt

        class XINPUT_GAMEPAD(ctypes.Structure):
            _fields_ = [("wButtons", wt.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                        ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                        ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]

        class XINPUT_STATE(ctypes.Structure):
            _fields_ = [("dwPacketNumber", wt.DWORD), ("Gamepad", XINPUT_GAMEPAD)]

        for dll in ("xinput1_4", "xinput9_1_0"):
            try:
                self._dll = ctypes.WinDLL(dll)
                break
            except OSError:
                self._dll = None
        if self._dll is None:
            return
        self._dll.XInputGetState.argtypes = [wt.DWORD, ctypes.POINTER(XINPUT_STATE)]
        self._dll.XInputGetState.restype = wt.DWORD
        self._state = XINPUT_STATE()
        self.available = True

    def _get(self, i: int) -> int | None:
        if self._dll.XInputGetState(i, ctypes.byref(self._state)) != 0:
            return None
        return self._state.Gamepad.wButtons

    def connected(self) -> list[int]:
        import time
        if time.perf_counter() - self._last_scan > self.rescan_s:
            self._connected = [i for i in range(4) if self._get(i) is not None]
            self._last_scan = time.perf_counter()
        return self._connected

    def pressed(self) -> bool:
        if not self.available:
            return False
        for i in self.connected():
            b = self._get(i)
            if b is not None and (b & self.mask) == self.mask:
                return True
        return False
