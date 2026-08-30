"""Hotkey string parsing shared by the UI and the test-suite.

The human-readable format accepted by the settings UI is ``ctrl+shift+F9``,
``F9``, ``d``, etc.  Tk uses binding sequences such as ``<Control-Shift-F9>``.
"""
from __future__ import annotations

import re

_FUNCTION_KEY = re.compile(r"^f([1-9]|1\d|2[0-4])$")

# Single printable characters plus the special Tk key names we allow.
_SINGLE_CHAR = re.compile(r"^[a-z0-9_]$")
_SPECIAL_KEYS = {
    "escape", "space", "tab", "return", "backspace", "home", "end",
    "delete", "insert", "up", "down", "left", "right", "prior", "next",
}

# Map lower-case input to the canonical Tcl/Tk keysym.
_TK_SPECIAL_NAMES = {
    "escape": "Escape",
    "space": "space",
    "tab": "Tab",
    "return": "Return",
    "backspace": "BackSpace",
    "home": "Home",
    "end": "End",
    "delete": "Delete",
    "insert": "Insert",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "prior": "Prior",
    "next": "Next",
}

_ALLOWED_MODS = {"ctrl", "control", "shift", "alt"}


def hotkey_str_to_tk(hk: str | None) -> str | None:
    """Convert a human hotkey string to a Tk binding sequence.

    Returns ``None`` for invalid input (empty, modifier-only, unknown key,
    unknown modifier, function key above F24, etc.).
    """
    if not hk:
        return None
    parts = [p.strip().lower() for p in str(hk).split("+") if p.strip()]
    if not parts:
        return None

    key = parts[-1]
    mods: list[str] = []
    for p in parts[:-1]:
        if p in ("ctrl", "control"):
            mods.append("Control")
        elif p == "shift":
            mods.append("Shift")
        elif p == "alt":
            mods.append("Alt")
        else:
            return None

    is_fkey = bool(_FUNCTION_KEY.match(key))
    if not _SINGLE_CHAR.match(key) and not is_fkey and key not in _SPECIAL_KEYS:
        return None

    if is_fkey:
        key_name = key.upper()
    elif key in _SPECIAL_KEYS:
        key_name = _TK_SPECIAL_NAMES[key]
    else:
        key_name = key
    if mods:
        return "<" + "-".join(mods) + "-" + key_name + ">"
    if is_fkey:
        return f"<{key_name}>"
    return f"<{key_name}>"


def is_valid_hotkey(hk: str | None) -> bool:
    """Return True if ``hk`` is a usable hotkey string."""
    return hotkey_str_to_tk(hk) is not None
