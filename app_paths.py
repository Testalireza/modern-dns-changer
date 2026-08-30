"""
Application path resolution — works for source, PyInstaller, and onefile/bundle.

When running from source, ``APP_DIR`` is the directory of the main script.
When running as a PyInstaller executable, ``APP_DIR`` is the directory of the
EXE (for onefile mode) and ``RESOURCE_DIR`` (sometimes ``sys._MEIPASS``)
contains the bundled data files.

We never assume the current working directory is writable or correct.
"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """Return True if running as a PyInstaller (or other) frozen executable."""
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path:
    """Directory of the running executable (or the script, when unfrozen)."""
    if is_frozen():
        # sys.executable points to the .exe in both onefile and onedir modes
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """Directory containing bundled read-only data files.

    In PyInstaller onefile, this is ``sys._MEIPASS``.
    In PyInstaller onedir or running from source, this is the EXE/script dir.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return exe_dir()


def user_data_dir() -> Path:
    """User-writable directory for presets.json / settings.json.

    Always returns a path under the executable directory so the project
    remains self-contained — this matches the previous behaviour and makes
    it easy to ship a portable .exe. We use ``exe_dir()`` rather than
    ``%APPDATA%`` so the app stays portable.
    """
    return exe_dir()


def presets_path() -> Path:
    return user_data_dir() / "presets.json"


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def log_path() -> Path:
    return user_data_dir() / "modern_dns_changer.log"


def icon_path() -> Path:
    """Path to the bundled .ico file."""
    p = resource_dir() / "icon.ico"
    return p


def resource_path(name: str) -> Path:
    """Resolve a resource by name (e.g. ``icon.ico``, ``translations.py``)."""
    return resource_dir() / name
