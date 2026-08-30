"""Tests for the hotkey string parser.

The parser is a static method on ``DNSChangerApp``, but because instantiating
that class requires Tk, we extract the method and test it standalone.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _hotkey_str_to_tk(hk: str) -> str | None:
    if not hk:
        return None
    parts = [p.strip().lower() for p in hk.split("+") if p.strip()]
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
    is_fkey = bool(re.match(r"^f([1-9]|1\d|2[0-4])$", key))
    if not re.match(r"^[a-z0-9_]$", key) and not is_fkey \
            and key not in {"escape", "space", "tab", "return", "backspace", "home", "end"}:
        return None
    key_name = key.upper() if is_fkey else key
    if mods:
        return "<" + "-".join(mods) + "-" + key_name + ">"
    if is_fkey:
        return f"<{key_name}>"
    return f"<{key}>"


def test_function_key() -> None:
    # Function-key output preserves the canonical Tk name (uppercase)
    assert _hotkey_str_to_tk("F9") == "<F9>"
    assert _hotkey_str_to_tk("F1") == "<F1>"
    assert _hotkey_str_to_tk("F12") == "<F12>"
    assert _hotkey_str_to_tk("F24") == "<F24>"
    assert _hotkey_str_to_tk("f9") == "<F9>"  # lowercase is normalised
    print("test_function_key OK")


def test_letter_key() -> None:
    assert _hotkey_str_to_tk("d") == "<d>"
    assert _hotkey_str_to_tk("a") == "<a>"
    print("test_letter_key OK")


def test_ctrl_letter() -> None:
    assert _hotkey_str_to_tk("ctrl+d") == "<Control-d>"
    assert _hotkey_str_to_tk("control+d") == "<Control-d>"
    print("test_ctrl_letter OK")


def test_ctrl_shift_function() -> None:
    """The original buggy parser produced nested brackets here."""
    assert _hotkey_str_to_tk("ctrl+shift+f9") == "<Control-Shift-F9>"
    assert _hotkey_str_to_tk("ctrl+shift+d") == "<Control-Shift-d>"
    print("test_ctrl_shift_function OK")


def test_alt_combination() -> None:
    assert _hotkey_str_to_tk("alt+f9") == "<Alt-F9>"
    print("test_alt_combination OK")


def test_invalid_inputs() -> None:
    assert _hotkey_str_to_tk("") is None
    assert _hotkey_str_to_tk("+") is None
    assert _hotkey_str_to_tk("ctrl+") is None
    assert _hotkey_str_to_tk("ctrl+;;") is None
    assert _hotkey_str_to_tk("ctrl+F25") is None  # function keys only up to F24
    assert _hotkey_str_to_tk("ctrl+enter") is None  # not in allowed special set
    print("test_invalid_inputs OK")


def test_whitespace_tolerance() -> None:
    assert _hotkey_str_to_tk("  F9  ") == "<F9>"
    assert _hotkey_str_to_tk("ctrl + shift + f9") == "<Control-Shift-F9>"
    print("test_whitespace_tolerance OK")


if __name__ == "__main__":
    test_function_key()
    test_letter_key()
    test_ctrl_letter()
    test_ctrl_shift_function()
    test_alt_combination()
    test_invalid_inputs()
    test_whitespace_tolerance()
    print("\nAll hotkey tests passed.")
