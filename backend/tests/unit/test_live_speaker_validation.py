"""Regression: provider segments without an ``id`` must never reach the matcher.

Incident shape: in clock-only mode (AUDIO_TIMELINE_V2 off) the legacy
``TranscriptProcessor.enqueue`` extended the segment buffer verbatim, so a
provider segment missing ``id`` stayed id-less while ``TranscriptSegment``
minted its own uuid the raw copy never saw. The capture-window map keyed
``None`` and the raw embedding queue forwarded ``id=None`` to the matcher; the
accepted owner decision then raised ``ValidationError`` building
``SpeakerLabelSuggestionEvent(segment_id=None)`` inside the matcher's broad
catch — in current code the emit precedes status publication, so the invalid
event aborts it and the suggestion never reaches the wire.

The real-path test drives the real receiver callback, ``process_loop``, the
raw detection queue, the real ``SpeakerMatcher`` and the real
``ListenSessionRuntime.emit_speaker_suggestion`` (wrapped to record a
``ValidationError`` before re-raising it) on ``FailoverStack``'s
strict-Firestore harness.
"""

import asyncio
import logging
from types import MethodType
from typing import Optional

import numpy as np
import pytest
from pydantic import ValidationError

from models.message_event import SpeakerLabelSuggestionEvent
from models.transcript_segment import SpeakerIdentityStatus
from routers.listen.runtime import ListenSessionRuntime
from tests.unit.test_listen_speaker_id_failover import (
    CONV,
    T0,
    FailoverStack,
    _frames_for,  # pyright: ignore[reportPrivateUsage]
    _owner,  # pyright: ignore[reportPrivateUsage]
    _unit_vector,  # pyright: ignore[reportPrivateUsage]
    _wait_for,  # pyright: ignore[reportPrivateUsage]
)
from utils.product_telemetry import set_product_telemetry_client_for_tests

SENSITIVE_NAME = 981113377
SENSITIVE_RUNTIME = 'sensitive-runtime-marker-9f2c'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _TelemetryClient:
    def __init__(self):
        self.events = []

    def capture(self, **event):
        self.events.append(event)


@pytest.fixture
def telemetry():
    client = _TelemetryClient()
    set_product_telemetry_client_for_tests(client)
    yield client
    set_product_telemetry_client_for_tests(None)


def _real_emitter(stack):
    """Bind the production emitter; record a ``ValidationError`` then re-raise."""
    emit = MethodType(ListenSessionRuntime.emit_speaker_suggestion, stack.host)
    captured = []

    def wrapped(*args, **kwargs):
        try:
            return emit(*args, **kwargs)
        except ValidationError as error:
            captured.append(error)
            raise

    stack.host.emit_speaker_suggestion = wrapped
    return captured


def _raw_segment(text, start, end, segment_id: Optional[str] = '__missing__'):
    segment = {
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'start': start,
        'end': end,
        'text': text,
        'is_user': False,
        'person_id': None,
    }
    if segment_id != '__missing__':
        segment['id'] = segment_id
    return segment


def _queued_detection(segment_id):
    return {
        'id': segment_id,
        'conversation_id': CONV,
        'speaker_id': 0,
        'speaker_id_scope': 'epoch:0',
        'abs_start': T0,
        'abs_end': T0 + 6.0,
        'duration': 6.0,
    }


async def _match_queued(stack, segment):
    """Drive the real matcher to a decision on directly positioned owner audio."""
    stack.state.audio_ring_buffer.write_positioned(_owner(6.0), T0)
    await stack.host.speakers.refresh_for_conversation(CONV)
    await stack.host.speakers.match(0, segment)


def _match_failures(caplog):
    return [record.getMessage() for record in caplog.records if 'Speaker ID match failed' in record.getMessage()]


async def _teardown(stack, *tasks):
    stack.state.active = False
    stack.state.shutdown_event.set()
    await stack.finish()
    try:
        for task in tasks:
            await asyncio.wait_for(task, timeout=30)
        for task in stack.tasks:
            task.cancel()
        await asyncio.gather(*stack.tasks, return_exceptions=True)
    finally:
        stack.restore()


@pytest.mark.parametrize('v2', [False, True])
def test_enqueue_normalizes_missing_ids_once_at_admission(monkeypatch, v2):
    """Every accepted raw gets one stable id before the queues diverge."""
    stack = FailoverStack(monkeypatch, v2=v2)
    try:
        missing = _raw_segment('missing id', 0.0, 1.0)
        explicit_none = _raw_segment('none id', 1.0, 2.0, None)
        empty = _raw_segment('empty id', 2.0, 3.0, '')
        given = _raw_segment('given id', 3.0, 4.0, 'provider-seg-9')
        stack.processor.enqueue([missing, explicit_none, empty, given])
        ids = [raw.get('id') for raw in stack.processor.segment_buffer]
        assert all(isinstance(value, str) and value for value in ids)
        assert len(set(ids)) == 4, 'distinct id-less segments need distinct capture-window keys'
        assert given['id'] == 'provider-seg-9'
        stack.processor.enqueue([missing])
        assert missing.get('id') == ids[0], 'a repeated/retried raw keeps its minted id'
        assert stack.receive_task is None, 'sync admission never mounts the receive loop'
    finally:
        stack.restore()


@pytest.mark.anyio
async def test_clock_only_missing_id_reaches_owner_suggestion(monkeypatch, caplog, telemetry):
    """The incident path end to end (v2 off): enqueue -> legacy process_loop ->
    capture windows -> raw queue -> matcher -> real event emission."""
    stack = FailoverStack(monkeypatch, v2=False)
    captured = _real_emitter(stack)
    loop_task = asyncio.create_task(stack.processor.process_loop())
    matcher_task = asyncio.create_task(stack.host.speakers.load_and_run())
    stack.tasks.extend([loop_task, matcher_task])
    caplog.set_level(logging.ERROR, logger='routers.listen.speakers')
    try:
        await stack.host.speakers.refresh_for_conversation(CONV)
        assert await stack.receiver.initialize_stt()
        websocket = await stack.run_receive(_frames_for(_owner(6.0)))
        stack.provider(0)['callback']([_raw_segment('owner speaks without a provider id', 0.0, 6.0)])

        await _wait_for(
            lambda: stack.host.speakers.voice_identity_status.get(0) == SpeakerIdentityStatus.user or captured,
            timeout=15.0,
            message='owner decision to emit its suggestion',
            stack=stack,
        )
        assert not captured, [
            (error.title, error.errors(include_input=False, include_context=False, include_url=False))
            for error in captured
        ]
        suggestions = [event for event in stack.sent_events if isinstance(event, SpeakerLabelSuggestionEvent)]
        assert suggestions, 'the accepted owner decision must emit a suggestion event'
        event = suggestions[-1]

        def _persisted_owner():
            return [
                segment
                for segment in stack.decode_segments()
                if 'without a provider id' in (segment.get('text') or '') and segment.get('is_user')
            ]

        await _wait_for(_persisted_owner, timeout=15.0, message='flushed owner label on the stored segment')
        persisted = _persisted_owner()[-1]
        assert event.segment_id == persisted['id']
        delivered = [
            segment
            for batch in websocket.sent_json
            if isinstance(batch, list)
            for segment in batch
            if 'without a provider id' in (segment.get('text') or '')
        ]
        assert delivered and any(segment.get('is_user') for segment in delivered)
    finally:
        await _teardown(stack, loop_task)


@pytest.mark.anyio
async def test_match_logs_validation_fields_for_bad_segment_id(monkeypatch, caplog, telemetry):
    """A ValidationError logs model, first loc and type — never the input value."""
    monkeypatch.setenv('PINNED_SPEAKER_PRIOR_ENABLED', 'false')
    stack = FailoverStack(monkeypatch, v2=False)
    _real_emitter(stack)
    caplog.set_level(logging.ERROR, logger='routers.listen.speakers')
    try:
        await _match_queued(stack, _queued_detection(segment_id=None))
        failures = _match_failures(caplog)
        assert failures
        message = failures[-1]
        assert 'type=ValidationError' in message
        assert 'validation_model=SpeakerLabelSuggestionEvent' in message
        assert 'validation_loc=segment_id' in message
        assert 'validation_type=string_type' in message
        assert 'input' not in message
    finally:
        stack.restore()


@pytest.mark.anyio
async def test_match_logs_first_error_only_for_multi_error_event(monkeypatch, caplog, telemetry):
    """A multi-error event reports the first loc only — never the rejected value."""
    monkeypatch.setenv('PINNED_SPEAKER_PRIOR_ENABLED', 'false')
    stack = FailoverStack(monkeypatch, v2=False)
    _real_emitter(stack)
    caplog.set_level(logging.ERROR, logger='routers.listen.speakers')
    try:
        stack.state.audio_ring_buffer.write_positioned(_owner(6.0), T0)
        await stack.host.speakers.refresh_for_conversation(CONV)
        stack.host.speakers.person_embeddings = {
            'person-9': {
                'embedding': np.asarray(_unit_vector(1), dtype=np.float32).reshape(1, -1),
                'name': SENSITIVE_NAME,
            }
        }
        await stack.host.speakers.match(0, _queued_detection(segment_id=None))
        failures = _match_failures(caplog)
        assert failures
        message = failures[-1]
        assert 'type=ValidationError' in message
        assert 'validation_model=SpeakerLabelSuggestionEvent' in message
        assert 'validation_loc=person_name' in message
        assert 'validation_type=string_type' in message
        assert 'segment_id' not in message
        assert str(SENSITIVE_NAME) not in message
    finally:
        stack.restore()


@pytest.mark.anyio
async def test_match_failure_without_validation_fields_for_plain_error(monkeypatch, caplog, telemetry):
    """A non-ValidationError keeps the original log shape — type only."""
    monkeypatch.setenv('PINNED_SPEAKER_PRIOR_ENABLED', 'false')
    stack = FailoverStack(monkeypatch, v2=False)

    def boom(*_args, **_kwargs):
        raise RuntimeError(SENSITIVE_RUNTIME)

    stack.host.emit_speaker_suggestion = boom
    caplog.set_level(logging.ERROR, logger='routers.listen.speakers')
    try:
        await _match_queued(stack, _queued_detection(segment_id='seg-queued'))
        failures = _match_failures(caplog)
        assert failures
        message = failures[-1]
        assert 'type=RuntimeError' in message
        assert 'validation_' not in message
        assert SENSITIVE_RUNTIME not in message
    finally:
        stack.restore()
