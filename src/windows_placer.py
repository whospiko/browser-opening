from __future__ import annotations

import sys
import time
from typing import Any

from app_log import get_logger
from monitors import Monitor

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes as wintypes

    user32 = ctypes.windll.user32

    # DPI awareness
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass

    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL

    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND

    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int

    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL

    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL

    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL

    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    LONG_PTR = ctypes.c_ssize_t
    if hasattr(user32, "GetWindowLongPtrW"):
        _get_window_long = user32.GetWindowLongPtrW
        _set_window_long = user32.SetWindowLongPtrW
    else:
        _get_window_long = user32.GetWindowLongW
        _set_window_long = user32.SetWindowLongW

    _get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_window_long.restype = LONG_PTR
    _set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
    _set_window_long.restype = LONG_PTR

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        # Per-Monitor DPI Aware V2 (Windows 10 1703+)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            # Per-Monitor DPI Aware (Windows 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                # System DPI Aware (Windows Vista+)
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def get_browser_window_handles() -> set[int]:
    """Return HWNDs of all currently visible top-level Chromium browser windows."""
    if sys.platform != "win32":
        return set()
    hwnds: set[int] = set()
    buf = ctypes.create_unicode_buffer(256)
    rect = wintypes.RECT()

    def _callback(hwnd: int, _lparam: Any) -> bool:
        if user32.IsWindowVisible(hwnd) and not user32.GetParent(hwnd):
            user32.GetClassNameW(hwnd, buf, 256)
            # Chrome, Edge, and Brave all use the class Chrome_WidgetWin_1 for top-level windows
            if buf.value == "Chrome_WidgetWin_1":
                # Ensure it has a meaningful size (ignore 0x0 or 1x1 utility surfaces)
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 100 and h > 100:
                        hwnds.add(hwnd)
        return True

    cb = WNDENUMPROC(_callback)
    user32.EnumWindows(cb, 0)
    return hwnds


def wait_for_new_window(
    before_hwnds: set[int],
    *,
    pid: int | None = None,
    timeout: float = 12.0,
) -> int | None:
    """Wait for a newly appeared browser window HWND that was not in before_hwnds."""
    if sys.platform != "win32":
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = get_browser_window_handles()
        diff = current - before_hwnds
        if diff:
            if pid is not None:
                lp_pid = wintypes.DWORD()
                for hwnd in diff:
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
                    if lp_pid.value == pid:
                        return hwnd
            # Return any new valid window handle
            return next(iter(diff))
        time.sleep(0.15)
    return None


GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

SW_RESTORE = 9
SW_MAXIMIZE = 3
HWND_TOP = 0
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040


def place_window(hwnd: int, monitor: Monitor, window_mode: str = "fullscreen") -> None:
    """Position and style a window on the specified monitor."""
    if sys.platform != "win32" or not hwnd:
        return
    log = get_logger()

    # Restore window first to clear any initial minimized state
    user32.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(0.08)

    if window_mode == "kiosk":
        # True borderless kiosk mode (no title bar, no window controls)
        style = _get_window_long(hwnd, GWL_STYLE)
        style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        _set_window_long(hwnd, GWL_STYLE, style)

        user32.SetWindowPos(
            hwnd,
            HWND_TOP,
            int(monitor.x),
            int(monitor.y),
            int(monitor.width),
            int(monitor.height),
            SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        )
        time.sleep(0.05)
        user32.SetWindowPos(
            hwnd,
            HWND_TOP,
            int(monitor.x),
            int(monitor.y),
            int(monitor.width),
            int(monitor.height),
            SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        )
    else:
        # "fullscreen" (full screen on window) and "maximized":
        # Display full screen on window with the title bar, close, and minimize buttons.
        style = _get_window_long(hwnd, GWL_STYLE)
        style |= (WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        _set_window_long(hwnd, GWL_STYLE, style)

        # Move window within the target monitor bounds first
        user32.SetWindowPos(
            hwnd,
            HWND_TOP,
            int(monitor.x),
            int(monitor.y),
            int(monitor.width),
            int(monitor.height),
            SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        )
        time.sleep(0.08)

        # Maximize the window onto that monitor — covers full screen of the monitor
        # while keeping the close, maximize, and minimize buttons visible.
        user32.ShowWindow(hwnd, SW_MAXIMIZE)

    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

    log.info(
        "Windows placer: placed window 0x%X on Monitor %d (%dx%d at %d,%d) mode=%s",
        hwnd,
        monitor.index,
        monitor.width,
        monitor.height,
        monitor.x,
        monitor.y,
        window_mode,
    )

