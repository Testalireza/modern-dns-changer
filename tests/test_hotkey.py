"""Tests for the shared hotkey string parser.

The parser lives in ``hotkeys.py`` and is used by both ``ui.py`` (via a thin
method wrapper) and the tests, so they can never drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hotkeys import is_valid_hotkey, hotkey_str_to_tk


def test_function_key() -> None:
    assert hotkey_str_to_tk("F9") == "<F9>"
    assert hotkey_str_to_tk("F1") == "<F1>"
    assert hotkey_str_to_tk("F12") == "<F12>"
    assert hotkey_str_to_tk("F24") == "<F24>"
    assert hotkey_str_to_tk("f9") == "<F9>"  # lowercase is normalised
    print("test_function_key OK")


def test_letter_key() -> None:
    assert hotkey_str_to_tk("d") == "<d>"
    assert hotkey_str_to_tk("a") == "<a>"
    print("test_letter_key OK")


def test_ctrl_letter() -> None:
    assert hotkey_str_to_tk("ctrl+d") == "<Control-d>"
    assert hotkey_str_to_tk("control+d") == "<Control-d>"
    print("test_ctrl_letter OK")


def test_ctrl_shift_function() -> None:
    assert hotkey_str_to_tk("ctrl+shift+f9") == "<Control-Shift-F9>"
    assert hotkey_str_to_tk("ctrl+shift+d") == "<Control-Shift-d>"
    print("test_ctrl_shift_function OK")


def test_alt_combination() -> None:
    assert hotkey_str_to_tk("alt+f9") == "<Alt-F9>"
    print("test_alt_combination OK")


def test_navigation_keys() -> None:
    assert hotkey_str_to_tk("up") == "<Up>"
    assert hotkey_str_to_tk("ctrl+down") == "<Control-Down>"
    assert hotkey_str_to_tk("prior") == "<Prior>"
    assert hotkey_str_to_tk("ctrl+next") == "<Control-Next>"
    print("test_navigation_keys OK")


def test_invalid_inputs() -> None:
    assert hotkey_str_to_tk("") is None
    assert hotkey_str_to_tk("+") is None
    assert hotkey_str_to_tk("ctrl+") is None
    assert hotkey_str_to_tk("ctrl+;;") is None
    assert hotkey_str_to_tk("ctrl+F25") is None  # function keys only up to F24
    assert hotkey_str_to_tk("ctrl+enter") is None  # not in allowed special set
    assert hotkey_str_to_tk("unknownmod+d") is None
    print("test_invalid_inputs OK")


def test_whitespace_tolerance() -> None:
    assert hotkey_str_to_tk("  F9  ") == "<F9>"
    assert hotkey_str_to_tk("ctrl + shift + f9") == "<Control-Shift-F9>"
    print("test_whitespace_tolerance OK")


def test_is_valid_hotkey() -> None:
    assert is_valid_hotkey("F9")
    assert is_valid_hotkey("ctrl+shift+d")
    assert not is_valid_hotkey("")
    assert not is_valid_hotkey("ctrl+")
    print("test_is_valid_hotkey OK")


if __name__ == "__main__":
    test_function_key()
    test_letter_key()
    test_ctrl_letter()
    test_ctrl_shift_function()
    test_alt_combination()
    test_navigation_keys()
    test_invalid_inputs()
    test_whitespace_tolerance()
    test_is_valid_hotkey()
    print("\nAll hotkey tests passed.")
