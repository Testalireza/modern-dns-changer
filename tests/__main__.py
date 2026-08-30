"""Run all unit tests for Modern DNS Changer.

Usage:
    python -m tests
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

TESTS = [
    "tests.test_app_paths",
    "tests.test_validators",
    "tests.test_storage",
    "tests.test_translations",
    "tests.test_dns_manager_parsing",
    "tests.test_dns_apply",
    "tests.test_hotkey",
]


def main() -> int:
    # Make sure the project root is on sys.path
    here = Path(__file__).resolve().parent.parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    failed: list[tuple[str, str]] = []
    for name in TESTS:
        print(f"--- {name} ---")
        try:
            mod = importlib.import_module(name)
            for attr in sorted(dir(mod)):
                if attr.startswith("test_"):
                    getattr(mod, attr)()
        except Exception:
            failed.append((name, traceback.format_exc()))
            print(f"  FAILED:\n{traceback.format_exc()}")
        else:
            print("  OK")

    print()
    if failed:
        print(f"{len(failed)} test module(s) failed.")
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
