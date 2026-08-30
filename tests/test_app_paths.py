"""Unit tests for app_paths."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app_paths import (
    exe_dir,
    is_frozen,
    presets_path,
    resource_dir,
    resource_path,
    settings_path,
    user_data_dir,
)


def test_is_frozen_false_in_source() -> None:
    # When running the tests from source, sys.frozen is not set
    assert is_frozen() is False
    print("test_is_frozen_false_in_source OK")


def test_exe_dir_returns_existing_path() -> None:
    p = exe_dir()
    assert isinstance(p, Path)
    assert p.is_dir()
    print("test_exe_dir_returns_existing_path OK")


def test_resource_dir_returns_existing_path() -> None:
    p = resource_dir()
    assert isinstance(p, Path)
    assert p.is_dir()
    print("test_resource_dir_returns_existing_path OK")


def test_presets_path_under_user_data_dir() -> None:
    p = presets_path()
    assert isinstance(p, Path)
    assert p.parent == user_data_dir()
    assert p.name == "presets.json"
    print("test_presets_path_under_user_data_dir OK")


def test_settings_path_under_user_data_dir() -> None:
    p = settings_path()
    assert p.parent == user_data_dir()
    assert p.name == "settings.json"
    print("test_settings_path_under_user_data_dir OK")


def test_resource_path() -> None:
    p = resource_path("icon.ico")
    assert p.parent == resource_dir()
    print("test_resource_path OK")


if __name__ == "__main__":
    test_is_frozen_false_in_source()
    test_exe_dir_returns_existing_path()
    test_resource_dir_returns_existing_path()
    test_presets_path_under_user_data_dir()
    test_settings_path_under_user_data_dir()
    test_resource_path()
    print("\nAll app_paths tests passed.")
