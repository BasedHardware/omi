"""Regression tests: real backend packages must survive collection poisoning.

Self-contained: each test poisons sys.modules, triggers the hook restore,
then verifies the real package was recovered. Does not depend on test
ordering or the existence of poisoning test files.
"""

import importlib
import importlib.util
import os
import sys
import types

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_conftest_path = os.path.join(os.path.dirname(__file__), "conftest.py")
_spec = importlib.util.spec_from_file_location("_unit_conftest_iso", _conftest_path)
_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_conftest)


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


def _poison_and_recover(name):
    """Poison name with a stub, run the hook restore, verify recovery."""
    real_mod = importlib.import_module(name)
    snapshots = _conftest._module_snapshots

    modules = {}
    paths = {}
    for k, v in list(sys.modules.items()):
        modules[k] = v
        p = getattr(v, '__path__', None)
        if p is not None:
            paths[k] = list(p)
    nodeid = f"test_sysmodules_isolation.py::_poison_{name}"
    snapshots[nodeid] = (modules, paths)

    stub = types.ModuleType(name)
    sys.modules[name] = stub

    class FakeReport:
        pass

    report = FakeReport()
    report.nodeid = nodeid
    _conftest.pytest_collectreport(report)

    assert sys.modules[name] is real_mod, f"{name} was not restored after poisoning"
    _assert_real_package(name)


def test_utils_survives_poisoning():
    _poison_and_recover("utils")


def test_database_survives_poisoning():
    _poison_and_recover("database")


def test_models_survives_poisoning():
    _poison_and_recover("models")


def test_routers_survives_poisoning():
    _poison_and_recover("routers")


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
