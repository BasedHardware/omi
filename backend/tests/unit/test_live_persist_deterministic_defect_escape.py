"""A deterministic in-process persist defect must reach the rollover escape.

Failure-Class: FC-permanent-write-rejection-retried-forever — sibling instance
in ``backend/routers/listen/transcripts.py`` (legacy live persist arm, prod
backend-listen 2026-10, ``ERROR:routers.listen.transcripts:Live transcript
persist failed; retained 5 segment(s) for retry type=ValueError`` at x58/30m):
the transient arm of the legacy persist loop replayed a deterministically
failing write every backoff tick. The failure was raised inside the
transaction's in-process planning — the strict stored-transcript decode
(``bytes.fromhex``/``json`` defects surface as ``ValueError``), a cyclic
absorption receipt, or a segment shape the model refuses — so it is a
property of the row or of the retained batch, and the identical replay can
only reproduce it. The permanent Firestore-rejection class already had the
bounded escape (shrink + mid-session rollover probe); the deterministic
in-process class fell through to the transient whole-batch retry forever,
with the ERROR line re-firing (x58/30m) while the same five segments were
retained and maxlen silently evicted the session's older speech. This change
classifies the deterministic in-process shapes at the same loop boundary and
gives them the same recovery the storage class already has, on the same
cadence; genuinely transient failures (contention, expired transaction,
timeouts, lost sockets) keep the whole-batch retry. On the parent commit
every test here fails to import (``_is_deterministic_persist_defect`` does
not exist) and, past that, the ValueError drain never escapes: the batch is
requeued whole forever, no rollover is ever probed, and the defect reason is
never counted.
"""

import asyncio
import json
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

import routers.listen.transcripts as transcripts_module
from routers.listen.transcripts import (
    LEGACY_PERSIST_SHRINK_FLOOR,
    LEGACY_PERSIST_STALL_REJECTS,
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

    Mirrors the oversized-persist suite's harness: production state is replaced
    with observables so `process_loop` can be driven as a supervised task.
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
    # The probe starts armed so tests observe the escape without seed state.
    processor._oversized_rollover_probe_at = 0.0
    processor._legacy_retry_until = 0.0
    processor._legacy_persist_failures = 0
    processor._legacy_persist_rejects = 0
    # The batch-poison budget (added after this suite) starts disarmed: this
    # suite pins the escape, not the terminal, so the pre-budget behavior —
    # at most one escape per window — stays observable here.
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


async def _run_until(processor, clock, condition, *, max_ticks=400):
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
# The classifier boundary
# ---------------------------------------------------------------------------


def test_classifier_splits_deterministic_valueerror_from_transient_runtimeerror():
    """A ValueError (strict decode / receipt defect shape) is deterministic; a
    RuntimeError-shaped fault is not and must keep the transient retry."""
    assert _is_deterministic_persist_defect(_poisoned_row_error())
    assert _is_deterministic_persist_defect(ValueError('Cyclic transcript segment absorption'))
    assert not _is_deterministic_persist_defect(RuntimeError('binding unavailable'))
    assert not _is_deterministic_persist_defect(TimeoutError('write deadline'))


def test_json_decode_error_joins_the_deterministic_class():
    """A stored blob that parses as neither hex nor JSON reaches the loop as
    ``json.JSONDecodeError`` — a ValueError subclass — and is deterministic."""
    error = None
    try:
        json.loads('{not json')
    except ValueError as raised:
        error = raised
    assert isinstance(error, json.JSONDecodeError)
    assert _is_deterministic_persist_defect(error)


def test_binascii_error_from_real_fromhex_joins_the_deterministic_class():
    """The literal prod shape: a corrupted stored blob fails ``bytes.fromhex``; the
    raised error is a plain ValueError on Python 3.11 and must classify deterministic."""
    error = None
    try:
        bytes.fromhex('zz-not-hex')
    except ValueError as raised:
        error = raised
    assert error is not None
    assert _is_deterministic_persist_defect(error)


def test_classifier_rejects_transient_firestore_classes():
    """Contention and the expired transaction id are the storage boundary's transient
    classes: they must never enter the deterministic in-process class."""
    assert not _is_deterministic_persist_defect(Aborted('409 Too much contention on these documents.'))
    expired = InvalidArgument('400 The referenced transaction has expired or is no longer valid.')
    assert not _is_deterministic_persist_defect(expired)
    assert not _is_deterministic_persist_defect(InvalidArgument('400 some other 400'))


def test_sdk_spent_transaction_valueerror_stays_transient():
    """The SDK's _Transactional raises a bare ValueError('Failed to commit transaction
    ...') once its own retries are spent; firestore_failure_reason classifies it as
    contention — a fresh transaction succeeds — so the escape must not fire on it."""
    assert not _is_deterministic_persist_defect(ValueError('Failed to commit transaction in 3 attempts.'))
    assert not _is_deterministic_persist_defect(
        ValueError('FAILED TO COMMIT TRANSACTION in 3 attempts.')
    ), 'the marker match is case-insensitive, like the storage boundary'


def test_lookalike_valueerror_messages_stay_deterministic():
    """Only the SDK's exact spent-transaction prefix is carved out: a poison message
    that merely mentions a transaction is still deterministic."""
    assert _is_deterministic_persist_defect(ValueError('segment transaction failed to commit its payload'))
    assert _is_deterministic_persist_defect(ValueError('poisoned receipt near transaction'))


def test_real_transcript_segment_validation_defect_classifies_deterministic():
    """The literal in-transaction poison: merge_live_segments rebuilds stored rows as
    TranscriptSegment models, so a stored row with an uncoercible span raises the
    real pydantic ValidationError inside the transaction — and it is deterministic."""
    from models.transcript_segment import TranscriptSegment

    error = None
    try:
        TranscriptSegment(**{'id': 's1', 'text': 'w', 'start': 'not-a-number', 'end': 1.0, 'is_user': False})
    except Exception as raised:
        error = raised
    assert error is not None, 'the real model must reject an uncoercible span'
    assert isinstance(error, Exception) and _is_deterministic_persist_defect(error)


def test_classifier_rejects_timeout_and_socket_faults():
    """Timeouts, broken connections and OS-level faults can differ on the next dial:
    they stay transient so a slow provider can never trigger a rollover."""
    assert not _is_deterministic_persist_defect(TimeoutError())
    assert not _is_deterministic_persist_defect(ConnectionError('socket closed'))
    assert not _is_deterministic_persist_defect(OSError('network unreachable'))


def test_classifier_governs_by_raised_type_not_by_cause():
    """The raised type decides, not the chain: a ValueError caused by a RuntimeError
    is deterministic, and a RuntimeError caused by a ValueError stays transient."""
    poisoned = ValueError('bad segment shape')
    poisoned.__cause__ = RuntimeError('deep layer')
    assert _is_deterministic_persist_defect(poisoned)

    flaky = RuntimeError('storage fault')
    flaky.__cause__ = ValueError('deep parse detail')
    assert not _is_deterministic_persist_defect(flaky)


def test_classifier_ignores_keyerror_typeerror_and_attributeerror_shapes():
    """Only the ValueError family joins the class; other exception shapes keep the
    transient retry until they are proven deterministic in prod."""
    assert not _is_deterministic_persist_defect(KeyError('transcript_segments'))
    assert not _is_deterministic_persist_defect(TypeError('unsupported operand'))
    assert not _is_deterministic_persist_defect(AttributeError('no attribute'))


def test_classifier_is_stateless():
    """The predicate answers from the exception alone: repeated calls on the same
    object give the same answer, so the loop cannot drift between attempts."""
    error = _poisoned_row_error()
    first = _is_deterministic_persist_defect(error)
    second = _is_deterministic_persist_defect(error)
    assert first is second is True


def test_defect_reason_label_is_in_the_shared_vocabulary():
    """`malformed_doc` must stay inside the shared bounded fallback vocabulary — a
    vocabulary drift would silently bucket the whole class under `other`."""
    assert 'malformed_doc' in ALLOWED_REASONS


# ---------------------------------------------------------------------------
# The loop's answer to a deterministic defect
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_deterministic_defect_probes_rollover_instead_of_replaying_forever(monkeypatch):
    """The x58/30m shape: a ValueError drain must reach the mid-session rollover
    escape instead of re-firing the same ERROR line every backoff tick forever."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(5), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0  # armed

    await _run_until(processor, _clock, lambda: rollover.await_count >= 1)

    rollover.assert_awaited_once_with(rollover=True)
    assert len(batches) <= 2, f'deterministic defect must not replay the batch many times: {batches}'


@pytest.mark.anyio
async def test_deterministic_defect_counts_a_truthful_reason_not_the_size_limit(monkeypatch):
    """The recovery must stay observable under its own reason: the poisoned-row
    class reports `malformed_doc`, never the size-limit reason it does not have."""
    fallbacks = []
    real_record = transcripts_module.record_fallback

    def spy_record(**kwargs):
        fallbacks.append(kwargs)
        return real_record(**kwargs)

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')  # observe the reject arm without the escape
    monkeypatch.setattr(transcripts_module, 'record_fallback', spy_record)

    await _run_until(processor, _clock, lambda: len(fallbacks) >= 2)

    assert fallbacks, 'each deterministic rejection is counted'
    for event in fallbacks:
        assert event['reason'] == 'malformed_doc'
        assert event['outcome'] == 'degraded'
        assert event['component'] == 'other'
        assert event['from_mode'] == 'live_transcript_persist'
        assert event['to_mode'] in {'shrink_retry', 'none'}


@pytest.mark.anyio
async def test_storage_rejection_keeps_its_own_reason_and_wins_the_branch(monkeypatch):
    """Precedence pin: a Firestore rejection is classified by the storage boundary and
    never re-labeled `malformed_doc` by the in-process classifier."""
    fallbacks = []
    monkeypatch.setattr(transcripts_module, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _size_limit_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(fallbacks) >= 1)

    assert fallbacks[0]['reason'] == 'document_size_limit'


@pytest.mark.anyio
async def test_transient_failures_still_requeue_the_whole_batch(monkeypatch):
    """Genuinely transient faults keep today's contract: whole-batch retry, no
    rollover probe, no malformed_doc counter — the retry can still succeed."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise RuntimeError(' firestore unavailable ')

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(3), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0
    fallbacks = []
    monkeypatch.setattr(transcripts_module, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    await _run_until(processor, _clock, lambda: len(batches) >= 2)

    assert batches == [3, 3], 'transient failures must requeue the full batch'
    assert len(processor.segment_buffer) == 3
    rollover.assert_not_called()
    assert not fallbacks


@pytest.mark.anyio
async def test_transients_never_arm_the_defect_probe_clock(monkeypatch):
    """A transient series must leave the probe pacing untouched: only a classified
    deterministic failure may spend a probe window."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise TimeoutError('slow storage')

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: len(batches) >= 3)

    rollover.assert_not_called()
    assert processor._oversized_rollover_probe_at == 0.0, 'transient failures never spend the probe window'


@pytest.mark.anyio
async def test_deterministic_defect_shrinks_above_the_shrink_floor(monkeypatch):
    """Both deterministic classes share the shrink contract: above the floor the
    newest tail is dropped so the oldest speech reaches the boundary first."""
    sizes = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        sizes.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(6), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(sizes) >= 2)

    assert sizes[:2] == [6, 5], 'the newest tail is dropped per attempt above the floor'
    # Attempt 1 drained 6 and retained 5; attempt 2 drained 5 and retained 4.
    assert len(processor.segment_buffer) == 4


@pytest.mark.anyio
async def test_deterministic_defect_stops_grinding_at_the_shrink_floor(monkeypatch):
    """The floor is shared: once the defect-drained batch is at or below it, the drop
    stops and the whole batch is retried — the rollover is the only escape."""
    sizes = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        sizes.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(5), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(sizes) >= 4)

    assert sizes[:3] == [5, 4, 4], 'the tail drop runs only while the batch is above the floor'
    assert sizes[3] == 4, 'at the floor the whole batch is retried — the drop stops'
    assert len(processor.segment_buffer) == LEGACY_PERSIST_SHRINK_FLOOR


@pytest.mark.anyio
async def test_deterministic_defect_probe_is_paced_once_per_window(monkeypatch):
    """The probe runs at most once per pacing window even while every attempt still
    fails: a poisoned row cannot churn generations every backoff tick."""

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: rollover.await_count >= 2, max_ticks=400)

    assert rollover.await_count == 2, 'the failed probe re-arms on the pacing clock, not per tick'
    assert len(processor.segment_buffer) == 1, 'the retained batch stays queued for the next window'


@pytest.mark.anyio
async def test_defect_probe_sets_the_shared_pacing_deadline(monkeypatch):
    """The pacing deadline is the shared constant: the defect arm must arm the same
    clock the storage class uses, so the two classes cannot double-probe one window."""
    probed_at = [0.0]

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover_fn(**_kwargs):
        probed_at[0] = _clock[0]
        return None

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=rollover)
    processor.host.conversations.create_new_in_progress_conversation = rollover_fn
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: processor._oversized_rollover_probe_at > 0)

    assert rollover.await_count == 0, 'the asyncmock was replaced by the pacing-recording double'
    assert probed_at[0] > 0
    assert processor._oversized_rollover_probe_at == pytest.approx(probed_at[0] + OVERSIZED_ROLLOVER_PROBE_SECONDS)


@pytest.mark.anyio
async def test_pacing_is_shared_across_the_two_deterministic_classes(monkeypatch):
    """A storage rejection and an in-process defect inside one window spend ONE probe:
    the shared pacing attribute must not let the second class probe again immediately."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        if len(calls) == 1:
            raise _size_limit_error()
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: len(calls) >= 2 and rollover.await_count >= 1)

    assert rollover.await_count == 1, 'the two classes share one probe window'


@pytest.mark.anyio
async def test_defect_probe_requires_a_conversation_to_roll_from(monkeypatch):
    """Without a current conversation there is nothing to roll away from: the probe
    must stay silent instead of creating a generation from nothing."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    state.current_conversation_id = None
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: len(batches) >= 3)

    rollover.assert_not_called(), 'no probe without a conversation id'
    assert len(processor.segment_buffer) == 2, 'the batch still waits for a conversation'


@pytest.mark.anyio
async def test_deterministic_defect_stall_escape_on_full_cap_backlog(monkeypatch):
    """The all-day-storm shape for the defect class: a full-cap backlog whose every
    dropped tail is instantly replaced never shrinks, so the stall counter alone must
    still earn the probe."""
    probed = []
    state_holder = {}

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(*_args, **_kwargs):
        state_holder['state'].current_conversation_id = 'conversation-2'
        probed.append(True)

    processor, state, _clock = _processor(
        monkeypatch, segments=_raw_segments(5), update=update, rollover=AsyncMock(return_value=None)
    )
    # Mirror the production deque contract: the stall escape requires the
    # backlog to be AT the bounded buffer's cap.
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
        _clock,
        lambda: processor._legacy_persist_rejects == 0 and bool(probed),
        max_ticks=LEGACY_PERSIST_STALL_REJECTS * 12,
    )

    assert probed, 'a stalled full-cap defect backlog reaches the rollover without ever shrinking'
    assert processor._legacy_persist_rejects == 0, 'an escape resets the stall counter'


@pytest.mark.anyio
async def test_full_cap_defect_backlog_keeps_the_oldest_speech_until_escape(monkeypatch):
    """While the stall counter earns the escape, the retained queue must keep the
    original batch: no silent eviction of the queued speech before the rollover."""
    probed = []
    retained_at_probe = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(*_args, **_kwargs):
        retained_at_probe.append([raw['id'] for raw in processor.segment_buffer])
        probed.append(True)

    processor, _state, _clock = _processor(
        monkeypatch, segments=_raw_segments(4), update=update, rollover=AsyncMock(return_value=None)
    )
    # A cap AT the shrink floor: every attempt is below_floor, so the whole
    # batch is kept and the stall counter alone must earn the escape.
    processor.segment_buffer = deque(processor.segment_buffer, maxlen=4)
    processor.host.conversations.create_new_in_progress_conversation = rollover

    def keep_full(segments, photos):
        for raw in segments or []:
            processor.segment_buffer.append(raw)

    processor._requeue_legacy_persist = keep_full
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: bool(probed), max_ticks=LEGACY_PERSIST_STALL_REJECTS * 12)

    assert probed, 'a stalled full-cap defect backlog reaches the rollover without ever shrinking'
    assert retained_at_probe[0] == [f'segment-{i}' for i in range(4)], 'the queued speech survives to the escape'


@pytest.mark.anyio
async def test_deterministic_defect_handoff_lands_speech_on_the_fresh_generation(monkeypatch):
    """End to end: the poisoned row rejects the batch, the probe adopts a fresh
    generation, and the retained speech persists exactly once there."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append([segment.id for segment in segments])
        if len(calls) == 1:
            raise _poisoned_row_error()
        return SimpleNamespace(id='conversation-2'), segments, []

    async def rollover(rollover):
        processor.host.state.current_conversation_id = 'conversation-2'
        return None

    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: len(processor.segment_buffer) == 0 and len(calls) >= 2)

    assert calls == [
        ['segment-0', 'segment-1'],
        ['segment-0', 'segment-1'],
    ], 'the retained batch persists exactly once on the fresh generation'
    assert processor._legacy_persist_failures == 0, 'a successful persist clears the failure ladder'


@pytest.mark.anyio
async def test_successful_persist_resets_the_defect_counters(monkeypatch):
    """One defect hiccup followed by a committed write starts every counter from zero:
    a later series must earn its own escape."""
    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        if len(calls) == 1:
            raise _poisoned_row_error()
        return SimpleNamespace(id='conversation-1'), segments, []

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(3), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(calls) >= 2)

    assert len(calls) == 2 and len(processor.segment_buffer) == 0, 'the remainder commits after the blip'
    assert processor._legacy_persist_rejects == 0, 'a successful persist clears the stall debt'
    assert processor._legacy_persist_failures == 0, 'a successful persist clears the backoff ladder'


@pytest.mark.anyio
async def test_defect_failures_count_toward_the_shared_stall_debt(monkeypatch):
    """The defect arm joins the stall economy: storage rejections and in-process
    defects accumulate one counter, and transients count nothing."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        if len(batches) == 3:
            raise RuntimeError('transient blip')
        if len(batches) in (1, 2):
            raise _size_limit_error()
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(batches) >= 4)

    assert processor._legacy_persist_rejects == 3, 'two storage rejects plus one defect reject count; the blip does not'


@pytest.mark.anyio
async def test_deterministic_defect_keeps_the_transient_backoff_ladder(monkeypatch):
    """The defect classification changes WHAT is retried, never HOW SOON: the .5/1/2/4/8s
    cap ladder stays identical so a poisoned row cannot speed up or slow down the loop."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, clock = _processor(monkeypatch, segments=_raw_segments(3), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, clock, lambda: clock[0] >= 20.0)

    # Attempt times t=11, 12, 13, 15, 19: the pre-change transient ladder's exact
    # rungs (+0.5, +1, +2, +4 backoffs; the 8s rung would next land at t=27).
    assert batches == [3, 3, 3, 3, 3], f'backoff cadence unchanged: batches at {batches}'


@pytest.mark.anyio
async def test_deterministic_defect_requeues_pristine_copies(monkeypatch):
    """The requeued batch must be the pre-offset pristine copy: a retry replays the
    drain from the original capture-clock values, never the offset-applied ones."""
    cache_data = {
        'transcript_segments': [],
        'started_at': datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc),
    }

    async def cache_get(_conversation_id):
        return dict(cache_data)

    calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        calls.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    # started_at pinned 50s before first audio: the drain offset is +50.
    state.first_audio_byte_timestamp = 100.0
    processor.cache = SimpleNamespace(get=cache_get)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(calls) >= 2)

    assert [raw['start'] for raw in processor.segment_buffer] == [
        0.0,
        1.0,
    ], 'the retained copies are pristine: the next drain re-applies the offset exactly once'


@pytest.mark.anyio
async def test_deterministic_defect_preserves_segment_order_for_retry(monkeypatch):
    """The requeued batch keeps its start-sorted order so the retry replays the same
    oldest-first sequence the drain attempted."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append([segment.id for segment in segments])
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(
        monkeypatch,
        segments=[
            {'id': 'segment-b', 'text': 'b', 'start': 5.0, 'end': 5.5},
            {'id': 'segment-a', 'text': 'a', 'start': 1.0, 'end': 1.5},
        ],
        update=update,
        rollover=rollover,
    )
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(batches) >= 1)

    assert batches[0] == ['segment-a', 'segment-b'], 'the drain sorts by start'
    assert [raw['id'] for raw in processor.segment_buffer] == [
        'segment-a',
        'segment-b',
    ], 'the requeue preserves the attempted order'


@pytest.mark.anyio
async def test_failed_defect_drain_never_delivers_to_the_client(monkeypatch):
    """Uncommitted text must never reach the client: a drain that ends in a defect
    failure delivers nothing, whatever the retry later commits."""
    delivered = []

    async def deliver(*_args, **_kwargs):
        delivered.append(True)

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._deliver_live_updates = deliver
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: processor._legacy_persist_failures >= 2)

    assert not delivered, 'a failed drain delivers nothing'


@pytest.mark.anyio
async def test_deterministic_defect_does_not_requeue_into_the_v2_lane(monkeypatch):
    """The legacy retry path requeues into the legacy buffer only: a defect failure
    must not leak segments into the v2 fallback lane."""

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: processor._legacy_persist_failures >= 1)

    assert not processor._v2_legacy_fallback, 'no v2 fallback leakage from the legacy arm'
    assert not processor._v2_legacy_fallback_ids


@pytest.mark.anyio
async def test_v2_batch_failure_never_probes_the_legacy_defect_arm(monkeypatch):
    """The escape is legacy-arm only: a v2 (audio-timeline) batch failing with a
    ValueError keeps its own budgeted retry and must not fire the legacy rollover."""
    seen = {}

    async def fake_process_v2_batches(segments, photos, _diarized):
        seen['segments'] = list(segments)
        raise _poisoned_row_error()

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

    assert [raw['id'] for raw in processor.segment_buffer] == ['v2-segment-0', 'v2-segment-1']
    assert rollover.await_count == 0, 'the legacy rollover probe must not fire from a v2 failure'


@pytest.mark.anyio
async def test_deterministic_defect_does_not_crash_the_persist_loop(monkeypatch):
    """A failing rollover must be absorbed: the retained batch stays queued for the
    next backoff tick instead of tearing down the session."""
    rollover = AsyncMock(side_effect=RuntimeError('binding unavailable'))

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: rollover.await_count >= 1)

    rollover.assert_awaited_once_with(rollover=True)
    assert len(processor.segment_buffer) == 2, 'a failed probe leaves the retained batch queued'


@pytest.mark.anyio
async def test_defect_escape_logs_the_rollover_warning(monkeypatch, caplog):
    """The escape is observable: the adopted-generation warning fires with the retained
    count so ops can see a poisoned row was abandoned mid-session."""

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    async def rollover(rollover):
        processor.host.state.current_conversation_id = 'conversation-2'
        return None

    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: processor.host.state.current_conversation_id == 'conversation-2')

    assert any('rollover escaped' in record.getMessage() for record in caplog.records), 'the escape is logged'


@pytest.mark.anyio
async def test_cancellation_during_a_defect_failure_requeues_and_propagates(monkeypatch):
    """Teardown must not lose speech: cancellation inside a defect-failing drain
    requeues the pristine batch and propagates, exactly like the transient arm."""
    update_calls = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        update_calls.append(len(segments))
        await asyncio.sleep(10)  # cancelled here
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(3), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    async def wait(_seconds):
        _clock[0] += 1.0
        await asyncio.sleep(0)
        return False

    processor.host.wait = wait
    task = asyncio.ensure_future(processor.process_loop())
    while len(update_calls) < 1 and not task.done():
        await asyncio.sleep(0)
    task.cancel()
    outcome = (await asyncio.gather(task, return_exceptions=True))[0]

    assert isinstance(outcome, asyncio.CancelledError), f'cancellation must propagate: {outcome!r}'
    assert len(processor.segment_buffer) == 3, 'the cancelled drain requeues its whole batch'


@pytest.mark.anyio
async def test_deterministic_defect_requeues_photos_with_the_batch(monkeypatch):
    """Photos were drained with the batch and must be requeued under a defect failure:
    the photo contract is unchanged by the classification."""

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    requeued = []

    def requeue(segs, ph):
        requeued.append(list(ph))
        for raw in segs or []:
            processor.segment_buffer.append(raw)
        for photo in ph or []:
            processor.photo_buffer.append(photo)

    processor._requeue_legacy_persist = requeue
    processor.photo_buffer = deque([SimpleNamespace(id='photo-1')])

    await _run_until(processor, _clock, lambda: len(requeued) >= 1)

    assert [photo.id for photo in requeued[0]] == ['photo-1'], 'photos ride the retry under a defect failure'


@pytest.mark.anyio
async def test_defect_batch_at_the_floor_is_retried_whole(monkeypatch):
    """Below the shrink floor the drop buys nothing: a small defect batch is retried
    whole — the floor contract holds without ever discarding the batch down to zero."""
    batches = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        batches.append(len(segments))
        raise _poisoned_row_error()

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = float('inf')

    await _run_until(processor, _clock, lambda: len(batches) >= 3)

    assert batches == [2, 2, 2], 'the floor batch stays whole'
    assert len(processor.segment_buffer) == 2


@pytest.mark.anyio
async def test_unplaced_fallback_lane_keeps_its_own_budget(monkeypatch):
    """The v2 unplaced fallback keeps its per-item retry budget: a ValueError from its
    persist must not fire the legacy probe or drain its queue."""

    async def failing_unplaced(_raw):
        raise ValueError('unplaced target unavailable')

    rollover = AsyncMock(return_value=None)
    processor, _state, _clock = _processor(
        monkeypatch, segments=_raw_segments(1), update=AsyncMock(return_value=None), rollover=rollover
    )
    state = processor.host.state
    state.capture_timeline_v2 = True
    raw = {'id': 'unplaced-1', 'text': 'late', 'start': 0.0, 'end': 0.5}
    processor._v2_legacy_fallback = deque([raw])
    processor._v2_legacy_fallback_ids = {'unplaced-1'}
    processor._v2_fallback_failures = {}
    processor._v2_fallback_retry_until = {}
    processor._v2_retry_until = 0.0
    processor._v2_committed_ids = set()
    processor._v2_photos_committed = False
    processor._v2_photos_requeued = False
    processor._v2_retry_counts = {}
    processor._v2_photo_failures = 0
    processor._persist_v1_unplaced = failing_unplaced
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, _clock, lambda: processor._v2_fallback_failures.get('unplaced-1', 0) >= 1)

    assert [item['id'] for item in processor._v2_legacy_fallback] == ['unplaced-1'], 'the fallback item stays queued'
    assert rollover.await_count == 0, 'the fallback lane never fires the legacy probe'
    assert processor._v2_fallback_retry_until['unplaced-1'] > 0, 'the fallback lane arms its own per-item backoff'
