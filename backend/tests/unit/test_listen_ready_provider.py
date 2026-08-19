"""Regression (#11306): the live-STT `ready` event must name the provider serving.

The backend emitted a bare ``MessageServiceStatusEvent(status='ready')`` as soon as
the provider socket opened. ``_create_stt_socket`` can walk the fallback chain
(#11695, #11752), so "Listening" could equally mean the Parakeet session the user
selected or a Modulate/Deepgram fallback socket that is about to die — the client
clears its terminal-failure state on ``ready`` and cannot tell the two apart.

These tests drive the real ``run()`` sequence with the vendor connect functions
stubbed, so the fallback the event has to report is produced by the production
chain rather than asserted about.
"""

import asyncio
import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from routers.listen import receiver as receiver_mod
from routers.listen.contracts import ListenRequest, ListenSessionState
from routers.listen.receiver import ListenReceiver
from routers.listen.runtime import ListenSessionRuntime
from utils.stt import provider_resilience, streaming
from utils.stt.streaming import STTService


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@contextmanager
def _serving_policy(models=('modulate-velma-2', 'dg-nova-3', 'parakeet')):
    """Drive the real provider gates off ``STT_SERVICE_MODELS``, not a stubbed answer."""
    with (
        patch.object(streaming, 'stt_service_models', list(models)),
        patch.object(streaming, '_deepgram_is_available', return_value=True),
        patch.dict(os.environ, {'HOSTED_PARAKEET_API_URL': 'ws://parakeet.omi.me/v3/stream'}),
    ):
        yield


class _RejectedSocket:
    """Velma's over-quota shape: the upgrade succeeds, then the stream is refused."""

    def __init__(self) -> None:
        self.death_reason = 'modulate error: Monthly usage limit reached.'
        self.finished = False

    @property
    def is_connection_dead(self) -> bool:
        return True

    def finish(self) -> None:
        self.finished = True


def _live_socket():
    return SimpleNamespace(is_connection_dead=False, death_reason=None, finish=lambda: None)


async def _idle():
    return None


def _runtime_for_ready(*, selected=STTService.modulate, custom_stt=False):
    """A runtime wired with the real receiver, stubbed only outside the STT path."""
    request = ListenRequest(
        websocket=SimpleNamespace(),
        uid='ready-user',
        codec='pcm8',
        sample_rate=16000,
    )
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = request
    runtime.state = ListenSessionState()
    runtime.session_id = 'ready-session'
    runtime.use_custom_stt = custom_stt
    runtime.is_multi_channel = False
    runtime.language = 'en'
    runtime.stt_service = selected
    runtime.stt_service_selected = selected
    runtime.stt_language = 'en'
    runtime.stt_model = 'velma-2'
    runtime.vocabulary = []
    runtime.client_device_context = SimpleNamespace(platform='ios')
    runtime.limits = SimpleNamespace(bg_drain_timeout=5.0)
    runtime.pusher_tasks = []

    events = []
    runtime.send_event = events.append

    async def asend_event(event):
        events.append(event)
        return True

    runtime.asend_event = asend_event
    runtime.emitted_events = events

    runtime._admit = AsyncMock(return_value=True)
    runtime._bootstrap = AsyncMock(return_value=True)
    runtime._start_pusher = AsyncMock()
    runtime._teardown = AsyncMock()
    runtime._heartbeat = _idle
    runtime._record_usage_periodically = _idle

    runtime.conversations = SimpleNamespace(
        send_last_conversation=AsyncMock(),
        prepare=AsyncMock(return_value=False),
        lifecycle_loop=_idle,
        process_pending=lambda *_args: _idle(),
    )
    runtime.transcripts = SimpleNamespace(process_loop=_idle)
    runtime.speakers = SimpleNamespace(load_and_run=_idle)

    def create_task(coro, *, name, **_kwargs):
        return asyncio.ensure_future(coro)

    async def supervise(*, receive_task):
        await receive_task
        return SimpleNamespace(reason='client_disconnect')

    runtime.task_supervisor = SimpleNamespace(
        start_session=lambda: None,
        create_task=create_task,
        create_lifetime_task=create_task,
        create_finite_task=create_task,
        supervise=supervise,
        drain_monitored=AsyncMock(return_value=0),
    )
    runtime.spawn = lambda coro, *, name: asyncio.ensure_future(coro)

    runtime.receiver = ListenReceiver(runtime, [], {})
    runtime.receiver.receive_data = _idle
    runtime.receiver._monitor_stt_death = _idle
    return runtime


def _ready_payload(runtime):
    ready = [event for event in runtime.emitted_events if getattr(event, 'status', None) == 'ready']
    assert len(ready) == 1, f'expected exactly one ready event, got {len(ready)}'
    return ready[0].to_json()


async def _run_session(runtime, *, modulate_socket, dg_socket=None):
    with (
        _serving_policy(),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'is_gate_enabled', return_value=False),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=modulate_socket)),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=dg_socket)),
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock(return_value=None)),
        patch.object(streaming, 'record_fallback'),
    ):
        await runtime.run()


@pytest.mark.anyio
async def test_ready_names_the_fallback_provider_actually_serving():
    """The #11306 shape: Modulate takes the session, refuses it, Deepgram serves.

    ``ready`` must say ``deepgram`` — the provider on the other end of the socket
    the client is about to stream into — not the ``modulate`` the policy selected.
    """
    runtime = _runtime_for_ready(selected=STTService.modulate)

    await _run_session(runtime, modulate_socket=_RejectedSocket(), dg_socket=_live_socket())

    assert runtime.stt_service == STTService.deepgram, 'the fallback chain did not move the session'
    payload = _ready_payload(runtime)
    assert payload['provider'] == 'deepgram'
    assert payload['reason'] == 'fallback_from_modulate'


@pytest.mark.anyio
async def test_ready_on_a_healthy_selected_provider_carries_no_fallback_reason():
    """A session served by the selected provider must not look like a fallback."""
    runtime = _runtime_for_ready(selected=STTService.modulate)

    await _run_session(runtime, modulate_socket=_live_socket())

    payload = _ready_payload(runtime)
    assert payload['provider'] == 'modulate'
    assert 'reason' not in payload, 'a healthy session must not carry a fallback reason'


@pytest.mark.anyio
async def test_ready_claims_no_backend_provider_for_custom_stt_sessions():
    """Custom-STT clients own transcript production; no backend provider serves them."""
    runtime = _runtime_for_ready(selected=STTService.modulate, custom_stt=True)

    await _run_session(runtime, modulate_socket=_live_socket())

    payload = _ready_payload(runtime)
    assert 'provider' not in payload
    assert 'reason' not in payload


@pytest.mark.anyio
async def test_ready_stays_additive_for_clients_that_ignore_the_new_fields():
    """``exclude_none=True`` keeps the legacy payload shape intact."""
    runtime = _runtime_for_ready(selected=STTService.modulate)

    await _run_session(runtime, modulate_socket=_live_socket())

    payload = _ready_payload(runtime)
    assert payload['type'] == 'service_status'
    assert payload['status'] == 'ready'
    assert 'status_text' not in payload
    assert 'outcome' not in payload
    assert 'retryable' not in payload


def test_ready_provider_is_resolved_at_emission_time_not_at_selection():
    """Pin the accessor contract #11359 established for the terminal-failure path.

    A value read before ``_create_stt_socket`` returns attributes a fallback
    session to the provider that never served it.
    """
    runtime = _runtime_for_ready(selected=STTService.parakeet)

    assert runtime._ready_event().to_json()['provider'] == 'parakeet'

    runtime.stt_service = STTService.modulate  # what _create_stt_socket does on fallback

    payload = runtime._ready_event().to_json()
    assert payload['provider'] == 'modulate'
    assert payload['reason'] == 'fallback_from_parakeet'


@pytest.mark.anyio
async def test_bootstrap_records_the_selected_provider_for_fallback_comparison(monkeypatch):
    """``_bootstrap`` must keep the selected provider so ``ready`` can spot a fallback."""
    import routers.listen.runtime as runtime_module
    from utils.listen_session_bootstrap import ListenConnectBase

    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = ListenRequest(websocket=SimpleNamespace(), uid='select-user', stt_service='parakeet')
    runtime.use_custom_stt = False
    runtime.session_id = 'select-session'
    runtime.language = 'en'

    base = ListenConnectBase(
        user_exists=True,
        user_has_credits=True,
        transcription_prefs={'single_language_mode': False, 'uses_custom_stt': False},
        fair_use_init_stage=None,
        fair_use_track_dg_usage=False,
        fair_use_dg_budget_exhausted=False,
    )

    async def close(**_kwargs):
        raise AssertionError('bootstrap must not close the socket in this test')

    monkeypatch.setattr(runtime_module, 'load_listen_connect_base', lambda *_a, **_k: _resolved(base))
    monkeypatch.setattr(
        runtime_module,
        'get_stt_service_for_language',
        lambda *_a, **_k: (STTService.modulate, 'en', 'velma-2'),
    )
    monkeypatch.setattr(runtime_module, 'finalize_listen_connect_context', _stop_after_selection)

    with pytest.raises(_SelectionRecorded):
        await runtime._bootstrap()

    assert runtime.stt_service_selected == STTService.modulate


class _SelectionRecorded(Exception):
    """Stop `_bootstrap` once provider selection is done; the rest needs live IO."""


def _stop_after_selection(*_args, **_kwargs):
    raise _SelectionRecorded


def _resolved(value):
    async def _coro():
        return value

    return _coro()
