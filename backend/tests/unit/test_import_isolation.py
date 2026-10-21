from __future__ import annotations

import importlib
from importlib.machinery import ExtensionFileLoader, ModuleSpec, SourceFileLoader
import sys
from pathlib import Path
from types import ModuleType

import pytest

from testing.import_isolation import (
    AutoMockModule,
    install_package_submodule_stubs,
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


@pytest.mark.parametrize("native_preloaded", [False, True])
def test_stub_modules_evicts_unlisted_native_extension_and_python_siblings(tmp_path: Path, native_preloaded: bool):
    package_name = "_import_isolation_extension_package"
    extension_name = f"{package_name}.native"
    sibling_name = f"{package_name}.sibling"
    fake_name = f"{package_name}.external_fake"
    package_path = tmp_path / package_name
    package_path.mkdir()
    extension_path = package_path / "native.cpython-311.so"
    sibling_path = package_path / "sibling.py"
    fake_path = tmp_path / "external_fake.py"
    extension_path.touch()
    sibling_path.touch()
    fake_path.touch()

    package = ModuleType(package_name)
    package.__path__ = [str(package_path)]  # type: ignore[attr-defined]
    package.__spec__ = ModuleSpec(package_name, loader=None, is_package=True)
    package.__spec__.submodule_search_locations = [str(package_path)]
    extension = ModuleType(extension_name)
    extension.__spec__ = ModuleSpec(
        extension_name,
        loader=ExtensionFileLoader(extension_name, str(extension_path)),
        origin=str(extension_path),
    )
    sibling = ModuleType(sibling_name)
    sibling.__spec__ = ModuleSpec(sibling_name, loader=None, origin=str(sibling_path))
    external_fake = ModuleType(fake_name)
    external_fake.__spec__ = ModuleSpec(fake_name, loader=None, origin=str(fake_path))

    try:
        if native_preloaded:
            # As with google._upb._message after a module-scope google.auth import.
            sys.modules[package_name] = package
            sys.modules[extension_name] = extension
            package.native = extension
        with stub_modules({}):
            if not native_preloaded:
                sys.modules[package_name] = package
                sys.modules[extension_name] = extension
                package.native = extension
            sys.modules[sibling_name] = sibling
            sys.modules[fake_name] = external_fake
            package.sibling = sibling
            package.external_fake = external_fake

        if native_preloaded:
            assert sys.modules[package_name] is package
            assert sys.modules[extension_name] is extension
            assert package.native is extension
        else:
            assert package_name not in sys.modules
            assert extension_name not in sys.modules
        assert sibling_name not in sys.modules
        assert fake_name not in sys.modules
        if native_preloaded:
            assert not hasattr(package, "sibling")
            assert not hasattr(package, "external_fake")
    finally:
        sys.modules.pop(fake_name, None)
        sys.modules.pop(sibling_name, None)
        sys.modules.pop(extension_name, None)
        sys.modules.pop(package_name, None)


def test_stub_modules_evicts_fake_with_origin_inside_native_namespace_family(tmp_path: Path):
    package_name = "_import_isolation_native_namespace"
    extension_name = f"{package_name}._native"
    fake_parent_name = f"{package_name}.secret"
    fake_name = f"{fake_parent_name}.internal"
    package_path = tmp_path / package_name
    secret_path = package_path / "secret"
    secret_path.mkdir(parents=True)
    extension_path = package_path / "_native.cpython-311.so"
    fake_path = secret_path / "internal.py"
    extension_path.touch()
    fake_path.touch()

    package = ModuleType(package_name)
    package.__path__ = [str(package_path)]  # type: ignore[attr-defined]
    package.__spec__ = ModuleSpec(package_name, loader=None, is_package=True)
    package.__spec__.submodule_search_locations = [str(package_path)]
    extension = ModuleType(extension_name)
    extension.__spec__ = ModuleSpec(
        extension_name,
        loader=ExtensionFileLoader(extension_name, str(extension_path)),
        origin=str(extension_path),
    )
    fake_parent = ModuleType(fake_parent_name)
    fake_parent.__path__ = [str(secret_path)]  # type: ignore[attr-defined]
    fake_parent.__spec__ = ModuleSpec(fake_parent_name, loader=None, is_package=True)
    fake_parent.__spec__.submodule_search_locations = [str(secret_path)]
    fake = ModuleType(fake_name)
    fake.__spec__ = ModuleSpec(fake_name, loader=None, origin=str(fake_path))

    try:
        with stub_modules({}):
            sys.modules[package_name] = package
            sys.modules[extension_name] = extension
            sys.modules[fake_parent_name] = fake_parent
            sys.modules[fake_name] = fake
            package._native = extension
            package.secret = fake_parent
            fake_parent.internal = fake

        assert package_name not in sys.modules
        assert extension_name not in sys.modules
        assert fake_name not in sys.modules
        assert fake_parent_name not in sys.modules
    finally:
        sys.modules.pop(fake_name, None)
        sys.modules.pop(fake_parent_name, None)
        sys.modules.pop(extension_name, None)
        sys.modules.pop(package_name, None)


def test_stub_modules_evicts_fake_with_forged_native_origin_suffix(tmp_path: Path):
    package_name = "_import_isolation_forged_native_origin"
    extension_name = f"{package_name}._native"
    fake_name = f"{package_name}.secret.internal"
    package_path = tmp_path / package_name
    secret_path = package_path / "secret"
    secret_path.mkdir(parents=True)
    extension_path = package_path / "_native.cpython-311.so"
    source_path = secret_path / "internal.py"
    forged_origin = secret_path / "internal.cpython-311.so"
    extension_path.touch()
    source_path.touch()
    forged_origin.touch()

    package = ModuleType(package_name)
    package.__path__ = [str(package_path)]  # type: ignore[attr-defined]
    package.__spec__ = ModuleSpec(package_name, loader=None, is_package=True)
    package.__spec__.submodule_search_locations = [str(package_path)]
    extension = ModuleType(extension_name)
    extension.__spec__ = ModuleSpec(
        extension_name,
        loader=ExtensionFileLoader(extension_name, str(extension_path)),
        origin=str(extension_path),
    )
    fake_parent_name = f"{package_name}.secret"
    fake_parent = ModuleType(fake_parent_name)
    fake_parent.__path__ = [str(secret_path)]  # type: ignore[attr-defined]
    fake_parent.__spec__ = ModuleSpec(fake_parent_name, loader=None, is_package=True)
    fake_parent.__spec__.submodule_search_locations = [str(secret_path)]
    fake = ModuleType(fake_name)
    fake.__spec__ = ModuleSpec(
        fake_name,
        loader=SourceFileLoader(fake_name, str(source_path)),
        origin=str(forged_origin),
    )

    try:
        with stub_modules({}):
            sys.modules[package_name] = package
            sys.modules[extension_name] = extension
            sys.modules[fake_parent_name] = fake_parent
            sys.modules[fake_name] = fake
            package._native = extension
            package.secret = fake_parent
            fake_parent.internal = fake

        assert package_name not in sys.modules
        assert extension_name not in sys.modules
        assert fake_name not in sys.modules
        assert fake_parent_name not in sys.modules
    finally:
        sys.modules.pop(fake_name, None)
        sys.modules.pop(fake_parent_name, None)
        sys.modules.pop(extension_name, None)
        sys.modules.pop(package_name, None)


def test_stub_modules_evicts_unlisted_extension_with_forged_loader_and_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = importlib.import_module("pydantic_core")
    extension_name = "pydantic_core._pydantic_core"
    fake_origin = tmp_path / "fake.so"
    fake_origin.touch()
    fake = ModuleType(extension_name)
    fake.__spec__ = ModuleSpec(
        extension_name,
        loader=ExtensionFileLoader(extension_name, str(fake_origin)),
        origin=str(fake_origin),
    )
    monkeypatch.delitem(sys.modules, extension_name, raising=False)
    monkeypatch.delattr(package, "_pydantic_core", raising=False)

    with stub_modules({}):
        sys.modules[extension_name] = fake
        package._pydantic_core = fake

    assert extension_name not in sys.modules
    assert not hasattr(package, "_pydantic_core")


def test_stub_modules_preserves_allowlisted_jiter_extension_with_existing_origin(
    monkeypatch: pytest.MonkeyPatch,
):
    package = importlib.import_module("jiter")
    extension = importlib.import_module("jiter.jiter")
    package_origin = package.__spec__.origin
    extension_origin = extension.__spec__.origin
    assert isinstance(package_origin, str) and Path(package_origin).is_file()
    assert isinstance(extension_origin, str) and Path(extension_origin).is_file()
    assert isinstance(extension.__spec__.loader, ExtensionFileLoader)

    fake_package = ModuleType("jiter")
    fake_package.__path__ = list(package.__path__)  # type: ignore[attr-defined]
    fake_package.__spec__ = ModuleSpec(
        "jiter",
        loader=SourceFileLoader("jiter", package_origin),
        origin=package_origin,
        is_package=True,
    )
    fake_package.__spec__.submodule_search_locations = list(package.__path__)
    fake_extension = ModuleType("jiter.jiter")
    fake_extension.__spec__ = ModuleSpec(
        "jiter.jiter",
        loader=ExtensionFileLoader("jiter.jiter", extension_origin),
        origin=extension_origin,
    )

    monkeypatch.delitem(sys.modules, "jiter.jiter", raising=False)
    monkeypatch.delitem(sys.modules, "jiter", raising=False)
    monkeypatch.delattr(package, "jiter", raising=False)
    with stub_modules({}):
        sys.modules["jiter"] = fake_package
        sys.modules["jiter.jiter"] = fake_extension
        fake_package.jiter = fake_extension

    assert sys.modules["jiter"] is fake_package
    assert sys.modules["jiter.jiter"] is fake_extension
    assert fake_package.jiter is fake_extension


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


def test_install_package_submodule_stubs_fills_an_empty_path_package(tmp_path: Path):
    """A new on-disk sibling resolves; a spy override and a retained real module stay."""

    pkg = tmp_path / "pkg"
    _write_pkg(pkg, "spy.py", "VALUE = 'disk'\n")
    _write_pkg(pkg, "unlisted.py", "VALUE = 'disk'\n")
    _write_pkg(pkg, "retained.py", "VALUE = 'real'\n")

    retained_name = "synthetic_obs.retained"
    spec = importlib.util.spec_from_file_location(retained_name, pkg / "retained.py")
    assert spec is not None and spec.loader is not None
    retained = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retained)

    parent = ModuleType("synthetic_obs")
    parent.__path__ = []  # type: ignore[attr-defined]
    spy = ModuleType("synthetic_obs.spy")
    spy.record = "spy"  # type: ignore[attr-defined]

    names = (
        "synthetic_obs",
        "synthetic_obs.spy",
        "synthetic_obs.unlisted",
        retained_name,
    )
    prior = {name: sys.modules.get(name) for name in names}
    saved: dict = {}
    try:
        sys.modules["synthetic_obs"] = parent
        sys.modules[retained_name] = retained
        install_package_submodule_stubs(
            "synthetic_obs",
            saved,
            overrides={"synthetic_obs.spy": spy},
            directory=pkg,
        )
        assert sys.modules["synthetic_obs.unlisted"].__name__ == "synthetic_obs.unlisted"
        assert sys.modules["synthetic_obs.spy"] is spy
        assert sys.modules[retained_name] is retained
        assert parent.unlisted is sys.modules["synthetic_obs.unlisted"]
        assert parent.spy is spy
        assert parent.retained is retained
        assert saved["synthetic_obs.unlisted"] is None
        assert saved["synthetic_obs.spy"] is None
        assert retained_name not in saved
    finally:
        for name, module in prior.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
