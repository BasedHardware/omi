"""A user finish inside the first 60 s archive window is a finish, not an empty recording.

The listen session marks ``server_batch_audio_received`` at the first frame and writes ``has_content``
only when an archive window commits. A finish before that used to be answered ``no_content`` and
ignored, so the recording stayed open until the socket closed or the quiet timer fired.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from google.cloud import firestore

from config import server_batch
from database import conversation_finalization_jobs as jobs
from routers import conversation_finalization as worker_router
from utils.conversations import demand_processing, finalizer
from utils.conversations import lifecycle
from utils.conversations.processing_trigger import ProcessingTrigger
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)
ROW = ('users', 'uid-1', 'conversations', 'conversation-1')


def _live(**row):
    return {
        'status': 'in_progress',
        'transcript_segments': [],
        'record_lane_owner': 'batch_live_v1',
        server_batch.MARKER: True,
        'server_batch_audio_received': True,
        'created_at': NOW - timedelta(seconds=37),
        **row,
    }


@pytest.fixture(autouse=True)
def _every_owner(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'on')


def _admit(row, trigger):
    """Run the real admission transaction and the real lifecycle reducer on a strict store."""
    db = StrictFirestore({ROW: row})
    intent = firestore.transactional(
        jobs._create_or_get_finalization_intent_txn
    )(  # pyright: ignore[reportPrivateUsage]
        db.transaction(),
        db.document('/'.join(ROW)),
        db.collection(jobs.FINALIZATION_JOBS_COLLECTION),
        'uid-1',
        'conversation-1',
        False,
        lambda conversation: lifecycle._finalization_admission(  # pyright: ignore[reportPrivateUsage]
            conversation, 'conversation-1'
        ),
        NOW,
        trigger=trigger,
    )
    return intent, db


def _intent(row, trigger):
    intent, db = _admit(row, trigger)
    if intent['status'] == 'no_content':
        # A refused finish writes nothing: the recording stays open for its natural end.
        assert db.rows == {ROW: row}
    return intent


def test_user_finish_before_the_first_archive_window_is_admitted():
    intent, db = _admit(_live(), ProcessingTrigger.CLIENT_FINALIZE)

    assert intent['status'] == 'queued'
    job = db.rows[(jobs.FINALIZATION_JOBS_COLLECTION, intent['job_id'])]
    assert (job['status'], job['uid'], job['conversation_id']) == ('queued', 'uid-1', 'conversation-1')
    assert job['processing_trigger'] == ProcessingTrigger.CLIENT_FINALIZE.value
    row = db.rows[ROW]
    assert row['status'] == 'processing'
    assert (row['finalization_job_id'], row['finalization_revision']) == (intent['job_id'], 1)


@pytest.mark.parametrize(
    'row',
    [
        _live(server_batch_audio_received=False),
        _live(server_batch_audio_received=None),
        _live(server_batch_audio_closed=True),
        _live(record_lane_owner=None),
        {'status': 'in_progress', 'transcript_segments': []},
        _live(listen_batch_producer={'version': 1, 'token': 't'}),
        _live(created_at=NOW - timedelta(seconds=3)),
        _live(created_at=None),
    ],
    ids=[
        'no-audio-yet',
        'unknown-audio',
        'closed-empty-archive',
        'not-batch-owned',
        'legacy-row',
        'reconnect-producer',
        'seconds-old-successor',
        'no-creation-time',
    ],
)
def test_a_recording_holding_no_live_audio_is_still_empty(row):
    assert _intent(row, ProcessingTrigger.CLIENT_FINALIZE)['status'] == 'no_content'


@pytest.mark.parametrize('trigger', [ProcessingTrigger.CAPTURE_END, ProcessingTrigger.USER_REPROCESS])
def test_only_a_user_finish_is_admitted_early(trigger):
    assert _intent(_live(), trigger)['status'] == 'no_content'


def test_kill_switch_restores_the_empty_answer(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BATCH_MANUAL_END', 'off')

    assert _intent(_live(), ProcessingTrigger.CLIENT_FINALIZE)['status'] == 'no_content'


@pytest.mark.parametrize(
    'mode,member,status', [('cohort', False, 'no_content'), ('cohort', True, 'queued'), ('off', True, 'no_content')]
)
def test_early_admission_rolls_out_with_the_fast_finish_cohort(monkeypatch, mode, member, status):
    asked = []
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', mode)
    monkeypatch.setattr(server_batch, 'in_rollout_cohort', lambda uid, name: asked.append((uid, name)) or member)

    assert _intent(_live(), ProcessingTrigger.CLIENT_FINALIZE)['status'] == status
    assert asked == ([('uid-1', 'v3-fast-finish')] if mode == 'cohort' else [])


def test_committed_audio_is_not_uncommitted():
    committed = _live(has_content=True, server_batch_audio_start=1.0, server_batch_audio_end=38.0)

    assert server_batch.live_audio_uncommitted(_live())
    assert not server_batch.live_audio_uncommitted(committed)
    assert not server_batch.user_finish_admits('uid-1', committed, NOW)


def _worker(monkeypatch, first, later):
    """Run the finalizer over ``first``; each later read returns the next of ``later``."""
    calls, reads = [], list(later)

    async def load(*_args):
        return None, first, SimpleNamespace(transcript_segments=[], photos=[])

    async def run(_executor, function, *args, **kwargs):
        if function is finalizer.conversations_db.get_conversation:
            calls.append('read')
            return reads.pop(0) if reads else first
        if function is finalizer.register_recording:
            calls.append(('register', args[1]))
            return True
        if function is finalizer.lifecycle_service.complete_server_batch_capture:
            calls.append(('complete', args[2]))
            return 'completed'
        if function is jobs.mark_finalization_retryable:
            calls.append('defer')
            return function(*args, **kwargs)
        raise AssertionError(function)

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', load)
    monkeypatch.setattr(finalizer, 'run_blocking', run)
    monkeypatch.setattr(finalizer, 'LIVE_ARCHIVE_COMMIT_POLL_SECONDS', 0)
    return calls


def _finalize(trigger):
    return finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job',
        dispatch_generation=1,
        lease_epoch=1,
        trigger=trigger,
    )


@pytest.mark.asyncio
async def test_worker_waits_for_the_live_commit_then_hands_the_recording_to_batch(monkeypatch):
    waiting = _live(status='processing')
    committed = {**waiting, 'has_content': True, 'server_batch_audio_start': 1.0, 'server_batch_audio_end': 38.0}
    calls = _worker(monkeypatch, waiting, [waiting, committed])

    result = await _finalize(ProcessingTrigger.CLIENT_FINALIZE)

    assert result is finalizer.ConversationFinalizationDisposition.completed
    assert calls == ['read', 'read', ('register', committed), ('complete', committed)]


def _route(monkeypatch, attempt_count=4):
    """Admit an early finish on a strict store and drive the real worker route and job transactions."""
    intent, db = _admit(_live(), ProcessingTrigger.CLIENT_FINALIZE)
    job_id = intent['job_id']
    job_path = (jobs.FINALIZATION_JOBS_COLLECTION, job_id)
    db.rows[job_path].update(dispatch_requested_at=NOW, attempt_count=attempt_count, worker_claim_count=attempt_count)
    deltas = []
    clock = [NOW]
    monkeypatch.setattr(jobs, '_client', lambda firestore_client=None: firestore_client or db)
    monkeypatch.setattr(jobs, '_now', lambda: clock[0])
    monkeypatch.setattr(jobs, '_record_projection_delta', lambda _txn, _collection, _job, **delta: deltas.append(delta))

    async def inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(worker_router, 'run_blocking', inline)
    monkeypatch.setattr(worker_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(worker_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(worker_router, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(worker_router, 'should_skip_background_account_mutation', lambda uid: False)
    monkeypatch.setattr(demand_processing, 'admit', lambda *args, **kwargs: True)
    assert finalizer.LIVE_ARCHIVE_COMMIT_WAIT_SECONDS <= 5
    monkeypatch.setattr(finalizer, 'LIVE_ARCHIVE_COMMIT_WAIT_SECONDS', 0)

    async def deliver(generation):
        async def payload():
            return {'job_id': job_id, 'dispatch_generation': generation}

        return await worker_router.run_listen_finalization_job(SimpleNamespace(json=payload), task_retry_count=0)

    return db, job_path, clock, deltas, deliver


@pytest.mark.asyncio
async def test_worker_defers_an_uncommitted_finish_and_replays_without_spending_an_attempt(monkeypatch):
    db, job_path, clock, deltas, deliver = _route(monkeypatch)
    job_id = job_path[1]
    row_before = dict(db.rows[ROW])
    calls = _worker(monkeypatch, db.rows[ROW], [])

    response = await deliver(1)

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'deferred'}
    # Custody: the delivery only yielded its lease. The _worker double raises on any other
    # writer, so the held audio was not registered, completed, or deleted as empty.
    assert calls == ['defer']
    assert db.rows[ROW] == row_before
    assert deltas == [{'queued': -1, 'leased': 1}, {'leased': -1, 'queued': 1}]
    job = db.rows[job_path]
    assert job['status'] == 'queued'
    assert job['attempt_count'] == job['worker_claim_count'] == 4
    assert job['last_failure_code'] == 'live_archive_uncommitted'
    assert job['live_archive_wait_started_at'] == NOW
    # Deleted (the strict fixture keeps the delete sentinel), so only the due time gates replay.
    assert not isinstance(job.get('dispatch_requested_at'), datetime)
    due = NOW + timedelta(seconds=10)
    assert job['reconcile_after_at'] == due

    stale_after = timedelta(minutes=5)
    clock[0] = due - timedelta(seconds=1)
    assert not jobs.claim_finalization_replay(job_id, stale_after=stale_after)['created']
    clock[0] = due
    replay = jobs.claim_finalization_replay(job_id, stale_after=stale_after, max_attempts=5)
    assert replay['created']
    assert replay['dispatch_generation'] == 2
    assert db.rows[job_path]['attempt_count'] == db.rows[job_path]['worker_claim_count'] == 4
    assert not jobs.claim_finalization_replay(job_id, stale_after=stale_after)['created']

    # Redelivered after the session commits the held audio: the recording goes to batch.
    committed = {**db.rows[ROW], 'has_content': True, 'server_batch_audio_start': 1.0, 'server_batch_audio_end': 38.0}
    db.rows[ROW] = committed
    calls = _worker(monkeypatch, committed, [])
    monkeypatch.setattr(jobs, 'mark_finalization_completed', lambda *args, **kwargs: True)

    response = await deliver(2)

    assert (response.status_code, json.loads(response.body)) == (200, {'status': 'done'})
    assert calls == [('register', committed), ('complete', committed)]
    assert db.rows[job_path]['live_archive_wait_started_at'] == NOW


@pytest.mark.asyncio
async def test_each_redelivery_inside_the_bound_defers_again(monkeypatch):
    db, job_path, clock, _deltas, deliver = _route(monkeypatch)
    db.rows[job_path]['live_archive_wait_started_at'] = NOW - jobs.LIVE_ARCHIVE_MAX_WAIT + timedelta(seconds=1)
    _worker(monkeypatch, db.rows[ROW], [])

    response = await deliver(1)

    assert json.loads(response.body) == {'status': 'deferred'}
    job = db.rows[job_path]
    # The first deferral's start is kept, so the bound counts from the first uncommitted delivery.
    assert job['live_archive_wait_started_at'] == NOW - jobs.LIVE_ARCHIVE_MAX_WAIT + timedelta(seconds=1)
    assert job['attempt_count'] == 4


@pytest.mark.asyncio
async def test_deferral_is_bounded_then_takes_the_counted_not_closed_retry(monkeypatch):
    db, job_path, clock, deltas, deliver = _route(monkeypatch, attempt_count=1)
    started = NOW - jobs.LIVE_ARCHIVE_MAX_WAIT
    db.rows[job_path]['live_archive_wait_started_at'] = started
    row_before = dict(db.rows[ROW])
    calls = _worker(monkeypatch, db.rows[ROW], [])

    response = await deliver(1)

    # The pre-existing safe path: a counted retry that leaves the conversation and its audio alone.
    assert (response.status_code, json.loads(response.body)) == (500, {'status': 'retry'})
    assert calls == ['defer']
    assert db.rows[ROW] == row_before
    job = db.rows[job_path]
    assert job['status'] == 'queued'
    assert job['attempt_count'] == 2
    assert job['last_failure_code'] != 'live_archive_uncommitted'
    assert job['live_archive_wait_started_at'] == started


@pytest.mark.asyncio
async def test_a_natural_end_does_not_wait(monkeypatch):
    calls = _worker(monkeypatch, _live(status='processing'), [])

    with pytest.raises(finalizer.ServerBatchArchiveNotClosed):
        await _finalize(ProcessingTrigger.CAPTURE_END)

    assert calls == []


@pytest.mark.asyncio
async def test_a_deleted_row_ends_the_wait_and_defers_to_the_replay_admission(monkeypatch):
    deferred = []
    monkeypatch.setattr(
        jobs, 'mark_finalization_retryable', lambda *args, **kwargs: deferred.append((args, kwargs)) or True
    )
    calls = _worker(monkeypatch, _live(status='processing'), [None])

    assert await _finalize(ProcessingTrigger.CLIENT_FINALIZE) is finalizer.ConversationFinalizationDisposition.deferred
    assert calls == ['read', 'defer']
    assert deferred == [(('job', 1, 1, 'live_archive_uncommitted'), {'count_attempt': False})]
