"""Unit tests for the tray lifecycle (no duplicate icons, clean stop).

The real Windows tray cannot be created in this environment, so we exercise
the controller with a mocked ``pystray`` layer.  This is the part that
guarantees repeated close/open/settings operations never spawn a second icon.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tray as tray_mod
from tray import TrayController


def _mock_pystray():
    """Patch ``tray.pystray`` (and the module flag) with a fake that records
    the Icons it creates."""
    fake = MagicMock()
    fake.Menu = MagicMock()
    fake.Menu.MenuItem = lambda *a, **k: object()
    fake.Menu.SEPARATOR = object()
    fake.MenuItem = lambda *a, **k: object()
    fake.SEPARATOR = object()
    icons: list = []
    fake.Icon = MagicMock(side_effect=lambda *a, **k: icons.append(MagicMock()) or icons[-1])
    p = patch.object(tray_mod, "pystray", fake)
    return p, icons


def test_start_is_idempotent_no_duplicate_icons() -> None:
    patcher, icons = _mock_pystray()
    with patch.object(tray_mod, "TRAY_AVAILABLE", True), patcher:
        ctrl = TrayController()
        assert ctrl.start(lambda: None, lambda: None, lambda: None) is True
        assert ctrl.is_running() is True
        first_thread = ctrl._thread
        # Repeated start calls (settings change, restore, close/reopen) must
        # not create another icon or thread.
        assert ctrl.start(lambda: None, lambda: None, lambda: None) is True
        assert ctrl.start(lambda: None, lambda: None, lambda: None) is True
        assert len(icons) == 1, f"expected one icon, got {len(icons)}"
        assert ctrl._thread is first_thread
    print("test_start_is_idempotent_no_duplicate_icons OK")


def test_stop_cleans_up_and_is_idempotent() -> None:
    patcher, _icons = _mock_pystray()
    with patch.object(tray_mod, "TRAY_AVAILABLE", True), patcher:
        ctrl = TrayController()
        ctrl.start(lambda: None, lambda: None, lambda: None)
        ctrl.stop()
        assert ctrl.is_running() is False
        # Stop again is safe.
        ctrl.stop()
        assert ctrl.is_running() is False
    print("test_stop_cleans_up_and_is_idempotent OK")


def test_tray_unavailable_returns_false() -> None:
    with patch.object(tray_mod, "TRAY_AVAILABLE", False):
        ctrl = TrayController()
        assert ctrl.start(lambda: None, lambda: None, lambda: None) is False
        assert ctrl.is_running() is False
    print("test_tray_unavailable_returns_false OK")


if __name__ == "__main__":
    test_start_is_idempotent_no_duplicate_icons()
    test_stop_cleans_up_and_is_idempotent()
    test_tray_unavailable_returns_false()
    print("\nAll tray lifecycle tests passed.")
