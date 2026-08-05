"""Unit tests for the account-deletion claim/reconcile logic (migrated to the WP2 storage port).

Tests the P1/P2 race-condition fixes: a fresh ``pending``/``running`` marker (recently written by an
in-progress deletion) must NOT be claimed, while stale/failed markers are recovered. The transaction
body ``_claim_deletion_wipe_txn`` now takes a neutral transaction handle + logical path, so the tests
drive it with the in-memory FakeDocumentStore (which satisfies the same get/update surface). The
non-transactional ``get_pending_deletion_wipes`` and the public ``mark_user_deletion_billing_failed``
are exercised through the injected ``_store`` seam. Real-backend parity is covered by the live
contract test.
"""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault('ENCRYPTION_SECRET', 'test-secret-for-ci')

import database.users as users_db
from tests.store_fakes import FakeDocumentStore

_PATH = 'account_deletions/uid1'


def _run_claim(data, stale_after=timedelta(minutes=10), running_stale_after=timedelta(minutes=30)):
    """Run the claim transaction body against a FakeDocumentStore; return (result, final_status)."""
    store = FakeDocumentStore()
    if data is not None:
        store.set(_PATH, data)
    # FakeDocumentStore satisfies the neutral tx surface (get(path)/update(path, fields)).
    result = users_db._claim_deletion_wipe_txn(store, _PATH, stale_after, running_stale_after)
    final = store.get(_PATH).to_dict() if store.exists(_PATH) else None
    return result, final


def _run_billing(data, monkeypatch):
    store = FakeDocumentStore()
    if data is not None:
        store.set(_PATH, data)
    monkeypatch.setattr(users_db, '_store', lambda: store)
    result = users_db.mark_user_deletion_billing_failed('uid1', 'sub_123', 'stripe down')
    return result, store.get(_PATH).to_dict()


def _run_mark_completed(data):
    """Run the ported transition helper ``(tx, path)`` against a FakeDocumentStore (neutral seam)."""
    store = FakeDocumentStore()
    store.set(_PATH, data)
    result = users_db._mark_user_deletion_wipe_completed_txn(store, _PATH)
    return result, store.get(_PATH).to_dict()


def test_mark_completed_refuses_outstanding_late_vm_cleanup():
    result, doc = _run_mark_completed(
        {'wipe_status': 'running', 'late_agent_vm_cleanup': {'vmName': 'omi-agent-uid', 'zone': 'us-central1-a'}}
    )

    assert result is False
    assert doc['wipe_status'] == 'failed'


def test_mark_completed_commits_without_late_vm_cleanup():
    result, doc = _run_mark_completed({'wipe_status': 'running'})

    assert result is True
    assert doc['wipe_status'] == 'completed'


def test_mark_billing_failed_allows_pre_wipe_states(monkeypatch):
    result, doc = _run_billing({'uid': 'uid1', 'wipe_status': 'deleting_auth'}, monkeypatch)
    assert result is True
    assert doc['wipe_status'] == 'billing_failed'
    assert doc['billing_subscription_id'] == 'sub_123'
    assert doc['billing_error'] == 'stripe down'


def test_mark_billing_failed_does_not_clobber_actionable_or_terminal_wipes(monkeypatch):
    for status in ('pending', 'retrying', 'running', 'failed', 'completed'):
        result, doc = _run_billing({'uid': 'uid1', 'wipe_status': status}, monkeypatch)
        assert result is False
        assert doc['wipe_status'] == status  # unchanged


def test_claim_txn_skips_fresh_pending_marker():
    now = datetime.now(timezone.utc)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(seconds=30)})
    assert result is None
    assert doc['wipe_status'] == 'pending'  # not claimed


def test_claim_txn_claims_stale_pending_marker():
    now = datetime.now(timezone.utc)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(minutes=15)})
    assert result == 'uid1'
    assert doc['wipe_status'] == 'retrying'
    assert 'wipe_claimed_at' in doc


def test_claim_txn_claims_failed_marker():
    now = datetime.now(timezone.utc)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'failed', 'wipe_failed_at': now - timedelta(seconds=5)})
    assert result == 'uid1'
    assert doc['wipe_status'] == 'retrying'


def test_claim_txn_skips_fresh_retrying_claim():
    now = datetime.now(timezone.utc)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'retrying', 'wipe_claimed_at': now - timedelta(seconds=30)})
    assert result is None


def test_claim_txn_skips_queued_retrying_claim():
    now = datetime.now(timezone.utc)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'retrying', 'wipe_claimed_at': now - timedelta(minutes=15)})
    assert result is None


def test_claim_txn_reclaims_stale_retrying_claim():
    now = datetime.now(timezone.utc)
    old_claimed = now - timedelta(minutes=45)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'retrying', 'wipe_claimed_at': old_claimed})
    assert result == 'uid1'
    assert doc['wipe_status'] == 'retrying'  # already retrying, status unchanged
    assert doc['wipe_claimed_at'] > old_claimed  # only the claim timestamp was refreshed


def test_claim_txn_returns_none_for_missing_doc():
    result, doc = _run_claim(None)
    assert result is None
    assert doc is None


def test_claim_txn_returns_none_for_unknown_status():
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'completed', 'wipe_completed_at': datetime.now(timezone.utc)})
    assert result is None
    assert doc['wipe_status'] == 'completed'


def test_claim_txn_skips_fresh_running_marker():
    now = datetime.now(timezone.utc)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'running', 'wipe_running_at': now - timedelta(minutes=12)})
    assert result is None


def test_claim_txn_claims_stale_running_marker():
    now = datetime.now(timezone.utc)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'running', 'wipe_running_at': now - timedelta(minutes=45)})
    assert result == 'uid1'
    assert doc['wipe_status'] == 'retrying'


def test_claim_txn_skips_running_marker_near_stale_boundary():
    now = datetime.now(timezone.utc)
    result, doc = _run_claim({'uid': 'uid1', 'wipe_status': 'running', 'wipe_running_at': now - timedelta(minutes=29)})
    assert result is None


# --- get_pending_deletion_wipes over-fetch/age-filter (through the injected store) ---


def _populate(store, docs_by_status):
    for status, docs in docs_by_status.items():
        for data in docs:
            store.set(f"account_deletions/{data['uid']}", data)


def test_get_pending_deletion_wipes_finds_stale_after_fresh_window(monkeypatch):
    now = datetime.now(timezone.utc)
    store = FakeDocumentStore()
    _populate(
        store,
        {
            'pending': [
                {'uid': 'fresh1', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(seconds=30)},
                {'uid': 'fresh2', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(seconds=60)},
                {'uid': 'stale1', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(minutes=15)},
            ],
        },
    )
    monkeypatch.setattr(users_db, '_store', lambda: store)
    result = users_db.get_pending_deletion_wipes(limit=100, stale_after=timedelta(minutes=10))
    uids = [r['uid'] for r in result]
    assert 'stale1' in uids
    assert 'fresh1' not in uids and 'fresh2' not in uids


def test_get_pending_deletion_wipes_respects_limit_with_over_fetch(monkeypatch):
    now = datetime.now(timezone.utc)
    store = FakeDocumentStore()
    _populate(
        store,
        {
            'failed': [
                {'uid': 'fail1', 'wipe_status': 'failed'},
                {'uid': 'fail2', 'wipe_status': 'failed'},
            ],
            'pending': [
                {'uid': 'stale1', 'wipe_status': 'pending', 'wipe_queued_at': now - timedelta(minutes=15)},
            ],
        },
    )
    monkeypatch.setattr(users_db, '_store', lambda: store)
    result = users_db.get_pending_deletion_wipes(limit=2, stale_after=timedelta(minutes=10))
    assert {r['uid'] for r in result} == {'fail1', 'fail2'}
    assert len(result) == 2


def test_get_pending_deletion_wipes_includes_stale_running(monkeypatch):
    now = datetime.now(timezone.utc)
    store = FakeDocumentStore()
    _populate(
        store,
        {
            'running': [
                {'uid': 'live1', 'wipe_status': 'running', 'wipe_running_at': now - timedelta(minutes=12)},
                {'uid': 'crashed1', 'wipe_status': 'running', 'wipe_running_at': now - timedelta(hours=7)},
            ],
        },
    )
    monkeypatch.setattr(users_db, '_store', lambda: store)
    result = users_db.get_pending_deletion_wipes(limit=100)
    uids = [r['uid'] for r in result]
    assert 'crashed1' in uids
    assert 'live1' not in uids
