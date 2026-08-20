from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from testing.import_isolation import (
    AutoMockModule,
    load_module_fresh,
    package_submodule_stubs,
    stub_modules,
)


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


def _write_pkg(root: Path, relative: str, content: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_package_submodule_stubs_covers_a_module_absent_from_extra(tmp_path: Path):
    """The derivation must cover a module that extra does not name.

    FC-hand-listed-test-isolation-membership: proving the helper against a name that
    extra already includes would prove nothing. A synthetic on-disk adopter that is
    deliberately absent from extra is the omission a hand-maintained list cannot
    survive, and it cannot go vacuous as other test files start mentioning modules.
    """

    pkg = tmp_path / "pkg"
    _write_pkg(pkg, "listed.py")
    _write_pkg(pkg, "unlisted_adopter.py")

    stubs = package_submodule_stubs(
        "synthetic.pkg",
        extra=["synthetic.pkg.listed"],
        directory=pkg,
    )

    assert "synthetic.pkg.unlisted_adopter" in stubs
    assert "synthetic.pkg.listed" in stubs


def test_package_submodule_stubs_includes_private_and_nested_modules(tmp_path: Path):
    pkg = tmp_path / "pkg"
    _write_pkg(pkg, "_private.py")
    _write_pkg(pkg, "visible.py")
    _write_pkg(pkg, "nested/__init__.py")
    _write_pkg(pkg, "nested/leaf.py")
    _write_pkg(pkg, "__init__.py")
    (pkg / ".hidden.py").write_text("", encoding="utf-8")
    (pkg / "notes.md").write_text("", encoding="utf-8")

    stubs = package_submodule_stubs("synthetic.pkg", directory=pkg)

    assert "synthetic.pkg._private" in stubs
    assert "synthetic.pkg.visible" in stubs
    assert "synthetic.pkg.nested" in stubs
    assert "synthetic.pkg.nested.leaf" in stubs
    assert hasattr(stubs["synthetic.pkg.nested"], "__path__")
    assert not hasattr(stubs["synthetic.pkg.visible"], "__path__")
    assert "synthetic.pkg.__init__" not in stubs
    assert "synthetic.pkg.notes" not in stubs
    assert not any(".hidden" in name for name in stubs)
    assert "synthetic.pkg.__pycache__" not in stubs


def test_package_submodule_stubs_unions_extra_without_letting_omission_opt_out():
    stubs = package_submodule_stubs("utils.conversations", extra=["utils.conversations.not_on_disk"])

    assert "utils.conversations" in stubs
    assert hasattr(stubs["utils.conversations"], "__path__")
    assert "utils.conversations.process_conversation" in stubs
    assert "utils.conversations.not_on_disk" in stubs


def test_package_submodule_stubs_covers_every_conversations_module_on_disk():
    """Independent glob of the incident package; extra cannot replace disk membership."""

    package_dir = Path(__file__).resolve().parents[2] / "utils" / "conversations"
    on_disk = {
        f"utils.conversations.{path.stem}" for path in package_dir.glob("*.py") if not path.name.startswith("__")
    }
    assert on_disk, "utils.conversations must still contain modules"
    assert "utils.conversations.meeting_receipt" in on_disk

    stubs = package_submodule_stubs("utils.conversations", extra=["utils.conversations.not_on_disk"])
    missing = sorted(on_disk - set(stubs))
    assert missing == []
    assert "utils.conversations.not_on_disk" in stubs


def test_package_submodule_stubs_resolves_from_disk_even_when_package_is_already_stubbed():
    """Spec lookup would report the fake; the filesystem is the honest source."""

    with stub_modules({"utils.conversations": AutoMockModule("utils.conversations")}):
        stubs = package_submodule_stubs("utils.conversations")

    assert "utils.conversations.process_conversation" in stubs


def test_package_submodule_stubs_rejects_a_non_package():
    with pytest.raises(LookupError):
        package_submodule_stubs("utils.conversations.process_conversation")


def test_package_submodule_stubs_rejects_a_path_escape_name():
    with pytest.raises(LookupError):
        package_submodule_stubs("..")


def test_package_submodule_stubs_can_omit_the_package_key(tmp_path: Path):
    """Legacy name-list adopters only need child names; parents are synthesized."""

    pkg = tmp_path / "pkg"
    _write_pkg(pkg, "child.py")
    stubs = package_submodule_stubs("synthetic.pkg", include_package=False, directory=pkg)
    assert "synthetic.pkg" not in stubs
    assert list(stubs) == ["synthetic.pkg.child"]
