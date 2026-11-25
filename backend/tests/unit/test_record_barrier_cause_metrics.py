"""Barrier cause counters observe refusals without changing the barrier decision."""

from unittest.mock import Mock

import pytest

from config import record_audio
from config.record_audio import BARRIER_NOT_CLOSED, barrier_blocker, require_record_audio_barrier
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import live

NOW = 2_000_000.0
CLOSED = {
    'record_lane_owner': 'batch_live_v1',
    'status': 'completed',
    'record_audio_closed': True,
    'finished_at': 'finish',
    'record_upload_revision': 2,
}
POD = {'pod': 'pusher-1', 'process_started_at': 10.0}


def refusal(row):
    with pytest.raises(ValueError) as caught:
        require_record_audio_barrier(row)
    return caught.value


def test_closed_row_still_passes_and_returns_the_same_snapshot():
    assert require_record_audio_barrier(CLOSED) == {
        'record_lane_owner': 'batch_live_v1',
        'status': 'completed',
        'finished_at': 'finish',
        'record_upload_revision': 2,
        'record_audio_partial': None,
    }


@pytest.mark.parametrize(
    'patch,blocker,kind',
    [
        ({'record_lane_owner': 'legacy_final_pass_v1'}, 'owner_other', 'none'),
        ({'status': 'in_progress', 'record_upload_sessions': {'a': POD}}, 'status_not_completed', 'pod'),
        ({'record_upload_sessions': {'a': POD}}, 'producer_tokens', 'pod'),
        ({'record_upload_sessions': {'a': True}}, 'producer_tokens', 'bare'),
        ({'record_upload_sessions': {'a': {**POD, 'pod': ''}}}, 'producer_tokens', 'podless'),
        ({'record_upload_sessions': {'a': {**POD, 'abandoned_at': 11.0}}}, 'producer_tokens', 'abandoned'),
        ({'record_upload_sessions': {'a': {**POD, 'abandoned_at': 11.0}, 'b': True}}, 'producer_tokens', 'bare'),
        ({'record_upload_sessions': {'a': 'x'}}, 'producer_tokens', 'other'),
        ({'record_upload_failed': True}, 'upload_failed', 'none'),
        ({'record_audio_closed': False, 'record_audio_partial': {'version': 0}}, 'partial_invalid', 'none'),
        ({'record_audio_closed': False}, 'audio_not_closed', 'none'),
    ],
)
def test_refusal_keeps_type_and_message_and_names_first_failing_clause(patch, blocker, kind):
    error = refusal({**CLOSED, **patch})
    assert type(error) is ValueError
    assert str(error) == BARRIER_NOT_CLOSED
    assert (error.barrier_blocker, error.barrier_token_kind) == (blocker, kind)
    assert barrier_blocker({**CLOSED, **patch}) == (blocker, kind)
    assert blocker in record_audio.BARRIER_BLOCKERS and kind in record_audio.TOKEN_KINDS


def test_staging_change_error_is_unchanged():
    with pytest.raises(ValueError, match='capture upload barrier changed during staging'):
        require_record_audio_barrier(CLOSED, expected={})


@pytest.fixture
def drain(monkeypatch):
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('RECORD_DRAIN_BARRIER_BACKOFF', 'off')
    monkeypatch.setattr(live.time, 'time', lambda: NOW)

    async def refuse(*args, **kwargs):
        require_record_audio_barrier({**CLOSED, 'record_upload_sessions': {'a': POD}})

    monkeypatch.setattr(live, 'admit_recording', refuse)
    store = MemoryStore()
    store.rows['jobs', 'record'] = {
        'segment_id': 'record',
        'owner_id': 'owner',
        'conversation_id': 'capture',
        'privacy_generation': 3,
        'state': 'record_pending',
        'available_at': 0,
        'enqueued_at': 1,
        'merge_pending': False,
    }
    return store


def metrics():
    return Mock(record_dead_letter=Mock(), record_barrier_refusals=Mock(), record_barrier_aged=Mock())


@pytest.mark.asyncio
async def test_retry_counts_an_attempt_only(drain):
    counters = metrics()
    await live.drain_recordings(drain, metrics=counters)
    counters.record_barrier_refusals.labels.assert_called_once_with('producer_tokens', 'pod')
    counters.record_barrier_aged.labels.assert_not_called()
    counters.record_dead_letter.inc.assert_not_called()


@pytest.mark.asyncio
async def test_committed_aged_flip_counts_once_and_keeps_the_existing_counter(drain):
    drain.rows['jobs', 'record']['record_dead_letter_deadline_at'] = NOW - 1
    counters = metrics()
    await live.drain_recordings(drain, metrics=counters)
    assert drain.rows['jobs', 'record']['state'] == 'dead'
    counters.record_dead_letter.inc.assert_called_once_with()
    counters.record_barrier_refusals.labels.assert_called_once_with('producer_tokens', 'pod')
    counters.record_barrier_aged.labels.assert_called_once_with('producer_tokens', 'pod')


@pytest.mark.asyncio
async def test_kill_switch_stops_only_the_cause_counters(drain, monkeypatch):
    monkeypatch.setenv('RECORD_BARRIER_CAUSE_METRICS', 'false')
    drain.rows['jobs', 'record']['record_dead_letter_deadline_at'] = NOW - 1
    counters = metrics()
    await live.drain_recordings(drain, metrics=counters)
    assert drain.rows['jobs', 'record']['state'] == 'dead'
    counters.record_dead_letter.inc.assert_called_once_with()
    counters.record_barrier_refusals.labels.assert_not_called()
    counters.record_barrier_aged.labels.assert_not_called()


@pytest.mark.asyncio
async def test_plain_barrier_error_and_counter_failure_never_change_the_drain(drain, monkeypatch):
    async def refuse(*args, **kwargs):
        raise ValueError(BARRIER_NOT_CLOSED)

    monkeypatch.setattr(live, 'admit_recording', refuse)
    counters = metrics()
    await live.drain_recordings(drain, metrics=counters)
    counters.record_barrier_refusals.labels.assert_called_once_with('unknown', 'unknown')

    counters = metrics()
    counters.record_barrier_refusals.labels.side_effect = RuntimeError('metrics down')
    drain.rows['jobs', 'record']['available_at'] = 0
    await live.drain_recordings(drain, metrics=counters)
    assert drain.rows['jobs', 'record']['available_at'] == NOW + 60
