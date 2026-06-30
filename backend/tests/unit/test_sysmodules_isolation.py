"""Regression tests: real backend packages must survive collection poisoning.

These tests run AFTER the poisoning files (alphabetically: test_action_item_*,
test_async_app_*, test_desktop_*, test_tools_router) and verify that the
conftest isolation hooks restored real packages correctly.

A fresh import of each protected package must return the real module, not a
types.ModuleType stub left behind by a poisoning test file.
"""

import importlib
import os
import sys
import types

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _is_under(path, parent):
    try:
        return os.path.commonpath([os.path.abspath(path), parent]) == parent
    except ValueError:
        return False


def _assert_real_package(name):
    """Import the package and verify it's real and rooted under backend/."""
    mod = importlib.import_module(name)

    mod_file = getattr(mod, '__file__', None)
    mod_path = getattr(mod, '__path__', None)

    if mod_file is not None:
        assert _is_under(mod_file, _BACKEND_DIR), f"{name}.__file__ = {mod_file} is not under {_BACKEND_DIR}"
        return

    if mod_path is not None and len(mod_path) > 0:
        for p in mod_path:
            assert _is_under(p, _BACKEND_DIR), f"{name}.__path__ entry {p} is not under {_BACKEND_DIR}"
        return

    raise AssertionError(
        f"{name} looks like a stub (no __file__, no __path__ under {_BACKEND_DIR}). "
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


def test_path_not_mutated():
    """Verify __path__ of real packages hasn't been mutated by stubs."""
    for name in ("utils", "database", "models", "routers"):
        mod = importlib.import_module(name)
        mod_path = getattr(mod, '__path__', None)
        if mod_path is not None:
            for p in mod_path:
                assert os.path.isdir(p), (
                    f"{name}.__path__ entry {p} does not exist on disk — " f"__path__ may have been mutated by a stub"
                )
