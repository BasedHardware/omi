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
