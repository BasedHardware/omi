"""A user finish inside the first 60 s archive window is a finish, not an empty recording.

The listen session marks ``server_batch_audio_received`` at the first frame and writes ``has_content``
only when an archive window commits. A finish before that used to be answered ``no_content`` and
ignored, so the recording stayed open until the socket closed or the quiet timer fired.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from google.cloud import firestore

from config import server_batch
from database import conversation_finalization_jobs as jobs
from utils.conversations import finalizer
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

    async def run(_executor, function, *args, **_kwargs):
        if function is finalizer.conversations_db.get_conversation:
            calls.append('read')
            return reads.pop(0) if reads else first
        if function is finalizer.register_recording:
            calls.append(('register', args[1]))
            return True
        if function is finalizer.lifecycle_service.complete_server_batch_capture:
            calls.append(('complete', args[2]))
            return 'completed'
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


@pytest.mark.asyncio
async def test_worker_keeps_the_not_closed_retry_when_the_audio_never_commits(monkeypatch):
    monkeypatch.setattr(finalizer, 'LIVE_ARCHIVE_COMMIT_WAIT_SECONDS', 0)
    calls = _worker(monkeypatch, _live(status='processing'), [])

    with pytest.raises(finalizer.ServerBatchArchiveNotClosed):
        await _finalize(ProcessingTrigger.CLIENT_FINALIZE)

    assert calls == []


@pytest.mark.asyncio
async def test_a_natural_end_does_not_wait(monkeypatch):
    calls = _worker(monkeypatch, _live(status='processing'), [])

    with pytest.raises(finalizer.ServerBatchArchiveNotClosed):
        await _finalize(ProcessingTrigger.CAPTURE_END)

    assert calls == []


@pytest.mark.asyncio
async def test_a_deleted_row_ends_the_wait(monkeypatch):
    calls = _worker(monkeypatch, _live(status='processing'), [None])

    with pytest.raises(finalizer.ServerBatchArchiveNotClosed):
        await _finalize(ProcessingTrigger.CLIENT_FINALIZE)

    assert calls == ['read']
