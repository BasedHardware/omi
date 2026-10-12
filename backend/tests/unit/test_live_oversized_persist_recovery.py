"""A conversation at Firestore's 1 MiB ceiling must not strand the live loop.

Failure-Class: FC-permanent-write-rejection-retried-forever — instance in
``backend/routers/listen/transcripts.py`` (legacy live persist arm, observed
2026-10-12 16:01Z→ in backend-listen): marathon conversations crossed
Firestore's 1,048,576-byte document ceiling, and every subsequent content
write came back ``InvalidArgument`` with the "exceeds the maximum allowed
size" 400 — a rejection no retry of the same (still growing) write can ever
satisfy. The legacy persist arm treated it like any transient failure: the
whole retained batch was requeued and replayed against the same poisoned row
every backoff tick (~400 rejects/hour while the storm lasted, each retaining
the deque cap of 1000 segments), the row's transcript froze for the rest of
the session, and ``segment_buffer``'s maxlen silently evicted the oldest
retained speech. The failure-class rule — a permanently rejected write must
move to storage that still accepts it — already holds in the sync and
finalization lanes; this pins it for the live lane: the size limit is
classified at the loop boundary, the retained batch shrinks (oldest speech
keeps its place and persists first on the smaller row), and the mid-session
rollover — the same recovery the no-merge-result path already exercises — is
probed at a bounded cadence when even a single retained segment is rejected,
without dropping that segment. On the parent commit every test here fails to
import (OVERSIZED_ROLLOVER_PROBE_SECONDS does not exist) and, past that, the
batch never shrinks and no rollover is ever probed.
"""

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.api_core.exceptions import InvalidArgument

import routers.listen.transcripts as transcripts_module
from routers.listen.transcripts import OVERSIZED_ROLLOVER_PROBE_SECONDS, TranscriptProcessor


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _size_limit_error() -> InvalidArgument:
    return InvalidArgument(
        "Document 'projects/based-hardware/databases/(default)/documents/users/uid/conversations/conv' "
        'cannot be written because its size (1,069,442 bytes) exceeds the maximum allowed size of '
        '1,048,576 bytes.'
    )


class _Segment:
    def __init__(self, **data):
        self.id = data['id']
        self.text = data['text']
        self.start = data['start']
        self.end = data['end']
        self.speech_profile_processed = data['speech_profile_processed']
        self.is_user = False
        self.speaker_id = data.get('speaker_id')

    def model_dump(self):
        return {'id': self.id, 'text': self.text}


def _processor(monkeypatch, *, segments, update, rollover):
    """A legacy-mode processor whose `update` (persist) carries the injected failure.

    `rollover` replaces LiveConversationController.create_new_in_progress_conversation
    so the loop's `rollover=True` await is observable without production state.
    """
    clock = [10.0]
    fake_time = SimpleNamespace(monotonic=lambda: clock[0], time=lambda: clock[0])

    state = SimpleNamespace(
        active=True,
        first_audio_byte_timestamp=100.0,
        last_transcript_time=None,
        words_transcribed_since_last_record=0,
        current_conversation_id='conversation-1',
        speaker_id_done=asyncio.Event(),
    )
    state.speaker_id_done.set()

    async def cache_get(_conversation_id):
        return {'transcript_segments': []}

    async def no_op(*_args, **_kwargs):
        return None

    host = SimpleNamespace(
        state=state,
        wait=no_op,
        request=SimpleNamespace(uid='user-1', onboarding_mode=False, websocket=SimpleNamespace()),
        transcript_send=None,
        user_has_credits=True,
        pusher_enabled=True,
        onboarding_handler=None,
        send_event=lambda _event: None,
        speakers=SimpleNamespace(drain=no_op, tasks=set()),
        complete_live_transcription=lambda: None,
        conversations=SimpleNamespace(create_new_in_progress_conversation=rollover),
    )
    processor = object.__new__(TranscriptProcessor)
    processor.host = host
    processor.segment_buffer = deque(segments)
    processor._v2_legacy_fallback = deque()
    processor._v2_legacy_fallback_ids = set()
    processor.photo_buffer = deque()
    processor.cache = SimpleNamespace(get=cache_get)
    processor.current_session_segments = {}
    processor.speaker_id_allocator = SimpleNamespace(
        hydrate=lambda _segments: None, hydrate_receipt=MagicMock(), assign=lambda _segment: None
    )
    processor._update_live_conversation = update
    processor._deliver_live_updates = no_op
    processor._speaker_detection = no_op
    processor._translate = no_op
    processor.flush_speaker_assignments = no_op
    processor._flush_failures = 0
    processor._flush_backoff_until = 0.0
    # Default: the rollover probe is disarmed (a test opts in by setting this to 0.0),
    # so shrink behavior is observed without any generation change in the way.
    processor._oversized_rollover_probe_at = float('inf')
    processor._legacy_retry_until = 0.0
    processor._legacy_persist_failures = 0

    monkeypatch.setattr(transcripts_module, 'time', fake_time)
    monkeypatch.setattr(transcripts_module, 'TranscriptSegment', _Segment)
    monkeypatch.setattr(transcripts_module, 'deserialize_conversation', lambda _data: SimpleNamespace())
    return processor, state, clock


async def _run_until(processor, clock, condition, *, max_ticks=400):
    """Drive process_loop as a supervised task until `condition` holds, then cancel.

    This mirrors production teardown: the live session's supervisor cancels the
    transcript task while a backlog is still retained (the loop deliberately
    keeps draining until its buffers empty). The fake `wait` never returns True
    so the loop's wait-gate never ends the session on its own; each call
    advances the fake clock one backoff tick.
    """
    ticks = [0]

    async def wait(_seconds):
        clock[0] += 1.0
        ticks[0] += 1
        # Yield to the loop so cancellation can land (production `wait` awaits
        # a real sleep/event; without a suspension point task.cancel() never
        # reaches the loop).
        await asyncio.sleep(0)
        return False

    processor.host.wait = wait
    task = asyncio.ensure_future(processor.process_loop())
    try:
        while not condition():
            if task.done() or ticks[0] > max_ticks:
                break
            await asyncio.sleep(0)
    finally:
        task.cancel()
        outcome = (await asyncio.gather(task, return_exceptions=True))[0]
        assert outcome is None or isinstance(outcome, asyncio.CancelledError), f'persist loop crashed: {outcome!r}'


def _raw_segments(count):
    return [{'id': f'segment-{i}', 'text': f'word {i}', 'start': float(i), 'end': float(i) + 0.5} for i in range(count)]


@pytest.mark.anyio
async def test_oversized_persist_shrinks_the_retried_batch_instead_of_replaying_it_whole(monkeypatch):
    """A 1 MiB rejection must shrink the retained batch by one per attempt — never replay
    the same full batch against the same poisoned row while maxlen silently evicts speech."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append([segment.id for segment in segments])
        raise _size_limit_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(3), update=update, rollover=rollover)

    await _run_until(processor, clock, lambda: len(batches) >= 3)

    assert batches == [
        ['segment-0', 'segment-1', 'segment-2'],
        ['segment-0', 'segment-1'],
        ['segment-0'],
    ], 'each permanent rejection must retry one segment fewer, oldest speech first'
    assert (
        len(processor.segment_buffer) == 1
    ), 'the backlog drains to its head; the last segment waits for the rollover probe'
    rollover.assert_not_called(), 'a shrinking backlog never needs the rollover probe'


@pytest.mark.anyio
async def test_oversized_persist_probes_rollover_when_a_single_segment_is_rejected(monkeypatch, caplog):
    """When even a single retained segment is rejected, the loop must probe the mid-session
    rollover — keeping the segment queued for the fresh generation, never discarding it."""
    state_holder = {}

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _size_limit_error()

    async def rollover(*_args, **_kwargs):
        state_holder['state'].current_conversation_id = 'conversation-2'
        state_holder['probed'] = True

    processor, state, clock = _processor(
        monkeypatch, segments=_raw_segments(1), update=update, rollover=AsyncMock(return_value=None)
    )
    processor.host.conversations.create_new_in_progress_conversation = rollover
    state_holder['state'] = state
    processor._oversized_rollover_probe_at = 0.0  # opt in immediately

    await _run_until(processor, clock, lambda: state_holder.get('probed', False))

    assert any('rollover escaped an over-limit conversation' in record.getMessage() for record in caplog.records)
    assert [raw['id'] for raw in processor.segment_buffer] == [
        'segment-0'
    ], 'a still-rejected segment stays retained for the fresh generation'


@pytest.mark.anyio
async def test_transient_persist_failure_keeps_the_whole_batch_retried(monkeypatch):
    """Only the permanent size limit may shrink the batch: transient failures keep today's
    whole-batch retry so no speech is ever dropped because of a timeout or contention."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise ValueError('transient')

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(3), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0  # even with the probe armed, transients never probe

    await _run_until(processor, clock, lambda: len(batches) >= 2)

    assert batches == [3, 3], 'transient failures must requeue the full batch'
    assert len(processor.segment_buffer) == 3
    rollover.assert_not_called()


@pytest.mark.anyio
async def test_rollover_probe_failure_does_not_crash_the_persist_loop(monkeypatch):
    """A failing rollover must be absorbed by the loop (the #19905 lesson): the retained
    batch stays queued for the next backoff tick instead of tearing down the session."""
    rollover = AsyncMock(side_effect=RuntimeError('binding unavailable'))

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _size_limit_error()

    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, clock, lambda: rollover.await_count >= 1)

    rollover.assert_awaited_once_with(rollover=True)
    assert len(processor.segment_buffer) == 1, 'a failed probe leaves the retained head queued'


@pytest.mark.anyio
async def test_oversized_backlog_lands_on_the_fresh_generation_after_rollover(monkeypatch):
    """End to end: the saturated row rejects the single retained segment, the rollover
    adopts a fresh conversation, and the retained speech persists there."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(segments)
        if len(calls) == 1:
            raise _size_limit_error()
        return SimpleNamespace(id='conversation-2'), segments, []

    def make_rollover(processor):
        async def rollover(*_args, **_kwargs):
            processor.host.state.current_conversation_id = 'conversation-2'

        return rollover

    processor, state, clock = _processor(
        monkeypatch, segments=_raw_segments(1), update=update, rollover=AsyncMock(return_value=None)
    )
    processor.host.conversations.create_new_in_progress_conversation = make_rollover(processor)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, clock, lambda: len(calls) >= 2)

    assert len(calls) == 2
    assert [segment.id for segment in calls[1]] == ['segment-0'], 'the retained speech persists after the rollover'
    assert state.current_conversation_id == 'conversation-2'
    assert len(processor.segment_buffer) == 0
    assert processor._legacy_persist_failures == 0, 'a successful persist resets the backoff ladder'
    assert OVERSIZED_ROLLOVER_PROBE_SECONDS == 60.0


@pytest.mark.anyio
async def test_probe_paces_at_one_attempt_per_interval_while_the_row_stays_saturated(monkeypatch):
    """A row that stays over the limit must not churn one rollover generation per
    backoff tick: the probe re-arms only after the full pacing interval."""
    rollover = AsyncMock(return_value=None)

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _size_limit_error()

    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0
    # Advance the clock far past two pacing intervals while the row keeps rejecting:
    # the second probe must fire only after OVERSIZED_ROLLOVER_PROBE_SECONDS.
    await _run_until(processor, clock, lambda: clock[0] >= 10.0 + 2 * OVERSIZED_ROLLOVER_PROBE_SECONDS + 5.0)

    assert rollover.await_count == 2, f'exactly one probe per pacing interval expected, got {rollover.await_count}'


@pytest.mark.anyio
async def test_v2_persistence_is_outside_the_oversized_shrink_contract(monkeypatch, caplog):
    """The shrink contract is legacy-arm only: a v2 (audio-timeline) batch keeps the
    existing whole-batch retry — v2 has its own budget and fallback lane, and the
    oversized probe must never fire from a v2 failure."""
    seen = {}

    async def fake_process_v2_batches(segments, photos, _diarized):
        seen['segments'] = list(segments)
        raise _size_limit_error()

    rollover = AsyncMock(return_value=None)
    segments = [dict(raw, id=f'v2-{raw["id"]}') for raw in _raw_segments(2)]
    processor, state, clock = _processor(
        monkeypatch, segments=segments, update=AsyncMock(return_value=None), rollover=rollover
    )
    state.capture_timeline_v2 = True
    processor._process_v2_batches = fake_process_v2_batches
    processor._v2_committed_ids = set()
    processor._v2_photos_committed = False
    processor._v2_photos_requeued = False
    processor._v2_retry_counts = {}
    processor._v2_retry_until = 0.0
    processor._v2_photo_failures = 0
    processor._oversized_rollover_probe_at = 0.0  # armed: the v2 arm must never consult it

    await _run_until(processor, clock, lambda: 'segments' in seen)

    assert [raw['id'] for raw in processor.segment_buffer] == [
        'v2-segment-0',
        'v2-segment-1',
    ], 'v2 retains the whole failed batch for its own retry'
    assert rollover.await_count == 0, 'the legacy rollover probe must not fire from a v2 failure'
    assert not any('rollover escaped' in record.getMessage() for record in caplog.records)


@pytest.mark.anyio
async def test_cancellation_during_a_failed_persist_requeues_the_whole_batch_and_propagates(monkeypatch):
    """Teardown must behave exactly as before: CancelledError propagates (the supervisor
    owns the session lifecycle) and the retained batch is requeued intact — shrink
    decisions and the rollover probe are reserved for genuine persist failures."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise asyncio.CancelledError()

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(3), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0

    async def wait(_seconds):
        clock[0] += 1.0
        await asyncio.sleep(0)
        return False

    processor.host.wait = wait
    task = asyncio.ensure_future(processor.process_loop())
    await asyncio.wait({task}, timeout=5.0)

    assert task.cancelled() or (
        task.done() and isinstance(task.exception(), asyncio.CancelledError)
    ), 'cancellation must propagate out of the persist loop'
    assert batches == [3], 'the batch was attempted whole before the cancellation'
    assert len(processor.segment_buffer) == 3, 'the retained batch is requeued intact'
    rollover.assert_not_called()


@pytest.mark.anyio
async def test_oversized_persist_telemetry_never_marks_the_recovery_recovered(monkeypatch):
    """Every classified size-limit rejection counts as degraded: the metric family must
    stay a truthful denominator for the recovery, never flip to a success outcome while
    segments are still being dropped."""
    fallbacks = []
    real_record = transcripts_module.record_fallback

    def spy_record(**kwargs):
        fallbacks.append(kwargs)
        return real_record(**kwargs)

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _size_limit_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')
    monkeypatch.setattr(transcripts_module, 'record_fallback', spy_record)

    await _run_until(processor, clock, lambda: len(fallbacks) >= 2)

    assert fallbacks, 'each permanent rejection is counted'
    for event in fallbacks:
        assert event['reason'] == 'document_size_limit'
        assert event['outcome'] == 'degraded'
        assert event['component'] == 'other'
        assert event['from_mode'] == 'live_transcript_persist'
        assert event['to_mode'] in {'shrink_retry', 'none'}


@pytest.mark.anyio
async def test_expired_transaction_invalidargument_is_not_classified_oversized(monkeypatch):
    """The classifier must split Firestore's two InvalidArgument 400s: an expired
    transaction id ('The referenced transaction has expired...') is transient — the
    storage boundary already restarts it — so the loop must keep the whole-batch
    retry and never shrink or probe on it. Today's storm contained both kinds; this
    pin keeps the shrink from ever firing on the wrong 400."""
    expired = InvalidArgument('400 The referenced transaction has expired or is no longer valid.')
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise expired

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(3), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0  # armed: the expired-txn class must not consult it

    await _run_until(processor, clock, lambda: len(batches) >= 2)

    assert batches == [3, 3], 'expired-transaction InvalidArgument keeps the whole-batch retry'
    assert len(processor.segment_buffer) == 3
    rollover.assert_not_called()


@pytest.mark.anyio
async def test_failed_persist_never_requeues_photos_under_oversized_shrink(monkeypatch):
    """Photos were drained with the batch and must be requeued whatever the failure
    class: the photo contract is unchanged by the shrink decision."""

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _size_limit_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    requeued = []

    def requeue(segs, ph):
        requeued.append(list(ph))
        for raw in segs or []:
            processor.segment_buffer.append(raw)
        for photo in ph or []:
            processor.photo_buffer.append(photo)

    processor._requeue_legacy_persist = requeue

    # The photo rides the same tick: process_loop drains both buffers into the
    # persist call and requeues both on failure.
    processor.photo_buffer = deque([SimpleNamespace(id='photo-1')])

    await _run_until(processor, clock, lambda: len(requeued) >= 1)

    assert requeued, 'the failed persist requeued its payload'
    assert [photo.id for photo in requeued[0]] == ['photo-1'], 'photos ride the retry regardless of the shrink decision'


@pytest.mark.anyio
async def test_oversized_retry_resumes_into_a_recovered_row_without_writing_twice(monkeypatch):
    """A row that recovers mid-shrink (finalization compacted it) must accept the
    remaining batch whole — no leftover retry loop, no duplicate of the dropped tail."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append([segment.id for segment in segments])
        if len(calls) == 1:
            raise _size_limit_error()
        assert [segment.id for segment in segments] == [
            'segment-0'
        ], 'the shrunk remainder persists exactly once after the row recovers'
        return SimpleNamespace(id='conversation-1'), segments, []

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, clock, lambda: len(calls) >= 2)

    assert calls == [
        ['segment-0', 'segment-1'],
        ['segment-0'],
    ], 'the dropped tail stays dropped; the remainder commits once'
    assert len(processor.segment_buffer) == 0


@pytest.mark.anyio
async def test_prolonged_saturation_never_empties_the_retained_queue(monkeypatch):
    """The shrink floor is one segment: however long the row stays over the limit,
    the loop must not discard the queue head — that is the rollover probe's job."""
    drops = []
    previous = [2]

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        drops.append(previous[0] - len(segments))
        previous[0] = len(segments)
        raise _size_limit_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, clock, lambda: clock[0] >= 10.0 + 240.0)

    assert len(processor.segment_buffer) == 1, 'the queue head survives saturation indefinitely'
    assert sum(drops) == 1, 'exactly one tail segment was dropped before the floor'


@pytest.mark.anyio
async def test_shrink_keeps_the_existing_transient_backoff_ladder(monkeypatch):
    """The shrink decision changes WHAT is retried, never HOW SOON: the legacy backoff
    ladder (.5/1/2/4/8s cap) stays identical so a size-limit conversation cannot speed
    up or slow down the loop relative to any other failure."""

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _size_limit_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, clock, lambda: processor._legacy_persist_failures >= 3)

    assert processor._legacy_persist_failures == 3
    assert processor._legacy_retry_until >= clock[0], 'the backoff gate is armed into the future'
    assert processor._legacy_retry_until - clock[0] <= 8.0, 'the ladder cap stays at 8 seconds'
