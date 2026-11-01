"""Strictly rejected live rows must not strand retained speech on one generation."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database import conversations as db
from models.transcript_segment import TranscriptSegment
from routers.listen import transcripts
from tests.unit.test_live_oversized_persist_recovery import _processor, _raw_segments, _run_until
from tests.unit.test_manual_speaker_assignments import world, read


def test_null_transcript_row_merges_as_empty(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = None
    fresh = _raw_segments(1)
    for raw in fresh:
        raw['is_user'] = False
    merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert merged.created_ids == {'segment-0'}
    assert read(world)['transcript_segments'] == merged.segments


@pytest.mark.parametrize('blob', [{}, {'corrupt': True}, False, 0, '', 'corrupt'])
def test_non_null_poison_still_fails_closed(world, blob):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = blob
    before = deepcopy(store.rows)
    with pytest.raises((ValueError, TypeError)):
        db.update_conversation_segments('u', 'c', [], live_segments=_raw_segments(1))
    assert store.rows == before


@pytest.mark.asyncio
async def test_transaction_commit_is_marked_before_post_commit_reply_fault(world, monkeypatch):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = []

    async def persist(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        is_multi_channel=False,
        state=SimpleNamespace(speaker_map_dirty=False, source_position_map=None),
        persistence=SimpleNamespace(call=persist),
        speakers=SimpleNamespace(segment_assignments={}, speaker_to_person={}, segment_identity_status={}),
    )
    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = host
    processor.cache = transcripts.ConversationCache(None)
    processor.cache.data = deepcopy(store.rows[path])
    processor._legacy_segments_committed = False
    monkeypatch.setattr(transcripts, 'late_audio_intake_enabled', lambda: False)
    monkeypatch.setattr(transcripts, 'publish_committed', AsyncMock(side_effect=ValueError('synthetic reply fault')))
    raw = dict(_raw_segments(1)[0], is_user=False)
    with pytest.raises(ValueError, match='synthetic reply fault'):
        await processor._update_live_conversation(
            SimpleNamespace(id='c', transcript_segments=[]),
            [TranscriptSegment(**raw)],
            [],
            datetime.now(timezone.utc),
            None,
        )
    assert processor._legacy_segments_committed is True
    assert [s['id'] for s in read(world)['transcript_segments']] == [raw['id']]


@pytest.mark.asyncio
@pytest.mark.parametrize('probe_fault', ['none', 'raise', 'noop'])
async def test_dict_poison_rolls_over_and_commits_entire_drain_once(world, monkeypatch, probe_fault):
    store, old_path, _ = world
    store.rows[old_path]['transcript_segments'] = {'corrupt': True}
    fresh_path = (*old_path[:-1], 'fresh')
    original = deepcopy(store.rows[old_path])
    attempts, probes, commits = [], [], []
    retained = _raw_segments(8)  # Above the oversized shrink floor: lose no tail.

    async def update(_conversation, segments, _photos, _finished, _started):
        owner = state.current_conversation_id
        attempts.append(owner)
        incoming = [dict(id=s.id, text=s.text, start=s.start, end=s.end, is_user=False) for s in segments]
        merged = db.update_conversation_segments('u', owner, [], live_segments=incoming)
        commits.append((owner, [s.id for s in segments]))
        return SimpleNamespace(id=owner), [], []

    async def rollover(**kwargs):
        assert kwargs == {'rollover': True}
        probes.append((len(attempts), clock[0]))
        assert list(processor.segment_buffer) == retained
        if len(probes) == 1 and probe_fault == 'raise':
            raise RuntimeError('synthetic unavailable')
        if len(probes) == 1 and probe_fault == 'noop':
            return
        store.rows[fresh_path] = dict(id='fresh', status='in_progress', transcript_segments=[])
        state.current_conversation_id = 'fresh'

    processor, state, clock = _processor(monkeypatch, segments=deepcopy(retained), update=update, rollover=rollover)
    state.current_conversation_id = 'c'
    processor._oversized_rollover_probe_at = 0.0
    await _run_until(processor, clock, lambda: bool(commits), max_ticks=250)
    assert probes[0][0] == transcripts.LEGACY_VALUE_ERROR_ROLLOVER_FAILURES
    if probe_fault != 'none':
        assert len(probes) == 2
        assert probes[1][1] - probes[0][1] >= transcripts.OVERSIZED_ROLLOVER_PROBE_SECONDS
    assert commits == [('fresh', [raw['id'] for raw in retained])]
    assert not processor.segment_buffer
    assert store.rows[old_path] == original
    saved = read((store, fresh_path, []))['transcript_segments']
    # The production merge may absorb adjacent same-speaker IDs; every word
    # must still appear exactly once, exclusively on the fresh generation.
    assert ' '.join(raw['text'] for raw in saved) == ' '.join(raw['text'] for raw in retained)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'boundary', ['conversation', 'conversation_at_threshold', 'transient', 'post_commit', 'success', 'late_reply']
)
async def test_value_error_debt_does_not_cross_boundaries(monkeypatch, boundary):
    attempts = []

    async def update(*args):
        attempts.append(state.current_conversation_id)
        if len(attempts) == (5 if boundary == 'conversation_at_threshold' else 4):
            if boundary in {'conversation', 'conversation_at_threshold'}:
                state.current_conversation_id = 'other'
            elif boundary == 'transient':
                raise RuntimeError('synthetic transient')
            elif boundary == 'post_commit':
                processor._legacy_segments_committed = True
            else:
                processor.segment_buffer.extend(_raw_segments(2))
                if boundary == 'late_reply':
                    raise transcripts.LateTranscriptReplyError()
                return SimpleNamespace(id=state.current_conversation_id), [], []
        raise ValueError('undecodable transcript_segments: dict')

    rollover = AsyncMock()
    processor, state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0
    await _run_until(processor, clock, lambda: len(attempts) >= 7)
    rollover.assert_not_awaited()
    assert len(processor.segment_buffer) == 2


@pytest.mark.asyncio
async def test_cancelled_rollover_keeps_entire_pristine_drain(monkeypatch):
    import asyncio

    async def update(*args):
        raise ValueError('undecodable transcript_segments: dict')

    rollover = AsyncMock(side_effect=asyncio.CancelledError())
    retained = _raw_segments(8)
    processor, _, clock = _processor(monkeypatch, segments=deepcopy(retained), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0
    await _run_until(processor, clock, lambda: rollover.await_count > 0)
    assert list(processor.segment_buffer) == retained


@pytest.mark.parametrize(
    'prefix',
    [
        'undecodable transcript_segments',
        'undecodable json blob',
        'undecodable manual_speaker_assignments',
        'Cyclic transcript segment absorption',
    ],
)
def test_reason_logs_only_fixed_vocabulary(prefix):
    payload = 'SyntheticPrivatePayload@example.invalid/abcdefghijklmnopqrstuvwxyz12'
    assert transcripts._legacy_persist_reason(ValueError(f'{prefix}: {payload}')) == prefix
    assert transcripts._legacy_persist_reason(ValueError(payload)) == 'other'
    assert transcripts._legacy_persist_reason(ValueError(f'{payload}: {prefix}')) == 'other'
    assert len(transcripts._legacy_persist_reason(ValueError(prefix))) <= 60


@pytest.mark.asyncio
async def test_loop_error_log_contains_no_private_error_payload(monkeypatch, caplog):
    payload = 'SyntheticPrivatePayload@example.invalid/abcdefghijklmnopqrstuvwxyz12'

    async def update(*args):
        raise ValueError(f'undecodable transcript_segments: {payload}')

    processor, _, clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=AsyncMock())
    await _run_until(processor, clock, lambda: bool(caplog.records))
    messages = [r.getMessage() for r in caplog.records if 'Live transcript persist failed' in r.getMessage()]
    assert messages
    assert all('reason=undecodable transcript_segments' in message and payload not in message for message in messages)
