"""Replay must close a silent-crash ladder without another worker delivery."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from database import conversation_finalization_jobs as jobs
from services import conversation_finalization as service
from models.account_cutover import AccountCutoverRecord, AccountCutoverState
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import lifecycle

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
    # Transport failure never consumes a worker claim. Replay stops minting
    # generations at its separate transport budget; the last task stays valid.
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


@pytest.mark.parametrize('enqueue_fails', [False, True])
def test_replay_transport_budget_holds_once_without_invalidating_latest_task(
    store, monkeypatch, inline_replay, enqueue_fails
):
    clock = [NOW]
    monkeypatch.setattr(jobs, '_now', lambda: clock[0])
    job = store.rows[JOB_PATH]
    job.update(status='queued', worker_claim_count=0, attempt_count=0)
    before_row = deepcopy(store.rows[ROW_PATH])
    if enqueue_fails:
        inline_replay.side_effect = RuntimeError('synthetic enqueue failure')
    outcome = 'enqueue_failed' if enqueue_fails else 'requeued'
    for expected in range(1, jobs.MAX_UNCLAIMED_REPLAY_DISPATCHES + 1):
        result = service.reconcile_listen_finalization_jobs(firestore_client=store)
        assert result[outcome] == 1
        assert result['dispatch_exhausted'] == 0
        assert job['replay_dispatches_without_claim'] == expected
        clock[0] += timedelta(minutes=6)
    before_hold = deepcopy(job)
    result = service.reconcile_listen_finalization_jobs(firestore_client=store)
    assert result['dispatch_exhausted'] == 1
    assert result['retired'] == result['requeued'] == result['enqueue_failed'] == 0
    assert job == before_hold | {
        'reconcile_after_at': jobs.firestore.DELETE_FIELD,
        'replay_dispatch_suspended_at': clock[0],
        'updated_at': clock[0],
    }
    writes = sum(len(tx.updates) + len(tx.sets) for tx in store.transactions)
    assert service.reconcile_listen_finalization_jobs(firestore_client=store)['dispatch_exhausted'] == 0
    assert sum(len(tx.updates) + len(tx.sets) for tx in store.transactions) == writes
    assert inline_replay.call_count == jobs.MAX_UNCLAIMED_REPLAY_DISPATCHES
    assert store.rows[ROW_PATH] == before_row
    service._record_dead_letter.assert_not_called()

    # A delayed task can still claim the held generation and restore its lease
    # marker. Once that lease expires, replay gets a new transport budget.
    claim = jobs.claim_finalization_job(
        JOB_PATH[-1], job['dispatch_generation'], count_worker_claim=True, firestore_client=store
    )
    assert claim['status'] == 'claimed'
    assert job['reconcile_after_at'] == job['lease_expires_at']
    clock[0] = job['lease_expires_at'] + timedelta(seconds=1)
    assert service.reconcile_listen_finalization_jobs(firestore_client=store)[outcome] == 1
    assert job['replay_dispatches_without_claim'] == 1
    assert job['worker_claim_count'] == 1
    assert job['replay_dispatch_suspended_at'] == jobs.firestore.DELETE_FIELD
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
    monkeypatch.setattr(service, 'is_listen_finalization_tasks_configured', lambda: True)
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


@pytest.fixture
def inline_replay(store, monkeypatch):
    """Listen's real inline admission mode with an independent worker binding."""
    monkeypatch.setenv('LISTEN_FINALIZATION_DISPATCH_MODE', 'inline')
    monkeypatch.delenv('LISTEN_FINALIZATION_REPLAY_ENABLED', raising=False)
    monkeypatch.setenv('LISTEN_FINALIZATION_DURABLE_ATTEMPT_CAP_ENABLED', 'true')
    for key, value in {
        'SYNC_TASKS_PROJECT': 'synthetic-project',
        'SYNC_TASKS_LOCATION': 'us-central1',
        'LISTEN_FINALIZATION_TASKS_QUEUE': 'conversation-finalization',
        'LISTEN_FINALIZATION_TASKS_HANDLER_URL': 'https://synthetic.invalid/finalize',
        'LISTEN_FINALIZATION_TASKS_INVOKER_SA': 'synthetic@synthetic-project.iam.gserviceaccount.com',
        'LISTEN_FINALIZATION_TASKS_MAX_ATTEMPTS': '5',
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(jobs, 'recover_stranded_byok_jobs', Mock(return_value={'blocked': 0, 'errors': 0}))
    monkeypatch.setattr(jobs, 'get_finalization_replay_oldest_overdue_age_seconds', lambda **_: 0)
    monkeypatch.setattr(
        jobs,
        'get_finalization_replay_candidates',
        Mock(side_effect=lambda **_: [deepcopy(store.rows[JOB_PATH]) | {'job_id': JOB_PATH[-1]}]),
    )
    monkeypatch.setattr(service, '_publish_job_metrics', Mock())
    monkeypatch.setattr(service, '_record_dead_letter', Mock())
    enqueue = Mock()
    monkeypatch.setattr(service, 'enqueue_listen_finalization_job', enqueue)
    return enqueue


def test_inline_replay_recovers_dead_workers_then_dead_letters(store, monkeypatch, inline_replay):
    clock = [NOW]
    monkeypatch.setattr(jobs, '_now', lambda: clock[0])
    store.rows[JOB_PATH].update(status='queued', worker_claim_count=0, attempt_count=0)
    before_row = deepcopy(store.rows[ROW_PATH])
    for _ in range(6):
        result = service.reconcile_listen_finalization_jobs(firestore_client=store)
        assert result['requeued'] == 1 and result['retired'] == 0
        generation = store.rows[JOB_PATH]['dispatch_generation']
        claim = jobs.claim_finalization_job(JOB_PATH[-1], generation, count_worker_claim=True, firestore_client=store)
        assert claim['status'] == 'claimed'
        # The worker dies without reporting failure. Let its real lease expire.
        clock[0] = store.rows[JOB_PATH]['lease_expires_at'] + timedelta(seconds=1)
    result = service.reconcile_listen_finalization_jobs(firestore_client=store)
    assert result['retired'] == 1 and result['requeued'] == 0
    assert inline_replay.call_count == 6
    assert store.rows[JOB_PATH]['status'] == 'dead_letter'
    assert store.rows[JOB_PATH]['last_failure_code'] == 'durable_attempts_exhausted'
    for key in ('transcript_segments', 'audio_files', 'photos', 'custom_field'):
        assert store.rows[ROW_PATH][key] == before_row[key]
    service.reconcile_listen_finalization_jobs(firestore_client=store)
    assert inline_replay.call_count == 6
    service._record_dead_letter.assert_called_once()


def test_inline_replay_live_lease_is_not_reclaimed(store, inline_replay):
    store.rows[JOB_PATH]['lease_expires_at'] = NOW + timedelta(minutes=10)
    store.rows[JOB_PATH]['reconcile_after_at'] = NOW - timedelta(minutes=1)
    before = deepcopy(store.rows)
    assert service.reconcile_listen_finalization_jobs(firestore_client=store)['skipped'] == 1
    # The existing backoff advances only scan bookkeeping, never the live lease,
    # dispatch generation, worker budget, fanout or conversation contents.
    assert store.rows[JOB_PATH] == before[JOB_PATH] | {
        'reconcile_after_at': NOW + timedelta(seconds=60),
        'updated_at': NOW,
    }
    assert store.rows[ROW_PATH] == before[ROW_PATH]
    inline_replay.assert_not_called()


def test_inline_replay_committed_effects_are_not_repeated(store, inline_replay):
    store.rows[JOB_PATH]['fanout_status'] = 'completed'
    before_row = deepcopy(store.rows[ROW_PATH])
    assert service.reconcile_listen_finalization_jobs(firestore_client=store)['requeued'] == 1
    generation = store.rows[JOB_PATH]['dispatch_generation']
    claim = jobs.claim_finalization_job(JOB_PATH[-1], generation, count_worker_claim=True, firestore_client=store)
    assert claim['status'] == 'claimed'
    # The existing worker short-circuits completed fanout into this completion;
    # the fanout CAS also refuses to claim those effects for a second execution.
    assert (
        jobs.claim_finalization_fanout(JOB_PATH[-1], generation, claim['lease_epoch'], firestore_client=store)['status']
        == 'completed'
    )
    assert jobs.mark_finalization_completed(JOB_PATH[-1], generation, claim['lease_epoch'], firestore_client=store)
    assert store.rows[JOB_PATH]['status'] == 'completed'
    assert store.rows[ROW_PATH] == before_row
    service._record_dead_letter.assert_not_called()


@pytest.mark.parametrize('mode', ['inline', 'cloud_tasks'])
@pytest.mark.parametrize('disabled_by', ['kill_switch', 'missing_binding', 'invalid_binding'])
def test_inline_replay_off_preserves_today_behavior(store, monkeypatch, inline_replay, disabled_by, mode):
    monkeypatch.setenv('LISTEN_FINALIZATION_DISPATCH_MODE', mode)
    if disabled_by == 'kill_switch':
        monkeypatch.setenv('LISTEN_FINALIZATION_REPLAY_ENABLED', 'false')
    elif disabled_by == 'missing_binding':
        monkeypatch.delenv('LISTEN_FINALIZATION_TASKS_QUEUE')
    else:
        monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_HANDLER_URL', 'not a URL')
    before = deepcopy(store.rows)
    assert not any(service.reconcile_listen_finalization_jobs(firestore_client=store).values())
    assert store.rows == before
    jobs.get_finalization_replay_candidates.assert_not_called()
    jobs.recover_stranded_byok_jobs.assert_called_once()
    service._publish_job_metrics.assert_called_once()
    inline_replay.assert_not_called()


def test_inline_replay_binding_does_not_enable_stale_admission(store, monkeypatch, inline_replay):
    heal = Mock()
    monkeypatch.setattr(service, 'run_selfheal_tick', heal)
    for enabled in ('true', 'false'):
        monkeypatch.setenv('LISTEN_FINALIZATION_REPLAY_ENABLED', enabled)
        assert service.reconcile_stale_in_progress_conversations(firestore_client=store)['mode'] == 'off'
    heal.assert_not_called()


def test_replay_kill_switch_also_stops_cloud_tasks_host(store, monkeypatch, inline_replay):
    monkeypatch.setenv('LISTEN_FINALIZATION_DISPATCH_MODE', 'cloud_tasks')
    monkeypatch.setenv('LISTEN_FINALIZATION_REPLAY_ENABLED', 'false')
    before = deepcopy(store.rows)
    assert not any(service.reconcile_listen_finalization_jobs(firestore_client=store).values())
    assert store.rows == before
    inline_replay.assert_not_called()


@pytest.mark.parametrize('kind', ['listen_quiet_check', 'conversation_merge'])
def test_inline_replay_does_not_run_or_defer_other_job_kinds(store, monkeypatch, inline_replay, kind):
    store.rows[JOB_PATH].update(kind=kind, reconcile_after_at=NOW - timedelta(minutes=1))
    before = deepcopy(store.rows)
    quiet = Mock()
    merge = Mock()
    claim = Mock()
    defer = Mock()
    monkeypatch.setattr(service.quiet_finalization, 'run', quiet)
    monkeypatch.setattr(lifecycle.merge_jobs, 'reconcile', merge)
    monkeypatch.setattr(jobs, 'claim_finalization_replay', claim)
    monkeypatch.setattr(jobs, 'defer_finalization_replay', defer)

    assert service.reconcile_listen_finalization_jobs(firestore_client=store)['skipped'] == 1
    assert store.rows == before
    for effect in (quiet, merge, claim, defer, inline_replay):
        effect.assert_not_called()


@pytest.mark.parametrize('kind', [{}, []])
def test_inline_replay_unknown_kind_cannot_abort_the_page(store, inline_replay, kind):
    store.rows[JOB_PATH]['kind'] = kind
    assert service.reconcile_listen_finalization_jobs(firestore_client=store)['retired'] == 1
    assert store.rows[JOB_PATH]['last_failure_code'] == 'durable_attempts_exhausted'
    inline_replay.assert_not_called()
