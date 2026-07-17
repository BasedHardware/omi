"""Behavioral regression coverage for the extracted listen runtime."""

from types import SimpleNamespace

import pytest

from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from utils.listen_session_bootstrap import ListenConnectBase


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
    monkeypatch.setattr(runtime_module, 'check_soft_caps', lambda _uid, *, speech_totals: caps)
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

    def select_stt(language, *, multi_lang_enabled, prefer_parakeet=False):
        selected_multi_language_options.append((language, multi_lang_enabled, prefer_parakeet))
        return 'test-stt', 'es', 'test-model'

    monkeypatch.setattr(runtime_module, 'load_listen_connect_base', lambda *_args, **_kwargs: _async_result(base))
    monkeypatch.setattr(runtime_module, 'get_stt_service_for_language', select_stt)
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'should_load_speech_profile', lambda **_kwargs: False)
    monkeypatch.setattr(runtime_module, 'should_enable_speaker_identification', lambda **_kwargs: False)
    monkeypatch.setattr(runtime_module, 'OnboardingHandler', lambda *_args: SimpleNamespace())

    assert await runtime._bootstrap() is True
    assert selected_multi_language_options == [('es', False, False)]


def test_runtime_emits_speaker_suggestion_event():
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(speaker_auto_assign_enabled=True)
    emitted_events = []
    runtime.send_event = emitted_events.append

    runtime.emit_speaker_suggestion(4, 'person-123', 'Avery', 'segment-123')

    assert emitted_events[0].event_type == 'speaker_label_suggestion'
    assert emitted_events[0].speaker_id == 4
    assert emitted_events[0].person_name == 'Avery'


async def _async_result(value):
    return value
