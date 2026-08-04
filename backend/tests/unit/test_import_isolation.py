from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from testing.import_isolation import load_module_fresh, stub_modules


def test_stub_modules_restores_child_attribute_when_child_is_stubbed_before_parent(monkeypatch):
    root_name = "_import_isolation_root"
    parent_name = f"{root_name}.parent"
    child_name = f"{parent_name}.child"

    root = ModuleType(root_name)
    root.__path__ = []  # type: ignore[attr-defined]
    original_parent = ModuleType(parent_name)
    original_parent.__path__ = []  # type: ignore[attr-defined]
    original_child = ModuleType(child_name)
    root.parent = original_parent
    original_parent.child = original_child

    monkeypatch.setitem(sys.modules, root_name, root)
    monkeypatch.setitem(sys.modules, parent_name, original_parent)
    monkeypatch.setitem(sys.modules, child_name, original_child)

    fake_parent = ModuleType(parent_name)
    fake_parent.__path__ = []  # type: ignore[attr-defined]
    fake_child = ModuleType(child_name)

    # This child-before-parent ordering previously left
    # ``original_parent.child`` pointing at ``fake_child`` after teardown.
    with stub_modules({child_name: fake_child, parent_name: fake_parent}):
        assert sys.modules[child_name] is fake_child
        assert sys.modules[parent_name] is fake_parent

    assert sys.modules[child_name] is original_child
    assert sys.modules[parent_name] is original_parent
    assert root.parent is original_parent
    assert original_parent.child is original_child


@pytest.fixture
def atom_keyword_index_with_top_level_typesense_only():
    module_path = Path(__file__).resolve().parents[2] / "utils" / "memory" / "atom_keyword_index.py"
    top_level_typesense_only = ModuleType("typesense")

    with stub_modules(
        {
            "typesense": top_level_typesense_only,
            "typesense.exceptions": None,
            "utils.memory.atom_keyword_index": None,
        }
    ):
        yield load_module_fresh("utils.memory.atom_keyword_index", str(module_path))


def test_atom_keyword_index_import_does_not_require_typesense_submodules(
    atom_keyword_index_with_top_level_typesense_only,
):
    assert callable(atom_keyword_index_with_top_level_typesense_only.is_indexable_long_term_atom)
