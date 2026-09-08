"""Import isolation must not depend on which test file ran first.

Regression guard for a cross-file pollution bug that cost one test 66 minutes.

`database.notifications` binds its Firestore handle at import time
(`from ._client import db`), so replacing `sys.modules["database._client"]` later
cannot reach an already-imported copy. `install_ws_i_heavy_import_stubs()`
deliberately will not displace a real module -- other callers depend on the real one
surviving -- so a caller that needs the stub to win must evict it first.

When that eviction was missing, `test_memory_replace_policy.py` ran in 0.36s alone
and 3953s after `test_working_observations_extractor.py`: `_extract_memories_canonical`
reached the real `get_user_time_zone`, hit a live Firestore client, and sat in
`google.api_core` retry backoff. It PASSED either way, so nothing failed -- only the
clock showed it, and CI runs files in separate processes, which is exactly why it
stayed invisible.
"""

from __future__ import annotations

import sys

from tests.unit.memory_import_isolation import (
    CLIENT_BINDING_DATABASE_MODULES,
    WS_I_HEAVY_STUB_MODULE_NAMES,
    drop_client_binding_modules,
    install_ws_i_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

_TARGET = "database.notifications"
_SNAPSHOT = [*CLIENT_BINDING_DATABASE_MODULES, *WS_I_HEAVY_STUB_MODULE_NAMES, "database._client"]


def test_drop_then_install_stubs_a_module_that_was_imported_first():
    saved = snapshot_sys_modules(_SNAPSHOT)
    try:
        import database.notifications  # noqa: F401  (populate sys.modules first)

        assert getattr(sys.modules[_TARGET], "__file__", None) is not None

        drop_client_binding_modules()
        install_ws_i_heavy_import_stubs()

        assert getattr(sys.modules[_TARGET], "__file__", None) is None
    finally:
        restore_sys_modules(saved)


def test_drop_clears_the_parent_package_attribute_too():
    """`import a.b as c` reads getattr(a, "b") before falling back to sys.modules."""
    saved = snapshot_sys_modules(_SNAPSHOT)
    try:
        import database
        import database.notifications  # noqa: F401

        drop_client_binding_modules()
        install_ws_i_heavy_import_stubs()

        # A stale parent attribute would hand back the real module and silently
        # defeat the stub even though sys.modules looks correct.
        assert getattr(database, "notifications") is sys.modules[_TARGET]
        assert getattr(getattr(database, "notifications"), "__file__", None) is None
    finally:
        restore_sys_modules(saved)


def test_install_alone_still_preserves_an_already_imported_real_module():
    """Other callers rely on this: install must not displace a real module."""
    saved = snapshot_sys_modules(_SNAPSHOT)
    try:
        import database.notifications  # noqa: F401

        real = sys.modules[_TARGET]
        install_ws_i_heavy_import_stubs()

        assert sys.modules[_TARGET] is real
    finally:
        restore_sys_modules(saved)
