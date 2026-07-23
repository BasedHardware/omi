"""Behavioral regression coverage for the extracted listen runtime."""

import asyncio
from collections import deque
from types import SimpleNamespace

import pytest

from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from routers.listen.transcripts import TranscriptProcessor
from utils.listen_session_bootstrap import ListenConnectBase
from utils.stt.streaming import STTService


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _Persistence:
    async def call(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


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
    monkeypatch.setattr(runtime_module, 'get_stt_service_for_language', select_stt)
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'should_load_speech_profile', lambda **_kwargs: False)
    monkeypatch.setattr(runtime_module, 'should_enable_speaker_identification', lambda **_kwargs: False)
    monkeypatch.setattr(runtime_module, 'OnboardingHandler', lambda *_args: SimpleNamespace())

    assert await runtime._bootstrap() is True
    assert selected_multi_language_options == [('es', False, None)]


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


def test_runtime_emits_speaker_suggestion_event():
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(speaker_auto_assign_enabled=True)
    emitted_events = []
    runtime.send_event = emitted_events.append

    runtime.emit_speaker_suggestion(4, 'person-123', 'Avery', 'segment-123')

    assert emitted_events[0].event_type == 'speaker_label_suggestion'
    assert emitted_events[0].speaker_id == 4
    assert emitted_events[0].person_name == 'Avery'


class _JourneyAttempt:
    instances = []

    def __init__(self, journey):
        self.journey = journey
        self.finished = False
        self.outcomes = []
        self.__class__.instances.append(self)

    def finish(self, outcome):
        if self.finished:
            return
        self.finished = True
        self.outcomes.append(outcome)


def _live_transcription_runtime(*, close_code=1001, stt_terminal_failure=False, live_transcription_failed=False):
    runtime = object.__new__(ListenSessionRuntime)
    runtime.state = SimpleNamespace(
        close_code=close_code,
        stt_terminal_failure=stt_terminal_failure,
        live_transcription_failed=live_transcription_failed,
        live_transcription_attempt=None,
    )
    return runtime


def test_live_transcription_journey_starts_once_and_success_wins_over_teardown(monkeypatch):
    import routers.listen.runtime as runtime_module

    _JourneyAttempt.instances = []
    monkeypatch.setattr(runtime_module, 'JourneyAttempt', _JourneyAttempt)
    runtime = _live_transcription_runtime(close_code=1011, stt_terminal_failure=True)

    runtime.start_live_transcription()
    runtime.start_live_transcription()
    runtime.complete_live_transcription()
    runtime._finish_live_transcription()

    assert len(_JourneyAttempt.instances) == 1
    assert _JourneyAttempt.instances[0].journey == 'live_transcription'
    assert _JourneyAttempt.instances[0].outcomes == ['success']


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

    _JourneyAttempt.instances = []
    monkeypatch.setattr(runtime_module, 'JourneyAttempt', _JourneyAttempt)
    runtime = _live_transcription_runtime(
        close_code=close_code,
        stt_terminal_failure=stt_terminal_failure,
        live_transcription_failed=live_transcription_failed,
    )

    runtime.start_live_transcription()
    runtime._finish_live_transcription()
    runtime._finish_live_transcription()

    assert _JourneyAttempt.instances[0].outcomes == [expected]


@pytest.mark.anyio
async def test_transcript_delivery_marks_live_transcription_success_only_after_a_nonempty_client_send(monkeypatch):
    import routers.listen.transcripts as transcripts_module

    class Segment:
        def __init__(self, **data):
            self.id = data['id']
            self.text = data['text']
            self.start = data['start']
            self.end = data['end']
            self.speech_profile_processed = data['speech_profile_processed']
            self.is_user = False

        def model_dump(self):
            return {'id': self.id, 'text': self.text}

        @staticmethod
        def combine_segments(_existing, new_segments):
            return new_segments, [], []

    class WebSocket:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    state = SimpleNamespace(
        active=True,
        first_audio_byte_timestamp=100.0,
        last_transcript_time=None,
        words_transcribed_since_last_record=0,
        current_conversation_id='conversation-1',
        speaker_id_done=asyncio.Event(),
    )
    state.speaker_id_done.set()
    websocket = WebSocket()
    delivered = []

    async def wait(_seconds):
        state.active = False
        return False

    async def cache_get(_conversation_id):
        return {'transcript_segments': []}

    async def update(_conversation, segments, _photos, _finished_at, _started_at):
        return SimpleNamespace(id='conversation-1'), segments, []

    async def no_op(*_args, **_kwargs):
        return None

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
    processor._update_live_conversation = update
    processor._translate = no_op
    processor._speaker_detection = no_op
    processor.flush_speaker_assignments = no_op

    monkeypatch.setattr(transcripts_module, 'TranscriptSegment', Segment)
    monkeypatch.setattr(transcripts_module, 'deserialize_conversation', lambda _data: SimpleNamespace())

    await processor.process_loop()

    assert websocket.sent == [[{'id': 'segment-1', 'text': 'Hello'}]]
    assert delivered == [True]


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
