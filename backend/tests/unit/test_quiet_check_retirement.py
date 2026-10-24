"""Lifecycle retirement uses the latest owner, independent of worker generation."""

from datetime import datetime, timedelta, timezone

import pytest
from google.cloud import firestore

from database import conversations, conversation_quiet_checks as checks
from database import quiet_check_retirement as retirement
from database import conversation_finalization_jobs as jobs
from models.conversation_enums import ConversationStatus
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_conversation_finalization_jobs import _Ref, _Transaction
from utils.metrics import OMI_FALLBACK_TOTAL

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
ROW = ('users', 'synthetic', 'conversations', 'capture')
JOB = ('conversation_finalization_jobs', checks.quiet_check_id('synthetic', 'capture'))


def seeded(row=None):
    return StrictFirestore(
        {
            ROW: {'source': 'omi', 'status': 'in_progress', 'has_content': True, 'finished_at': NOW, **(row or {})},
            JOB: {
                'kind': 'listen_quiet_check',
                'status': 'waiting_quiet',
                'dispatch_generation': 7,
                'reconcile_after_at': NOW,
                'due_at': NOW,
            },
        }
    )


def assert_retired(store):
    assert store.rows[JOB]['status'] == 'quiet_done'
    # The narrow fixture preserves DELETE_FIELD; SDK deletion is covered in the emulator.
    assert store.rows[JOB]['reconcile_after_at'] is firestore.DELETE_FIELD
    assert store.rows[JOB]['dispatch_generation'] == 7


@pytest.mark.parametrize(
    'patch',
    [
        {'deleted': True},
        {'discarded': True},
        {'sync_merged_into': 'survivor'},
        {'status': 'processing'},
        {'status': 'completed'},
        {'status': 'failed'},
        {'status': 'merging'},
        {'finalization_job_id': 'processing-owner'},
    ],
)
def test_retire_latest_generation_for_nonlive_owner(patch):
    store = seeded(patch)
    assert retirement.stop_quiet_check_for_conversation('synthetic', 'capture', firestore_client=store)
    assert_retired(store)


def test_missing_owner_retires_without_creating_missing_jobs():
    store = seeded()
    del store.rows[ROW]
    assert retirement.stop_quiet_check_for_conversation('synthetic', 'capture', firestore_client=store)
    assert_retired(store)
    empty = StrictFirestore()
    assert not retirement.stop_quiet_check_for_conversation('synthetic', 'absent', firestore_client=empty)
    assert empty.rows == {}


def test_cleanup_after_reopen_preserves_successor_and_worker_generation_fence():
    store = seeded()
    assert not retirement.stop_quiet_check_for_conversation('synthetic', 'capture', firestore_client=store)
    checks.stop_quiet_check(JOB[-1], 6, firestore_client=store)
    assert store.rows[JOB]['status'] == 'waiting_quiet'
    assert store.rows[JOB]['dispatch_generation'] == 7


@pytest.mark.parametrize(
    'target', [ConversationStatus.processing, ConversationStatus.completed, ConversationStatus.failed]
)
def test_shared_status_claim_retires_quiet_check(monkeypatch, target):
    store = seeded()
    monkeypatch.setattr(conversations, 'db', store)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a: None)
    assert conversations.claim_conversation_status('synthetic', 'capture', ConversationStatus.in_progress, target)
    assert store.rows[ROW]['status'] == target.value
    assert_retired(store)


def test_refused_donor_arm_retires_old_check_and_counts_once():
    store = seeded({'sync_merged_into': 'survivor'})
    before = checks.ARM_METRICS['refused']._value.get()
    assert checks.arm_quiet_check('synthetic', 'capture', 120, firestore_client=store) is None
    assert checks.ARM_METRICS['refused']._value.get() == before + 1
    assert_retired(store)


def test_expected_vs_actual_reconnect_arms(monkeypatch):
    store = seeded()
    del store.rows[JOB]
    monkeypatch.setattr(checks, '_now', lambda: NOW)
    before = {key: metric._value.get() for key, metric in checks.ARM_METRICS.items()}
    checks.arm_quiet_check('synthetic', 'capture', 120, firestore_client=store)
    for _ in range(4):
        checks.arm_quiet_check('synthetic', 'capture', 120, firestore_client=store)
    actual = {key: metric._value.get() - before[key] for key, metric in checks.ARM_METRICS.items()}
    assert actual == {'created': 1, 'rearmed': 0, 'reused': 4, 'refused': 0}
    assert store.rows[JOB]['dispatch_generation'] == 1
    assert len([path for path in store.rows if path[0] == 'conversation_finalization_jobs']) == 1


@pytest.mark.parametrize('status', sorted(jobs.TERMINAL_JOB_STATUSES | {'blocked_byok'}))
def test_terminal_nonquiet_claim_clears_due_index(status):
    transaction = _Transaction()
    ref = _Ref(JOB[-1], {'kind': 'listen_finalization', 'status': status, 'reconcile_after_at': NOW})
    intent = jobs._claim_finalization_replay_txn(transaction, ref, timedelta(seconds=60), NOW)
    assert intent['status'] == status and not intent['created']
    assert transaction.updates == [(ref, {'reconcile_after_at': firestore.DELETE_FIELD, 'updated_at': NOW})]


@pytest.mark.parametrize('status', sorted(jobs.TERMINAL_JOB_STATUSES | {'blocked_byok'}))
def test_terminal_nonquiet_backoff_clears_index_and_preserves_newer_snapshot(monkeypatch, status):
    store = seeded()
    store.rows[JOB].update(kind='conversation_merge', status=status)
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    candidate = dict(store.rows[JOB], job_id=JOB[-1])
    assert jobs.defer_finalization_replay(candidate, firestore_client=store)
    assert store.rows[JOB]['reconcile_after_at'] is firestore.DELETE_FIELD
    store.rows[JOB].update(status='queued', dispatch_generation=8, reconcile_after_at=NOW)
    assert not jobs.defer_finalization_replay(candidate, firestore_client=store)
    assert store.rows[JOB]['reconcile_after_at'] == NOW


@pytest.mark.parametrize('failure_stage', ['read', 'write'])
def test_cleanup_failure_preserves_committed_processing_admission(monkeypatch, caplog, failure_stage):
    store = seeded()
    monkeypatch.setattr(conversations, 'db', store)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a: None)

    def fail(*args, **kwargs):
        raise RuntimeError('synthetic cleanup dependency failure')

    with monkeypatch.context() as fault:
        if failure_stage == 'read':
            # Initial quiet-job read fails before cleanup can start a transaction.
            original_collection = store.collection

            def collection(name):
                if name == 'conversation_finalization_jobs':
                    raise RuntimeError('synthetic cleanup read failure')
                return original_collection(name)

            fault.setattr(store, 'collection', collection)
        else:
            fault.setattr(retirement, '_retire', fail)
        assert conversations.claim_conversation_status(
            'synthetic', 'capture', ConversationStatus.in_progress, ConversationStatus.processing
        )
    assert store.rows[ROW]['status'] == 'processing'
    assert store.rows[JOB]['status'] == 'waiting_quiet'
    assert store.rows[JOB]['reconcile_after_at'] == NOW
    assert 'event=quiet_check_retirement outcome=deferred' in caplog.text
    # The same indexed obligation remains repairable when the dependency recovers.
    assert retirement.stop_quiet_check_for_conversation('synthetic', 'capture', firestore_client=store)
    assert_retired(store)


@pytest.mark.parametrize('operation', ['conversation', 'job', 'account'])
def test_indirect_cleanup_read_failure_is_deferred_after_commit(caplog, operation):
    metric = OMI_FALLBACK_TOTAL.labels(
        component='conversation_finalization',
        from_mode='inline',
        to_mode='durable_queued',
        reason='unavailable',
        outcome='degraded',
    )
    before = metric._value.get()

    class UnavailableClient:
        def collection(self, name):
            raise RuntimeError('synthetic post-commit dependency failure')

    client = UnavailableClient()
    if operation == 'conversation':
        assert not retirement.stop_quiet_check_for_conversation('synthetic', 'capture', firestore_client=client)
    elif operation == 'job':
        retirement.stop_quiet_checks_for_job('terminal-job', firestore_client=client)
    else:
        retirement.stop_quiet_checks_for_account('synthetic', firestore_client=client)
    assert 'event=quiet_check_retirement outcome=deferred' in caplog.text
    assert metric._value.get() == before + 1
    assert 'omi_fallback_event component=conversation_finalization' in caplog.text


@pytest.mark.parametrize('cleanup_succeeds', [True, False])
def test_processing_rollback_restores_index_and_fences_pre_admission_deliveries(monkeypatch, cleanup_succeeds):
    store = seeded()
    monkeypatch.setattr(conversations, 'db', store)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a: None)
    with monkeypatch.context() as fault:
        if not cleanup_succeeds:

            def fail(*args, **kwargs):
                raise RuntimeError('synthetic deferred admission cleanup')

            fault.setattr(retirement, '_retire', fail)
        assert conversations.claim_conversation_status(
            'synthetic', 'capture', ConversationStatus.in_progress, ConversationStatus.processing
        )
    assert conversations.claim_conversation_status(
        'synthetic', 'capture', ConversationStatus.processing, ConversationStatus.in_progress
    )
    job = store.rows[JOB]
    assert store.rows[ROW]['status'] == 'in_progress'
    assert job['status'] == 'waiting_quiet' and job['dispatch_generation'] == 8
    assert isinstance(job['reconcile_after_at'], datetime)
    assert job['due_at'] == job['reconcile_after_at']
    checks.stop_quiet_check(JOB[-1], 7, firestore_client=store)
    assert job['status'] == 'waiting_quiet' and job['dispatch_generation'] == 8
    assert not conversations.claim_conversation_status(
        'synthetic', 'capture', ConversationStatus.processing, ConversationStatus.in_progress
    )
    assert job['dispatch_generation'] == 8


def test_processing_rollback_does_not_invent_an_unowed_check(monkeypatch):
    store = seeded({'status': 'processing'})
    del store.rows[JOB]
    monkeypatch.setattr(conversations, 'db', store)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a: None)
    assert conversations.claim_conversation_status(
        'synthetic', 'capture', ConversationStatus.processing, ConversationStatus.in_progress
    )
    assert JOB not in store.rows


def test_processing_rollback_cannot_commit_live_without_restoring_owed_custody(monkeypatch):
    store = seeded({'status': 'processing'})
    store.rows[JOB]['status'] = 'quiet_done'
    store.rows[JOB].pop('reconcile_after_at')
    original_collection = store.collection

    def collection(name):
        if name == 'conversation_finalization_jobs':
            raise RuntimeError('synthetic rollback custody read failure')
        return original_collection(name)

    monkeypatch.setattr(conversations, 'db', store)
    monkeypatch.setattr(store, 'collection', collection)
    with pytest.raises(RuntimeError, match='rollback custody read'):
        conversations.claim_conversation_status(
            'synthetic', 'capture', ConversationStatus.processing, ConversationStatus.in_progress
        )
    assert store.rows[ROW]['status'] == 'processing'
    assert store.rows[JOB]['status'] == 'quiet_done'


def test_deferred_cleanup_telemetry_failure_cannot_invalidate_owner_result(monkeypatch, caplog):
    def fail(**kwargs):
        raise RuntimeError('synthetic telemetry failure')

    class UnavailableClient:
        def collection(self, name):
            raise RuntimeError('synthetic cleanup read failure')

    monkeypatch.setattr(retirement, 'record_fallback', fail)
    assert not retirement.stop_quiet_check_for_conversation(
        'synthetic', 'capture', firestore_client=UnavailableClient()
    )
    assert 'outcome=telemetry_failed' in caplog.text
    assert 'outcome=deferred' in caplog.text
