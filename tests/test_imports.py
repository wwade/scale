"""Smoke tests: every top-level module must be importable in CI.

This catches regressions like:
- A new top-level call to BLE / Gmail at import time (would break in CI).
- A missing system dependency for `bluepy` / `bleak`.
- A typo or removed dep in `pyproject.toml`.
"""

import importlib


def test_import_simulator():
    importlib.import_module("simulator")


def test_import_monitor():
    importlib.import_module("monitor")


def test_import_discover():
    importlib.import_module("discover")
