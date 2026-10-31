"""Replay must close a silent-crash ladder without another worker delivery."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from database import conversation_finalization_jobs as jobs
from services import conversation_finalization as service
from models.account_cutover import AccountCutoverRecord, AccountCutoverState
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)
JOB_PATH = (jobs.FINALIZATION_JOBS_COLLECTION, 'synthetic-job')
ROW_PATH = ('users', 'synthetic-owner', 'conversations', 'synthetic-recording')


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    monkeypatch.setattr(jobs, 'stop_quiet_checks_for_job', Mock())
    return StrictFirestore(
        {
            JOB_PATH: {
                'uid': ROW_PATH[1],
                'conversation_id': ROW_PATH[-1],
                'status': 'leased',
                'dispatch_generation': 52,
                'lease_epoch': 56,
                'lease_expires_at': NOW - timedelta(seconds=1),
                'attempt_count': 4,
                'worker_claim_count': 55,
                'fanout_status': 'pending',
                'finalization_revision': 3,
                'created_at': NOW - timedelta(hours=23),
            },
            ROW_PATH: {
                'status': 'processing',
                'discarded': False,
                'finalization_job_id': JOB_PATH[-1],
                'finalization_revision': 3,
                'transcript_segments': [{'text': 'Synthetic transcript.'}],
                'audio_files': [{'id': 'synthetic-audio'}],
                'photos': [{'description': 'Synthetic photo'}],
                'structured': {'title': '', 'overview': ''},
                'custom_field': {'untouched': True},
            },
        }
    )


def replay(store, *, max_attempts=5):
    return jobs.claim_finalization_replay(
        JOB_PATH[-1], stale_after=timedelta(minutes=5), max_attempts=max_attempts, firestore_client=store
    )


@pytest.mark.parametrize('status', ['queued', 'leased'])
@pytest.mark.parametrize('attempts,claims', [(4, 55), (0, 6), (5, 0)])
def test_stale_replay_terminalizes_only_exhausted_budget(store, status, attempts, claims):
    job = store.rows[JOB_PATH]
    job.update(status=status, attempt_count=attempts, worker_claim_count=claims)
    before_job = deepcopy(job)
    before_row = deepcopy(store.rows[ROW_PATH])

    intent = replay(store)

    assert intent['created'] is True
    assert intent['status'] == 'dead_letter'
    expected_job = {
        **before_job,
        'status': 'dead_letter',
        'updated_at': NOW,
        'terminal_at': NOW,
        'terminal_outcome': 'failure',
        'lease_expires_at': NOW,
        'reconcile_after_at': jobs.firestore.DELETE_FIELD,
        'task_retry_count': max(attempts, claims - 1),
        'attempt_count': max(attempts, claims - 1),
        'last_failure_code': 'durable_attempts_exhausted',
    }
    assert store.rows[JOB_PATH] == expected_job
    assert store.rows[ROW_PATH] == {
        **before_row,
        'status': 'completed',
        'finalization_status': 'dead_letter',
        'structured': {'title': 'Synthetic transcript.', 'overview': ''},
        'summary_retryable': True,
    }
    jobs.stop_quiet_checks_for_job.assert_called_once()
    # It cannot mint another Cloud Task or write another attention item.
    writes = sum(len(tx.updates) + len(tx.sets) for tx in store.transactions)
    assert replay(store)['created'] is False
    assert sum(len(tx.updates) + len(tx.sets) for tx in store.transactions) == writes + 1


@pytest.mark.parametrize('claims', [0, 4, 5])
def test_healthy_replays_do_not_consume_worker_budget_and_can_succeed(store, claims):
    store.rows[JOB_PATH].update(status='queued', worker_claim_count=claims, attempt_count=0)
    before_row = deepcopy(store.rows[ROW_PATH])
    # Enqueue failure / task not delivered: arbitrarily many reconciler passes
    # never consume a worker claim. The exact boundary is claims - 1 >= 5.
    for _ in range(8):
        store.rows[JOB_PATH]['dispatch_requested_at'] = NOW - timedelta(minutes=6)
        assert replay(store)['status'] == 'queued'
        assert store.rows[JOB_PATH]['worker_claim_count'] == claims
    generation = store.rows[JOB_PATH]['dispatch_generation']
    claim = jobs.claim_finalization_job(JOB_PATH[-1], generation, count_worker_claim=True, firestore_client=store)
    assert claim['status'] == 'claimed'
    assert store.rows[JOB_PATH]['worker_claim_count'] == claims + 1
    # Below exhaustion, the real claimed lease can complete normally.
    if claims < 5:
        store.rows[JOB_PATH]['fanout_status'] = 'completed'
        assert jobs.mark_finalization_completed(JOB_PATH[-1], generation, claim['lease_epoch'], firestore_client=store)
    assert store.rows[ROW_PATH] == before_row


@pytest.mark.parametrize('guard', ['live_lease', 'fresh_queue', 'byok', 'disabled', 'committed_fanout'])
def test_replay_retains_existing_admission_guards(store, guard):
    job = store.rows[JOB_PATH]
    cap = 5
    if guard == 'live_lease':
        job['lease_expires_at'] = NOW + timedelta(seconds=1)
    elif guard == 'fresh_queue':
        job.update(status='queued', dispatch_requested_at=NOW)
    elif guard == 'byok':
        job['requires_byok'] = True
    elif guard == 'disabled':
        cap = None
    else:
        job['fanout_status'] = 'completed'
    before_row = deepcopy(store.rows[ROW_PATH])
    assert replay(store, max_attempts=cap)['status'] != 'dead_letter'
    assert store.rows[ROW_PATH] == before_row


def test_replay_does_not_mutate_a_newer_conversation_binding(store):
    store.rows[ROW_PATH]['finalization_revision'] = 4
    before_row = deepcopy(store.rows[ROW_PATH])
    assert replay(store)['status'] == 'dead_letter'
    assert store.rows[ROW_PATH] == before_row


@pytest.mark.parametrize('field', ['uid', 'conversation_id'])
@pytest.mark.parametrize('value', [None, '', 17, {}])
def test_exhausted_replay_without_valid_binding_closes_only_job(store, field, value):
    if value is None:
        store.rows[JOB_PATH].pop(field)
    else:
        store.rows[JOB_PATH][field] = value
    before = deepcopy(store.rows)

    intent = replay(store)

    assert intent['created'] is True
    assert intent['status'] == 'dead_letter'
    assert store.rows[JOB_PATH]['last_failure_code'] == 'durable_attempts_exhausted'
    assert store.rows[JOB_PATH]['dispatch_generation'] == before[JOB_PATH]['dispatch_generation']
    assert {path: row for path, row in store.rows.items() if path != JOB_PATH} == {
        path: row for path, row in before.items() if path != JOB_PATH
    }
    assert all(path == JOB_PATH for tx in store.transactions for path, _ in tx.updates)
    assert not any(tx.creates or tx.sets for tx in store.transactions)
    assert replay(store)['created'] is False


@pytest.mark.parametrize('guard', ['deleting', 'cutover', 'malformed_cutover'])
def test_replay_preserves_worker_account_admission_fences(store, monkeypatch, guard):
    if guard == 'deleting':
        store.rows[('account_deletions', ROW_PATH[1])] = {'wipe_status': 'pending_deletion'}
    else:
        monkeypatch.setenv('ACCOUNT_CUTOVER_ENFORCEMENT', 'on')
        store.rows[('users', ROW_PATH[1], 'account_cutover', 'state')] = (
            AccountCutoverRecord(uid=ROW_PATH[1], state=AccountCutoverState.new).persisted_payload()
            if guard == 'cutover'
            else {'state': 'invalid'}
        )
    before_row = deepcopy(store.rows[ROW_PATH])
    # Existing worker owns account fencing; replay cannot bypass it to write
    # a dead-letter update into a deleted or migrating account.
    assert replay(store)['status'] == 'queued'
    assert store.rows[ROW_PATH] == before_row


def test_real_reconciler_claim_path_retires_without_enqueue(store, monkeypatch):
    monkeypatch.setenv('LISTEN_FINALIZATION_DURABLE_ATTEMPT_CAP_ENABLED', 'true')
    monkeypatch.setattr(service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(service, 'get_listen_finalization_tasks_max_attempts_for_worker', lambda: 5)
    monkeypatch.setattr(jobs, 'recover_stranded_byok_jobs', lambda **_: {'blocked': 0, 'errors': 0})
    monkeypatch.setattr(jobs, 'get_finalization_replay_oldest_overdue_age_seconds', lambda **_: 0)
    monkeypatch.setattr(jobs, 'get_finalization_replay_candidates', lambda **_: [{'job_id': JOB_PATH[-1]}])
    monkeypatch.setattr(jobs, 'defer_finalization_replay', Mock())
    monkeypatch.setattr(service, '_publish_job_metrics', Mock())
    recorded = Mock()
    enqueue = Mock()
    monkeypatch.setattr(service, '_record_dead_letter', recorded)
    monkeypatch.setattr(service, 'enqueue_listen_finalization_job', enqueue)

    result = service.reconcile_listen_finalization_jobs(firestore_client=store)

    assert result['retired'] == 1
    assert result['requeued'] == 0
    assert store.rows[JOB_PATH]['status'] == 'dead_letter'
    enqueue.assert_not_called()
    recorded.assert_called_once_with(JOB_PATH[-1], firestore_client=store)
