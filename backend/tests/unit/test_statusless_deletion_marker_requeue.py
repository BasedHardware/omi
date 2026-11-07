"""Tests for requeuing status-less account-deletion markers (one-shot, explicit operator path).

Uses the same stubbing as test_claim_deletion_wipe_txn.py so database.users imports
without Firestore credentials.
"""

import os
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault('ENCRYPTION_SECRET', 'test-secret-for-ci')

# ---------------------------------------------------------------------------
# Module stubbing with cleanup
# ---------------------------------------------------------------------------
# The real ``database.users`` module cannot be imported without Firestore
# credentials, so we install lightweight stubs for its transitive imports.
# We track every entry we touch so an autouse fixture can restore sys.modules
# after this module's tests finish — preventing the stubs from leaking into
# other unit tests in a multi-file pytest run (e.g. test_rate_limiting.py
# expects the real database.redis_db.check_rate_limit).
_STUB_PRIORS: dict[str, 'types.ModuleType | None'] = {}


def _install_stub(name, mod):
    """Install *mod* under *name*, remembering the prior sys.modules entry."""
    if name not in _STUB_PRIORS:
        _STUB_PRIORS[name] = sys.modules.get(name)
    sys.modules[name] = mod


# Stub database._client so firestore.Client() is never called at import time.
# We only need this for module load; the transaction function under test does
# not use the db singleton at all (it receives doc_ref as an argument).
_fake_client_mod = types.ModuleType('database._client')
setattr(_fake_client_mod, 'db', MagicMock())
setattr(_fake_client_mod, 'delete_collection_recursive', MagicMock())
setattr(_fake_client_mod, 'document_id_from_seed', MagicMock())
setattr(_fake_client_mod, 'get_firestore_client', MagicMock())
setattr(_fake_client_mod, 'get_data_plane_firestore_client', MagicMock())
setattr(_fake_client_mod, 'data_plane_db', getattr(_fake_client_mod, 'db'))
_install_stub('database._client', _fake_client_mod)

# Stub database.firestore_cache and database.redis_db since database/users.py
# imports from them at module level, and they transitively require real clients.
for _mod_name in ('database.firestore_cache', 'database.redis_db'):
    _mod = types.ModuleType(_mod_name)
    for _attr in (
        'CachePolicy',
        'get_or_fetch',
        'invalidate',
        'delete_cached_user_geolocation',
        'try_acquire_client_device_write_lock',
        'try_acquire_user_platform_write_lock',
    ):
        setattr(_mod, _attr, MagicMock())
    _install_stub(_mod_name, _mod)

# Stub utils.subscription (imported at module level for get_default_basic_subscription)
_utils_sub = types.ModuleType('utils.subscription')
setattr(_utils_sub, 'get_default_basic_subscription', MagicMock())
_install_stub('utils.subscription', _utils_sub)

# The deletion modules are imported against the stubs above, so record their prior
# sys.modules entry now; the autouse fixture below restores/removes it so the
# half-stubbed module does not leak into other unit-test modules.
for _module_name in ('database.account_deletion_grace', 'database.users'):
    if _module_name not in _STUB_PRIORS:
        _STUB_PRIORS[_module_name] = sys.modules.get(_module_name)

from database import users as users_db  # noqa: E402
from database import account_deletion_grace as deletion_grace_db  # noqa: E402

# Restore all stubbed sys.modules entries IMMEDIATELY after capturing the
# users_db reference. pytest imports/collects later test modules before any
# module-scoped fixture teardown runs, so if we waited for fixture teardown
# the half-stubbed entries (database._client, database.redis_db, etc.) would
# still be in sys.modules while later tests are collected, causing them to
# bind MagicMock-backed helpers instead of their own stubs or the real modules.
for _name, _prior in _STUB_PRIORS.items():
    if _prior is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _prior
_db_pkg = sys.modules.get('database')
if _db_pkg is not None:
    for _attribute in ('users', 'account_deletion_grace'):
        if hasattr(_db_pkg, _attribute):
            delattr(_db_pkg, _attribute)


def _make_snapshot(data):
    snap = types.SimpleNamespace()
    snap.exists = data is not None
    snap.to_dict = lambda: data
    snap.id = 'uid-1'
    return snap


def _make_txn():
    updates = []
    txn = types.SimpleNamespace()
    txn._updates = updates
    txn.update = lambda ref, fields: updates.append((ref, fields))
    return txn


def _run(data, generated='generated-job'):
    txn = _make_txn()
    raw_fn = getattr(
        users_db._requeue_statusless_deletion_marker_txn, 'to_wrap', users_db._requeue_statusless_deletion_marker_txn
    )
    snapshot = _make_snapshot(data)
    doc_ref = types.SimpleNamespace(get=lambda transaction=None: snapshot)
    result = raw_fn(txn, doc_ref, generated)
    return result, txn._updates


def test_statusless_marker_moves_to_pending_with_new_job_id():
    result, updates = _run({'uid': 'uid-1'})
    assert result == 'generated-job'
    assert len(updates) == 1
    fields = updates[0][1]
    assert fields['wipe_status'] == 'pending'
    assert fields['wipe_job_id'] == 'generated-job'
    assert isinstance(fields['wipe_queued_at'], datetime)


def test_statusless_marker_keeps_existing_job_id():
    result, updates = _run({'uid': 'uid-1', 'wipe_job_id': 'existing-job'})
    assert result == 'existing-job'
    assert updates[0][1]['wipe_job_id'] == 'existing-job'


def test_blank_status_is_treated_as_statusless():
    result, updates = _run({'wipe_status': '   '})
    assert result == 'generated-job'
    assert updates[0][1]['wipe_status'] == 'pending'


def test_marker_with_any_status_is_never_overwritten():
    for status in ('pending', 'running', 'completed', 'cancelled', 'failed', 'pending_deletion'):
        result, updates = _run({'wipe_status': status})
        assert result is None, status
        assert updates == [], status


def test_missing_marker_is_a_noop():
    result, updates = _run(None)
    assert result is None
    assert updates == []
