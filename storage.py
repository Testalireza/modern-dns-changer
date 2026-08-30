"""
JSON storage with atomic writes and schema migration.
"""
from __future__ import annotations

import ipaddress
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from logger import get_logger
from presets import merge_user_presets
from validators import is_valid_dns, normalize_dns, sanitize_preset_name

# Thread-safe storage
_LOCKS: dict[str, threading.Lock] = {}
_GLOBAL_LOCK = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _GLOBAL_LOCK:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def load_json(path: Path, default: Any) -> Any:
    """Load a JSON file. Returns ``default`` if the file does not exist or
    cannot be parsed."""
    log = get_logger()
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, type(default)):
            log.warning("load_json: type mismatch for %s (got %s, expected %s); using default",
                        path, type(data).__name__, type(default).__name__)
            return default
        return data
    except (OSError, json.JSONDecodeError) as exc:
        log.error("load_json: failed to read %s: %s", path, exc)
        return default


def save_json(path: Path, data: Any) -> bool:
    """Atomically write ``data`` to ``path`` as JSON. Returns True on success."""
    log = get_logger()
    lock = _lock_for(path)
    with lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write to a temp file in the same directory, then atomically replace
            fd, tmp_path = tempfile.mkstemp(
                prefix=path.name + ".",
                suffix=".tmp",
                dir=str(path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                os.replace(tmp_path, path)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return True
        except (OSError, TypeError, ValueError) as exc:
            log.error("save_json: failed to write %s: %s", path, exc)
            return False


# Defaults ----------------------------------------------------------------

DEFAULT_SETTINGS: dict = {
    "theme": "dark",
    "language": "en",
    "hotkey": "F9",
    "preset_a": "",
    "preset_b": "",
    # "tray" (default, preserves the historical close-to-tray behaviour) or
    # "exit" (close the window fully terminates the application).
    "close_behavior": "tray",
    # Kept for backwards compatibility with settings files written before the
    # close_behavior setting existed.
    "minimize_to_tray": True,
    "last_adapter": "",
    "window_geometry": "800x580",
    "schema_version": 1,
}


def _coerce_bool(value: Any, default: bool = True) -> bool:
    """Coerce common JSON/bool/string representations into a real ``bool``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "off", "no", "")
    return default


def _coerce_int(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_close_behavior(raw: dict, legacy_bool: bool) -> str:
    """Return ``"tray"`` or ``"exit"`` for a settings dict.

    The new ``close_behavior`` key wins when it is present in the *raw* file
    and is valid.  Older settings files use the boolean ``minimize_to_tray``
    key; when neither is meaningful the historical default (``"tray"``) is used.
    """
    if "close_behavior" in raw:
        value = raw.get("close_behavior")
        if value in ("tray", "exit"):
            return value
    return "tray" if legacy_bool else "exit"


def sanitize_settings(raw: Any) -> dict:
    """Return a clean settings dict with defaults for every key/value.

    This is the single point that protects the UI from malformed, missing or
    invalid persisted settings (``null`` theme, a boolean stored as a string,
    an accidental non-dict settings file, old settings without the new
    ``close_behavior`` key, etc.).
    """
    if not isinstance(raw, dict):
        raw = {}

    merged = dict(DEFAULT_SETTINGS)
    merged.update(raw)

    theme = merged.get("theme")
    if theme not in ("dark", "light"):
        theme = DEFAULT_SETTINGS["theme"]
    language = merged.get("language")
    if language not in ("en", "fa"):
        language = DEFAULT_SETTINGS["language"]

    def _text(key: str) -> str:
        val = merged.get(key, DEFAULT_SETTINGS.get(key, ""))
        return val if isinstance(val, str) else ""

    hotkey = _text("hotkey").strip() or DEFAULT_SETTINGS["hotkey"]
    window_geometry = _text("window_geometry").strip() or DEFAULT_SETTINGS["window_geometry"]
    legacy_tray = _coerce_bool(merged.get("minimize_to_tray"), True)
    close_behavior = _normalize_close_behavior(raw, legacy_tray)

    return {
        "theme": theme,
        "language": language,
        "hotkey": hotkey,
        "preset_a": _text("preset_a"),
        "preset_b": _text("preset_b"),
        "close_behavior": close_behavior,
        "minimize_to_tray": close_behavior == "tray",
        "last_adapter": _text("last_adapter"),
        "window_geometry": window_geometry,
        "schema_version": _coerce_int(merged.get("schema_version"), 1),
    }


def sanitize_presets(raw: Any) -> dict:
    """Return a clean presets dict.

    Invalid entries are dropped instead of being passed to the UI, which would
    otherwise crash on ``entry.get(...)`` or send invalid DNS values to
    ``netsh``.
    """
    if not isinstance(raw, dict):
        return {}
    clean: dict = {}
    for name, value in raw.items():
        try:
            clean_name = sanitize_preset_name(str(name))
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        primary = (value.get("primary") or "").strip()
        secondary = (value.get("secondary") or "").strip()
        if not primary or not is_valid_dns(primary):
            continue
        try:
            primary = normalize_dns(primary)
        except ValueError:
            continue
        if secondary and is_valid_dns(secondary):
            try:
                secondary = normalize_dns(secondary)
            except ValueError:
                secondary = ""
        else:
            secondary = ""
        if primary.lower() == secondary.lower():
            secondary = ""
        if secondary:
            try:
                if ipaddress.ip_address(primary).version != ipaddress.ip_address(secondary).version:
                    continue  # mixed IPv4/IPv6 presets are not supported
            except (ipaddress.AddressValueError, ValueError):
                continue
        clean[clean_name] = {"primary": primary, "secondary": secondary}
    return clean


def load_user_presets(path: Path) -> dict:
    """Load only the user-created presets from ``presets.json``.

    Built-in presets are *not* stored in the file; they are merged in by
    :func:`merged_presets` at display time.  This keeps existing user files
    intact and makes it impossible for the defaults to overwrite user data.
    """
    return sanitize_presets(load_json(path, {}))


def load_presets(path: Path) -> dict:
    """Load the full display preset list (built-in defaults + user presets).

    Existing user presets are always preserved.  A user preset whose name
    matches a built-in name overrides that built-in entry instead of creating
    a duplicate.
    """
    return merged_presets(load_user_presets(path))


def merged_presets(user_presets: dict) -> dict:
    """Merge sanitized user presets with the built-in defaults."""
    return merge_user_presets(sanitize_presets(user_presets))


def save_presets(path: Path, user_presets: dict) -> bool:
    """Persist ``user_presets`` to ``presets.json``.

    Only *user-created* entries are written here.  The UI maintains
    ``user_presets`` separately from the merged display list, so built-in
    presets are normally never present in this dict.  If a legacy file already
    contains a user preset whose name matches a built-in (e.g. a custom
    ``Cloudflare``), saving must preserve that user data rather than drop it.
    """
    return save_json(path, sanitize_presets(user_presets))


def load_settings(path: Path) -> dict:
    raw = load_json(path, dict(DEFAULT_SETTINGS))
    return sanitize_settings(raw)


def save_settings(path: Path, settings: dict) -> bool:
    return save_json(path, sanitize_settings(settings))
