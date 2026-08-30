"""
Windows-specific utilities: admin check, theme detection, Win11 effects.
All functions are safe to call on non-Windows platforms (no-ops).
"""
from __future__ import annotations

import ctypes
import os
import sys

from logger import get_logger


def is_windows() -> bool:
    return sys.platform == "win32"


def is_admin() -> bool:
    """Return True if the current process is running as Administrator."""
    if not is_windows():
        # On non-Windows the app cannot perform DNS changes; always return False
        # so the UI prompts the user. The app is designed to no-op gracefully.
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError) as exc:
        get_logger().warning("is_admin: %s", exc)
        return False


def request_admin_elevation() -> bool:
    """Request UAC elevation and relaunch the current process.

    Returns ``True`` if the elevation request was *launched* (not necessarily
    accepted by the user). Returns ``False`` if we cannot relaunch.
    """
    log = get_logger()
    if not is_windows():
        return False
    try:
        # When running as a frozen EXE, sys.executable is the .exe
        # When running from source, sys.executable is python.exe and we
        # need to pass the script path as the first argument.
        exe = sys.executable
        if getattr(sys, "frozen", False):
            params = None
        else:
            params = f'"{os.path.abspath(__file__)}"'
        SW_SHOWNORMAL = 1
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, None, SW_SHOWNORMAL
        )
        # ShellExecuteW returns > 32 on success
        if rc <= 32:
            log.error("request_admin_elevation: ShellExecuteW returned %d", rc)
            return False
        return True
    except (AttributeError, OSError) as exc:
        log.error("request_admin_elevation: %s", exc)
        return False


def detect_windows_theme() -> str:
    """Return ``"light"`` or ``"dark"`` based on the current Windows
    application theme. Returns ``"dark"`` on failure or non-Windows.
    """
    if not is_windows():
        return "dark"
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if int(value) == 1 else "dark"
    except (OSError, AttributeError, ValueError) as exc:
        get_logger().debug("detect_windows_theme: %s — defaulting to dark", exc)
        return "dark"


# ------------------------------------------------------------------ Win11 effects

# DWM window attributes (Windows 11)
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_CAPTION_COLOR = 35
DWMWA_SYSTEMBACKDROP_TYPE = 38  # 2 = Mica
DWMWA_BORDER_COLOR = 34
DWMWA_WINDOW_CORNER_PREFERENCE = 33  # 2 = rounded

_BACKDROP_MICA = 2
_CORNER_ROUND = 2


def apply_windows11_effects(hwnd: int | None, dark: bool = True) -> None:
    """Apply Mica backdrop, dark title bar, and rounded corners to ``hwnd``.

    Silently no-ops on non-Windows or if the underlying APIs are missing.
    """
    if not is_windows() or not hwnd:
        return
    log = get_logger()
    try:
        dwm = ctypes.WinDLL("dwmapi.dll")
    except (OSError, AttributeError) as exc:
        log.debug("apply_windows11_effects: dwmapi not available: %s", exc)
        return
    dark_int = 1 if dark else 0
    pairs = [
        (DWMWA_USE_IMMERSIVE_DARK_MODE, dark_int),
        (DWMWA_SYSTEMBACKDROP_TYPE, _BACKDROP_MICA),
        (DWMWA_WINDOW_CORNER_PREFERENCE, _CORNER_ROUND),
    ]
    for attr, val in pairs:
        try:
            dwm.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_int(attr),
                ctypes.byref(ctypes.c_int(int(val))),
                ctypes.c_int(4),
            )
        except (OSError, AttributeError, ValueError) as exc:
            log.debug("apply_windows11_effects: attr %d failed: %s", attr, exc)


def get_hwnd(window) -> int | None:
    """Return the native HWND for a Tkinter ``Toplevel`` or root window."""
    if not is_windows():
        return None
    try:
        window.update_idletasks()
        # winfo_id() returns the window's X11 id; on Windows we need the
        # top-level HWND, which is the parent of that.
        wid = window.winfo_id()
        parent = ctypes.windll.user32.GetParent(wid)
        return int(parent) if parent else int(wid)
    except (AttributeError, OSError, ValueError) as exc:
        get_logger().debug("get_hwnd: %s", exc)
        return None


def set_dpi_awareness() -> None:
    """Enable per-monitor DPI awareness on Windows."""
    if not is_windows():
        return
    try:
        # Try the modern call first
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            # Fall back to the older system-DPI awareness flag
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError) as exc:
            get_logger().debug("set_dpi_awareness: %s", exc)
