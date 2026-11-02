"""Lost BYOK ownership returns to user-reconnect waiting, without task dispatch."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import conversation_finalization_jobs as jobs
from services import conversation_finalization as service
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
    StrictFirestoreTransaction,
)

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
STALE = timedelta(seconds=300)


@pytest.fixture(autouse=True)
def finalization_fixture_metadata(monkeypatch):
    """Adapt snapshot metadata and projection merge; retain strict read ordering.

    The shared fixture intentionally omits snapshot IDs and merge-set. These
    finalizer tests need metadata and atomic numeric projection transforms only.
    """
    original_get = StrictFirestoreDocument.get
    original_set = StrictFirestoreTransaction.set
    original_update = StrictFirestoreTransaction.update

    def get(ref, *args, **kwargs):
        snapshot = original_get(ref, *args, **kwargs)
        snapshot.id = ref.id
        snapshot.reference = ref
        return snapshot

    def set_projection(txn, ref, data, *, merge=False):
        if not merge:
            return original_set(txn, ref, data)
        assert ref.path[0] == jobs.FINALIZATION_PROJECTION_COLLECTION
        txn._assert_reference_belongs(ref)
        txn.has_written = True
        txn.sets.append((ref.path, data))
        row = txn._database.rows.setdefault(ref.path, {})
        for key, value in data.items():
            row[key] = row.get(key, 0) + value.value if isinstance(value, jobs.firestore.Increment) else value

    def update_with_field_deletion(txn, ref, data):
        original_update(txn, ref, data)
        # Model the SDK result, so repeated claims see the due index absent.
        for key, value in data.items():
            if value is jobs.firestore.DELETE_FIELD:
                txn._database.rows[ref.path].pop(key, None)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(StrictFirestoreTransaction, 'set', set_projection)
    monkeypatch.setattr(StrictFirestoreTransaction, 'update', update_with_field_deletion)


def store_job(status='leased', **extra):
    store = StrictFirestore()
    ref = store.collection(jobs.FINALIZATION_JOBS_COLLECTION).document('job')
    store.rows[ref.path] = {
        'status': status,
        'requires_byok': True,
        'dispatch_generation': 4,
        'lease_epoch': 2,
        'fanout_status': 'completed',
        'lease_expires_at': NOW - timedelta(seconds=1),
        'created_at': NOW - timedelta(days=3),
        'updated_at': NOW - STALE,
        'projection_generation': jobs.FINALIZATION_PROJECTION_GENERATION,
        'projection_shard': 0,
        **extra,
    }
    return store, ref


@pytest.mark.parametrize('status', ['queued', 'leased'])
def test_reclaim_projection_idempotency_and_stale_terminal_fence(status):
    store, ref = store_job(status)
    txn = store.transaction()
    projection = store.collection(jobs.FINALIZATION_PROJECTION_COLLECTION)
    intent = jobs._claim_finalization_replay_txn(txn, ref, STALE, NOW, projection)
    assert intent['status'] == 'blocked_byok'
    assert not intent['created']
    data = ref.get().to_dict()
    assert data['lease_epoch'] == 3
    assert 'reconcile_after_at' not in data
    fields = txn.sets[0][1]
    assert fields[status].value == -1
    assert fields['blocked_byok'].value == 1
    repeat = store.transaction()
    jobs._claim_finalization_replay_txn(repeat, ref, STALE, NOW, projection)
    assert not repeat.updates and not repeat.sets
    assert jobs._claim_finalization_job_txn(store.transaction(), ref, 4, False, 1500, NOW)['status'] == 'blocked_byok'
    assert not jobs._mark_finalization_completed_txn(store.transaction(), ref, 4, 2, NOW, projection)
    # Public reconnect path returns the same generation to the live owner.
    resumed = jobs.resume_blocked_byok_job_for_live_session('job', firestore_client=store)
    assert resumed['status'] == 'queued'
    assert isinstance(ref.get().to_dict()['reconcile_after_at'], datetime)
    claim = jobs._claim_finalization_job_txn(
        store.transaction(), ref, 4, True, 1500, NOW, projection_collection=projection
    )
    assert claim['status'] == 'claimed' and claim['lease_epoch'] == 4
    assert ref.get().to_dict()['reconcile_after_at'] == NOW + timedelta(seconds=1500)
    assert not jobs._mark_finalization_completed_txn(store.transaction(), ref, 4, 2, NOW, projection)
    assert jobs._mark_finalization_completed_txn(store.transaction(), ref, 4, 4, NOW, projection)


@pytest.mark.parametrize(
    'status,extra',
    [
        ('leased', {'lease_expires_at': NOW + timedelta(seconds=1)}),
        ('leased', {'lease_expires_at': None}),
        ('queued', {'last_byok_resume_at': NOW - timedelta(seconds=1)}),
        ('queued', {'updated_at': NOW - timedelta(seconds=1)}),
    ],
)
def test_reclaim_preserves_live_or_unknown_ownership(status, extra):
    store, ref = store_job(status, **extra)
    txn = store.transaction()
    jobs._claim_finalization_replay_txn(txn, ref, STALE, NOW)
    assert not txn.updates


def test_non_byok_replay_and_recovery_filter():
    store, ref = store_job(requires_byok=False)
    txn = store.transaction()
    jobs._claim_finalization_replay_txn(txn, ref, STALE, NOW, byok_only=True)
    assert not txn.updates
    intent = jobs._claim_finalization_replay_txn(store.transaction(), ref, STALE, NOW)
    assert intent['created'] and intent['status'] == 'queued' and intent['dispatch_generation'] == 5


def test_byok_retry_keeps_due_timestamp():
    store, ref = store_job()
    assert jobs._mark_finalization_retryable_txn(store.transaction(), ref, 4, 2, 'failed', NOW)
    assert ref.get().to_dict()['reconcile_after_at'] == NOW + jobs.get_finalization_reconcile_stale_after()


def test_legacy_scan_rotates_and_reclaims_row_without_due_timestamp(monkeypatch):
    # Query seam verifies the existing indexed shape and bounded cursor, while
    # actual ownership writes use the strict document transaction fixture.
    store, ref = store_job()
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    snapshot = SimpleNamespace(id='job', reference=SimpleNamespace(path='/'.join(ref.path)), to_dict=ref.get().to_dict)
    query = Mock()
    query.order_by.return_value = query
    query.limit.return_value = query
    query.start_after.return_value = query
    query.stream.side_effect = [[snapshot], [], [], []]
    build = Mock(return_value=query)
    monkeypatch.setattr(jobs, 'FINALIZATION_OLDEST_NONTERMINAL_QUERY', SimpleNamespace(build=build))
    result = jobs.recover_stranded_byok_jobs(limit=1, firestore_client=store)
    assert result == {'scanned': 1, 'blocked': 1, 'errors': 0}
    assert ref.get().to_dict()['status'] == 'blocked_byok'
    jobs.recover_stranded_byok_jobs(limit=1000, firestore_client=store)
    assert [call.args[1] for call in build.call_args_list] == [
        {'status': 'queued'},
        {'status': 'leased'},
        {'status': 'queued'},
        {'status': 'leased'},
    ]
    assert [call.args[0] for call in query.limit.call_args_list] == [1, 1, 50, 50]
    query.start_after.assert_called_once()
    state = (
        store.collection(jobs.STALE_PROCESSING_SWEEP_STATE_COLLECTION).document('byok_reclaim_queued').get().to_dict()
    )
    assert state['resume_after_path'] is None and state['generation'] == 2


def test_recovery_runs_in_inline_mode_without_task_dispatch(monkeypatch):
    recover = Mock(return_value={'blocked': 0, 'errors': 0})
    enqueue = Mock()
    monkeypatch.setattr(service.jobs_db, 'recover_stranded_byok_jobs', recover)
    monkeypatch.setattr(service, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(service, '_publish_job_metrics', Mock())
    monkeypatch.setattr(service, 'enqueue_listen_finalization_job', enqueue)
    service.reconcile_listen_finalization_jobs()
    recover.assert_called_once()
    enqueue.assert_not_called()
