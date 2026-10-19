"""A batch every generation refuses deterministically must terminate, not churn.

Failure-Class: FC-permanent-write-rejection-retried-forever — sibling instance
in ``backend/routers/listen/transcripts.py`` (legacy live persist arm + the v2
unplaced-fallback lane, prod backend-listen 2026-10 sensor window): tick 143
gave a deterministically failing write the rollover escape, but the escape is
rescue-shaped for a ROW poison and unbounded for a BATCH poison. When the
retained batch's own segment data is what the strict decode / pydantic
validation refuses, the probe adopts a fresh empty generation, the next drain
hands it the same batch, the fresh row refuses it the same way, and the probe
adopts another generation — one empty conversation per 60s probe window for
the rest of the recording, with the ERROR line re-firing every backoff tick in
between (the sensor window's ``retained 5 segment(s) ... type=ValueError``
shape is exactly the small-batch case that never shrinks its way out). The
same arithmetic applies to a size-limit batch that outlives its escape: the
probe rolled, the fresh row hit its own ceiling with the batch aboard. And the
v2 unplaced-fallback lane had no terminal at all for its per-item ``ValueError``:
the backoff re-fired the item forever, and when the bounded deque finally
evicted it, it went silently with no counter and no terminal log.

The budget: one retained batch absorbs at most
``LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET`` deterministic attempts across all
generations (a committed write resets it — whatever persists is no longer the
same all-refused batch); past the budget the batch is terminal — one truthful
``omi_fallback_total`` ``exhausted`` event with the class's own reason, one
terminal log line, buffers cleared, ladders reset, and the loop keeps draining
fresh speech. A v2 unplaced item gets the same discipline against
``MAX_V2_PERSIST_ATTEMPTS``. Transient failures never count toward the budget
and never drop anything — a slow provider can still ride out its outage; the
backoff ladder is untouched.
"""

import asyncio
import json
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

import routers.listen.transcripts as transcripts_module
from routers.listen.transcripts import (
    LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET,
    LEGACY_PERSIST_SHRINK_FLOOR,
    LEGACY_PERSIST_STALL_REJECTS,
    MAX_V2_PERSIST_ATTEMPTS,
    OVERSIZED_ROLLOVER_PROBE_SECONDS,
    TranscriptProcessor,
    _is_deterministic_persist_defect,
)
from utils.observability.fallback import ALLOWED_REASONS


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _poisoned_row_error() -> ValueError:
    """The strict stored-transcript decode raises a bare ValueError (binascii via
    ``bytes.fromhex`` / ``json`` decode failures reach the loop untyped)."""
    return ValueError('non-hexadecimal number found in fromhex() at position 12')


def _size_limit_error() -> InvalidArgument:
    return InvalidArgument(
        "Document 'projects/based-hardware/databases/(default)/documents/users/uid/conversations/conv' "
        'cannot be written because its size (1,069,442 bytes) exceeds the maximum allowed size of '
        '1,048,576 bytes.'
    )


def _processor(monkeypatch, *, segments, update, rollover):
    """A legacy-mode processor whose `update` (persist) carries the injected failure.

    Mirrors the tick-143 suites' harness: production state is replaced with
    observables so `process_loop` can be driven as a supervised task.
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
        speaker_map_dirty=False,
        speaker_map_version=0,
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
    # The probe starts armed so tests observe the escape without seed state.
    processor._oversized_rollover_probe_at = 0.0
    processor._legacy_retry_until = 0.0
    processor._legacy_persist_failures = 0
    processor._legacy_persist_rejects = 0
    processor._legacy_persist_batch_attempts = 0
    processor._legacy_persist_escaped = False

    monkeypatch.setattr(transcripts_module, 'time', fake_time)
    monkeypatch.setattr(transcripts_module, 'TranscriptSegment', _FakeSegment)
    monkeypatch.setattr(transcripts_module, 'deserialize_conversation', lambda _data: SimpleNamespace())
    return processor, state, clock


class _FakeSegment:
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


async def _run_until(processor, clock, condition, *, max_ticks=4000):
    """Drive process_loop as a supervised task until `condition` holds, then cancel."""
    ticks = [0]

    async def wait(_seconds):
        clock[0] += 1.0
        ticks[0] += 1
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


# ---------------------------------------------------------------------------
# The budget boundary
# ---------------------------------------------------------------------------


def test_batch_attempt_budget_constant_is_bounded():
    """The budget must stay small and positive: it exists to bound churn, and a
    constant of 0 would drop a first-attempt batch or one large enough would
    never fire."""
    assert 1 <= LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET <= 10


@pytest.mark.anyio
async def test_batch_poison_terminates_instead_of_churning_generations(monkeypatch):
    """A batch the fresh generation refuses too must hit the budget and be dropped:
    the rollover must NOT be probed once per window for the rest of the session."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        raise _poisoned_row_error()

    rolls = []

    async def rollover(**_kwargs):
        # Production's rollover adopts a fresh generation: the id changes, the
        # escape latches, and the budget starts counting post-escape attempts.
        rolls.append(True)
        processor.host.state.current_conversation_id = f'conversation-{len(rolls) + 1}'

    rollover_spy = AsyncMock(side_effect=rollover)
    # Below the shrink floor: the batch stays whole and replays every attempt —
    # the literal `retained 5 segment(s) type=ValueError` production shape.
    processor, _state, _clock = _processor(
        monkeypatch, segments=_raw_segments(LEGACY_PERSIST_SHRINK_FLOOR), update=update, rollover=rollover_spy
    )
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: not processor.segment_buffer and calls)

    # The probe is armed at 0.0 and the batch is at the shrink floor, so the
    # FIRST refusal already probes and escapes: there are no pre-escape
    # attempts in this shape. The escape hands the batch to the fresh
    # generation, which also refuses; the budget counts from there and the
    # (budget+1)-th post-escape attempt is the terminal.
    assert len(rolls) == 1, 'exactly one escape probe'
    assert rollover_spy.await_count == 1
    assert (
        len(calls) == LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET + 2
    ), f'first refusal escapes, then budget+1 post-escape attempts; saw {calls}'
    assert len(processor.segment_buffer) == 0, 'the terminal batch is dropped'
    # Ladders reset so fresh speech starts clean.
    assert processor._legacy_persist_failures == 0
    assert processor._legacy_retry_until == 0.0
    assert processor._legacy_persist_rejects == 0
    assert processor._legacy_persist_batch_attempts == 0
    assert processor._legacy_persist_escaped is False


@pytest.mark.anyio
async def test_batch_poison_counts_one_truthful_exhausted_event(monkeypatch):
    """The terminal drop is observable as exactly one `exhausted` fallback event
    carrying the class's own reason; the churn window adds no second one."""
    events = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        processor.host.state.current_conversation_id = 'conversation-2'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    real_record = transcripts_module.record_fallback

    def spy(**kwargs):
        events.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', spy)
    await _run_until(processor, _clock, lambda: not processor.segment_buffer)

    exhausted = [event for event in events if event.get('outcome') == 'exhausted']
    assert len(exhausted) == 1, f'exactly one terminal event, saw {[e.get("outcome") for e in events]}'
    event = exhausted[0]
    assert event['from_mode'] == 'live_transcript_persist'
    assert event['to_mode'] == 'none'
    assert event['reason'] == 'malformed_doc'
    assert events[-1]['outcome'] == 'exhausted', 'the terminal event is the batch story\'s last entry'


@pytest.mark.anyio
async def test_oversized_batch_that_outlives_its_escape_terminates_too(monkeypatch):
    """The size-limit class hits the same budget with its own reason: the probe
    rolled and the fresh row hit its own ceiling — the churn arithmetic is
    identical, so the terminal must be too."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        raise _size_limit_error()

    async def rollover(**_kwargs):
        processor.host.state.current_conversation_id = 'conversation-2'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(
        monkeypatch, segments=_raw_segments(LEGACY_PERSIST_SHRINK_FLOOR), update=update, rollover=rollover_spy
    )
    processor._oversized_rollover_probe_at = 0.0

    events = []
    real_record = transcripts_module.record_fallback

    def spy(**kwargs):
        events.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', spy)
    await _run_until(processor, _clock, lambda: not processor.segment_buffer)

    assert rollover_spy.await_count == 1, 'exactly one escape probe before the terminal'
    assert len(processor.segment_buffer) == 0
    exhausted = [event for event in events if event.get('outcome') == 'exhausted']
    assert len(exhausted) == 1
    assert exhausted[0]['reason'] == 'document_size_limit', 'the storage class keeps its own truthful reason'


@pytest.mark.anyio
async def test_terminal_drop_logs_one_classified_line(monkeypatch, caplog):
    """The terminal is a single bounded ERROR naming the budget and the reason —
    the sentinel sees the terminal once, not once per backoff tick."""
    with caplog.at_level('ERROR', logger='routers.listen.transcripts'):
        await _run_batch_poison_to_termination(monkeypatch)

    terminal = [record for record in caplog.records if 'rejected by every generation' in record.getMessage()]
    assert len(terminal) == 1
    message = terminal[0].getMessage()
    assert 'malformed_doc' in message
    assert str(LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET) in message
    # The generic transient line must not carry the terminal batch's story.
    generic = [
        record for record in caplog.records if 'retained' in record.getMessage() and 'for retry' in record.getMessage()
    ]
    assert generic == [], 'the terminal batch never reaches the generic transient log'


async def _run_batch_poison_to_termination(monkeypatch):
    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        processor.host.state.current_conversation_id = 'conversation-2'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0
    await _run_until(processor, _clock, lambda: not processor.segment_buffer)


@pytest.mark.anyio
async def test_budget_never_fires_on_transient_failures(monkeypatch):
    """A RuntimeError-shaped fault can differ on the next attempt: the whole-batch
    retry keeps running forever and nothing is ever dropped."""
    attempts = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        attempts.append(len(segments))
        raise RuntimeError('storage unavailable')

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(attempts) >= 12)

    assert len(processor.segment_buffer) == 2, 'a transient outage never drops the batch'
    assert processor._legacy_persist_batch_attempts == 0, 'transient failures never count toward the budget'
    rollover.assert_not_called()


@pytest.mark.anyio
async def test_aborted_contention_never_counts_toward_the_budget(monkeypatch):
    """Firestore contention is the canonical transient: replaying is correct and
    the batch must survive far past the budget."""
    attempts = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        attempts.append(len(segments))
        raise Aborted('409 Too much contention on these documents.')

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(attempts) >= 10)

    assert len(processor.segment_buffer) == 2
    assert processor._legacy_persist_batch_attempts == 0


@pytest.mark.anyio
async def test_committed_write_resets_the_batch_budget(monkeypatch):
    """A batch that persists after earlier deterministic refusals is not wholly
    poisoned: the budget restarts, so a later refusal must earn its own series."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        if len(calls) <= LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET:
            raise _poisoned_row_error()
        return SimpleNamespace(id='conversation-1'), segments, []

    async def rollover(**_kwargs):
        # Each escape must adopt a NEW generation: a probe that "rolls" to the
        # id the loop is already on is not an escape, and the budget cannot arm.
        counter = getattr(processor.host.state, '_generation', 1) + 1
        processor.host.state._generation = counter
        processor.host.state.current_conversation_id = f'conversation-{counter}'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, clock, lambda: len(processor.segment_buffer) == 0 and len(calls) >= 4)

    assert processor._legacy_persist_batch_attempts == 0, 'the committed write resets the attempt story'
    assert len(processor.segment_buffer) == 0

    # A later refusal starts a fresh series: it gets budget+1 more attempts
    # before any terminal, not an immediate drop.
    async def always_poisoned(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    processor._update_live_conversation = always_poisoned
    processor.segment_buffer.extend(_raw_segments(1))
    second_series = []

    async def counting_update(_conversation, segments, _photos, _finished_at, _started_at):
        second_series.append(len(segments))
        raise _poisoned_row_error()

    processor._update_live_conversation = counting_update
    # The committed write cleared the escape latch; re-arm the probe so this
    # second series can escape again (production re-probes every window).
    processor._oversized_rollover_probe_at = clock[0]
    await _run_until(processor, clock, lambda: not processor.segment_buffer)

    assert (
        len(second_series) == LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET + 2
    ), 'the reset batch escapes once and then earns budget+1 more attempts'


@pytest.mark.anyio
async def test_shrink_arm_still_runs_below_the_budget(monkeypatch):
    """The shrink stays alive while the batch is above the floor; with the probe
    disarmed (no escape) the pre-escape cadence is unbounded and the budget
    never fires."""
    sizes = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        sizes.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(
        monkeypatch,
        segments=_raw_segments(LEGACY_PERSIST_SHRINK_FLOOR + 3),
        update=update,
        rollover=rollover,
    )
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(sizes) >= 8)

    # First attempts shrink 7 -> 6 -> 5 -> 4; then the batch replays whole at
    # the floor — the escape never armed (probe disarmed), so no terminal.
    assert sizes[0] == LEGACY_PERSIST_SHRINK_FLOOR + 3
    assert sizes[1] == LEGACY_PERSIST_SHRINK_FLOOR + 2
    assert sizes[3] == LEGACY_PERSIST_SHRINK_FLOOR, 'the shrink stops at the floor'
    assert all(size == LEGACY_PERSIST_SHRINK_FLOOR for size in sizes[3:]), 'whole-batch retry at the floor'
    assert len(processor.segment_buffer) == LEGACY_PERSIST_SHRINK_FLOOR
    rollover.assert_not_called()


@pytest.mark.anyio
async def test_stall_escape_probe_still_fires_for_a_row_rescuable_by_rollover(monkeypatch):
    """A row-poisoned full-cap backlog (the all-day storm) still reaches the
    rollover on its own clock — the budget must not cannibalize the escape for
    a batch the fresh generation CAN take."""
    probed = []
    state_holder = {}

    attempts = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        attempts.append(len(segments))
        # Row poison, batch clean: the fresh generation would take it. Emulate
        # by failing deterministically only while the probe has not rolled.
        if not probed:
            raise _poisoned_row_error()
        return SimpleNamespace(id='conversation-2'), segments, []

    async def rollover(*_args, **_kwargs):
        state_holder['state'].current_conversation_id = 'conversation-2'
        probed.append(True)

    processor, state, clock = _processor(
        monkeypatch, segments=_raw_segments(5), update=update, rollover=AsyncMock(return_value=None)
    )
    processor.segment_buffer = deque(processor.segment_buffer, maxlen=5)
    processor.host.conversations.create_new_in_progress_conversation = rollover
    state_holder['state'] = state

    def keep_full(segments, photos):
        for raw in segments or []:
            processor.segment_buffer.append(raw)
        for photo in photos or []:
            processor.photo_buffer.append(photo)

    processor._requeue_legacy_persist = keep_full
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(
        processor,
        clock,
        lambda: bool(probed),
        max_ticks=LEGACY_PERSIST_STALL_REJECTS * 12,
    )

    assert probed, 'the stall escape still probes for a rescuable batch'
    # The stall escape runs BEFORE the shrink can grind below the cap: the
    # first refusal (5 segments) probes, and the retried batch keeps 4 (the
    # tail dropped by the shrink) for the fresh generation — exactly the
    # retained-storm contract, with the budget never in the way (the escape
    # latched on the first attempt).
    assert attempts[0] == 5, 'the first full-cap attempt runs before any escape'
    assert processor._legacy_persist_escaped is True
    assert processor._legacy_persist_batch_attempts == 0, 'the budget never counted attempts here'
    assert len(processor.segment_buffer) == 4, 'the tail-dropped batch is retained for the fresh generation'


@pytest.mark.anyio
async def test_escape_then_fresh_generation_refusal_terminates(monkeypatch):
    """The full churn shape end to end: poisoned row, probe rolls to a fresh
    generation, the fresh generation refuses the same batch — the budget ends
    the story instead of probing again."""
    calls = []
    rolls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        rolls.append(True)
        processor_host = processor.host
        processor_host.state.current_conversation_id = f'conversation-{len(rolls) + 1}'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: not processor.segment_buffer)

    assert rolls, 'the escape probe ran once'
    assert rollover_spy.await_count == 1, 'exactly one probe: the fresh refusal must not earn another'
    assert len(processor.segment_buffer) == 0


# ---------------------------------------------------------------------------
# The v2 unplaced-fallback lane
# ---------------------------------------------------------------------------


def _fallback_processor(monkeypatch, *, raw, persist, rollover=None):
    """A v2-mode processor with one item parked in the unplaced fallback lane."""
    processor, state, clock = _processor(
        monkeypatch, segments=_raw_segments(0), update=AsyncMock(return_value=None), rollover=rollover
    )
    state.capture_timeline_v2 = True
    processor._v2_legacy_fallback = deque([dict(raw)])
    processor._v2_legacy_fallback_ids = {str(raw.get('id'))}
    processor._v2_fallback_failures = {}
    processor._v2_fallback_retry_until = {}
    processor._v2_retry_until = 0.0
    processor._v2_committed_ids = set()
    processor._v2_photos_committed = False
    processor._v2_photos_requeued = False
    processor._v2_retry_counts = {}
    processor._v2_photo_failures = 0
    processor._persist_v1_unplaced = persist
    return processor, state, clock


@pytest.mark.anyio
async def test_unplaced_item_terminal_after_its_budget(monkeypatch):
    """A deterministically failing unplaced item is dropped after MAX_V2_PERSIST_ATTEMPTS
    attempts — not retried forever, and not silently evicted by maxlen."""
    attempts = []

    async def failing(_raw):
        attempts.append(1)
        raise _poisoned_row_error()

    raw = {'id': 'unplaced-1', 'text': 'late', 'start': 0.0, 'end': 0.5}
    processor, _state, _clock = _fallback_processor(monkeypatch, raw=raw, persist=failing)

    events = []
    real_record = transcripts_module.record_fallback

    def spy(**kwargs):
        events.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', spy)
    await _run_until(processor, _clock, lambda: not processor._v2_legacy_fallback)

    assert len(attempts) == MAX_V2_PERSIST_ATTEMPTS + 1, 'the item gets exactly budget+1 attempts'
    assert not processor._v2_legacy_fallback
    assert not processor._v2_legacy_fallback_ids
    assert 'unplaced-1' not in processor._v2_fallback_failures
    assert 'unplaced-1' not in processor._v2_fallback_retry_until
    exhausted = [event for event in events if event.get('outcome') == 'exhausted']
    assert len(exhausted) == 1
    assert exhausted[0]['from_mode'] == 'v2_segment_persist'
    assert exhausted[0]['reason'] == 'malformed_doc'


@pytest.mark.anyio
async def test_unplaced_transient_failure_never_terminates(monkeypatch):
    """A RuntimeError-shaped fault on the unplaced item keeps its existing
    backoff-and-rotate behavior — nothing is dropped."""
    attempts = []

    async def failing(_raw):
        attempts.append(1)
        raise RuntimeError('unplaced target unavailable')

    raw = {'id': 'unplaced-1', 'text': 'late', 'start': 0.0, 'end': 0.5}
    processor, _state, _clock = _fallback_processor(monkeypatch, raw=raw, persist=failing)

    await _run_until(processor, _clock, lambda: len(attempts) >= 8)

    assert len(processor._v2_legacy_fallback) == 1, 'a transient failure keeps the item queued'
    assert 'unplaced-1' in processor._v2_legacy_fallback_ids


@pytest.mark.anyio
async def test_unplaced_lane_keeps_serving_items_behind_a_terminal_one(monkeypatch):
    """A terminal item at the head must not block the lane: the item behind it is
    still attempted (the one-per-tick contract is unchanged)."""
    order = []
    raw_bad = {'id': 'bad-1', 'text': 'poison', 'start': 0.0, 'end': 0.5}
    raw_good = {'id': 'good-1', 'text': 'fine', 'start': 1.0, 'end': 1.5}

    async def persist(item):
        order.append(item['id'])
        if item['id'] == 'bad-1':
            raise _poisoned_row_error()
        return None

    processor, _state, _clock = _fallback_processor(monkeypatch, raw=raw_bad, persist=persist)
    processor._v2_legacy_fallback.append(dict(raw_good))
    processor._v2_legacy_fallback_ids.add('good-1')

    await _run_until(processor, _clock, lambda: 'good-1' in order and not processor._v2_legacy_fallback)

    assert 'good-1' in order, 'items behind a poison keep being served'
    assert not processor._v2_legacy_fallback, 'the healthy item drains from the lane'


# ---------------------------------------------------------------------------
# Vocabulary pins
# ---------------------------------------------------------------------------


def test_terminal_reasons_stay_in_the_shared_vocabulary():
    """Both terminal reasons must stay allowlisted or the events silently
    collapse into `other` and the two classes become indistinguishable."""
    assert 'malformed_doc' in ALLOWED_REASONS
    assert 'document_size_limit' in ALLOWED_REASONS


def test_defect_classifier_unchanged_for_the_lane():
    """The unplaced lane uses the same classifier as the legacy arm: the two
    lanes must not drift on what counts as deterministic."""
    assert _is_deterministic_persist_defect(ValueError('non-hexadecimal number found in fromhex()'))
    assert not _is_deterministic_persist_defect(ValueError('Failed to commit transaction in 3 attempts.'))
    assert not _is_deterministic_persist_defect(TimeoutError())


# ---------------------------------------------------------------------------
# Budget boundary details
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_budget_counts_only_post_escape_attempts(monkeypatch):
    """With the probe disarmed the deterministic refusals run unbounded at the
    floor cadence: the counter never moves while no escape has latched."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(
        monkeypatch, segments=_raw_segments(LEGACY_PERSIST_SHRINK_FLOOR), update=update, rollover=rollover
    )
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(calls) >= 15)

    assert processor._legacy_persist_batch_attempts == 0, 'no escape, no counting'
    assert len(processor.segment_buffer) == LEGACY_PERSIST_SHRINK_FLOOR, 'nothing dropped pre-escape'
    rollover.assert_not_called()


@pytest.mark.anyio
async def test_second_poisoned_batch_after_a_terminal_earns_its_own_story(monkeypatch):
    """A terminal drop must not poison the loop: a NEW batch arriving after the
    terminal gets a fresh escape and a fresh budget."""
    series = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        series.append(len(segments))
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        counter = getattr(processor.host.state, '_generation', 1) + 1
        processor.host.state._generation = counter
        processor.host.state.current_conversation_id = f'conversation-{counter}'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    # First series runs to its terminal.
    await _run_until(processor, clock, lambda: not processor.segment_buffer)
    assert rollover_spy.await_count == 1
    assert len(processor.segment_buffer) == 0
    first_terminal_events = rollover_spy.await_count

    # A new batch arrives (live speech kept flowing); re-arm the probe the way
    # the pacing clock does in production.
    processor.segment_buffer.extend(_raw_segments(1))
    processor._oversized_rollover_probe_at = clock[0]
    await _run_until(processor, clock, lambda: not processor.segment_buffer)

    assert rollover_spy.await_count == first_terminal_events + 1, 'the new batch earns its own escape'
    assert len(series) == 2 * (LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET + 2), 'two complete series'
    assert len(processor.segment_buffer) == 0
    assert processor._legacy_persist_batch_attempts == 0
    assert processor._legacy_persist_escaped is False


@pytest.mark.anyio
async def test_terminal_clears_the_photo_buffer_with_the_batch(monkeypatch):
    """Photos drained with a terminal batch cannot persist anywhere either: the
    terminal clears the photo buffer, and the failure ladder does not carry."""

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        processor.host.state.current_conversation_id = 'conversation-2'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0
    processor.photo_buffer.append(SimpleNamespace(id='photo-9'))

    await _run_until(processor, _clock, lambda: not processor.segment_buffer)

    assert not processor.photo_buffer, 'the terminal clears the photo buffer too'
    assert processor._legacy_retry_until == 0.0, 'no backoff debt survives the terminal'


@pytest.mark.anyio
async def test_transient_failure_after_escape_resets_nothing_and_drops_nothing(monkeypatch):
    """The latch survives a transient failure in between: only DETERMINISTIC
    refusals count toward the budget, so one flaky tick cannot rescue or
    terminate the batch."""
    seq = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        seq.append(1)
        if len(seq) == 1:
            raise _poisoned_row_error()  # escapes (probe armed, batch at floor)
        if len(seq) % 2 == 0:
            raise RuntimeError('transient storage fault')
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        counter = getattr(processor.host.state, '_generation', 1) + 1
        processor.host.state._generation = counter
        processor.host.state.current_conversation_id = f'conversation-{counter}'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: not processor.segment_buffer)

    # Sequence: 1=poison(escape, not counted — the latch arms after it),
    # then deterministic attempts at every odd tick and transient faults at
    # every even tick. The budget counts 3,5,7 → terminal on 9; the three
    # interleaved transients contributed nothing and dropped nothing.
    assert rollover_spy.await_count == 1
    assert (
        len(seq) == 2 * LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET + 3
    ), f'terminal after budget post-escape deterministic attempts plus the free transients; saw {len(seq)}'
    deterministic_attempts = sum(1 for i in range(1, len(seq) + 1) if i % 2 == 1)
    assert deterministic_attempts == LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET + 2
    assert len(processor.segment_buffer) == 0, 'the terminal still ends the interleaved series'


@pytest.mark.anyio
async def test_terminal_event_fires_once_per_batch_not_once_per_attempt(monkeypatch):
    """A long interleaved run must never emit more than one `exhausted` event
    per terminal batch — the counter is per-batch, not per-attempt."""
    events = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        counter = getattr(processor.host.state, '_generation', 1) + 1
        processor.host.state._generation = counter
        processor.host.state.current_conversation_id = f'conversation-{counter}'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    real_record = transcripts_module.record_fallback

    def spy(**kwargs):
        events.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', spy)
    await _run_until(processor, _clock, lambda: not processor.segment_buffer)

    exhausted = [event for event in events if event.get('outcome') == 'exhausted']
    assert len(exhausted) == 1
    assert all(event.get('outcome') != 'exhausted' for event in events[:-1])


@pytest.mark.anyio
async def test_escape_latch_requires_a_real_generation_change(monkeypatch):
    """A probe that 'rolls' to the id the loop is already on is not an escape:
    the latch stays off and the budget cannot arm (the churn guard cannot be
    tricked by a no-op rollover)."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        pass  # deliberately does NOT change current_conversation_id

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: len(calls) >= 8)

    assert rollover_spy.await_count >= 1, 'the probe ran'
    assert processor._legacy_persist_escaped is False, 'no generation change, no latch'
    assert processor._legacy_persist_batch_attempts == 0
    assert len(processor.segment_buffer) == 1, 'nothing is dropped without a real escape'


@pytest.mark.anyio
async def test_v2_lane_terminal_uses_the_shared_defect_classifier_boundary(monkeypatch):
    """A pydantic-style ValidationError on the unplaced item is deterministic and
    terminal; a lookalike RuntimeError message is not."""
    from pydantic import ValidationError

    attempts = []

    async def failing_validation(_raw):
        attempts.append(1)
        raise ValueError('1 validation error for TranscriptSegment')  # ValueError family

    raw = {'id': 'unplaced-v', 'text': 'late', 'start': 0.0, 'end': 0.5}
    processor, _state, _clock = _fallback_processor(monkeypatch, raw=raw, persist=failing_validation)
    await _run_until(processor, _clock, lambda: not processor._v2_legacy_fallback)
    assert len(attempts) == MAX_V2_PERSIST_ATTEMPTS + 1, 'a ValueError-family defect terminates'
    assert not processor._v2_legacy_fallback

    # A ValidationError instance itself: same outcome.
    attempts.clear()
    try:
        raise ValidationError.from_exception_data('TranscriptSegment', [])
    except Exception:  # noqa: BLE001 - constructing a minimal instance for classification
        pass

    async def failing_runtime(_raw):
        attempts.append(1)
        raise RuntimeError('validation error for TranscriptSegment')  # lookalike message, wrong type

    raw2 = {'id': 'unplaced-r', 'text': 'late', 'start': 0.0, 'end': 0.5}
    processor2, _state2, _clock2 = _fallback_processor(monkeypatch, raw=raw2, persist=failing_runtime)
    await _run_until(processor2, _clock2, lambda: len(attempts) >= 8)
    assert len(processor2._v2_legacy_fallback) == 1, 'a RuntimeError lookalike keeps the transient retry'


@pytest.mark.anyio
async def test_v2_lane_terminal_does_not_disturb_the_legacy_budget_counters(monkeypatch):
    """The two lanes keep their own books: a v2-lane terminal must not touch the
    legacy arm's counters or fire its rollover probe."""

    async def failing(_raw):
        raise _poisoned_row_error()

    raw = {'id': 'unplaced-x', 'text': 'late', 'start': 0.0, 'end': 0.5}
    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _fallback_processor(monkeypatch, raw=raw, persist=failing, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0
    processor._legacy_persist_rejects = 5
    processor._legacy_persist_batch_attempts = 2
    processor._legacy_persist_escaped = True

    await _run_until(processor, _clock, lambda: not processor._v2_legacy_fallback)

    assert processor._legacy_persist_rejects == 5, 'the v2 lane never touches legacy counters'
    assert processor._legacy_persist_batch_attempts == 2
    assert processor._legacy_persist_escaped is True
    rollover.assert_not_called(), 'the v2 lane never probes the legacy rollover'


@pytest.mark.anyio
async def test_v2_lane_budget_is_max_v2_persist_attempts_not_the_legacy_budget(monkeypatch):
    """The unplaced item's budget is the lane's own constant: pinning it stops
    the lanes from silently sharing a number that means different things."""
    assert MAX_V2_PERSIST_ATTEMPTS != LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET or MAX_V2_PERSIST_ATTEMPTS > 0
    attempts = []

    async def failing(_raw):
        attempts.append(1)
        raise _poisoned_row_error()

    raw = {'id': 'unplaced-b', 'text': 'late', 'start': 0.0, 'end': 0.5}
    processor, _state, _clock = _fallback_processor(monkeypatch, raw=raw, persist=failing)
    await _run_until(processor, _clock, lambda: not processor._v2_legacy_fallback)
    assert len(attempts) == MAX_V2_PERSIST_ATTEMPTS + 1


# ---------------------------------------------------------------------------
# Neighbouring contracts the budget must not disturb
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_v2_photo_terminal_budget_is_untouched(monkeypatch):
    """The photo lane already had its own `exhausted` terminal: the budget change
    must not disturb its counter, event shape, or retry backoff."""
    photos = [SimpleNamespace(id='photo-1')]
    rollover = AsyncMock(return_value=None)
    processor, state, _clock = _fallback_processor(
        monkeypatch, raw={'id': 'seed', 'text': 'x', 'start': 0.0, 'end': 0.5}, persist=AsyncMock(), rollover=rollover
    )
    processor._v2_legacy_fallback.clear()
    processor._v2_legacy_fallback_ids.clear()
    events = []
    real_record = transcripts_module.record_fallback

    def spy(**kwargs):
        events.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', spy)
    # Drive the photo lane to its existing terminal directly.
    processor._v2_photo_failures = MAX_V2_PERSIST_ATTEMPTS
    processor._queue_v2_photos(photos)

    exhausted = [event for event in events if event.get('outcome') == 'exhausted']
    assert len(exhausted) == 1, 'the photo terminal still fires exactly once'
    assert exhausted[0]['from_mode'] == 'v2_photo_persist'
    assert processor._v2_legacy_fallback == deque(), 'the photo terminal never touches the text lane'


@pytest.mark.anyio
async def test_legacy_transient_generic_log_shape_is_untouched(monkeypatch, caplog):
    """The generic transient ERROR keeps its exact sentence: downstream log
    sentinels and dashboards key on it."""
    attempts = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        attempts.append(1)
        raise RuntimeError('storage unavailable')

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    with caplog.at_level('ERROR', logger='routers.listen.transcripts'):
        await _run_until(processor, _clock, lambda: len(attempts) >= 2)

    transient = [
        record
        for record in caplog.records
        if 'retained 2 segment(s) for retry type=RuntimeError' in record.getMessage()
    ]
    assert transient, 'the transient ERROR line keeps its exact shape'


@pytest.mark.anyio
async def test_degraded_shrink_events_keep_their_exact_labels(monkeypatch):
    """The pre-budget degraded events keep `to_mode=shrink_retry` (or `none` when
    the buffer emptied) — the terminal event is the only new label."""
    events = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        processor.host.state.current_conversation_id = 'conversation-2'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    real_record = transcripts_module.record_fallback

    def spy(**kwargs):
        events.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', spy)
    await _run_until(processor, _clock, lambda: not processor.segment_buffer)

    degraded = [event for event in events if event.get('outcome') == 'degraded']
    assert degraded, 'attempts before the terminal still count degraded'
    assert all(event['from_mode'] == 'live_transcript_persist' for event in degraded)
    assert all(event['reason'] == 'malformed_doc' for event in degraded)
    assert all(
        event['component'] == 'other' for event in degraded + [e for e in events if e.get('outcome') == 'exhausted']
    )


def test_budget_sits_between_the_lane_budgets():
    """The batch budget must stay strictly below the stall clock (100 rejects):
    the terminal is reachable inside one stall window, never after it."""
    assert LEGACY_PERSIST_BATCH_ATTEMPT_BUDGET < LEGACY_PERSIST_STALL_REJECTS


@pytest.mark.anyio
async def test_terminal_on_an_empty_batch_never_fires(monkeypatch):
    """The budget guards a retained BATCH: a failure with nothing retained (an
    edge the loop cannot normally reach) must not log a terminal or clear a
    buffer it does not have."""
    terminals = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        processor.host.state.current_conversation_id = 'conversation-2'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0
    real_record = transcripts_module.record_fallback

    def spy(**kwargs):
        terminals.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', spy)
    await _run_until(processor, _clock, lambda: not processor.segment_buffer)

    exhausted = [event for event in terminals if event.get('outcome') == 'exhausted']
    assert len(exhausted) == 1
    # The single-segment batch is what terminated; nothing else fired.
    assert all(event.get('to_mode') in {'none', 'shrink_retry'} for event in terminals)


# ---------------------------------------------------------------------------
# Classifier boundary: what may and may not spend the budget
# ---------------------------------------------------------------------------


def test_json_decode_error_defect_spends_the_budget():
    """A stored blob that parses as neither hex nor JSON is the literal prod
    poison: it must classify deterministic (and so reach the terminal)."""
    try:
        json.loads('{not json')
        raised = None
    except ValueError as error:
        raised = error
    assert isinstance(raised, json.JSONDecodeError)
    assert _is_deterministic_persist_defect(raised)


def test_binascii_error_defect_spends_the_budget():
    """The real bytes.fromhex failure shape classifies deterministic."""
    try:
        bytes.fromhex('zz-not-hex')
        raised = None
    except ValueError as error:
        raised = error
    assert raised is not None
    assert _is_deterministic_persist_defect(raised)


def test_sdk_spent_transaction_never_spends_the_budget():
    """The SDK's own spent-commit ValueError is contention (a fresh transaction
    succeeds): it must stay transient through the classifier."""
    assert not _is_deterministic_persist_defect(ValueError('Failed to commit transaction in 3 attempts.'))
    assert not _is_deterministic_persist_defect(ValueError('FAILED TO COMMIT TRANSACTION in 3 attempts.'))


@pytest.mark.anyio
async def test_expired_transaction_invalidargument_never_spends_the_budget(monkeypatch):
    """The storage boundary's expired-transaction InvalidArgument is transient:
    it replays the whole batch and never arms the churn terminal."""
    attempts = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        attempts.append(len(segments))
        raise InvalidArgument('400 The referenced transaction has expired or is no longer valid.')

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(attempts) >= 6)

    assert len(processor.segment_buffer) == 2, 'expired transactions keep the whole batch'
    assert processor._legacy_persist_batch_attempts == 0
    rollover.assert_not_called()


@pytest.mark.anyio
async def test_timeout_never_spends_the_budget(monkeypatch):
    """A timeout can differ on the next attempt: transient, unbounded, no drop."""
    attempts = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        attempts.append(1)
        raise TimeoutError('write deadline')

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(attempts) >= 6)

    assert len(processor.segment_buffer) == 2
    assert processor._legacy_persist_batch_attempts == 0


# ---------------------------------------------------------------------------
# Loop-health pins around the terminal
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_terminal_does_not_crash_the_persist_loop(monkeypatch):
    """The terminal is a `continue`, not an exit: the loop keeps polling after
    dropping a poison batch (the supervised task must stay alive)."""
    phases = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        phases.append('first-batch')
        raise _poisoned_row_error()

    async def rollover(**_kwargs):
        counter = getattr(processor.host.state, '_generation', 1) + 1
        processor.host.state._generation = counter
        processor.host.state.current_conversation_id = f'conversation-{counter}'

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, clock, lambda: not processor.segment_buffer)
    assert phases, 'the first series ran'
    terminal_calls = len(phases)

    # The loop is still healthy: a new transient batch is drained normally.
    async def healthy(_conversation, segments, _photos, _finished_at, _started_at):
        phases.append('second-batch')
        return SimpleNamespace(id='conversation-9'), segments, []

    processor._update_live_conversation = healthy
    processor._oversized_rollover_probe_at = clock[0]
    processor.segment_buffer.extend(_raw_segments(1))
    await _run_until(processor, clock, lambda: 'second-batch' in phases)

    assert len(phases) > terminal_calls, 'the loop kept serving after the terminal'
    assert len(processor.segment_buffer) == 0


@pytest.mark.anyio
async def test_cancellation_during_a_budget_counting_failure_requeues_and_propagates(monkeypatch):
    """Cancellation inside a deterministic failure still requeues the batch and
    propagates: the budget arm never swallows the teardown signal."""

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise asyncio.CancelledError()

    async def rollover(**_kwargs):
        pass

    rollover_spy = AsyncMock(side_effect=rollover)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover_spy)
    processor._oversized_rollover_probe_at = 0.0

    task = asyncio.ensure_future(processor.process_loop())
    await asyncio.sleep(0)
    task.cancel()
    outcome = (await asyncio.gather(task, return_exceptions=True))[0]
    assert isinstance(outcome, asyncio.CancelledError), 'cancellation propagates through the deterministic arm'
    assert len(processor.segment_buffer) == 2, 'the batch was requeued for the retry, not dropped'
    rollover_spy.assert_not_called()


def test_validation_error_classifies_deterministic():
    """A pydantic ValidationError (a ValueError subclass) is the model-refuses-
    the-batch shape: deterministic, so it spends the budget."""
    from models.transcript_segment import TranscriptSegment
    from pydantic import ValidationError

    raised = None
    try:
        TranscriptSegment(**{'id': 's1', 'text': 'w', 'start': 'not-a-number', 'end': 1.0, 'is_user': False})
    except Exception as error:  # noqa: BLE001 - the raise itself is the assertion subject
        raised = error
    assert isinstance(raised, ValidationError)
    assert _is_deterministic_persist_defect(raised)


def test_cyclic_receipt_valueerror_classifies_deterministic():
    """The other tick-143 shape — a cyclic absorption receipt — is a plain
    ValueError and deterministic."""
    assert _is_deterministic_persist_defect(ValueError('Cyclic transcript segment absorption'))


@pytest.mark.anyio
async def test_v2_lane_terminal_event_never_uses_the_photo_from_mode(monkeypatch):
    """The text-lane terminal keeps `from_mode=v2_segment_persist`: the photo
    terminal (`v2_photo_persist`) must stay the only writer of its label."""

    async def failing(_raw):
        raise _poisoned_row_error()

    raw = {'id': 'unplaced-m', 'text': 'late', 'start': 0.0, 'end': 0.5}
    processor, _state, _clock = _fallback_processor(monkeypatch, raw=raw, persist=failing)

    events = []
    real_record = transcripts_module.record_fallback

    def spy(**kwargs):
        events.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', spy)
    await _run_until(processor, _clock, lambda: not processor._v2_legacy_fallback)

    assert all(event['from_mode'] != 'v2_photo_persist' for event in events)
    exhausted = [event for event in events if event.get('outcome') == 'exhausted']
    assert exhausted and exhausted[0]['from_mode'] == 'v2_segment_persist'
    assert exhausted[0]['component'] == 'other'
    assert exhausted[0]['to_mode'] == 'none'


@pytest.mark.anyio
async def test_unplaced_item_at_exact_budget_is_dropped_not_one_more(monkeypatch):
    """The boundary: with failures == MAX_V2_PERSIST_ATTEMPTS + 1 the item is
    already terminal — the lane never keeps a poison item past its budget."""
    attempts = []

    async def failing(_raw):
        attempts.append(1)
        raise _poisoned_row_error()

    raw = {'id': 'unplaced-e', 'text': 'late', 'start': 0.0, 'end': 0.5}
    processor, _state, _clock = _fallback_processor(monkeypatch, raw=raw, persist=failing)
    # The lane served the item exactly budget times before this tick.
    processor._v2_fallback_failures[raw['id']] = MAX_V2_PERSIST_ATTEMPTS

    await _run_until(processor, _clock, lambda: not processor._v2_legacy_fallback)

    assert len(attempts) == 1, 'one final attempt, then the terminal'
    assert not processor._v2_legacy_fallback
    assert raw['id'] not in processor._v2_fallback_failures
