"""The live speaker-map flush must classify its failures, not replay them raw.

Failure-Class: FC-permanent-write-rejection-retried-forever — sibling instance
in ``backend/routers/listen/transcripts.py`` (live speaker-map flush, prod
backend-listen 2026-10 sensor window): the drain boundary caught every
``flush_speaker_assignments`` exception with one ERROR line and no backoff of
any kind, so a deterministically failing flush — a row the strict decode
cannot read, a segment shape pydantic refuses, a permanent Firestore write
rejection — was re-called on the very next eligible drain tick (~1.7/s) and
re-logged at ERROR for the rest of the recording (``Live speaker flush failed
type=ValueError`` at x14/30m on a steady one-call-per-tick cadence). Tick 143
gave the sibling legacy-persist arm the same split; the flush lane was missed.

The mechanism, mirroring the persist arm: deterministic refusals absorb a
bounded per-generation budget (``SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET``)
on quick retries, then park the flush on an exponentially growing interval
(60s base, doubling, 600s cap) with one truthful
``omi_fallback_total{component="other",from_mode="live_speaker_flush",
to_mode="none",reason="malformed_doc",outcome="exhausted"}`` counter. The park
is keyed to the conversation that refused, is generation-refusal evidence the
rollover arm front-loads its probe to, and is invalidated by any generation
change; a committed flush resets the budget through the success path. Transient
faults keep the existing small backoff ladder, park nothing, and never count.
"""

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.api_core.exceptions import InvalidArgument

import routers.listen.transcripts as transcripts_module
from routers.listen.transcripts import (
    SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET,
    TranscriptProcessor,
    _is_deterministic_persist_defect,
)
from utils.observability.fallback import ALLOWED_COMPONENTS, ALLOWED_OUTCOMES, ALLOWED_REASONS


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _decode_error() -> ValueError:
    """The strict stored-transcript decode's bare ValueError shape."""
    return ValueError('non-hexadecimal number found in fromhex() at position 12')


def _validation_error() -> Exception:
    """A pydantic-shaped refusal (the model rejects the segment batch)."""
    return ValueError('1 validation error for TranscriptSegment')


def _size_limit_error() -> InvalidArgument:
    """A permanent Firestore write rejection (the 1 MiB ceiling shape)."""
    return InvalidArgument(
        "Document 'projects/based-hardware/databases/(default)/documents/users/uid/conversations/conv' "
        'cannot be written because its size (1,069,442 bytes) exceeds the maximum allowed size of '
        '1,048,576 bytes.'
    )


def _make_deterministic_shapes():
    """The deterministic shape builders and their reasons, shared by the
    classification contract tests and the behavior tests."""
    return [
        (_decode_error, 'malformed_doc'),
        (_validation_error, 'malformed_doc'),
        (_size_limit_error, 'malformed_doc'),
    ]


_DETERMINISTIC_SHAPES = [make for make, _reason in _make_deterministic_shapes()]
_TRANSIENT_SHAPES = [
    (lambda: RuntimeError('contention')),
    (lambda: TimeoutError('provider slow')),
    (lambda: ValueError('Failed to commit transaction after 5 attempts.')),
]


class _FlushHarness:
    """A legacy-mode processor whose speaker-map flush carries the injected behavior.

    Mirrors the tick-143/146 suites' harness: production state is replaced with
    observables so `process_loop` can be driven as a supervised task. `flush=None`
    keeps the REAL ``flush_speaker_assignments`` (dependencies stubbed via
    ``persistence``); anything else replaces the method outright.
    """

    def __init__(self, monkeypatch, *, flush=None, update=None, persistence=None):
        clock = [10.0]
        fake_time = SimpleNamespace(monotonic=lambda: clock[0], time=lambda: clock[0])
        self.clock = clock
        self.flush_calls = [0]
        self.rolls = [0]
        self.fallback_events = []

        state = SimpleNamespace(
            active=True,
            first_audio_byte_timestamp=100.0,
            last_transcript_time=None,
            words_transcribed_since_last_record=0,
            current_conversation_id='conversation-1',
            speaker_id_done=asyncio.Event(),
            speaker_map_dirty=True,
            speaker_map_version=0,
        )
        state.speaker_id_done.set()
        self.state = state

        async def cache_get(_conversation_id, **_kwargs):
            return {'id': state.current_conversation_id, 'transcript_segments': []}

        async def no_op(*_args, **_kwargs):
            return None

        async def persistence_call(fn, *args, **kwargs):
            if persistence is not None:
                return await persistence(fn, *args, **kwargs)
            return [{'id': 'stub-segment'}]

        async def rollover(**_kwargs):
            self.rolls[0] += 1
            state.current_conversation_id = f'conversation-{1 + self.rolls[0]}'
            state.speaker_map_dirty = False

        self.rollover = AsyncMock(side_effect=rollover)
        host = SimpleNamespace(
            state=state,
            wait=no_op,
            request=SimpleNamespace(uid='user-1', onboarding_mode=False, websocket=SimpleNamespace()),
            transcript_send=None,
            user_has_credits=True,
            pusher_enabled=True,
            onboarding_handler=None,
            send_event=lambda _event: None,
            speakers=SimpleNamespace(
                drain=no_op,
                tasks=set(),
                speaker_to_person={0: ('person-1', 'Owner')},
                segment_assignments={},
                segment_identity_status={},
            ),
            persistence=SimpleNamespace(call=persistence_call),
            complete_live_transcription=lambda: None,
            conversations=SimpleNamespace(create_new_in_progress_conversation=self.rollover),
        )
        processor = object.__new__(TranscriptProcessor)
        processor.host = host
        processor.segment_buffer = deque()
        processor._v2_legacy_fallback = deque()
        processor._v2_legacy_fallback_ids = set()
        processor.photo_buffer = deque()
        processor.cache = SimpleNamespace(
            get=cache_get, update_segments=lambda _segments: None, protection_level='standard'
        )
        processor.current_session_segments = {}
        processor.speaker_id_allocator = SimpleNamespace(
            hydrate=lambda _segments: None, hydrate_receipt=MagicMock(), assign=lambda _segment: None
        )
        processor._update_live_conversation = update if update is not None else no_op
        processor._deliver_live_updates = no_op
        processor._speaker_detection = no_op
        processor._translate = no_op

        real_flush = TranscriptProcessor.flush_speaker_assignments

        async def flush_spy(conversation_id):
            self.flush_calls[0] += 1
            if flush is not None:
                return await flush(conversation_id)
            return await real_flush(processor, conversation_id)

        processor.flush_speaker_assignments = flush_spy
        processor._flush_failures = 0
        processor._flush_backoff_until = 0.0
        processor._speaker_flush_defect_attempts = 0
        processor._speaker_flush_park_until = 0.0
        processor._speaker_flush_park_conversation = None
        # Effectively unarmed: only the park front-load may arm it observably.
        processor._oversized_rollover_probe_at = float('inf')
        processor._legacy_retry_until = 0.0
        processor._legacy_persist_failures = 0
        processor._legacy_persist_rejects = 0
        processor._legacy_persist_batch_attempts = 0
        processor._legacy_persist_escaped = False
        self.processor = processor

        real_record = transcripts_module.record_fallback

        def record_spy(**kwargs):
            self.fallback_events.append(kwargs)
            return real_record(**kwargs)

        monkeypatch.setattr(transcripts_module, 'record_fallback', record_spy)
        monkeypatch.setattr(transcripts_module, 'time', fake_time)
        monkeypatch.setattr(transcripts_module, 'TranscriptSegment', _FakeSegment)
        monkeypatch.setattr(
            transcripts_module,
            'deserialize_conversation',
            lambda _data: SimpleNamespace(id=state.current_conversation_id, transcript_segments=[]),
        )

    def seed_park(self, *, attempts=SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET, until=None, conversation=None):
        """Seed the park state as a deterministic refusal storm would have left it."""
        processor = self.processor
        processor._speaker_flush_defect_attempts = attempts
        processor._speaker_flush_park_until = self.clock[0] + 60.0 if until is None else until
        processor._speaker_flush_park_conversation = (
            processor.host.state.current_conversation_id if conversation is None else conversation
        )

    async def run_until(self, condition, *, max_ticks=12000):
        """Drive process_loop as a supervised task until `condition` holds."""
        ticks = [0]

        async def wait(_seconds):
            self.clock[0] += 1.0
            ticks[0] += 1
            await asyncio.sleep(0)
            return False

        self.processor.host.wait = wait
        task = asyncio.ensure_future(self.processor.process_loop())
        try:
            while not condition():
                if task.done() or ticks[0] > max_ticks:
                    break
                await asyncio.sleep(0)
        finally:
            task.cancel()
            outcome = (await asyncio.gather(task, return_exceptions=True))[0]
            assert outcome is None or isinstance(outcome, asyncio.CancelledError), f'flush loop crashed: {outcome!r}'


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


def _raw_segments(count):
    return [{'id': f'segment-{i}', 'text': f'word {i}', 'start': float(i), 'end': float(i) + 0.5} for i in range(count)]


def _exhausted(events):
    return [event for event in events if event.get('outcome') == 'exhausted']


# ---------------------------------------------------------------------------
# The handler, unit-under-glass: one shape per test, no loop
# ---------------------------------------------------------------------------


def _bare_processor_with_state(monkeypatch):
    """A minimal processor exposing exactly what `_handle_speaker_flush_failure`
    touches, so each classification test drives the real handler directly."""
    events = []
    real_record = transcripts_module.record_fallback

    def record_spy(**kwargs):
        events.append(kwargs)
        return real_record(**kwargs)

    monkeypatch.setattr(transcripts_module, 'record_fallback', record_spy)
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(state=SimpleNamespace(current_conversation_id='conversation-1'))
    processor._flush_failures = 0
    processor._flush_backoff_until = 0.0
    processor._speaker_flush_defect_attempts = 0
    processor._speaker_flush_park_until = 0.0
    processor._speaker_flush_park_conversation = None
    return processor, events


def test_handler_counts_decode_shape_toward_the_budget(monkeypatch):
    """The decode refusal, fed straight to the handler, advances the
    per-generation budget by exactly one and sets only the quick backoff."""
    processor, events = _bare_processor_with_state(monkeypatch)

    processor._handle_speaker_flush_failure(_decode_error())

    assert processor._speaker_flush_defect_attempts == 1
    assert processor._speaker_flush_park_until == 0.0, 'first refusal stays inside the budget'
    assert processor._flush_backoff_until > 0.0
    assert not events, 'the budget window is silent at the metric layer'


def test_handler_counts_validation_shape_toward_the_budget(monkeypatch):
    """The pydantic refusal takes the same budget arm as the decode shape."""
    processor, events = _bare_processor_with_state(monkeypatch)

    processor._handle_speaker_flush_failure(_validation_error())

    assert processor._speaker_flush_defect_attempts == 1
    assert processor._speaker_flush_park_until == 0.0
    assert processor._flush_backoff_until > 0.0
    assert not events


def test_handler_counts_size_limit_shape_toward_the_budget(monkeypatch):
    """The permanent Firestore write rejection takes the same budget arm: it
    is classified by the oversized arm, not the ValueError predicate."""
    processor, events = _bare_processor_with_state(monkeypatch)

    processor._handle_speaker_flush_failure(_size_limit_error())

    assert processor._speaker_flush_defect_attempts == 1
    assert processor._speaker_flush_park_until == 0.0
    assert processor._flush_backoff_until > 0.0
    assert not events


def test_handler_keeps_runtime_error_on_the_small_ladder(monkeypatch):
    """A bare RuntimeError takes the legacy ladder and leaves the budget,
    park, and key untouched."""
    processor, events = _bare_processor_with_state(monkeypatch)

    processor._handle_speaker_flush_failure(RuntimeError('contention'))

    assert processor._speaker_flush_defect_attempts == 0
    assert processor._speaker_flush_park_until == 0.0
    assert processor._speaker_flush_park_conversation is None
    assert processor._flush_backoff_until > 0.0, 'the transient ladder still backs off'
    assert not events


def test_handler_keeps_timeout_on_the_small_ladder(monkeypatch):
    """A TimeoutError takes the legacy ladder: a slow provider plausibly heals."""
    processor, events = _bare_processor_with_state(monkeypatch)

    processor._handle_speaker_flush_failure(TimeoutError('provider slow'))

    assert processor._speaker_flush_defect_attempts == 0
    assert processor._speaker_flush_park_until == 0.0
    assert processor._speaker_flush_park_conversation is None
    assert processor._flush_backoff_until > 0.0
    assert not events


def test_handler_keeps_spent_transaction_on_the_small_ladder(monkeypatch):
    """The SDK's spent-transaction ValueError is contention by contract and
    stays on the transient ladder."""
    processor, events = _bare_processor_with_state(monkeypatch)

    processor._handle_speaker_flush_failure(ValueError('Failed to commit transaction after 5 attempts.'))

    assert processor._speaker_flush_defect_attempts == 0
    assert processor._speaker_flush_park_until == 0.0
    assert processor._speaker_flush_park_conversation is None
    assert processor._flush_backoff_until > 0.0
    assert not events


def test_handler_park_key_names_the_current_generation(monkeypatch):
    """The parked key records the conversation that refused — the identity the
    drain boundary and the rollover arm later compare against."""
    processor, _events = _bare_processor_with_state(monkeypatch)
    processor.host.state.current_conversation_id = 'conversation-poisoned'
    processor._speaker_flush_defect_attempts = SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET

    processor._handle_speaker_flush_failure(_decode_error())

    assert processor._speaker_flush_park_conversation == 'conversation-poisoned'


def test_handler_terminal_log_names_attempts_and_park_duration(monkeypatch, caplog):
    """The park's single ERROR keeps the sentinel-usable shape: the attempt
    count and the parked seconds are both in the rendered message."""
    import logging

    processor, _events = _bare_processor_with_state(monkeypatch)
    processor._speaker_flush_defect_attempts = SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET

    with caplog.at_level(logging.ERROR, logger='routers.listen.transcripts'):
        processor._handle_speaker_flush_failure(_decode_error())

    messages = [record.getMessage() for record in caplog.records if 'speaker flush' in record.getMessage()]
    assert len(messages) == 1, f'exactly one terminal ERROR, saw {messages}'
    assert 'parking the flush' in messages[0]
    assert str(SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET + 1) in messages[0]


@pytest.mark.anyio
async def test_partial_budget_streak_resets_on_a_committed_flush(monkeypatch):
    """A failure followed by a committed flush clears the partial budget: one
    deterministic refusal never poisons the lane's next few attempts."""
    behavior = {'fail': True}

    async def persistence_call(_fn, *args, **kwargs):
        if behavior['fail']:
            behavior['fail'] = False
            raise _decode_error()
        return [{'id': 'stub-segment'}]

    harness = _FlushHarness(monkeypatch, flush=None, persistence=persistence_call)
    processor = harness.processor

    await harness.run_until(lambda: processor.host.state.speaker_map_dirty is False)

    assert processor._speaker_flush_defect_attempts == 0, 'the committed flush cleared the partial budget'
    assert processor._speaker_flush_park_until == 0.0
    assert processor._speaker_flush_park_conversation is None
    assert not _exhausted(harness.fallback_events), 'one refusal never reaches the terminal counter'


# ---------------------------------------------------------------------------
# Constants and classification contracts
# ---------------------------------------------------------------------------


def test_speaker_flush_budget_constant_is_bounded():
    """The budget must stay small and positive: it exists to absorb boundary
    races without delaying the lane, and 0 would park on the first refusal."""
    assert 1 <= SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET <= 10


def test_deterministic_classification_matches_the_persist_arm():
    """The flush lane must classify with the SAME predicate the persist arm
    uses: a defect for one lane is a defect for the other."""
    assert _is_deterministic_persist_defect(_decode_error())
    assert _is_deterministic_persist_defect(ValueError('cyclic absorption receipt detected'))
    assert not _is_deterministic_persist_defect(ValueError('Failed to commit transaction after 5 attempts'))
    assert not _is_deterministic_persist_defect(RuntimeError('socket gone'))
    assert not _is_deterministic_persist_defect(TimeoutError('slow'))


def test_speaker_flush_fallback_labels_are_in_the_contract_vocabulary():
    """The terminal event's labels must be contract-legal: no invented
    vocabulary for the counter, the reason, the component, or the outcome."""
    assert 'malformed_doc' in ALLOWED_REASONS
    assert 'other' in ALLOWED_COMPONENTS
    assert 'exhausted' in ALLOWED_OUTCOMES


# ---------------------------------------------------------------------------
# The transient arm: existing ladder, nothing counted, nothing parked
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_transient_flush_failure_takes_the_backoff_ladder(monkeypatch):
    """A transient failure sets the small backoff and advances the bounded
    failure counter — the legacy behavior, preserved verbatim."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=RuntimeError('contention')))
    processor = harness.processor

    await harness.run_until(lambda: processor._flush_failures >= 2)

    assert harness.flush_calls[0] >= 2
    assert processor._flush_backoff_until > 0.0
    assert processor._flush_backoff_until <= harness.clock[0] + 5.0, 'the transient ladder caps at 5s'
    assert 1 <= processor._flush_failures <= 4, 'the transient counter stays bounded'


@pytest.mark.anyio
async def test_transient_flush_failure_parks_nothing_and_counts_nothing(monkeypatch):
    """The park, its conversation key, and the defect budget stay untouched by
    transient faults — the split is per-failure, not per-lane."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=TimeoutError('provider slow')))
    processor = harness.processor

    await harness.run_until(lambda: processor._flush_failures >= 3)

    assert processor._speaker_flush_defect_attempts == 0
    assert processor._speaker_flush_park_until == 0.0
    assert processor._speaker_flush_park_conversation is None
    assert not harness.fallback_events, 'transient refusals emit no fallback event'


@pytest.mark.anyio
async def test_runtime_error_shape_stays_on_the_transient_arm(monkeypatch):
    """A bare RuntimeError — contention, a lost socket — must stay transient."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=RuntimeError('contention')))
    processor = harness.processor

    await harness.run_until(lambda: processor._flush_failures >= 1)

    assert processor._speaker_flush_defect_attempts == 0
    assert not _exhausted(harness.fallback_events)


@pytest.mark.anyio
async def test_timeout_shape_stays_on_the_transient_arm(monkeypatch):
    """A TimeoutError — a slow provider — plausibly heals and stays transient."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=TimeoutError('provider slow')))
    processor = harness.processor

    await harness.run_until(lambda: processor._flush_failures >= 1)

    assert processor._speaker_flush_defect_attempts == 0
    assert not _exhausted(harness.fallback_events)


@pytest.mark.anyio
async def test_spent_transaction_shape_stays_on_the_transient_arm(monkeypatch):
    """The SDK's spent-transaction ValueError is contention by contract (a
    fresh transaction succeeds) and stays transient here too."""
    harness = _FlushHarness(
        monkeypatch, flush=AsyncMock(side_effect=ValueError('Failed to commit transaction after 5 attempts.'))
    )
    processor = harness.processor

    await harness.run_until(lambda: processor._flush_failures >= 1)

    assert processor._speaker_flush_defect_attempts == 0
    assert not _exhausted(harness.fallback_events)


@pytest.mark.anyio
async def test_transient_flush_never_produces_the_exhausted_counter(monkeypatch):
    """Whatever the transient arm does, it must not emit the terminal
    `exhausted` outcome — that outcome is the deterministic class's story."""

    async def transient(_conversation_id):
        raise RuntimeError('socket vanished')

    harness = _FlushHarness(monkeypatch, flush=transient)
    processor = harness.processor
    await harness.run_until(lambda: processor._flush_failures >= 1)
    assert not _exhausted(harness.fallback_events)


@pytest.mark.anyio
async def test_transient_then_deterministic_sequence_counts_only_the_defects(monkeypatch):
    """A lane that fails transiently twice and then deterministically must
    carry ONLY the deterministic failures into the budget."""
    plan = [RuntimeError('contention'), TimeoutError('slow'), _decode_error(), _decode_error()]
    calls = [0]

    async def planned(_conversation_id):
        index = min(calls[0], len(plan) - 1)
        calls[0] += 1
        raise plan[index]

    harness = _FlushHarness(monkeypatch, flush=planned)
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_defect_attempts >= 2)

    assert processor._speaker_flush_defect_attempts == 2, 'transient failures never count'
    assert processor._speaker_flush_park_until == 0.0, 'still inside the budget'
    assert processor._flush_failures == 2, 'the transient arm still kept its own count'


# ---------------------------------------------------------------------------
# The deterministic arm: budget, then park
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_decode_error_shape_reaches_the_park(monkeypatch):
    """The strict stored-transcript decode's bare ValueError — the exact prod
    signature's `type=ValueError` — takes the budget-and-park arm."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=_decode_error()))
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)

    assert processor._speaker_flush_defect_attempts == SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET + 1
    assert processor._speaker_flush_park_conversation == 'conversation-1'
    assert len(_exhausted(harness.fallback_events)) == 1


@pytest.mark.anyio
async def test_validation_error_shape_reaches_the_park(monkeypatch):
    """A pydantic-shaped refusal — the model rejects the segment batch every
    time — takes the budget-and-park arm too."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=_validation_error()))
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)

    assert processor._speaker_flush_defect_attempts == SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET + 1
    assert len(_exhausted(harness.fallback_events)) == 1


@pytest.mark.anyio
async def test_size_limit_shape_reaches_the_park(monkeypatch):
    """The permanent Firestore write rejection (the 1 MiB ceiling) — a refusal
    no retry can answer — takes the budget-and-park arm as well."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=_size_limit_error()))
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)

    assert processor._speaker_flush_defect_attempts == SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET + 1
    assert len(_exhausted(harness.fallback_events)) == 1


@pytest.mark.anyio
async def test_deterministic_flush_within_budget_retries_quickly_and_counts(monkeypatch):
    """The first deterministic refusals stay inside the quick-retry budget:
    a short backoff is set and the budget counter advances, but nothing parks."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=_decode_error()))
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_defect_attempts >= 2)

    assert harness.flush_calls[0] >= 2
    # The boundary is between ticks: the last attempt raised and set the
    # backoff, and no later tick has been ELIGIBLE yet — the backoff still
    # names a moment after the current clock reading.
    assert processor._flush_backoff_until > 0.0
    assert processor._flush_backoff_until <= harness.clock[0] + 2.0, 'within-budget retries stay quick'
    assert processor._speaker_flush_park_until == 0.0, 'nothing parks inside the budget'
    assert not _exhausted(harness.fallback_events)


@pytest.mark.anyio
async def test_deterministic_flush_parks_past_the_budget_with_one_truthful_counter(monkeypatch):
    """Crossing the budget parks the flush on the exponential base and counts
    exactly one `exhausted` fallback event with the class's own labels."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=_decode_error()))
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)

    assert processor._speaker_flush_defect_attempts == SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET + 1
    assert processor._speaker_flush_park_conversation == 'conversation-1'
    park = processor._speaker_flush_park_until - harness.clock[0]
    assert 59.0 <= park <= 61.0, f'the park base is 60s, saw {park}'
    exhausted = _exhausted(harness.fallback_events)
    assert len(exhausted) == 1, f'exactly one terminal event, saw {[e.get("outcome") for e in harness.fallback_events]}'
    event = exhausted[0]
    assert event['from_mode'] == 'live_speaker_flush'
    assert event['to_mode'] == 'none'
    assert event['reason'] == 'malformed_doc'
    assert event['component'] == 'other'
    assert harness.fallback_events[-1]['outcome'] == 'exhausted', "the terminal event is the story's last entry"


@pytest.mark.anyio
async def test_each_budget_refusal_before_the_park_is_quick_and_silent(monkeypatch):
    """Attempts 1..budget set only the small backoff: no park, no counter, no
    ERROR-grade terminal line — the park is the FIRST loud event."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=_decode_error()))
    processor = harness.processor

    await harness.run_until(
        lambda: processor._speaker_flush_defect_attempts >= SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET
    )

    assert processor._speaker_flush_park_until == 0.0
    assert not harness.fallback_events, 'the budget window is silent at the metric layer'


# ---------------------------------------------------------------------------
# The park: gating, growth, cap, expiry
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_parked_flush_is_not_recalled_until_the_park_expires(monkeypatch):
    """The whole point: while parked, the drain boundary must not re-call the
    flush at the ~1.7/s drain cadence — the park, not the tick, gates calls."""

    async def failing(_conversation_id):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing)
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)
    calls_at_park = harness.flush_calls[0]
    parked_conversation = processor._speaker_flush_park_conversation
    park_until = processor._speaker_flush_park_until

    # Keep the recording alive and dirty past the park boundary so the loop
    # would re-call the flush at every tick if the park did not gate it.
    def still_dirty():
        processor.host.state.speaker_map_dirty = True
        processor.host.state.current_conversation_id = parked_conversation
        return harness.clock[0] >= park_until + 5.0

    await harness.run_until(still_dirty)

    assert (
        harness.flush_calls[0] <= calls_at_park + 2
    ), f'the parked flush must not ride the drain cadence: {calls_at_park} -> {harness.flush_calls[0]}'


@pytest.mark.anyio
async def test_park_expiration_resumes_flushing_on_the_exponential_ladder(monkeypatch):
    """After the park expires the flush is attempted again, and repeated
    refusals grow the park geometrically (60 -> 120 -> ... capped at 600)."""

    async def failing(_conversation_id):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing)
    processor = harness.processor
    parks = []

    def watch_park():
        if processor._speaker_flush_park_until > parks_last_value():
            parks.append(processor._speaker_flush_park_until)
        return len(parks) >= 3

    def parks_last_value():
        return parks[-1] if parks else 0.0

    await harness.run_until(watch_park, max_ticks=8000)

    # The parks must grow (60 -> 120 -> ...), each consecutive gap doubling the
    # base (the retry happens exactly at expiry in fake time), and none may
    # exceed the 600s cap beyond the clock at observation.
    assert parks == sorted(set(parks)) and len(parks) >= 3, f'parks grow strictly, saw {parks}'
    base = (parks[1] - parks[0]) / 2
    assert 59.0 <= base <= 61.0, f'the first park uses the 60s base, saw {base}'
    deltas = [b - a for a, b in zip(parks, parks[1:])]
    assert all(b >= a for a, b in zip(deltas, deltas[1:])), f'parks grow geometrically, saw {deltas}'
    assert all(until <= harness.clock[0] + 601.0 for until in parks), f'cap held, saw {parks}'


@pytest.mark.anyio
async def test_park_cannot_exceed_its_cap(monkeypatch):
    """The exponential park is capped at 600s: a session-long refusal must not
    grow an unbounded wait."""

    async def failing(_conversation_id):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing)
    processor = harness.processor
    # Pretend the lane has been refusing for a long time already.
    processor._speaker_flush_defect_attempts = 40

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)

    park = processor._speaker_flush_park_until - harness.clock[0]
    assert park <= 601.0, f'the park hit its cap: {park}'


@pytest.mark.anyio
async def test_park_expiration_retry_that_succeeds_ends_the_story(monkeypatch):
    """A park-expiration retry that commits ends the failure story: no further
    terminal events, the flush stays quiet until the map goes dirty again."""
    behavior = {'fail': True}

    async def failing_then_well(_conversation_id):
        if behavior['fail']:
            raise _decode_error()
        return None

    harness = _FlushHarness(monkeypatch, flush=failing_then_well)
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)
    events_at_park = len(harness.fallback_events)
    behavior['fail'] = False
    processor.host.state.speaker_map_dirty = True

    await harness.run_until(lambda: processor.host.state.speaker_map_dirty is False)

    assert len(_exhausted(harness.fallback_events)) == 1
    assert len(harness.fallback_events) == events_at_park, 'the committed flush adds no fallback event'


# ---------------------------------------------------------------------------
# The park key: generation changes invalidate it
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_park_is_keyed_to_the_conversation_that_refused(monkeypatch):
    """A generation change invalidates the park: a flush parked against
    conversation-1 must fire immediately once the recording rolls to a new
    conversation — the fresh row gets its attempt without waiting."""

    async def failing(_conversation_id):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing)
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)
    calls_at_park = harness.flush_calls[0]
    park_until = processor._speaker_flush_park_until

    # Roll the recording WITHOUT the success-path reset (a lifecycle-style
    # rollover the flush lane does not observe): the park must die with its
    # conversation.
    processor.host.state.current_conversation_id = 'conversation-rolled'
    processor.host.state.speaker_map_dirty = True

    await harness.run_until(lambda: harness.flush_calls[0] > calls_at_park or harness.clock[0] > park_until + 3.0)

    assert harness.flush_calls[0] > calls_at_park, 'the stale park must not gate the fresh generation'


@pytest.mark.anyio
async def test_park_survives_while_the_conversation_is_unchanged(monkeypatch):
    """The key cuts both ways: while the conversation is unchanged the park
    holds even when the state object is re-dirtied — no accidental early retry."""

    async def failing(_conversation_id):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing)
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)
    calls_at_park = harness.flush_calls[0]
    park_until = processor._speaker_flush_park_until

    def dirty_same_generation():
        processor.host.state.speaker_map_dirty = True
        return harness.clock[0] >= park_until - 5.0

    await harness.run_until(dirty_same_generation)

    assert harness.flush_calls[0] == calls_at_park, 'the park holds for its own conversation'


@pytest.mark.anyio
async def test_success_path_reset_clears_the_key_with_the_park(monkeypatch):
    """A committed flush clears the park AND its conversation key together:
    no half-reset state can leave a stale gate behind."""
    harness = _FlushHarness(monkeypatch, flush=None, persistence=None)
    processor = harness.processor
    # Seed a park as if the lane had refused, then let the REAL flush commit.
    processor._speaker_flush_defect_attempts = SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET
    processor._speaker_flush_park_until = 10.0  # already expired in fake time
    processor._speaker_flush_park_conversation = 'conversation-1'

    await harness.run_until(lambda: processor.host.state.speaker_map_dirty is False)

    assert processor._speaker_flush_park_until == 0.0
    assert processor._speaker_flush_park_conversation is None
    assert processor._speaker_flush_defect_attempts == 0


@pytest.mark.anyio
async def test_budget_resets_when_the_flush_commits_again(monkeypatch):
    """One committed flush proves the current generation accepts the map: the
    deterministic budget restarts from zero for whatever comes next."""
    behavior = {'failures_left': 0}

    async def persistence_call(_fn, *args, **kwargs):
        if behavior['failures_left'] > 0:
            behavior['failures_left'] -= 1
            raise _decode_error()
        return [{'id': 'stub-segment'}]

    harness = _FlushHarness(monkeypatch, flush=None, persistence=persistence_call)
    processor = harness.processor

    # Drive the lane to a parked state first.
    behavior['failures_left'] = 10**6
    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)
    # Then make the flush succeed: a park-expiration retry commits, and the
    # success path must clear both the budget and the park.
    behavior['failures_left'] = 0
    processor.host.state.speaker_map_dirty = True

    await harness.run_until(
        lambda: processor._speaker_flush_defect_attempts == 0 and processor._speaker_flush_park_until == 0.0
    )

    assert processor._speaker_flush_park_conversation is None


# ---------------------------------------------------------------------------
# Boundary wiring: the drain tick
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_clean_boundary_skips_the_flush_when_the_map_is_not_dirty(monkeypatch):
    """No dirty flag, no flush call — the boundary must not invent work."""
    harness = _FlushHarness(monkeypatch, flush=None)
    processor = harness.processor
    processor.host.state.speaker_map_dirty = False

    def settle():
        return harness.clock[0] >= 15.0

    await harness.run_until(settle)

    assert harness.flush_calls[0] == 0


@pytest.mark.anyio
async def test_backoff_gate_delays_the_flush_even_without_a_park(monkeypatch):
    """The pre-existing `_flush_backoff_until` gate still applies for the
    transient arm: the boundary must not call inside the backoff window."""
    harness = _FlushHarness(monkeypatch, flush=AsyncMock(side_effect=RuntimeError('contention')))
    processor = harness.processor

    await harness.run_until(lambda: processor._flush_failures >= 1)
    calls_after_first = harness.flush_calls[0]
    # Re-arm only the quick backoff (its window may already be in the past at
    # observation time): the boundary must respect a LIVE backoff window.
    processor._flush_backoff_until = harness.clock[0] + 8.0

    def inside_backoff():
        processor.host.state.speaker_map_dirty = True
        return harness.clock[0] < harness.processor._flush_backoff_until - 0.5

    await harness.run_until(inside_backoff)

    assert harness.flush_calls[0] == calls_after_first, 'the backoff gate holds between attempts'


@pytest.mark.anyio
async def test_flush_only_lane_keeps_the_loop_alive_while_parked(monkeypatch):
    """A parked flush must not crash or starve the loop: the supervised task
    keeps ticking (the harness asserts no crash on cancel inside run_until)."""

    async def failing(_conversation_id):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing)
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)
    before = harness.clock[0]

    def ticking():
        processor.host.state.speaker_map_dirty = True
        return harness.clock[0] >= before + 20.0

    await harness.run_until(ticking)

    assert harness.clock[0] >= before + 20.0, 'the loop kept ticking through the park'


# ---------------------------------------------------------------------------
# Rollover integration: the park as generation-refusal evidence
# ---------------------------------------------------------------------------


def _seed_segments(processor, count=6):
    processor.segment_buffer = deque(_raw_segments(count))


@pytest.mark.anyio
async def test_rollover_probe_is_front_loaded_to_the_park_boundary(monkeypatch):
    """With the flush parked for the current generation, a failing batch
    persist against the same row arms the rollover probe at the park boundary —
    not on the far-out sweep schedule: the flush already proved the row refuses
    writes, so the recording rolls as soon as the park expires."""

    async def failing_flush(_conversation_id):
        raise _decode_error()

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing_flush, update=update)
    processor = harness.processor
    harness.seed_park()
    park_until = processor._speaker_flush_park_until
    _seed_segments(processor)

    await harness.run_until(lambda: processor._oversized_rollover_probe_at != float('inf'))

    assert (
        processor._oversized_rollover_probe_at <= park_until + 1.0
    ), 'the probe must be armed no later than the park boundary'


@pytest.mark.anyio
async def test_probe_front_load_requires_the_matching_conversation(monkeypatch):
    """A park left over from an earlier generation must NOT front-load the
    probe for the current one: the evidence is conversation-scoped."""

    async def failing_flush(_conversation_id):
        raise _decode_error()

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing_flush, update=update)
    processor = harness.processor
    harness.seed_park(conversation='conversation-stale')
    _seed_segments(processor)

    await harness.run_until(lambda: harness.clock[0] >= processor._speaker_flush_park_until + 3.0)

    assert processor._oversized_rollover_probe_at == float('inf'), 'a stale park must not arm the probe'


@pytest.mark.anyio
async def test_escape_at_the_front_loaded_boundary_resets_the_flush_lane(monkeypatch):
    """The escape probe fires at the front-loaded boundary and the rollover
    clears the flush park, its key, and the budget: the fresh row's flush is
    attempted immediately."""

    async def failing_flush(_conversation_id):
        raise _decode_error()

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing_flush, update=update)
    processor = harness.processor
    harness.seed_park()
    _seed_segments(processor)

    await harness.run_until(lambda: len(harness.rollover.mock_calls) > 0)

    assert harness.rolls[0] == 1, 'exactly one escape probe'
    assert processor._speaker_flush_park_until == 0.0
    assert processor._speaker_flush_park_conversation is None
    assert processor._speaker_flush_defect_attempts == 0


@pytest.mark.anyio
async def test_rollover_escape_resets_the_flush_park_and_budget(monkeypatch):
    """Direct wiring check on the escape branch: even without an active park
    at escape time the reset lines are total (no partial state survives the
    generation change)."""

    async def failing_flush(_conversation_id):
        raise _decode_error()

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing_flush, update=update)
    processor = harness.processor
    # An ACTIVE park for the current generation is what arms the probe via the
    # persist failure; the expiry during the storm then fires the escape.
    harness.seed_park(attempts=SPEAKER_FLUSH_DETERMINISTIC_ATTEMPT_BUDGET + 1)
    _seed_segments(processor)

    await harness.run_until(lambda: len(harness.rollover.mock_calls) > 0)

    assert processor._speaker_flush_park_conversation is None
    assert processor._speaker_flush_defect_attempts == 0


# ---------------------------------------------------------------------------
# Real flush integration (success path wiring)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_real_flush_success_runs_the_full_success_path(monkeypatch):
    """The real ``flush_speaker_assignments`` against stubbed persistence:
    a committed write clears budget, park, and key, and clears the dirty flag
    when the map did not change while writing."""
    harness = _FlushHarness(monkeypatch, flush=None, persistence=None)
    processor = harness.processor
    processor._speaker_flush_defect_attempts = 2
    processor.host.state.speaker_map_dirty = True

    await harness.run_until(lambda: processor.host.state.speaker_map_dirty is False)

    assert harness.flush_calls[0] >= 1
    assert processor._speaker_flush_defect_attempts == 0
    assert processor._speaker_flush_park_until == 0.0
    assert processor._speaker_flush_park_conversation is None


@pytest.mark.anyio
async def test_real_flush_failure_propagates_to_the_boundary_classifier(monkeypatch):
    """The real flush raising inside the boundary takes the deterministic arm:
    the budget counts, and the ERROR-line evidence keeps the same message
    shape the sentinel expects."""

    async def persistence_call(_fn, *args, **kwargs):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=None, persistence=persistence_call)
    processor = harness.processor

    await harness.run_until(lambda: processor._speaker_flush_defect_attempts >= 1)

    assert processor._speaker_flush_defect_attempts == 1
    assert not _exhausted(harness.fallback_events), 'still inside the budget: no terminal counter yet'


# ---------------------------------------------------------------------------
# Doc-contract mirrors (the invariants the docs promise)
# ---------------------------------------------------------------------------


def test_budget_failure_shapes_are_exactly_the_persist_arm_predicates():
    """The doc promises the flush split is the persist arm's classification:
    verify the predicate on the full shape list used by these tests. The
    1 MiB shape is classified by the permanent-write-rejection arm
    (`_handle_oversized_legacy_persist`), not the ValueError predicate."""
    for make_error in _DETERMINISTIC_SHAPES[:-1]:
        assert _is_deterministic_persist_defect(make_error()), make_error.__name__
    assert not _is_deterministic_persist_defect(_size_limit_error()), 'size-limit is the other arm'
    for make_error in _TRANSIENT_SHAPES:
        assert not _is_deterministic_persist_defect(make_error())


@pytest.mark.anyio
async def test_terminal_counter_fires_once_per_park_not_once_per_refusal(monkeypatch):
    """Refusals inside the park window (only the expiry retries exist) must
    not each emit the exhausted counter: one story, one counter."""

    async def failing(_conversation_id):
        raise _decode_error()

    harness = _FlushHarness(monkeypatch, flush=failing)
    processor = harness.processor
    parks = []

    def watch_two_parks():
        if processor._speaker_flush_park_until > (parks[-1] if parks else 0.0):
            parks.append(processor._speaker_flush_park_until)
        return len(parks) >= 2

    await harness.run_until(watch_two_parks, max_ticks=8000)

    assert len(parks) >= 2, f'two park episodes observed, saw {parks}'
    assert (
        len(_exhausted(harness.fallback_events)) == 2
    ), f'one counter per park episode, saw {len(_exhausted(harness.fallback_events))}'


@pytest.mark.anyio
async def test_parked_state_does_not_block_the_persist_lane(monkeypatch):
    """The flush park must not gate batch persistence: with the flush parked,
    segments still drain through the persist arm (flush-only branch skipped)."""

    async def failing_flush(_conversation_id):
        raise _decode_error()

    committed = []

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        committed.append(len(segments))
        return None

    harness = _FlushHarness(monkeypatch, flush=failing_flush, update=update)
    processor = harness.processor
    _seed_segments(processor, count=2)

    # Park the flush first.
    await harness.run_until(lambda: processor._speaker_flush_park_until > 0.0)
    _seed_segments(processor, count=2)

    await harness.run_until(lambda: bool(committed))

    assert committed, 'the persist lane drained while the flush was parked'
