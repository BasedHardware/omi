"""Behavioral regression coverage for the extracted listen runtime."""

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from routers.listen.transcripts import TranscriptProcessor
from utils.async_tasks import WebSocketTaskSupervisor
from utils.listen_session_bootstrap import ListenConnectBase
from utils.onboarding import ONBOARDING_QUESTIONS, OnboardingHandler
from utils.stt.streaming import STTService
from starlette.websockets import WebSocketState


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _Persistence:
    async def call(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def _deletion_teardown_runtime(request, persistence_call):
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = request
    runtime.state = SimpleNamespace(
        shutdown_event=asyncio.Event(),
        active=True,
        stt_terminal_failure=False,
        close_code=1001,
        current_conversation_id='conversation-1',
    )
    runtime.task_supervisor = SimpleNamespace(end_session=MagicMock(), drain_all=AsyncMock())
    runtime._finish_live_transcription = MagicMock()
    runtime.transcripts = SimpleNamespace(
        flush_translations=AsyncMock(),
        flush_speaker_assignments=AsyncMock(),
        clear=MagicMock(),
    )
    runtime.receiver = SimpleNamespace(finish=MagicMock(), flush_multi_channel_tail=AsyncMock(), clear=MagicMock())
    runtime._flush_usage = AsyncMock()
    runtime.persistence = SimpleNamespace(call=persistence_call)
    runtime.conversations = SimpleNamespace(process_conversation=AsyncMock())
    runtime.is_multi_channel = False
    runtime.pusher_close = None
    runtime.onboarding_handler = None
    runtime.parity_capture = SimpleNamespace(persist=MagicMock())
    runtime.speakers = SimpleNamespace(clear=MagicMock())
    return runtime


def _assert_deletion_teardown_skipped_owner_writes(runtime):
    runtime.task_supervisor.drain_all.assert_awaited_once_with(timeout=5.0, cancel=True)
    runtime.transcripts.flush_translations.assert_not_awaited()
    runtime.transcripts.flush_speaker_assignments.assert_not_awaited()
    runtime.receiver.flush_multi_channel_tail.assert_not_awaited()
    runtime._flush_usage.assert_not_awaited()
    runtime.conversations.process_conversation.assert_not_awaited()
    runtime.parity_capture.persist.assert_not_called()


@pytest.mark.anyio
async def test_deletion_fence_teardown_cancels_tasks_without_owner_persistence():
    request = ListenRequest(
        websocket=SimpleNamespace(client_state=WebSocketState.DISCONNECTED),
        uid='deleted-owner',
    )
    request.owner_persistence_blocked.set()
    persistence_call = AsyncMock()
    runtime = _deletion_teardown_runtime(request, persistence_call)

    await runtime._teardown()

    persistence_call.assert_not_awaited()
    _assert_deletion_teardown_skipped_owner_writes(runtime)


@pytest.mark.anyio
async def test_teardown_rechecks_deletion_authority_before_owner_persistence():
    request = ListenRequest(
        websocket=SimpleNamespace(client_state=WebSocketState.DISCONNECTED),
        uid='newly-deleted-owner',
    )
    authority_reads = []

    async def persistence_call(function, *args):
        authority_reads.append((function, args))
        return True

    runtime = _deletion_teardown_runtime(request, persistence_call)

    await runtime._teardown()

    assert len(authority_reads) == 1
    assert authority_reads[0][0].__name__ == '_account_deletion_blocks_owner_persistence'
    assert authority_reads[0][1] == ('newly-deleted-owner',)
    assert request.owner_persistence_blocked.is_set()
    _assert_deletion_teardown_skipped_owner_writes(runtime)


def _runtime_for_periodic_usage(*, tracking, exhausted):
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='fair-use-user')
    runtime.session_id = 'fair-use-session'
    runtime.use_custom_stt = False
    runtime.persistence = _Persistence()
    runtime.state = SimpleNamespace(
        active=True,
        fair_use_last_check_ts=0.0,
        fair_use_track_dg_usage=tracking,
        fair_use_dg_budget_exhausted=exhausted,
        fair_use_plan=None,
    )

    async def wait(_seconds):
        runtime.state.active = False
        return False

    async def flush_usage(*, final):
        assert final is False
        return 0

    async def refresh_credits(*, transcription_seconds):
        assert transcription_seconds == 0

    runtime.wait = wait
    runtime._flush_usage = flush_usage
    runtime._refresh_credits = refresh_credits
    return runtime


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('caps', 'initial_tracking', 'initial_exhausted', 'expected_tracking', 'expected_exhausted'),
    [
        (['daily'], False, False, True, False),
        ([], True, True, False, False),
    ],
)
async def test_periodic_fair_use_check_preserves_proactive_tracking_and_clears_stale_restriction(
    monkeypatch, caps, initial_tracking, initial_exhausted, expected_tracking, expected_exhausted
):
    import routers.listen.runtime as runtime_module

    runtime = _runtime_for_periodic_usage(tracking=initial_tracking, exhausted=initial_exhausted)
    started_classifier_tasks = []

    async def classifier(*_args):
        return None

    def start_background(coro, *, name):
        started_classifier_tasks.append(name)
        coro.close()

    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', True)
    monkeypatch.setattr(runtime_module, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 60_000)
    monkeypatch.setattr(runtime_module, 'get_rolling_speech_ms', lambda _uid: {'daily_ms': 1})
    monkeypatch.setattr(runtime_module, 'check_soft_caps', lambda _uid, *, speech_totals, plan: caps)
    monkeypatch.setattr(runtime_module, 'is_daily_audio_ceiling_exceeded', lambda _uid, *, speech_totals: False)
    monkeypatch.setattr(
        runtime_module.user_db, 'get_user_valid_subscription', lambda _uid: SimpleNamespace(plan='basic')
    )
    monkeypatch.setattr(runtime_module, 'get_enforcement_stage', lambda _uid: 'observe')
    monkeypatch.setattr(runtime_module, 'trigger_classifier_if_needed', classifier)
    monkeypatch.setattr(runtime_module, 'start_background_task', start_background)

    await runtime._record_usage_periodically()

    assert runtime.state.fair_use_track_dg_usage is expected_tracking
    assert runtime.state.fair_use_dg_budget_exhausted is expected_exhausted
    assert started_classifier_tasks == (['fair_use_classifier:fair-use-user:fair-use-session'] if caps else [])


@pytest.mark.anyio
async def test_bootstrap_forces_single_language_before_selecting_stt_for_onboarding(monkeypatch):
    import routers.listen.runtime as runtime_module

    request = ListenRequest(
        websocket=SimpleNamespace(),
        uid='onboarding-user',
        language='es',
        onboarding_mode=True,
    )
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = request
    runtime.use_custom_stt = False
    runtime.state = SimpleNamespace(speaker_id_enabled=False, audio_ring_buffer=None)
    runtime.task_supervisor = WebSocketTaskSupervisor(uid=request.uid, label='listen')

    async def bootstrap_persistence_call(*_args, **_kwargs):
        return False

    runtime.persistence = SimpleNamespace(call=bootstrap_persistence_call)
    runtime.is_multi_channel = False
    runtime.has_speech_profile = False
    runtime.transcripts = SimpleNamespace(enqueue=lambda _segments: None)
    runtime._build_components = lambda: None

    base = ListenConnectBase(
        user_exists=True,
        user_has_credits=True,
        transcription_prefs={'single_language_mode': False, 'uses_custom_stt': False},
        fair_use_init_stage=None,
        fair_use_track_dg_usage=False,
        fair_use_dg_budget_exhausted=False,
    )
    selected_multi_language_options = []

    def select_stt(language, *, multi_lang_enabled, preferred_service=None):
        selected_multi_language_options.append((language, multi_lang_enabled, preferred_service))
        return 'test-stt', 'es', 'test-model'

    monkeypatch.setattr(runtime_module, 'load_listen_connect_base', lambda *_args, **_kwargs: _async_result(base))
    monkeypatch.setattr(runtime_module.user_db, 'ensure_backend_onboarding_admission', lambda _uid: True, raising=False)
    monkeypatch.setattr(runtime_module.user_db, 'get_backend_onboarding_admission', lambda _uid: 'a' * 32)
    monkeypatch.setattr(runtime_module, 'get_stt_service_for_language', select_stt)
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'should_load_speech_profile', lambda **_kwargs: False)
    monkeypatch.setattr(runtime_module, 'should_enable_speaker_identification', lambda **_kwargs: False)

    async def _noop_question():
        return None

    monkeypatch.setattr(
        runtime_module,
        'OnboardingHandler',
        lambda *_args, **_kwargs: SimpleNamespace(send_current_question=_noop_question),
    )

    assert await runtime._bootstrap() is True
    await runtime.task_supervisor.drain_all(timeout=1.0, cancel=False)
    assert selected_multi_language_options == [('es', False, None)]


@pytest.mark.anyio
async def test_bootstrap_sends_first_onboarding_question_before_any_audio(monkeypatch):
    """An onboarding session's question flow is server-driven: the first question
    must reach the client at connect time, before any segments arrive. Dropping
    this kickoff leaves the speech-profile page frozen at 0% with no question."""
    import routers.listen.runtime as runtime_module

    sent_events = []

    async def send_json(event):
        sent_events.append(event)

    request = ListenRequest(
        websocket=SimpleNamespace(client_state=WebSocketState.CONNECTED, send_json=send_json),
        uid='onboarding-user',
        language='en',
        onboarding_mode=True,
    )
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = request
    runtime.use_custom_stt = False
    runtime.state = SimpleNamespace(speaker_id_enabled=False, audio_ring_buffer=None, active=True)
    runtime.task_supervisor = WebSocketTaskSupervisor(uid=request.uid, label='listen')

    async def bootstrap_persistence_call(*_args, **_kwargs):
        return False

    runtime.persistence = SimpleNamespace(call=bootstrap_persistence_call)
    runtime.is_multi_channel = False
    runtime.has_speech_profile = False
    enqueued_segments = []
    runtime.transcripts = SimpleNamespace(enqueue=enqueued_segments.extend)
    runtime._build_components = lambda: None

    base = ListenConnectBase(
        user_exists=True,
        user_has_credits=True,
        transcription_prefs={'single_language_mode': False, 'uses_custom_stt': False},
        fair_use_init_stage=None,
        fair_use_track_dg_usage=False,
        fair_use_dg_budget_exhausted=False,
    )
    monkeypatch.setattr(runtime_module, 'load_listen_connect_base', lambda *_args, **_kwargs: _async_result(base))
    monkeypatch.setattr(runtime_module.user_db, 'ensure_backend_onboarding_admission', lambda _uid: True, raising=False)
    monkeypatch.setattr(runtime_module.user_db, 'get_backend_onboarding_admission', lambda _uid: 'a' * 32)
    monkeypatch.setattr(
        runtime_module, 'get_stt_service_for_language', lambda language, **_kwargs: ('test-stt', 'en', 'test-model')
    )
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'should_load_speech_profile', lambda **_kwargs: False)
    monkeypatch.setattr(runtime_module, 'should_enable_speaker_identification', lambda **_kwargs: False)

    assert await runtime._bootstrap() is True
    await runtime.task_supervisor.drain_all(timeout=2.0, cancel=False)

    assert [event['type'] for event in sent_events] == ['onboarding_question']
    first_question = sent_events[0]
    assert first_question['question'] == ONBOARDING_QUESTIONS[0]['question']
    assert first_question['question_index'] == 0
    assert first_question['total_questions'] == len(ONBOARDING_QUESTIONS)
    assert enqueued_segments and enqueued_segments[0]['speaker_id'] == OnboardingHandler.OMI_SPEAKER_ID


def test_allocator_sentinel_matches_the_onboarding_handler_reservation():
    # The allocator reserves OMI_SPEAKER_ID_SENTINEL so a long session with
    # many provider transitions can never allocate 99 to a real speaker. That
    # reservation is only meaningful while it equals the value onboarding
    # actually stamps its question segments with, so pin the two together.
    # (This file already owns the heavy utils.onboarding import chain.)
    from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL

    assert OMI_SPEAKER_ID_SENTINEL == OnboardingHandler.OMI_SPEAKER_ID


@pytest.mark.anyio
async def test_bootstrap_passes_explicit_parakeet_through_capability_aware_selection(monkeypatch):
    import routers.listen.runtime as runtime_module

    request = ListenRequest(
        websocket=SimpleNamespace(),
        uid='language-routing-user',
        language='es',
        stt_service='parakeet',
    )
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = request
    runtime.use_custom_stt = False
    runtime.state = SimpleNamespace(speaker_id_enabled=False, audio_ring_buffer=None)

    async def bootstrap_persistence_call(*_args, **_kwargs):
        return False

    runtime.persistence = SimpleNamespace(call=bootstrap_persistence_call)
    runtime.is_multi_channel = False
    runtime.has_speech_profile = False
    runtime._build_components = lambda: None

    base = ListenConnectBase(
        user_exists=True,
        user_has_credits=True,
        transcription_prefs={'single_language_mode': False, 'uses_custom_stt': False},
        fair_use_init_stage=None,
        fair_use_track_dg_usage=False,
        fair_use_dg_budget_exhausted=False,
    )

    def select_stt(language, *, multi_lang_enabled, preferred_service=None):
        assert (language, multi_lang_enabled, preferred_service) == ('es', True, 'parakeet')
        return STTService.modulate, 'multi', 'velma-2'

    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.test')
    monkeypatch.setattr(runtime_module, 'load_listen_connect_base', lambda *_args, **_kwargs: _async_result(base))
    monkeypatch.setattr(runtime_module, 'get_stt_service_for_language', select_stt)
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'should_load_speech_profile', lambda **_kwargs: False)
    monkeypatch.setattr(runtime_module, 'should_enable_speaker_identification', lambda **_kwargs: False)

    assert await runtime._bootstrap() is True
    assert (runtime.stt_service, runtime.stt_language, runtime.stt_model) == (
        STTService.modulate,
        'multi',
        'velma-2',
    )


def test_runtime_emits_speaker_suggestion_event(monkeypatch):
    import routers.listen.runtime as runtime_module

    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='user-1', speaker_auto_assign_enabled=True)
    runtime.recording_session_id = 'recording-1'
    runtime.state = SimpleNamespace(current_conversation_id='conversation-1')
    emitted_events = []
    product_events = []
    runtime.send_event = emitted_events.append
    monkeypatch.setattr(runtime_module, 'emit_product_event', lambda **event: product_events.append(event))

    runtime.emit_speaker_suggestion(4, 'person-123', 'Avery', 'segment-123')

    assert emitted_events[0].event_type == 'speaker_label_suggestion'
    assert emitted_events[0].speaker_id == 4
    assert emitted_events[0].person_name == 'Avery'
    assert product_events == [
        {
            'uid': 'user-1',
            'event': 'Speaker Identity Proposed',
            'properties': {
                'recording_id': 'recording-1',
                'conversation_id': 'conversation-1',
                'speaker_id': 4,
                'matched_existing_person': True,
                'auto_assign_enabled': True,
                'proposal_source': 'live_speaker_identification',
            },
        }
    ]


class _LiveSTTAttempt:
    instances = []

    def __init__(self, *, provider, platform, **context):
        self.provider = provider
        self.platform = platform
        self.context = context
        self.finished = False
        self.terminals = []
        self.__class__.instances.append(self)

    def finish(self, outcome, *, phase):
        if self.finished:
            return
        self.finished = True
        self.terminals.append((outcome, phase))


def _live_transcription_runtime(*, close_code=1001, stt_terminal_failure=False, live_transcription_failed=False):
    runtime = object.__new__(ListenSessionRuntime)
    runtime.use_custom_stt = False
    runtime.state = SimpleNamespace(
        close_code=close_code,
        stt_terminal_failure=stt_terminal_failure,
        live_transcription_failed=live_transcription_failed,
        live_transcription_attempt=None,
        client_live_transcription_attempt=None,
    )
    runtime.stt_service = STTService.deepgram
    runtime.stt_model = 'nova-3'
    runtime.stt_language = 'en'
    runtime.recording_session_id = 'recording-123'
    runtime.request = SimpleNamespace(uid='user-123', source='phone')
    runtime.state.current_conversation_id = 'conversation-123'
    runtime.client_device_context = SimpleNamespace(platform='ios')
    runtime.client_kind = 'mobile_ios'
    return runtime


def test_live_transcription_journey_starts_once_and_success_wins_over_teardown(monkeypatch):
    import routers.listen.runtime as runtime_module

    _LiveSTTAttempt.instances = []
    client_attempt = MagicMock(finished=False)
    client_attempt.succeed.side_effect = lambda: setattr(client_attempt, 'finished', True)
    client_attempt.fail.side_effect = lambda _issue: setattr(client_attempt, 'finished', True)
    client_attempt.cancel.side_effect = lambda: setattr(client_attempt, 'finished', True)
    monkeypatch.setattr(runtime_module, 'LiveSTTAttempt', _LiveSTTAttempt)
    client_attempt_factory = MagicMock(return_value=client_attempt)
    monkeypatch.setattr(runtime_module, 'ClientJourneyAttempt', client_attempt_factory)
    runtime = _live_transcription_runtime(close_code=1011, stt_terminal_failure=True)

    runtime.start_live_transcription()
    runtime.start_live_transcription()
    runtime.complete_live_transcription()
    runtime._finish_live_transcription()

    assert len(_LiveSTTAttempt.instances) == 1
    assert _LiveSTTAttempt.instances[0].provider == 'deepgram'
    assert _LiveSTTAttempt.instances[0].platform == 'ios'
    assert _LiveSTTAttempt.instances[0].context == {
        'uid': 'user-123',
        'recording_id': 'recording-123',
        'conversation_id': 'conversation-123',
        'source': 'phone',
        'model': 'nova-3',
        'language': 'en',
    }
    assert _LiveSTTAttempt.instances[0].terminals == [('success', 'transcript_delivery')]
    client_attempt_factory.assert_called_once_with('live_transcription', 'mobile_ios')
    client_attempt.succeed.assert_called_once_with()
    client_attempt.fail.assert_not_called()


def test_custom_stt_does_not_create_a_backend_provider_attempt(monkeypatch):
    import routers.listen.runtime as runtime_module

    _LiveSTTAttempt.instances = []
    monkeypatch.setattr(runtime_module, 'LiveSTTAttempt', _LiveSTTAttempt)
    runtime = _live_transcription_runtime()
    runtime.use_custom_stt = True

    runtime.start_live_transcription()
    runtime.complete_live_transcription()
    runtime._finish_live_transcription()

    assert _LiveSTTAttempt.instances == []


@pytest.mark.parametrize(
    ('close_code', 'stt_terminal_failure', 'live_transcription_failed', 'expected'),
    [
        (1000, False, False, 'cancelled'),
        (1011, False, False, 'failure'),
        (1001, True, False, 'failure'),
        (1001, False, True, 'failure'),
    ],
)
def test_live_transcription_teardown_classifies_unsent_attempts_once(
    monkeypatch, close_code, stt_terminal_failure, live_transcription_failed, expected
):
    import routers.listen.runtime as runtime_module

    _LiveSTTAttempt.instances = []
    client_attempt = MagicMock(finished=False)
    client_attempt.succeed.side_effect = lambda: setattr(client_attempt, 'finished', True)
    client_attempt.fail.side_effect = lambda _issue: setattr(client_attempt, 'finished', True)
    client_attempt.cancel.side_effect = lambda: setattr(client_attempt, 'finished', True)
    monkeypatch.setattr(runtime_module, 'LiveSTTAttempt', _LiveSTTAttempt)
    monkeypatch.setattr(runtime_module, 'ClientJourneyAttempt', MagicMock(return_value=client_attempt))
    runtime = _live_transcription_runtime(
        close_code=close_code,
        stt_terminal_failure=stt_terminal_failure,
        live_transcription_failed=live_transcription_failed,
    )

    runtime.start_live_transcription()
    runtime._finish_live_transcription()
    runtime._finish_live_transcription()

    assert _LiveSTTAttempt.instances[0].terminals == [(expected, 'teardown')]
    if expected == 'failure':
        client_attempt.fail.assert_called_once_with('provider_error')
        client_attempt.cancel.assert_not_called()
    else:
        client_attempt.cancel.assert_called_once_with()
        client_attempt.fail.assert_not_called()


@pytest.mark.anyio
async def test_event_delivery_after_close_stops_queueing_events_for_a_gone_socket():
    """A post-close RuntimeError means the client is gone, same as a disconnect."""
    attempts = []

    async def send_json(payload):
        attempts.append(payload)
        raise RuntimeError("Unexpected ASGI message 'websocket.send', after sending 'websocket.close'.")

    runtime = object.__new__(ListenSessionRuntime)
    runtime.state = SimpleNamespace(active=True)
    runtime.request = SimpleNamespace(websocket=SimpleNamespace(send_json=send_json))

    event = SimpleNamespace(to_json=lambda: {'type': 'ping'})
    assert await runtime.asend_event(event) is False
    assert runtime.state.active is False

    # Now inactive, so the next event is not even attempted.
    assert await runtime.asend_event(event) is False
    assert attempts == [{'type': 'ping'}]


def _transcript_processor_for_delivery(monkeypatch, websocket):
    """One buffered segment ready to deliver, with the loop ending after that pass."""
    import routers.listen.transcripts as transcripts_module

    class Segment:
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

        @staticmethod
        def combine_segments(_existing, new_segments):
            return new_segments, [], []

    state = SimpleNamespace(
        active=True,
        first_audio_byte_timestamp=100.0,
        last_transcript_time=None,
        words_transcribed_since_last_record=0,
        current_conversation_id='conversation-1',
        speaker_id_done=asyncio.Event(),
    )
    state.speaker_id_done.set()
    delivered = []
    flushed = []

    async def wait(_seconds):
        state.active = False
        return False

    async def cache_get(_conversation_id):
        return {'transcript_segments': []}

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        return SimpleNamespace(id='conversation-1'), segments, []

    async def no_op(*_args, **_kwargs):
        return None

    async def flush_speaker_assignments(conversation_id):
        flushed.append(conversation_id)

    host = SimpleNamespace(
        state=state,
        wait=wait,
        request=SimpleNamespace(uid='user-1', onboarding_mode=False, websocket=websocket),
        transcript_send=None,
        user_has_credits=True,
        pusher_enabled=True,
        onboarding_handler=None,
        send_event=lambda _event: None,
        speakers=SimpleNamespace(drain=no_op),
        complete_live_transcription=lambda: delivered.append(True),
    )
    processor = object.__new__(TranscriptProcessor)
    processor.host = host
    processor.segment_buffer = deque([{'id': 'segment-1', 'text': 'Hello', 'start': 0.0, 'end': 0.5}])
    processor.photo_buffer = deque()
    processor.cache = SimpleNamespace(get=cache_get)
    processor.current_session_segments = {}
    processor.speaker_id_allocator = SimpleNamespace(hydrate=lambda _segments: None, assign=lambda _segment: None)
    processor._update_live_conversation = update
    processor._translate = no_op
    processor._speaker_detection = no_op
    processor.flush_speaker_assignments = flush_speaker_assignments

    monkeypatch.setattr(transcripts_module, 'TranscriptSegment', Segment)
    monkeypatch.setattr(transcripts_module, 'deserialize_conversation', lambda _data: SimpleNamespace())

    return processor, delivered, flushed


class _ProductTelemetryClient:
    def __init__(self):
        self.events = []

    def capture(self, **event):
        self.events.append(event)


@pytest.mark.anyio
async def test_transcript_delivery_marks_live_transcription_success_only_after_a_nonempty_client_send(monkeypatch):
    class WebSocket:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    websocket = WebSocket()
    processor, delivered, flushed = _transcript_processor_for_delivery(monkeypatch, websocket)

    await processor.process_loop()

    assert websocket.sent == [[{'id': 'segment-1', 'text': 'Hello'}]]
    assert delivered == [True]
    assert flushed == ['conversation-1']


@pytest.mark.anyio
async def test_transcript_loop_still_flushes_speaker_assignments_when_the_client_socket_is_closed(monkeypatch):
    """A send after close must not kill the loop before its final speaker flush.

    Starlette answers a send on a closed socket with RuntimeError. That escaped the
    lifetime task, so the tail of `process_loop` never ran and the session's
    speaker -> person assignments were never written to the conversation.
    """

    class ClosedWebSocket:
        def __init__(self):
            self.attempts = 0

        async def send_json(self, _payload):
            self.attempts += 1
            raise RuntimeError(
                "Unexpected ASGI message 'websocket.send', after sending 'websocket.close' "
                'or response already completed.'
            )

    websocket = ClosedWebSocket()
    processor, delivered, flushed = _transcript_processor_for_delivery(monkeypatch, websocket)

    await processor.process_loop()

    assert websocket.attempts == 1
    assert flushed == ['conversation-1']
    # Nothing reached the client, so the live-transcription attempt is not a success.
    assert delivered == []
    assert processor.host.state.active is False


@pytest.mark.anyio
async def test_transcript_loop_emits_diarization_completion_after_terminal_flush(monkeypatch):
    from utils.product_telemetry import set_product_telemetry_client_for_tests

    websocket = SimpleNamespace(send_json=lambda _payload: _async_result(None))
    processor, _delivered, flushed = _transcript_processor_for_delivery(monkeypatch, websocket)
    processor.segment_buffer[0]['speaker_id'] = 2
    processor.host.recording_session_id = 'recording-1'
    telemetry = _ProductTelemetryClient()
    set_product_telemetry_client_for_tests(telemetry)

    await processor.process_loop()

    assert flushed == ['conversation-1']
    assert telemetry.events[0]['event'] == 'Diarization Completed'
    assert telemetry.events[0]['properties']['speaker_count'] == 1
    assert telemetry.events[0]['properties']['recording_id'] == 'recording-1'
    assert telemetry.events[0]['properties']['conversation_id'] == 'conversation-1'


@pytest.mark.anyio
async def test_transcript_loop_attributes_diarization_completion_to_each_conversation(monkeypatch):
    from utils.product_telemetry import set_product_telemetry_client_for_tests

    websocket = SimpleNamespace(send_json=lambda _payload: _async_result(None))
    processor, _delivered, _flushed = _transcript_processor_for_delivery(monkeypatch, websocket)
    processor.host.recording_session_id = 'recording-1'
    telemetry = _ProductTelemetryClient()
    set_product_telemetry_client_for_tests(telemetry)
    processor.segment_buffer[0]['speaker_id'] = 2
    waits = 0
    updates = 0

    async def wait(_seconds):
        nonlocal waits
        waits += 1
        if waits == 2:
            processor.host.state.active = False
        return False

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        nonlocal updates
        updates += 1
        if updates == 1:
            processor.host.state.current_conversation_id = 'conversation-2'
            processor.segment_buffer.append(
                {'id': 'segment-2', 'text': 'World', 'start': 1.0, 'end': 1.5, 'speaker_id': 3}
            )
        return SimpleNamespace(id=f'conversation-{updates}'), segments, []

    processor.host.wait = wait
    processor._update_live_conversation = update

    await processor.process_loop()

    assert [event['properties']['conversation_id'] for event in telemetry.events] == [
        'conversation-1',
        'conversation-2',
    ]
    assert [event['properties']['speaker_count'] for event in telemetry.events] == [1, 1]


async def _async_result(value):
    return value


@pytest.mark.anyio
async def test_custom_stt_flush_meters_speech_in_isolated_lane(monkeypatch):
    """#7690: a custom-STT session's speech reaches the fair-use meter under
    the custom_stt lane — and nothing else: no transcription usage recording,
    no realtime-lane write that live enforcement would read."""
    import routers.listen.runtime as runtime_module

    recorded = []
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', True)
    monkeypatch.setattr(
        runtime_module, 'record_speech_ms', lambda uid, ms, source='realtime': recorded.append((uid, ms, source))
    )
    monkeypatch.setattr(
        runtime_module, 'record_usage', lambda *a, **k: (_ for _ in ()).throw(AssertionError('billed custom STT'))
    )

    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='custom-stt-user')
    runtime.use_custom_stt = True
    runtime.persistence = _Persistence()
    runtime.state = SimpleNamespace(
        fair_use_track_dg_usage=False,
        dg_usage_ms_pending=0,
        last_usage_record_timestamp=123.0,
        words_transcribed_since_last_record=7,
        last_audio_received_time=124.0,
    )
    runtime.receiver = SimpleNamespace(vad_gate=SimpleNamespace(consume_speech_ms_delta=lambda: 4200))

    assert await runtime._flush_usage(final=False) == 0
    assert recorded == [('custom-stt-user', 4200, 'custom_stt')]

    # No speech delta → no meter write either.
    runtime.receiver = SimpleNamespace(vad_gate=SimpleNamespace(consume_speech_ms_delta=lambda: 0))
    assert await runtime._flush_usage(final=True) == 0
    assert recorded == [('custom-stt-user', 4200, 'custom_stt')]


def _heartbeat_runtime(send_text):
    from starlette.websockets import WebSocketState

    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(
        websocket=SimpleNamespace(client_state=WebSocketState.CONNECTED, send_text=send_text)
    )
    runtime.state = SimpleNamespace(active=True, last_activity_time=None)
    return runtime


@pytest.mark.anyio
async def test_heartbeat_treats_gone_peer_as_disconnect_not_crash():
    """A client that vanishes between the state read and the keepalive write ends the
    session as a disconnect; the heartbeat must not raise out of its supervised task."""
    from fastapi.websockets import WebSocketDisconnect

    async def send_text(_payload):
        raise WebSocketDisconnect()

    runtime = _heartbeat_runtime(send_text)
    await runtime._heartbeat()

    assert runtime.state.active is False


@pytest.mark.anyio
async def test_heartbeat_stops_after_close_message_instead_of_crashing():
    """The ASGI server refuses a send once the close frame went out — same disconnect."""

    async def send_text(_payload):
        raise RuntimeError('Cannot call "send" once a close message has been sent.')

    runtime = _heartbeat_runtime(send_text)
    await runtime._heartbeat()

    assert runtime.state.active is False
