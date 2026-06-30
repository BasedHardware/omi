"""Regression tests: real backend packages must survive collection poisoning.

These tests run AFTER the poisoning files (alphabetically: test_action_item_*,
test_async_app_*, test_desktop_*, test_tools_router) and verify that the
conftest isolation hooks restored real packages correctly.

A fresh import of each protected package must return the real module, not a
types.ModuleType stub left behind by a poisoning test file.
"""

import importlib
import sys
import types


def _assert_real_package(name):
    """Import the package and verify it's real, not a stub."""
    mod = importlib.import_module(name)
    has_file = getattr(mod, '__file__', None) is not None
    has_path = getattr(mod, '__path__', None) is not None and len(mod.__path__) > 0
    has_loader = getattr(mod, '__loader__', None) is not None
    assert has_file or has_path or has_loader, (
        f"{name} looks like a stub (no __file__, no __path__, no __loader__). "
        f"A poisoning test file may have leaked into sys.modules."
    )


def test_utils_is_real_package():
    _assert_real_package("utils")


def test_database_is_real_package():
    _assert_real_package("database")


def test_models_is_real_package():
    _assert_real_package("models")


def test_routers_is_real_package():
    _assert_real_package("routers")
