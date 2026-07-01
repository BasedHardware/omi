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
import types
from contextlib import contextmanager
from types import ModuleType
from typing import Iterator
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

    It ALSO snapshots the full set of ``sys.modules`` keys at entry and evicts any
    keys added during the block on teardown. This is what makes a fixture hermetic:
    modules freshly loaded/exec'd while the fakes were active (e.g. via
    ``load_module_fresh``) are removed afterwards so subsequent test files see the
    *real* module (or no module), never a stub-fed version left behind.

    Use ONLY inside a function/fixture scope (never at module scope in a test file —
    the static checker bans that). For most test seams prefer ``monkeypatch.setattr``
    on a lazy-held singleton instead (see module docstring).

    Example::

        with stub_modules({"database.vector_db": AutoMockModule("database.vector_db")}):
            from routers.memories import router  # picks up the fake
    """
    saved: dict[str, ModuleType | None] = {name: sys.modules.get(name) for name in mapping}
    saved_parent_attrs: dict[str, ModuleType | None] = {name: _get_parent_attr(name) for name in mapping}
    saved_keys: set[str] = set(sys.modules)
    try:
        for name, module in mapping.items():
            if module is None:
                sys.modules.pop(name, None)
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
        #    exec'd via load_module_fresh against the fakes). This prevents a
        #    stub-fed version of a real module from leaking to later test files.
        for extra in list(sys.modules.keys() - saved_keys):
            sys.modules.pop(extra, None)


def _get_parent_attr(name: str) -> ModuleType | None:
    if "." not in name:
        return None
    parent_name, child_name = name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if isinstance(parent, ModuleType):
        return getattr(parent, child_name, None)
    return None


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


__all__ = ["AutoMockModule", "stub_modules", "load_module_fresh"]
