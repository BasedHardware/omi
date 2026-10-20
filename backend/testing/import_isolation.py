"""Sanctioned import-isolation primitives for backend tests.

WHY this exists: the backend unit suite must run in a single pytest process, and the
old pattern (mutating ``sys.modules`` at module scope) leaks fakes across tests. This
module provides the *only* sanctioned mechanisms for the rare residual cases where
faking a dependency is genuinely required after Tier-1 (import purity) has done its
job. See ``backend/docs/test_isolation.md`` and
``.coordination/test-isolation/DECISIONS.md`` D2.

TWO mechanisms, in priority order:

1. **Preferred: ``monkeypatch.setattr`` on a lazy-held singleton** (Tier 1 + Tier 2).
   If production code defers client construction into a lazy getter, tests inject a
   fake by patching the module attribute — NOT by replacing ``sys.modules``. This is
   pytest-native, auto-restored at fixture teardown, and correct by construction. No
   helper here is required for this path.

2. **Reserve only: ``stub_modules`` context manager** — for the rare case a fake must
   be active *before* the target module imports. It snapshots the affected
   ``sys.modules`` entries and parent-package attributes, installs fakes, and restores
   on exit. It is NOT for module-scope use in test files (the static checker bans
   that); it is for use inside fixtures/functions.

``AutoMockModule`` is a factory for import-complete stub modules (missing attributes
resolve to ``MagicMock``). It is the sanctioned replacement for ad-hoc
``types.ModuleType`` stubs.

NOTE: the legacy ``tests/unit/memory_import_isolation.py`` is deprecated (DECISIONS
D3). Do not extend it; migrate its consumers to the mechanisms here.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from importlib.machinery import ExtensionFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Iterator, Mapping
from unittest.mock import MagicMock


class AutoMockModule(ModuleType):
    """Import-complete stub module: unknown attributes resolve to ``MagicMock``.

    Unlike a bare ``types.ModuleType`` (which raises ``AttributeError`` on unknown
    attrs), an ``AutoMockModule`` lets a transitively-imported chain succeed without
    the real dependency. Use via ``stub_modules`` or instantiate directly inside a
    fixture scope.
    """

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _has_existing_file_origin(module: ModuleType | None) -> bool:
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None) if spec else None
    return isinstance(origin, str) and Path(origin).is_file()


def _is_existing_extension_module(module: ModuleType | None) -> bool:
    spec = getattr(module, "__spec__", None)
    loader = getattr(spec, "loader", None) if spec else None
    return isinstance(loader, ExtensionFileLoader) and _has_existing_file_origin(module)


def install_auto_mock_modules(names: Iterable[str]) -> None:
    """Stub each top-level dependency with an ``AutoMockModule`` before an import.

    Module-import-time companion to :func:`stub_modules` for the residual case where
    the module under test imports optional dependencies eagerly and the stub must be
    present before that import runs. Prefer ``stub_modules`` (fixture scope) when the
    import does not need the fakes up front; the static checker bans direct
    module-scope ``sys.modules`` writes in test files, so route through here instead.
    """
    for name in names:
        if name not in sys.modules or not isinstance(sys.modules[name], AutoMockModule):
            sys.modules[name] = AutoMockModule(name)


def _set_parent_attr(name: str, module: ModuleType | None) -> None:
    if "." not in name:
        return
    parent_name, child_name = name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if isinstance(parent, ModuleType):
        if module is None:
            if getattr(parent, child_name, None) is not None:
                delattr(parent, child_name)
        else:
            setattr(parent, child_name, module)


@contextmanager
def stub_modules(mapping: dict[str, ModuleType | None]) -> Iterator[None]:
    """Temporarily install fake modules into ``sys.modules`` and restore on exit.

    Snapshots the prior state of each name (present/absent) and the parent package's
    attribute, installs the provided modules, and restores everything on exit —
    including deleting entries that were absent before and repairing parent attrs.

    It ALSO snapshots the FULL ``sys.modules`` mapping (key -> object) at entry and
    restores it on teardown: newly-added keys are evicted except for exact names in
    the explicit import-safety allowlist, and existing keys whose object was swapped
    (e.g. by ``load_module_fresh`` re-exec'ing a module against the fakes) are
    restored to the original object. Explicit fakes are restored and backend-owned
    modules are always evicted, so a stub-fed backend copy never leaks to later
    test files.

    Use ONLY inside a function/fixture scope (never at module scope in a test file —
    the static checker bans that). For most test seams prefer ``monkeypatch.setattr``
    on a lazy-held singleton instead (see module docstring).

    Example::

        with stub_modules({"database.vector_db": AutoMockModule("database.vector_db")}):
            from routers.memories import router  # picks up the fake
    """
    # Explicit per-name state for the requested fakes (presence + parent attr).
    saved: dict[str, ModuleType | None] = {name: sys.modules.get(name) for name in mapping}
    saved_parent_attrs: dict[str, ModuleType | None] = {name: _get_parent_attr(name) for name in mapping}
    # Full-process snapshot so we can also restore *objects* that were swapped in
    # place (load_module_fresh) — not just absent keys.
    saved_modules: dict[str, ModuleType] = dict(sys.modules)
    saved_keys: set[str] = set(saved_modules)
    # Parent-attr values for every submodule present at entry, so that attrs added
    # during the block (for keys absent at entry) can be distinguished and cleared.
    saved_submodule_attrs: dict[str, ModuleType | None] = {
        name: _get_parent_attr(name) for name in saved_keys if "." in name
    }
    try:
        for name, module in mapping.items():
            if module is None:
                sys.modules.pop(name, None)
                # Also drop the parent-package attribute so ``pkg.child`` does not
                # resolve to the original module via attribute access.
                _set_parent_attr(name, None)
            else:
                sys.modules[name] = module
                _set_parent_attr(name, module)
        yield
    finally:
        # 1. Restore each explicitly-faked name + its parent attr.
        for name in mapping:
            original = saved.get(name)
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
            prior_parent = saved_parent_attrs.get(name)
            if prior_parent is None:
                _set_parent_attr(name, None)
            else:
                _set_parent_attr(name, prior_parent)
        # 2. Evict any module keys that appeared during the block (e.g. a module
        #    exec'd via load_module_fresh against the fakes) and clear the parent
        #    attribute each one set, so a stub-fed version never leaks to later files.
        # Preserve only these exact families. Jiter's source package must remain
        # paired with its extension because its initializer binds the child module;
        # the listed Google modules register descriptors in protobuf's global pool.
        # Add future native families explicitly rather than discovering .so files.
        _extension_family_companions = {
            "google": (
                "google._upb._message",
                "proto",
                "google.ai.generativelanguage_v1beta.types.cache_service",
                "google.ai.generativelanguage_v1beta.types.cached_content",
                "google.ai.generativelanguage_v1beta.types.citation",
                "google.ai.generativelanguage_v1beta.types.content",
                "google.ai.generativelanguage_v1beta.types.discuss_service",
                "google.ai.generativelanguage_v1beta.types.file",
                "google.ai.generativelanguage_v1beta.types.file_service",
                "google.ai.generativelanguage_v1beta.types.generative_service",
                "google.ai.generativelanguage_v1beta.types.model",
                "google.ai.generativelanguage_v1beta.types.model_service",
                "google.ai.generativelanguage_v1beta.types.permission",
                "google.ai.generativelanguage_v1beta.types.permission_service",
                "google.ai.generativelanguage_v1beta.types.prediction_service",
                "google.ai.generativelanguage_v1beta.types.retriever",
                "google.ai.generativelanguage_v1beta.types.retriever_service",
                "google.ai.generativelanguage_v1beta.types.safety",
                "google.ai.generativelanguage_v1beta.types.text_service",
                "google.ai.generativelanguage_v1beta.types.tuned_model",
            ),
            "jiter": ("jiter", "jiter.jiter"),
        }
        extra_names = list(sys.modules.keys() - saved_keys)
        preserve_for_import_safety: set[str] = set()
        extra_name_set = set(extra_names)
        google_extension_loaded = _is_existing_extension_module(sys.modules.get("google._upb._message"))
        jiter_extension_loaded = _is_existing_extension_module(sys.modules.get("jiter.jiter"))
        if google_extension_loaded:
            for companion_name in _extension_family_companions["google"]:
                if companion_name in extra_name_set and _has_existing_file_origin(sys.modules.get(companion_name)):
                    preserve_for_import_safety.add(companion_name)
        if jiter_extension_loaded:
            for companion_name in _extension_family_companions["jiter"]:
                if companion_name not in extra_name_set:
                    continue
                companion = sys.modules.get(companion_name)
                if companion_name == "jiter.jiter":
                    if _is_existing_extension_module(companion):
                        preserve_for_import_safety.add(companion_name)
                elif _has_existing_file_origin(companion):
                    preserve_for_import_safety.add(companion_name)
        for extra in extra_names:
            if extra in preserve_for_import_safety:
                continue
            _clear_parent_attr_if_added(extra, saved_submodule_attrs)
            sys.modules.pop(extra, None)
        # 3. Restore existing keys whose object was swapped in place (load_module_fresh
        #    overwrites sys.modules[name] for a key that already existed at entry).
        for name, original in saved_modules.items():
            current = sys.modules.get(name)
            if current is not None and current is not original:
                sys.modules[name] = original
        # 4. Rebind submodules on the now-restored parent package objects.
        #
        # A mapping may replace both ``pkg.child`` and ``pkg`` in that order.
        # Installing the child first mutates the original ``pkg.child`` attribute;
        # restoring that attribute before restoring ``pkg`` only repairs the fake
        # parent and leaves the original parent pointing at the fake child.  String
        # monkeypatch targets then resolve through the stale parent attribute even
        # though ``sys.modules["pkg.child"]`` is correct.  Do this final pass only
        # after every module object is back in ``sys.modules``.
        for name, original_parent_attr in saved_submodule_attrs.items():
            _set_parent_attr(name, original_parent_attr)
        for name, original_parent_attr in saved_parent_attrs.items():
            _set_parent_attr(name, original_parent_attr)


def _get_parent_attr(name: str) -> ModuleType | None:
    if "." not in name:
        return None
    parent_name, child_name = name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if isinstance(parent, ModuleType):
        return getattr(parent, child_name, None)
    return None


def _clear_parent_attr_if_added(name: str, saved_submodule_attrs: dict[str, ModuleType | None]) -> None:
    """Delete a parent-package child attribute that was added during a stub block.

    ``name`` is a module key that was absent at entry (being evicted), so its parent
    attribute was absent too under normal Python import semantics. Clear it so the
    submodule does not leak via attribute access. ``saved_submodule_attrs`` records
    per-submodule parent attrs at entry; absent entries mean "was not present" → safe
    to delete.
    """
    if "." not in name:
        return
    parent_name, child_name = name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if not isinstance(parent, ModuleType):
        return
    entry_attr = saved_submodule_attrs.get(name)
    current = getattr(parent, child_name, None)
    if current is None or current is entry_attr:
        return
    try:
        delattr(parent, child_name)
    except AttributeError:
        pass


def load_module_fresh(name: str, path: str) -> ModuleType:
    """Execute a module from ``path`` into ``sys.modules[name]`` fresh.

    Use inside a ``stub_modules`` block when the target module binds a dependency at
    import time (e.g. ``from database._client import db``) and must therefore be
    re-exec'd against the fake. Drops any prior cached instance first so the exec
    always runs against the current (faked) ``sys.modules``.

    Example::

        with stub_modules({"database._client": fake_client, "google.cloud.firestore": fake}):
            goals = load_module_fresh("database.goals", "database/goals.py")
    """
    import importlib.util

    sys.modules.pop(name, None)
    # Do NOT pass submodule_search_locations: passing it (even []) marks the module
    # as a package, which corrupts ``__package__`` and breaks relative imports
    # (e.g. ``from ._client import db`` in database/*.py would resolve to the wrong
    # dotted name). A regular module load inherits the correct parent package.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Stdlib-only relevance policy that sync intake and the pipeline import at module
# scope. Harnesses that replace ``utils.conversations`` with a stub register the
# real files so the policy under test is production's, never a copy.
PURE_RELEVANCE_MODULES = (
    'utils.conversations.processing_trigger',
    'utils.conversations.relevance_circuit',
    'utils.conversations.relevance_rules',
    'utils.conversations.relevance',
    'utils.conversations.fragment_visibility',
)


def register_pure_relevance_modules(saved_modules: dict[str, ModuleType | None]) -> None:
    """Exec the real relevance modules into ``sys.modules``, saving priors for restore."""
    backend = Path(__file__).resolve().parents[1]
    for name in PURE_RELEVANCE_MODULES:
        saved_modules.setdefault(name, sys.modules.get(name))
        load_module_fresh(name, str(backend.joinpath(*name.split('.')).with_suffix('.py')))


def fake_firestore_transactional(func):
    """Firestore ``transactional`` replacement for unit-test fake transactions.

    The production fallback in ``database.memory_non_active_routes`` exists only for
    environments where Firestore is unavailable. Tests that load the module against a
    fake Firestore module need the same transaction lifecycle contract without
    copying the wrapper body into each test file.
    """

    def wrapper(transaction, *args, **kwargs):
        if hasattr(transaction, "_begin"):
            transaction._begin()
        try:
            result = func(transaction, *args, **kwargs)
            if hasattr(transaction, "_commit"):
                transaction._commit()
            return result
        except Exception:
            if hasattr(transaction, "_rollback"):
                transaction._rollback()
            raise
        finally:
            if hasattr(transaction, "_clean_up"):
                transaction._clean_up()

    return wrapper


def _dotted_parts(package: str) -> list[str]:
    """Split a dotted package name, rejecting path-escape and non-identifier segments."""

    parts = package.split(".")
    if not parts or any(not part.isidentifier() for part in parts):
        raise LookupError(f"package_submodule_stubs: {package!r} is not a dotted package name")
    return parts


def _package_directory(package: str) -> Path:
    """Resolve a dotted package to its directory on disk, ignoring ``sys.modules``.

    Deliberately does NOT use ``importlib.util.find_spec``: inside a ``stub_modules``
    block the package may already be a stub whose ``__spec__`` is ``None``, so spec
    lookup would report the fake instead of the real tree. This file lives at
    ``backend/testing/import_isolation.py``, so ``parent.parent`` is the backend root
    and joining the dotted name is the honest source — independent of cwd and of
    whatever is currently in ``sys.modules``.
    """

    backend_root = Path(__file__).resolve().parent.parent
    return backend_root.joinpath(*_dotted_parts(package))


def _skip_directory_entry(name: str) -> bool:
    """Skip hidden and dunder entries; keep ``_``-prefixed modules.

    A router can ``from pkg._private import X``. Treating an underscore as an opt-out
    would recreate the hand-list failure for those modules. ``__init__.py`` and
    ``__pycache__`` still drop out because they start with ``__``.
    """

    return name.startswith(".") or name.startswith("__")


def _enumerate_submodules(package: str, directory: Path) -> dict[str, bool]:
    """Map dotted child names to ``is_package``, walking nested packages.

    Sub-packages are included so a later ``from pkg.child.leaf import X`` can resolve
    against stubs in ``sys.modules``. They must present as packages (empty ``__path__``)
    *and* have their children stubbed: empty ``__path__`` prevents the import system
    from loading the real nested module off disk.
    """

    found: dict[str, bool] = {}
    for entry in sorted(directory.iterdir(), key=lambda path: path.name):
        if _skip_directory_entry(entry.name):
            continue
        if entry.is_dir():
            child = f"{package}.{entry.name}"
            nested = _enumerate_submodules(child, entry)
            if nested or (entry / "__init__.py").is_file():
                found[child] = True
                found.update(nested)
        elif entry.is_file() and entry.suffix == ".py":
            found[f"{package}.{entry.stem}"] = False
    return found


def package_submodule_stubs(
    package: str,
    *,
    extra: Iterable[str] = (),
    include_package: bool = True,
    directory: Path | None = None,
) -> dict[str, ModuleType]:
    """Derive a stub set from a package's real submodules instead of hand-listing them.

    WHY this exists: a hand-maintained list of module names drifts silently. The next
    module added to the package is absent from the list, and every suite that stubs
    that package fails at *collection* with ``ModuleNotFoundError`` — which reads as a
    product bug rather than a stale fixture, and which the module's author discovers in
    CI rather than the fixture's owner discovering it locally. This is
    ``FC-hand-listed-test-isolation-membership`` in the backend.

    The membership is derived from the source signal — what actually sits in the
    package directory — and then unioned with ``extra``, so naming something
    explicitly is still allowed but omitting it is not an opt-out.

    Submodules are enumerated from disk and never imported, so no package side effect
    runs. Sub-packages are stubbed with an empty ``__path__`` so they present as
    packages and can themselves parent further stubs, without the import system
    searching the real tree.

    ``directory`` overrides the on-disk location (tests); the dotted ``package`` is
    still the stub identity. The default resolves under the backend root without
    consulting ``sys.modules``.

    Example::

        fakes = package_submodule_stubs("utils.conversations")
        with stub_modules(fakes):
            from routers.conversations import router
    """

    _dotted_parts(package)
    package_dir = directory if directory is not None else _package_directory(package)
    if not package_dir.is_dir():
        raise LookupError(f"package_submodule_stubs: {package!r} is not a package directory ({package_dir})")

    stubs: dict[str, ModuleType] = {}

    def _stub(name: str, *, is_package: bool) -> ModuleType:
        module = AutoMockModule(name)
        if is_package:
            module.__path__ = []  # type: ignore[attr-defined]
        return module

    if include_package:
        stubs[package] = _stub(package, is_package=True)

    for name, is_package in _enumerate_submodules(package, package_dir).items():
        stubs[name] = _stub(name, is_package=is_package)

    for name in extra:
        if name not in stubs:
            stubs[name] = _stub(name, is_package=False)

    return stubs


def install_package_submodule_stubs(
    package: str,
    saved_modules: dict[str, Any],
    *,
    overrides: Mapping[str, ModuleType] | None = None,
    directory: Path | None = None,
) -> None:
    """Bind every on-disk submodule under a package stub whose ``__path__`` is empty.

    An empty ``__path__`` stops the import system from reading the real tree, so a
    hand-listed child set drifts: the next module added to ``package`` raises
    ``ModuleNotFoundError`` at collection. Membership comes from
    ``package_submodule_stubs``. ``overrides`` replace the auto-mock (harness spies).
    A child already loaded from a real file stays in ``sys.modules`` and is attached
    to the parent, so telemetry retained before the package stub survives.

    The parent must already sit in ``sys.modules``. Each name this function writes
    is recorded with ``setdefault``, so a caller that snapshotted the name earlier
    keeps that original for restore.
    """

    parent = sys.modules.get(package)
    if not isinstance(parent, ModuleType):
        raise LookupError(f"install_package_submodule_stubs: {package!r} is not an installed module")

    chosen = dict(overrides or {})
    for name in chosen:
        if not name.startswith(package + "."):
            raise LookupError(f"install_package_submodule_stubs: {name!r} is not a child of {package!r}")

    modules = package_submodule_stubs(package, include_package=False, directory=directory)
    modules.update(chosen)
    for name, module in modules.items():
        if name not in chosen:
            existing = sys.modules.get(name)
            if _has_existing_file_origin(existing):
                _set_parent_attr(name, existing)
                continue
        saved_modules.setdefault(name, sys.modules.get(name))
        sys.modules[name] = module
        _set_parent_attr(name, module)


__all__ = [
    "AutoMockModule",
    "stub_modules",
    "load_module_fresh",
    "fake_firestore_transactional",
    "package_submodule_stubs",
    "install_package_submodule_stubs",
]
