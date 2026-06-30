"""Direct tests for the stub_modules() context manager."""

import sys
import types

from tests.unit._sysmodules_helpers import stub_modules


def _make_module(name):
    mod = types.ModuleType(name)
    return mod


def test_install_adds_to_sysmodules():
    stub = _make_module("_test_stub_helper_pkg")
    try:
        with stub_modules(["_test_stub_helper_pkg"]) as install:
            install({"_test_stub_helper_pkg": stub})
            assert sys.modules["_test_stub_helper_pkg"] is stub
    finally:
        sys.modules.pop("_test_stub_helper_pkg", None)


def test_restore_removes_new_entries():
    name = "_test_stub_helper_new"
    assert name not in sys.modules
    stub = _make_module(name)
    with stub_modules([name]) as install:
        install({name: stub})
        assert sys.modules[name] is stub
    assert name not in sys.modules


def test_restore_puts_back_original():
    name = "_test_stub_helper_orig"
    original = _make_module(name)
    sys.modules[name] = original
    try:
        stub = _make_module(name)
        with stub_modules([name]) as install:
            install({name: stub})
            assert sys.modules[name] is stub
        assert sys.modules[name] is original
    finally:
        sys.modules.pop(name, None)


def test_parent_attr_set_on_install():
    parent = _make_module("_test_stub_parent")
    sys.modules["_test_stub_parent"] = parent
    try:
        child_stub = _make_module("_test_stub_parent.child")
        with stub_modules(["_test_stub_parent.child"]) as install:
            install({"_test_stub_parent.child": child_stub})
            assert getattr(parent, "child", None) is child_stub
    finally:
        sys.modules.pop("_test_stub_parent.child", None)
        sys.modules.pop("_test_stub_parent", None)


def test_parent_attr_deleted_when_not_preexisting():
    parent = _make_module("_test_stub_p2")
    sys.modules["_test_stub_p2"] = parent
    assert not hasattr(parent, "newchild")
    try:
        child_stub = _make_module("_test_stub_p2.newchild")
        with stub_modules(["_test_stub_p2.newchild"]) as install:
            install({"_test_stub_p2.newchild": child_stub})
            assert hasattr(parent, "newchild")
        assert not hasattr(parent, "newchild")
    finally:
        sys.modules.pop("_test_stub_p2.newchild", None)
        sys.modules.pop("_test_stub_p2", None)


def test_parent_attr_restored_when_preexisting():
    parent = _make_module("_test_stub_p3")
    original_child = _make_module("_test_stub_p3.existing")
    parent.existing = original_child
    sys.modules["_test_stub_p3"] = parent
    sys.modules["_test_stub_p3.existing"] = original_child
    try:
        replacement = _make_module("_test_stub_p3.existing")
        with stub_modules(["_test_stub_p3.existing"]) as install:
            install({"_test_stub_p3.existing": replacement})
            assert parent.existing is replacement
        assert parent.existing is original_child
        assert sys.modules["_test_stub_p3.existing"] is original_child
    finally:
        sys.modules.pop("_test_stub_p3.existing", None)
        sys.modules.pop("_test_stub_p3", None)


def test_restore_on_exception():
    name = "_test_stub_exc"
    assert name not in sys.modules
    stub = _make_module(name)
    try:
        with stub_modules([name]) as install:
            install({name: stub})
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert name not in sys.modules
