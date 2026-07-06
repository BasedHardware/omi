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
setattr(_fake_client_mod, 'document_id_from_seed', MagicMock())
_install_stub('database._client', _fake_client_mod)

# Stub database.firestore_cache and database.redis_db since database/users.py
# imports from them at module level, and they transitively require real clients.
for _mod_name in ('database.firestore_cache', 'database.redis_db'):
    _mod = types.ModuleType(_mod_name)
    for _attr in (
        'CachePolicy',
        'get_or_fetch',
        'invalidate',
        'try_acquire_client_device_write_lock',
        'try_acquire_user_platform_write_lock',
    ):
        setattr(_mod, _attr, MagicMock())
    _install_stub(_mod_name, _mod)

# Stub utils.subscription (imported at module level for get_default_basic_subscription)
_utils_sub = types.ModuleType('utils.subscription')
setattr(_utils_sub, 'get_default_basic_subscription', MagicMock())
_install_stub('utils.subscription', _utils_sub)

# database.users is imported against the stubs above, so record its prior
# sys.modules entry now; the autouse fixture below restores/removes it so the
# half-stubbed module does not leak into other unit-test modules.
if 'database.users' not in _STUB_PRIORS:
    _STUB_PRIORS['database.users'] = sys.modules.get('database.users')

from database import users as users_db  # noqa: E402

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
if _db_pkg is not None and hasattr(_db_pkg, 'users'):
    delattr(_db_pkg, 'users')


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
    sets = []
    txn = types.SimpleNamespace()
    txn._updates = updates
    txn._sets = sets
    txn.update = lambda ref, fields: updates.append((ref, fields))
    txn.set = lambda ref, fields, **kwargs: sets.append((ref, fields, kwargs))
    return txn


def _run_claim(data, stale_after=timedelta(minutes=10), running_stale_after=timedelta(minutes=30)):
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

    result = raw_fn(txn, FakeDocRef(), stale_after, running_stale_after)
    return result, txn._updates


def _run_mark_billing_failed(data):
    txn = _make_txn()
    txn_obj = users_db._mark_user_deletion_billing_failed_txn
    raw_fn = getattr(txn_obj, 'to_wrap', txn_obj)
    snapshot = _make_snapshot(data)

    class FakeDocRef:
        def get(self, transaction=None):
            return snapshot

    result = raw_fn(txn, FakeDocRef(), 'uid1', 'sub_123', 'stripe down')
    return result, txn._sets


def test_mark_billing_failed_allows_pre_wipe_states():
    result, sets = _run_mark_billing_failed({'uid': 'uid1', 'wipe_status': 'deleting_auth'})

    assert result is True
    assert len(sets) == 1
    _, fields, kwargs = sets[0]
    assert fields['wipe_status'] == 'billing_failed'
    assert fields['billing_subscription_id'] == 'sub_123'
    assert fields['billing_error'] == 'stripe down'
    assert kwargs == {'merge': True}


def test_mark_billing_failed_does_not_clobber_actionable_or_terminal_wipes():
    for status in ('pending', 'retrying', 'running', 'failed', 'completed'):
        result, sets = _run_mark_billing_failed({'uid': 'uid1', 'wipe_status': status})
        assert result is False
        assert sets == []


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


def test_claim_txn_skips_queued_retrying_claim():
    """A retrying claim that is stale for ``stale_after`` (10 min) but fresh
    for ``running_stale_after`` (30 min) is NOT re-claimed.

    This is the review fix: a queued-but-not-yet-running retrying claim
    should not be re-enqueued by the periodic reconciler.
    """
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'retrying',
        'wipe_claimed_at': now - timedelta(minutes=15),  # stale for 10 min, fresh for 30 min
    }
    result, updates = _run_claim(data)
    assert result is None
    assert len(updates) == 0


def test_claim_txn_reclaims_stale_retrying_claim():
    """A retrying claim older than ``running_stale_after`` (30 min) is re-claimed.

    The longer window is used because a retrying wipe was just claimed and
    enqueued; if the executor backlog is full the future may sit queued
    beyond the 10-min ``stale_after`` without transitioning to ``running``.
    """
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'retrying',
        'wipe_claimed_at': now - timedelta(minutes=45),  # stale: 45min > 30min running_stale_after
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


# ---------------------------------------------------------------------------
# running state tests (review P2: don't reclaim live wipes solely by age)
# ---------------------------------------------------------------------------


def test_claim_txn_skips_fresh_running_marker():
    """A fresh ``running`` marker belongs to a live worker — must NOT be claimed.

    This is the core fix for the review concern: a slow but live wipe should
    not be duplicate-claimed just because it has been running for a while.
    The ``running`` stale window (default 30 min) is much longer than the
    ``pending`` stale window (10 min).
    """
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'running',
        'wipe_running_at': now - timedelta(minutes=12),  # 12 min: stale for pending, fresh for running
    }
    result, updates = _run_claim(data)
    assert result is None
    assert len(updates) == 0


def test_claim_txn_claims_stale_running_marker():
    """A ``running`` marker older than ``running_stale_after`` IS claimed.

    The worker almost certainly crashed or the pod was killed mid-execution.
    """
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'running',
        'wipe_running_at': now - timedelta(minutes=45),  # 45 min: stale even for running window
    }
    result, updates = _run_claim(data)
    assert result == 'uid1'
    assert updates[0][1]['wipe_status'] == 'retrying'


def test_claim_txn_skips_running_marker_near_stale_boundary():
    """A ``running`` marker just under the stale boundary is NOT claimed.

    Uses 29 min to avoid sub-second timing flakiness with the default
    30 min ``running_stale_after``.
    """
    now = datetime.now(timezone.utc)
    data = {
        'uid': 'uid1',
        'wipe_status': 'running',
        'wipe_running_at': now - timedelta(minutes=29),  # 29 min: just under 30 min boundary
    }
    result, updates = _run_claim(data)
    assert result is None
    assert len(updates) == 0


# ---------------------------------------------------------------------------
# get_pending_deletion_wipes: over-fetch regression test (review P2)
# ---------------------------------------------------------------------------


class _FakeDocSnapshot:
    def __init__(self, data):
        self._data = data
        self.id = data.get('uid')

    def to_dict(self):
        return self._data


class _FakeCollection:
    """Minimal Firestore collection mock that streams a list of doc dicts."""

    def __init__(self, docs_by_status):
        # docs_by_status: {'pending': [...], 'failed': [...], 'retrying': [...]}
        self._docs_by_status = docs_by_status
        self._status = None

    def where(self, field, op, value):
        # Only equality filters are used in get_pending_deletion_wipes.
        assert op == '=='
        self._status = value
        return self

    def limit(self, n):
        # Should no longer be called for age-filtered queries after the fix.
        # Record it but still return all docs so the test is robust.
        return self

    def stream(self):
        for data in self._docs_by_status.get(self._status, []):
            yield _FakeDocSnapshot(data)


def test_get_pending_deletion_wipes_finds_stale_after_fresh_window():
    """P2: stale pending docs beyond a fresh window must not be skipped.

    Before the fix, ``.limit(budget)`` capped the query before the age filter,
    so a page of fresh ``pending`` docs hid stale records that needed recovery.
    After the fix the query over-fetches all docs of each status and ages them
    in Python, breaking as soon as ``limit`` actionable records are collected.
    """
    now = datetime.now(timezone.utc)
    stale_after = timedelta(minutes=10)

    docs_by_status = {
        'failed': [],
        'pending': [
            # Fresh pending docs come first — these would fill a tight limit.
            {'uid': 'fresh1', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(seconds=30)},
            {'uid': 'fresh2', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(seconds=60)},
            # Stale pending doc beyond the fresh window — must be returned.
            {'uid': 'stale1', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(minutes=15)},
        ],
        'retrying': [],
    }

    fake_collection = _FakeCollection(docs_by_status)
    fake_db = types.SimpleNamespace()
    fake_db.collection = lambda name: fake_collection

    with patch.object(users_db, 'db', fake_db):
        result = users_db.get_pending_deletion_wipes(limit=100, stale_after=stale_after)

    uids = [r['uid'] for r in result]
    assert 'stale1' in uids, 'stale pending record must be found past the fresh window'
    assert 'fresh1' not in uids
    assert 'fresh2' not in uids


def test_get_pending_deletion_wipes_respects_limit_with_over_fetch():
    """The limit is still honoured even when over-fetching: only ``limit``
    actionable records are returned (failed first, then stale pending)."""
    now = datetime.now(timezone.utc)
    stale_after = timedelta(minutes=10)

    docs_by_status = {
        'failed': [
            {'uid': 'fail1', 'wipe_status': 'failed'},
            {'uid': 'fail2', 'wipe_status': 'failed'},
        ],
        'pending': [
            {'uid': 'stale1', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(minutes=15)},
        ],
        'retrying': [],
    }

    fake_collection = _FakeCollection(docs_by_status)
    fake_db = types.SimpleNamespace()
    fake_db.collection = lambda name: fake_collection

    with patch.object(users_db, 'db', fake_db):
        result = users_db.get_pending_deletion_wipes(limit=2, stale_after=stale_after)

    uids = {r['uid'] for r in result}
    assert uids == {'fail1', 'fail2'}
    assert len(result) == 2


def test_get_pending_deletion_wipes_includes_stale_running():
    """Stale ``running`` records (worker crashed mid-execution) are recovered.

    A ``running`` marker older than ``running_stale_after`` (default 6 hours)
    is included so the reconciler can re-enqueue a wipe whose worker died.
    """
    now = datetime.now(timezone.utc)

    docs_by_status = {
        'failed': [],
        'pending': [],
        'running': [
            # Fresh running — worker is live, should NOT be recovered.
            {'uid': 'live1', 'wipe_status': 'running', 'wipe_running_at': now - timedelta(minutes=12)},
            # Stale running — worker probably crashed, SHOULD be recovered.
            {'uid': 'crashed1', 'wipe_status': 'running', 'wipe_running_at': now - timedelta(hours=7)},
        ],
        'retrying': [],
    }

    fake_collection = _FakeCollection(docs_by_status)
    fake_db = types.SimpleNamespace()
    fake_db.collection = lambda name: fake_collection

    with patch.object(users_db, 'db', fake_db):
        result = users_db.get_pending_deletion_wipes(limit=100)

    uids = [r['uid'] for r in result]
    assert 'crashed1' in uids, 'stale running record must be recovered'
    assert 'live1' not in uids, 'fresh running record must not be recovered'
