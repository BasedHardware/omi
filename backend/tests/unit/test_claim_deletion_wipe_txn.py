"""Unit tests for the _claim_deletion_wipe_txn transaction logic.

Tests the P1 race-condition fix: a fresh ``pending`` marker (recently
re-queued by a retrying delete request) must NOT be claimed inside the
transaction, because Firebase auth deletion may not have succeeded yet.

The real ``database.users`` module cannot be imported without Firestore
credentials (``_client.py`` calls ``firestore.Client()`` at module level),
so we stub only ``database._client`` before importing. Everything else in
``database.users`` is real Python that operates on the passed-in
transaction/doc_ref objects.
"""

import os
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

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
setattr(_fake_client_mod, 'document_id_from_seed', MagicMock())
_install_stub('database._client', _fake_client_mod)

# Stub database.firestore_cache and database.redis_db since database/users.py
# imports from them at module level, and they transitively require real clients.
for _mod_name in ('database.firestore_cache', 'database.redis_db'):
    _mod = types.ModuleType(_mod_name)
    for _attr in ('CachePolicy', 'get_or_fetch', 'invalidate', 'try_acquire_user_platform_write_lock'):
        setattr(_mod, _attr, MagicMock())
    _install_stub(_mod_name, _mod)

# Stub utils.subscription (imported at module level for get_default_basic_subscription)
_utils_sub = types.ModuleType('utils.subscription')
setattr(_utils_sub, 'get_default_basic_subscription', MagicMock())
_install_stub('utils.subscription', _utils_sub)

from database import users as users_db  # noqa: E402


@pytest.fixture(autouse=True, scope='module')
def _restore_sys_modules():
    """Restore sys.modules entries this module stubbed.

    After all tests in this module finish, each stubbed name is either removed
    (if it was absent before) or restored to its prior object, so the stubs do
    not leak into later test modules in a multi-file pytest run.
    """
    yield
    for _name, _prior in _STUB_PRIORS.items():
        if _prior is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prior


def _make_snapshot(data):
    """Create a minimal mock snapshot object."""
    snap = types.SimpleNamespace()
    snap.exists = data is not None
    snap.to_dict = lambda: data
    snap.id = data.get('uid') if data else None
    return snap


def _make_txn():
    """Create a mock transaction that records update calls."""
    updates = []
    txn = types.SimpleNamespace()
    txn._updates = updates
    txn.update = lambda ref, fields: updates.append((ref, fields))
    return txn


def _run_claim(data, stale_after=timedelta(minutes=10)):
    """Run the claim transaction with given doc data, return (result, updates).

    The @transactional decorator wraps the raw function in a _Transactional
    object. We access the raw function via .to_wrap and call it directly with
    lightweight mocks, avoiding the need for a real Firestore transaction.
    """
    txn = _make_txn()
    txn_obj = users_db._claim_deletion_wipe_txn
    raw_fn = getattr(txn_obj, 'to_wrap', txn_obj)
    snapshot = _make_snapshot(data)

    class FakeDocRef:
        def get(self, transaction=None):
            return snapshot

    result = raw_fn(txn, FakeDocRef(), stale_after)
    return result, txn._updates


def test_claim_txn_skips_fresh_pending_marker():
    """P1: a fresh pending marker (recently queued) must NOT be claimed.

    This is the exact race condition flagged in the review: the reconciler
    query returns a stale pending record, but by the time the transaction
    runs a new delete request has refreshed wipe_queued_at. Claiming it
    would enqueue a wipe before Firebase auth deletion has succeeded.
    """
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'pending',
        'wipe_queued_at': now - timedelta(seconds=30),  # fresh: only 30s old
    }
    result, updates = _run_claim(data)
    assert result is None
    assert len(updates) == 0  # no transaction.update called


def test_claim_txn_claims_stale_pending_marker():
    """A stale pending marker (older than stale_after) IS claimed."""
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'pending',
        'wipe_queued_at': now - timedelta(minutes=15),  # stale: 15min old
    }
    result, updates = _run_claim(data)
    assert result == 'uid1'
    assert len(updates) == 1
    assert updates[0][1]['wipe_status'] == 'retrying'
    assert 'wipe_claimed_at' in updates[0][1]


def test_claim_txn_claims_failed_marker():
    """A failed marker is always claimable regardless of age."""
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'failed',
        'wipe_failed_at': now - timedelta(seconds=5),  # recent failure
    }
    result, updates = _run_claim(data)
    assert result == 'uid1'
    assert updates[0][1]['wipe_status'] == 'retrying'


def test_claim_txn_skips_fresh_retrying_claim():
    """A retrying claim that is not stale is refused."""
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'retrying',
        'wipe_claimed_at': now - timedelta(seconds=30),  # fresh claim
    }
    result, updates = _run_claim(data)
    assert result is None
    assert len(updates) == 0


def test_claim_txn_reclaims_stale_retrying_claim():
    """A retrying claim older than stale_after is re-claimed."""
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'retrying',
        'wipe_claimed_at': now - timedelta(minutes=15),  # stale claim
    }
    result, updates = _run_claim(data)
    assert result == 'uid1'
    # Only updates wipe_claimed_at (doesn't re-set wipe_status, already retrying)
    assert 'wipe_status' not in updates[0][1]
    assert 'wipe_claimed_at' in updates[0][1]


def test_claim_txn_returns_none_for_missing_doc():
    """A non-existent document returns None."""
    result, updates = _run_claim(None)
    assert result is None
    assert len(updates) == 0


def test_claim_txn_returns_none_for_unknown_status():
    """An unknown status (e.g. 'completed', 'cancelled') returns None."""
    data = {
        'uid': 'uid1',
        'wipe_status': 'completed',
        'wipe_completed_at': datetime.now(timezone.utc),
    }
    result, updates = _run_claim(data)
    assert result is None
    assert len(updates) == 0
