"""Modern DNS Changer v4.1 — entry point.

The actual application logic lives in dedicated modules. This file:
  * sets up logging,
  * configures DPI awareness on Windows,
  * auto-elevates to Administrator on first run (if necessary),
  * starts the GUI event loop.

Run from source:
    python main.py

Build a standalone EXE:
    build.bat
or
    pyinstaller build.spec --clean --noconfirm
"""
from __future__ import annotations

import os
import sys


def _setup_environment() -> None:
    """Apply OS-level tweaks before any GUI is created."""
    # Hide the console window when launched via pythonw.exe
    if getattr(sys, "frozen", False) or sys.executable.endswith("pythonw.exe"):
        try:
            import ctypes
            whnd = ctypes.windll.kernel32.GetConsoleWindow()
            if whnd:
                ctypes.windll.user32.ShowWindow(whnd, 0)  # SW_HIDE
        except (OSError, AttributeError):
            pass

    # High-DPI support on Windows
    try:
        from platform_utils import set_dpi_awareness
        set_dpi_awareness()
    except ImportError:
        pass

    # Make sure the script directory is on sys.path so we can import
    # sibling modules whether the user is running from source, from a
    # console, or from PyInstaller.
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)


def _ensure_admin() -> None:
    """If we are not elevated on Windows, relaunch ourselves with UAC."""
    try:
        from platform_utils import is_admin, is_windows, request_admin_elevation
    except ImportError:
        return
    if not is_windows():
        return
    if is_admin():
        return
    # We are non-elevated on Windows. Relaunch elevated and exit this process.
    if request_admin_elevation():
        sys.exit(0)
    # If elevation was declined or failed, the UI will show a banner asking
    # the user to restart manually.


def main() -> int:
    _setup_environment()

    # Configure logging first so any startup errors are captured
    try:
        from app_paths import log_path
        from logger import setup_logging, get_logger
        setup_logging(log_path())
    except Exception as exc:  # pragma: no cover
        # Fall back to stderr if logging cannot be initialised
        print(f"[startup] logging setup failed: {exc}", file=sys.stderr)
    log = None
    try:
        log = get_logger()
    except Exception:
        pass
    if log:
        log.info("=" * 60)
        log.info("Modern DNS Changer starting (frozen=%s)", getattr(sys, "frozen", False))

    # Auto-elevate to admin on Windows
    _ensure_admin()

    # Now build the GUI
    try:
        import customtkinter as ctk
        from ui import DNSChangerApp
        ctk.set_default_color_theme("blue")
        app = DNSChangerApp()
        app.mainloop()
        return 0
    except ImportError as exc:
        msg = (
            f"Missing dependency: {exc}\n\n"
            "Run:\n    pip install -r requirements.txt\n"
        )
        sys.stderr.write(msg)
        try:
            from tkinter import messagebox
            messagebox.showerror("Modern DNS Changer", msg)
        except Exception:
            pass
        return 1
    except Exception as exc:  # pragma: no cover
        # Last-ditch: log + show a dialog if possible
        try:
            if log:
                log.exception("Fatal error: %s", exc)
        except Exception:
            pass
        try:
            from tkinter import messagebox
            messagebox.showerror("Modern DNS Changer", f"Fatal error:\n\n{exc}")
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
