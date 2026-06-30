"""Integration tests for the conftest.py sys.modules isolation hooks.

These tests exercise the snapshot/restore logic by directly calling the
internal functions and simulating what happens during Module collection.
"""

import importlib.util
import os
import sys
import types

_conftest_path = os.path.join(os.path.dirname(__file__), "conftest.py")
_spec = importlib.util.spec_from_file_location("_unit_conftest", _conftest_path)
_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_conftest)


def _make_module(name, path=None):
    mod = types.ModuleType(name)
    if path is not None:
        mod.__path__ = path
    return mod


def _snapshot_and_restore(nodeid, mutate_fn):
    """Directly snapshot sys.modules, run mutate, then restore via the hook logic."""
    snapshots = _conftest._module_snapshots

    modules = {}
    paths = {}
    for k, v in list(sys.modules.items()):
        modules[k] = v
        p = getattr(v, '__path__', None)
        if p is not None:
            paths[k] = list(p)
    snapshots[nodeid] = (modules, paths)

    mutate_fn()

    class FakeReport:
        pass

    report = FakeReport()
    report.nodeid = nodeid
    _conftest.pytest_collectreport(report)


class TestHookParentAttrCleanup:
    def test_new_child_removed(self):
        parent = _make_module("_thook_pkg", path=["/fake"])
        sys.modules["_thook_pkg"] = parent
        try:

            def mutate():
                child = _make_module("_thook_pkg.newchild")
                sys.modules["_thook_pkg.newchild"] = child
                parent.newchild = child

            _snapshot_and_restore("hooks::new_child", mutate)
            assert "_thook_pkg.newchild" not in sys.modules
            assert not hasattr(parent, "newchild")
        finally:
            sys.modules.pop("_thook_pkg.newchild", None)
            sys.modules.pop("_thook_pkg", None)

    def test_replaced_child_restored(self):
        parent = _make_module("_thook_pkg2", path=["/fake"])
        original_child = _make_module("_thook_pkg2.sub")
        parent.sub = original_child
        sys.modules["_thook_pkg2"] = parent
        sys.modules["_thook_pkg2.sub"] = original_child
        try:

            def mutate():
                replacement = _make_module("_thook_pkg2.sub")
                sys.modules["_thook_pkg2.sub"] = replacement
                parent.sub = replacement

            _snapshot_and_restore("hooks::replaced_child", mutate)
            assert sys.modules["_thook_pkg2.sub"] is original_child
            assert parent.sub is original_child
        finally:
            sys.modules.pop("_thook_pkg2.sub", None)
            sys.modules.pop("_thook_pkg2", None)


class TestHookPathRestoration:
    def test_mutated_path_restored(self):
        mod = _make_module("_thook_pathpkg")
        mod.__path__ = ["/original/path"]
        sys.modules["_thook_pathpkg"] = mod
        try:

            def mutate():
                mod.__path__ = ["/poisoned/path"]

            _snapshot_and_restore("hooks::path_mutation", mutate)
            assert list(mod.__path__) == ["/original/path"]
        finally:
            sys.modules.pop("_thook_pathpkg", None)


class TestHookFullPoisonCycle:
    def test_poison_and_restore_cycle(self):
        """Simulate exactly what poisoning test files do: replace a package."""
        real_pkg = _make_module("_thook_realpkg")
        real_pkg.__path__ = ["/real/path"]
        real_pkg.__file__ = "/real/path/__init__.py"
        real_child = _make_module("_thook_realpkg.api")
        real_child.__file__ = "/real/path/api.py"
        real_pkg.api = real_child
        sys.modules["_thook_realpkg"] = real_pkg
        sys.modules["_thook_realpkg.api"] = real_child
        try:

            def mutate():
                stub_pkg = types.ModuleType("_thook_realpkg")
                stub_child = types.ModuleType("_thook_realpkg.api")
                stub_pkg.api = stub_child
                sys.modules["_thook_realpkg"] = stub_pkg
                sys.modules["_thook_realpkg.api"] = stub_child

            _snapshot_and_restore("hooks::full_poison", mutate)
            assert sys.modules["_thook_realpkg"] is real_pkg
            assert sys.modules["_thook_realpkg.api"] is real_child
            assert real_pkg.api is real_child
            assert list(real_pkg.__path__) == ["/real/path"]
        finally:
            sys.modules.pop("_thook_realpkg.api", None)
            sys.modules.pop("_thook_realpkg", None)
