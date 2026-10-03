"""STT_FAILOVER_RECOVERY_ENABLED: default-off inert gate for live STT failover recovery.

OFF must reproduce pinned main behavior (legacy receivers, plain asyncio.Queue
adapters, no recovery controller, no new metrics); ON retains the recovery
state machine. Session mode is pinned once at construction and never re-read.
"""

from __future__ import annotations

import asyncio
import collections
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.live_stt_recovery import (
    current_recovery_enabled,
    recovery_enabled,
    session_recovery_enabled,
)
from routers.listen import legacy_recovery
from routers.listen import receiver as receiver_module
from routers.listen.receiver import ListenReceiver
from routers.listen.runtime import ListenSessionRuntime
from tests.unit.test_live_session_transcript_outcome import _runtime
from utils.stt import connect_backoff as connect_backoff_module
from utils.stt import (
    legacy_replay,
    live_chain,
    live_failure,
    live_health,
    live_metrics,
    live_router,
    live_session,
    streaming,
)
from utils.stt.connect_backoff import ConnectRefusalBackoff
from utils.stt.live_chain import LiveChainExhausted
from utils.stt.live_health import FleetHealth
from utils.stt.live_failure import PendingLiveFailover
from utils.stt.live_outcome import LiveLegOutcome
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.recovery_state import LiveRecoveryController, current_recovery
from utils.stt.resilient_stream import (
    MAX_RECONNECTS,
    MAX_RECONNECTS_PER_MINUTE,
    ResilientAudio,
    socket_is_finishing,
)
from utils.stt.send_queue import AudioSendQueue
from utils.stt.soniox import SafeSonioxSocket, SonioxRateLimitError
from utils.stt.streaming import STTService, SafeModulateSocket
from utils.stt.vad_gate import GatedSTTSocket

ENV = 'STT_FAILOVER_RECOVERY_ENABLED'


@pytest.fixture(autouse=True)
def _isolated_stt_state(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'off')
    fleet = FleetHealth()
    for module in (live_health, live_chain, live_session, streaming):
        monkeypatch.setattr(module, 'health', fleet)
    monkeypatch.setattr(
        connect_backoff_module,
        '_shared',
        ConnectRefusalBackoff(on_event=live_chain._connect_backoff_event),
    )
    monkeypatch.setattr(live_chain, '_recent_connect_failures', collections.deque(maxlen=1000))
    monkeypatch.setattr(live_router, '_target_circuits', {})
    monkeypatch.setattr(live_router, '_capacity_until', {})
    for service, attribute in (
        (STTService.parakeet, '_parakeet_circuit'),
        (STTService.deepgram, '_deepgram_circuit'),
        (STTService.modulate, '_modulate_circuit'),
        (STTService.soniox, '_soniox_circuit'),
    ):
        monkeypatch.setattr(
            streaming,
            attribute,
            ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30, provider_label=service.value),
        )


@pytest.fixture(autouse=True)
def _unpinned_context():
    token = current_recovery_enabled.set(None)
    try:
        yield
    finally:
        current_recovery_enabled.reset(token)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _listen_host(**overrides):
    host = SimpleNamespace(
        is_multi_channel=False,
        use_custom_stt=False,
        request=SimpleNamespace(sample_rate=16000, websocket=AsyncMock(), uid='uid', codec='pcm16'),
        state=SimpleNamespace(active=True, stt_terminal_failure=False),
        vocabulary=[],
        stt_service=None,
        stt_language='en',
        stt_model=None,
        multi_lang_enabled=False,
        language_profile=None,
    )
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


def _receiver(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, flag)
    return ListenReceiver(_listen_host(), [SimpleNamespace()], {0: 0})


@pytest.mark.parametrize('value', [None, 'false', '1', 'yes', 'TRUE!', 'on'])
def test_flag_off_values(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, value)
    assert recovery_enabled() is False


@pytest.mark.parametrize('value', ['true', 'TRUE'])
def test_flag_true(monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    assert recovery_enabled() is True


def test_context_pin_overrides_env(monkeypatch):
    monkeypatch.setenv(ENV, 'true')
    token = current_recovery_enabled.set(False)
    try:
        assert recovery_enabled() is False
    finally:
        current_recovery_enabled.reset(token)


def test_session_helper_ignores_mock_truthiness(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    owner = MagicMock()
    owner.recovery_enabled = MagicMock()
    assert session_recovery_enabled(owner) is False
    pinned = SimpleNamespace(recovery_enabled=True)
    assert session_recovery_enabled(SimpleNamespace(receiver=pinned)) is True


def test_receiver_snapshot_off_survives_env_flip(monkeypatch):
    receiver = _receiver(monkeypatch, 'false')
    assert receiver.recovery_enabled is False
    assert receiver.recovery is None
    assert receiver._stt_recovery_exhausted is False
    monkeypatch.setenv(ENV, 'true')
    assert receiver.recovery_enabled is False
    assert receiver.recovery is None
    assert session_recovery_enabled(receiver) is False
    successor = _receiver(monkeypatch, 'true')
    assert successor.recovery_enabled is True
    assert isinstance(successor.recovery, LiveRecoveryController)


def test_receiver_snapshot_on_survives_env_flip(monkeypatch):
    receiver = _receiver(monkeypatch, 'true')
    assert receiver.recovery_enabled is True
    assert receiver.recovery is not None
    monkeypatch.delenv(ENV, raising=False)
    assert receiver.recovery_enabled is True
    assert receiver.recovery is not None
    assert session_recovery_enabled(receiver) is True
    new_receiver = _receiver(monkeypatch, None)
    assert new_receiver.recovery_enabled is False
    assert new_receiver.recovery is None


def _runtime_request():
    return SimpleNamespace(
        codec='pcm16',
        client_conversation_id=None,
        client_device_context='test-device',
        websocket=SimpleNamespace(headers={}),
        custom_stt_mode=SimpleNamespace(value='disabled'),
        channels=1,
        language='en',
        conversation_timeout=None,
        uid='test-uid',
        source='phone_call',
    )


def test_runtime_pin_survives_delayed_build(monkeypatch):
    monkeypatch.setenv(ENV, 'true')
    runtime = ListenSessionRuntime(_runtime_request())
    assert runtime.recovery_enabled is True
    monkeypatch.delenv(ENV, raising=False)
    assert session_recovery_enabled(runtime) is True
    runtime._build_components()
    assert runtime.receiver.recovery_enabled is True
    assert runtime.receiver.recovery is not None
    monkeypatch.setenv(ENV, 'false')
    runtime_off = ListenSessionRuntime(_runtime_request())
    monkeypatch.setenv(ENV, 'true')
    assert runtime_off.recovery_enabled is False
    assert session_recovery_enabled(runtime_off) is False
    runtime_off._build_components()
    assert runtime_off.receiver.recovery_enabled is False
    assert runtime_off.receiver.recovery is None


@pytest.mark.anyio
async def test_run_context_resets_on_cancellation(monkeypatch):
    monkeypatch.setenv(ENV, 'true')
    runtime = ListenSessionRuntime(_runtime_request())

    async def boom():
        assert current_recovery_enabled.get() is True
        raise asyncio.CancelledError()

    runtime._run = boom
    with pytest.raises(asyncio.CancelledError):
        await runtime.run()
    assert current_recovery_enabled.get() is None


@pytest.mark.anyio
async def test_off_raw_paid_queues_are_plain_asyncio(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    loop = asyncio.get_running_loop()
    ws = AsyncMock()
    for cls in (SafeModulateSocket, SafeSonioxSocket):
        socket = cls(ws, lambda _segments: None, loop)
        try:
            assert type(socket._send_queue) is asyncio.Queue
            assert socket._send_queue.maxsize == 2000
            socket.enable_writer_pacing(16000, 1.0)
            assert socket._writer_pace is None
        finally:
            socket._recv_task.cancel()
            socket._send_task.cancel()
            await asyncio.gather(socket._recv_task, socket._send_task, return_exceptions=True)


@pytest.mark.anyio
async def test_on_raw_paid_queues_use_send_queue_and_pacing(monkeypatch):
    monkeypatch.setenv(ENV, 'true')
    loop = asyncio.get_running_loop()
    ws = AsyncMock()
    for cls in (SafeModulateSocket, SafeSonioxSocket):
        socket = cls(ws, lambda _segments: None, loop)
        try:
            assert isinstance(socket._send_queue, AudioSendQueue)
            socket.enable_writer_pacing(16000, 1.0)
            assert socket._writer_pace is not None
        finally:
            socket._recv_task.cancel()
            socket._send_task.cancel()
            await asyncio.gather(socket._recv_task, socket._send_task, return_exceptions=True)


class _FakeModulateWS:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    def __aiter__(self):
        async def gen():
            await asyncio.Event().wait()
            yield b''

        return gen()

    async def send(self, data: Any) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        pass


@pytest.mark.anyio
async def test_off_finalize_eos_send_order(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    loop = asyncio.get_running_loop()
    ws = _FakeModulateWS()
    socket = SafeModulateSocket(ws, lambda _segments: None, loop)
    try:
        assert socket.send(b'\x01\x02') is True
        socket._send_queue.put_nowait(b'__EOS__')
        await asyncio.wait_for(socket._send_task, timeout=2)
        assert ws.sent == [b'\x01\x02', '']
    finally:
        socket._recv_task.cancel()
        await asyncio.gather(socket._recv_task, return_exceptions=True)


@pytest.mark.anyio
async def test_spawned_writer_inherits_pinned_off(monkeypatch):
    monkeypatch.setenv(ENV, 'true')
    token = current_recovery_enabled.set(False)
    loop = asyncio.get_running_loop()
    try:
        socket = SafeSonioxSocket(AsyncMock(), lambda _segments: None, loop)
    finally:
        current_recovery_enabled.reset(token)
    try:
        assert type(socket._send_queue) is asyncio.Queue
        assert socket.recovery_enabled is False
    finally:
        socket._recv_task.cancel()
        socket._send_task.cancel()
        await asyncio.gather(socket._recv_task, socket._send_task, return_exceptions=True)


@pytest.mark.anyio
async def test_off_429_records_failure_on_releases(monkeypatch):
    """OFF: a 429 typed rejection keeps main's circuit semantics (record_failure)."""
    monkeypatch.delenv(ENV, raising=False)
    circuit = streaming._circuit_for_primary(STTService.modulate)
    recorded: list[bool] = []
    released: list[bool] = []
    monkeypatch.setattr(circuit, 'record_failure', lambda: recorded.append(True))
    monkeypatch.setattr(circuit, 'release_probe', lambda: released.append(True))
    monkeypatch.setattr(circuit, 'allow_request', lambda **kw: True)

    socket = SimpleNamespace(
        is_connection_dead=True,
        death_reason='rate limited',
        typed_death_reason='provider_rate_limited',
    )

    async def connect():
        return socket

    with pytest.raises(Exception):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=connect,
            connect_parakeet=None,
            connect_soniox=None,
            connect_modulate=None,
            connect_deepgram=None,
            use_config=False,
        )
    assert released == []
    assert recorded == [True]


@pytest.mark.anyio
async def test_on_429_releases_probe(monkeypatch):
    monkeypatch.setenv(ENV, 'true')
    circuit = streaming._circuit_for_primary(STTService.modulate)
    recorded: list[bool] = []
    released: list[bool] = []
    monkeypatch.setattr(circuit, 'record_failure', lambda: recorded.append(True))
    monkeypatch.setattr(circuit, 'release_probe', lambda: released.append(True))
    monkeypatch.setattr(circuit, 'allow_request', lambda **kw: True)

    socket = SimpleNamespace(
        is_connection_dead=True,
        death_reason='rate limited',
        typed_death_reason='provider_rate_limited',
    )

    async def connect():
        return socket

    with pytest.raises(Exception):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=connect,
            connect_parakeet=None,
            connect_soniox=None,
            connect_modulate=None,
            connect_deepgram=None,
            use_config=False,
        )
    assert released == [True]
    assert recorded == []


def test_off_strict_capture_cap_135(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    ring = ResilientAudio(16000, ring_seconds=90, strict_replay=True, recovery_enabled=False)
    for _ in range(10):
        ring.reserve_replacement_headroom()
    assert ring.ring_seconds == 135


def test_on_capture_cap_150(monkeypatch):
    monkeypatch.setenv(ENV, 'true')
    ring = ResilientAudio(16000, ring_seconds=90, strict_replay=True, recovery_enabled=True)
    for _ in range(10):
        ring.reserve_replacement_headroom()
    assert ring.ring_seconds == 150


def test_off_reconnect_budgets(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    ring = ResilientAudio(16000, recovery_enabled=False)
    attempts = [ring.admit('soniox', 'connection_lost', samples=1) for _ in range(4)]
    assert attempts == [True, True] + [False] * 2
    aged = ResilientAudio(16000, recovery_enabled=False)
    now = time.monotonic()
    aged._attempts = collections.deque([now - 120, now - 90])
    aged._total_attempts = MAX_RECONNECTS
    assert aged.admit('soniox', 'connection_lost', samples=1) is False
    replay_limited = ResilientAudio(16000, recovery_enabled=False)
    assert replay_limited.admit('soniox', 'connection_lost', samples=31 * 16000) is False
    assert MAX_RECONNECTS_PER_MINUTE == 2


def test_pending_departing_exhausted_off_degraded_on(monkeypatch):
    emitted: list[str] = []
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **kw: emitted.append(kw['outcome']))

    monkeypatch.delenv(ENV, raising=False)
    outcome = LiveLegOutcome('t', 'en', None, None, lambda *a: True)
    outcome.recovery_enabled = False
    pending = PendingLiveFailover(from_mode='a', to_mode='b', reason='x', source_outcome=outcome)
    outcome.owner_closing = True
    pending.note_failure(None)
    assert emitted == ['exhausted']

    monkeypatch.setenv(ENV, 'true')
    emitted.clear()
    outcome = LiveLegOutcome('t', 'en', None, None, lambda *a: True)
    outcome.recovery_enabled = True
    pending = PendingLiveFailover(from_mode='a', to_mode='b', reason='x', source_outcome=outcome)
    outcome.owner_closing = True
    pending.note_failure(None)
    assert emitted == ['degraded']


def test_managed_finishing_fence_same_both_modes():
    managed = SimpleNamespace(
        leg_outcome=SimpleNamespace(owner_closing=True),
        _finishing=False,
        _conn=None,
        raw=None,
    )
    assert socket_is_finishing(managed) is True
    managed_cleanup = SimpleNamespace(
        leg_outcome=SimpleNamespace(owner_closing=False),
        _finishing=False,
        _conn=None,
        raw=SimpleNamespace(leg_outcome=None, _finishing=True, _conn=None, raw=None),
    )
    assert socket_is_finishing(managed_cleanup) is False


def test_unmanaged_finishing_differs(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    off_socket = SimpleNamespace(leg_outcome=None, _finishing=True, _conn=None, raw=None, recovery_enabled=False)
    assert socket_is_finishing(off_socket) is True
    on_socket = SimpleNamespace(leg_outcome=None, _finishing=True, _conn=None, raw=None, recovery_enabled=True)
    assert socket_is_finishing(on_socket) is False
    assert socket_is_finishing(on_socket, include_unmanaged_finishing=True) is True


@pytest.mark.anyio
async def test_off_replay_emits_only_baseline_metrics(monkeypatch):

    monkeypatch.delenv(ENV, raising=False)
    replay_audio = live_metrics.REPLAY_AUDIO.labels(source='soniox', successor='soniox')._value.get()
    replay_seconds = live_metrics.REPLAY_SECONDS.labels(provider='soniox')._value.get()
    ring = ResilientAudio(16000, recovery_enabled=False)
    chunk = bytes(3200)
    ring.append(chunk, 0)
    socket = SimpleNamespace(
        is_connection_dead=False,
        send=lambda data, start_sample=None: True,
    )
    rejected = legacy_replay.replay_chunks(socket, ring.snapshot(), source=ring, provider='soniox', soniox=None)
    assert rejected is None
    assert live_metrics.REPLAY_AUDIO.labels(source='soniox', successor='soniox')._value.get() == replay_audio
    assert live_metrics.REPLAY_SECONDS.labels(provider='soniox')._value.get() == pytest.approx(replay_seconds + 0.1)


def test_off_receiver_dispatch_uses_legacy(monkeypatch):
    receiver = _receiver(monkeypatch, 'false')
    assert receiver.recovery is None
    dispatched: list[str] = []

    async def legacy(self, *a, **k):
        dispatched.append('legacy')
        return True

    monkeypatch.setattr(legacy_recovery, 'failover_stt_socket', legacy)
    asyncio.run(receiver._failover_stt_socket())
    assert dispatched == ['legacy']


@pytest.mark.parametrize('value,expected', [(None, 135), ('false', 135), ('true', 150)])
def test_default_pin_constructor_headroom(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, value)
    ring = ResilientAudio(16000, ring_seconds=90, strict_replay=True)
    for _ in range(10):
        ring.reserve_replacement_headroom()
    assert ring.ring_seconds == expected


def test_default_pin_survives_env_flip(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    ring_off = ResilientAudio(16000, ring_seconds=90, strict_replay=True)
    monkeypatch.setenv(ENV, 'true')
    for _ in range(10):
        ring_off.reserve_replacement_headroom()
    assert ring_off._recovery_enabled is False
    assert ring_off.ring_seconds == 135
    ring_on = ResilientAudio(16000, ring_seconds=90, strict_replay=True)
    monkeypatch.delenv(ENV, raising=False)
    for _ in range(10):
        ring_on.reserve_replacement_headroom()
    assert ring_on._recovery_enabled is True
    assert ring_on.ring_seconds == 150


class _CapacitySocket:
    def __init__(self, *, recovery=None):
        self.calls: list[tuple[Any, Any]] = []
        if recovery is not None:
            self.recovery_enabled = recovery

    @property
    def is_connection_dead(self):
        return False

    @property
    def death_reason(self):
        return None

    async def wait_send_capacity(self, limit=None, timeout=None):
        self.calls.append((limit, timeout))
        return True


@pytest.mark.anyio
async def test_gated_wait_capacity_pinned_both_directions(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    off_inner = _CapacitySocket()
    off_gated = GatedSTTSocket(off_inner)
    monkeypatch.setenv(ENV, 'true')
    assert await off_gated.wait_send_capacity(limit=5, timeout=1.0) is True
    assert off_inner.calls == []

    on_inner = _CapacitySocket()
    on_gated = GatedSTTSocket(on_inner)
    monkeypatch.delenv(ENV, raising=False)
    assert await on_gated.wait_send_capacity(limit=5, timeout=1.0) is True
    assert on_inner.calls == [(5, 1.0)]

    monkeypatch.delenv(ENV, raising=False)
    pinned_inner = _CapacitySocket(recovery=True)
    pinned_gated = GatedSTTSocket(pinned_inner)
    assert await pinned_gated.wait_send_capacity(limit=7, timeout=2.0) is True
    assert pinned_inner.calls == [(7, 2.0)]


class _FlagFakeSocket:
    def __init__(self, *, dead=False, recovery=None):
        self.dead = dead
        self.finished = False
        self.sent: list[bytes] = []
        if recovery is not None:
            self.recovery_enabled = recovery

    @property
    def is_connection_dead(self):
        return self.dead

    @property
    def death_reason(self):
        return 'ws closed' if self.dead else None

    @property
    def typed_death_reason(self):
        return 'connection_lost' if self.dead else None

    def send(self, data, start_sample=None):
        self.sent.append(data)
        return True

    def finalize(self):
        pass

    def finish(self):
        self.finished = True


def _soniox_failover_receiver(monkeypatch, flag):
    receiver = _receiver(monkeypatch, flag)
    receiver.host.stt_service = STTService.soniox
    ring = ResilientAudio(16000, recovery_enabled=receiver.recovery_enabled)
    ring.append(bytes(3200), 0)
    receiver._resilient_audio = ring
    receiver._window_replay_audio = ring
    receiver._window_replay_started = True
    receiver._pending_live_failover = None
    receiver.stt_socket = _FlagFakeSocket(dead=True)
    receiver._stt_rebuild = (lambda: (None, None, None), 16000)

    async def _no_reconnect():
        return False

    monkeypatch.setattr(receiver, '_reconnect_stt_socket_locked', _no_reconnect)
    monkeypatch.setattr(
        receiver_module,
        'select_live_replacement',
        lambda *a, **k: (STTService.parakeet, 'en', 'parakeet'),
    )
    monkeypatch.setattr(receiver_module, 'managed_chain_enabled', lambda _host: False)
    monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    return receiver


def _metric_totals():
    metrics = {
        'replay_wall': live_metrics.REPLAY_WALL,
        'replay_audio': live_metrics.REPLAY_AUDIO,
        'replay_queue': live_metrics.REPLAY_QUEUE_HIGH_WATER,
        'replay_skipped': live_metrics.REPLAY_SKIPPED,
        'replay_closed': live_metrics.REPLAY_CLOSED,
        'recovery_attempts': live_metrics.RECOVERY_ATTEMPTS,
        'connect_backoff': live_metrics.CONNECT_BACKOFF,
    }
    return {
        name: sum(
            sample.value
            for family in metric.collect()
            for sample in family.samples
            if not sample.name.endswith('_created')
        )
        for name, metric in metrics.items()
    }


@pytest.mark.anyio
async def test_off_receiver_failover_replay_emits_only_baseline_metrics(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    receiver = _soniox_failover_receiver(monkeypatch, 'false')
    replacement = _FlagFakeSocket()

    async def _create(*_args, **_kwargs):
        return replacement

    monkeypatch.setattr(receiver, '_create_stt_socket', _create)
    replay_seconds = live_metrics.REPLAY_SECONDS.labels(provider='soniox')._value.get()
    before = _metric_totals()
    assert await receiver._failover_stt_socket() is True
    assert _metric_totals() == before
    assert live_metrics.REPLAY_SECONDS.labels(provider='soniox')._value.get() == pytest.approx(replay_seconds + 0.1)
    assert receiver.stt_socket is replacement
    assert replacement.sent == [bytes(3200)]


@pytest.mark.anyio
async def test_create_stt_socket_context_pins_and_resets(monkeypatch):
    observations: list[tuple[str, bool | None]] = []
    loop = asyncio.get_running_loop()

    async def fake_connect(self, callback, sample_rate, **kwargs):
        observations.append(('entry', current_recovery_enabled.get()))

        async def probe():
            observations.append(('task', current_recovery_enabled.get()))

        await asyncio.create_task(probe())
        socket = SafeSonioxSocket(AsyncMock(), lambda _segments: None, loop)
        observations.append(('socket', socket.recovery_enabled))
        return socket

    monkeypatch.setattr(ListenReceiver, '_connect_stt_socket', fake_connect)

    receiver_off = _receiver(monkeypatch, 'false')
    monkeypatch.setenv(ENV, 'true')
    socket = await receiver_off._create_stt_socket(None, 16000)
    assert observations[-3:] == [('entry', False), ('task', False), ('socket', False)]
    assert type(socket._send_queue) is asyncio.Queue
    assert current_recovery_enabled.get() is None
    socket._recv_task.cancel()
    socket._send_task.cancel()
    await asyncio.gather(socket._recv_task, socket._send_task, return_exceptions=True)

    observations.clear()
    monkeypatch.delenv(ENV, raising=False)
    receiver_on = _receiver(monkeypatch, 'true')
    monkeypatch.delenv(ENV, raising=False)
    socket = await receiver_on._create_stt_socket(None, 16000)
    assert observations[-3:] == [('entry', True), ('task', True), ('socket', True)]
    assert isinstance(socket._send_queue, AudioSendQueue)
    assert current_recovery_enabled.get() is None
    socket._recv_task.cancel()
    socket._send_task.cancel()
    await asyncio.gather(socket._recv_task, socket._send_task, return_exceptions=True)

    async def boom(self, *args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(ListenReceiver, '_connect_stt_socket', boom)
    with pytest.raises(asyncio.CancelledError):
        await receiver_on._create_stt_socket(None, 16000)
    assert current_recovery_enabled.get() is None


@pytest.mark.anyio
async def test_configured_chain_429_breaker_semantics(monkeypatch):
    breaker_off = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    monkeypatch.setattr(streaming, '_circuit_for_primary', lambda _service: breaker_off)
    monkeypatch.delenv(ENV, raising=False)

    async def fail():
        raise SonioxRateLimitError('transient 429')

    with pytest.raises(RuntimeError, match='Configured STT chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=STTService.soniox,
            connect_primary=fail,
            callbacks={STTService.soniox: fail},
            failed=set(),
            models=['soniox'],
        )
    assert breaker_off.state == 'open'

    breaker_on = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    monkeypatch.setattr(streaming, '_circuit_for_primary', lambda _service: breaker_on)
    monkeypatch.setenv(ENV, 'true')
    with pytest.raises(LiveChainExhausted):
        await live_chain.connect_configured_chain(
            primary_service=STTService.soniox,
            connect_primary=fail,
            callbacks={STTService.soniox: fail},
            failed=set(),
            models=['soniox'],
        )
    assert breaker_on.state == 'closed'


@pytest.mark.anyio
async def test_off_chain_429_walks_to_capable_provider_without_backoff(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)

    def _boom(*_args, **_kwargs):
        raise AssertionError('connect backoff acquire called while recovery disabled')

    monkeypatch.setattr(connect_backoff_module.connect_backoff(), 'acquire', _boom)
    backoff_before = _metric_totals()['connect_backoff']

    async def fail():
        raise SonioxRateLimitError('transient 429')

    async def ok():
        return _FlagFakeSocket()

    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    socket, service = await live_chain.connect_configured_chain(
        primary_service=STTService.soniox,
        connect_primary=fail,
        callbacks={STTService.soniox: fail, STTService.parakeet: ok},
        failed=set(),
        models=['soniox', 'parakeet'],
    )
    assert service == STTService.parakeet
    assert _metric_totals()['connect_backoff'] == backoff_before


def test_terminal_after_text_gated_by_pin(monkeypatch):
    counter = live_metrics.LIVE_SESSION_TERMINAL_AFTER_TEXT.labels(provider='soniox')
    before = counter._value.get()
    monkeypatch.delenv(ENV, raising=False)
    runtime_off = _runtime(delivered=True, terminal=True)
    runtime_off.recovery_enabled = False
    runtime_off.stt_service = STTService.soniox
    ListenSessionRuntime._record_session_transcript_outcome(runtime_off)
    assert counter._value.get() == before
    runtime_on = _runtime(delivered=True, terminal=True)
    runtime_on.recovery_enabled = True
    runtime_on.stt_service = STTService.soniox
    ListenSessionRuntime._record_session_transcript_outcome(runtime_on)
    assert counter._value.get() == before + 1


@pytest.mark.anyio
@pytest.mark.parametrize('enabled', [False, True])
async def test_create_stt_socket_pins_missing_mode_once(monkeypatch, enabled):
    receiver = object.__new__(ListenReceiver)
    receiver.host = _listen_host()
    seen: list[bool | None] = []

    async def fake_connect(self, callback, sample_rate, **kwargs):
        seen.append(current_recovery_enabled.get())
        assert current_recovery.get() is None
        return _FlagFakeSocket()

    monkeypatch.setattr(ListenReceiver, '_connect_stt_socket', fake_connect)
    monkeypatch.setenv(ENV, 'true' if enabled else 'false')
    first = await receiver._create_stt_socket(None, 16000)
    assert receiver.recovery_enabled is enabled
    monkeypatch.setenv(ENV, 'false' if enabled else 'true')
    second = await receiver._create_stt_socket(None, 16000)
    assert receiver.recovery_enabled is enabled
    assert seen == [enabled, enabled]
    assert isinstance(first, _FlagFakeSocket) and isinstance(second, _FlagFakeSocket)
    assert current_recovery_enabled.get() is None
    assert current_recovery.get() is None


@pytest.mark.anyio
@pytest.mark.parametrize('pinned', [False, True])
async def test_run_pins_missing_mode_from_receiver_and_resets(monkeypatch, pinned):
    monkeypatch.setenv(ENV, 'false' if pinned else 'true')
    runtime = object.__new__(ListenSessionRuntime)
    runtime.receiver = SimpleNamespace(recovery_enabled=pinned)
    seen: list[bool | None] = []

    async def stub(self):
        seen.append(current_recovery_enabled.get())
        raise asyncio.CancelledError()

    monkeypatch.setattr(ListenSessionRuntime, '_run', stub)
    with pytest.raises(asyncio.CancelledError):
        await runtime.run()
    assert runtime.recovery_enabled is pinned
    assert seen == [pinned]
    assert current_recovery_enabled.get() is None


_RECOVERY_SERIES_PROBE = (
    'from prometheus_client import REGISTRY\n'
    'import utils.stt.live_metrics  # noqa: F401\n'
    "print(sum(1 for m in REGISTRY.collect() if m.name == 'omi_stt_replay_wall_seconds' for _ in m.samples))\n"
)


@pytest.mark.parametrize('value, expect_series', [(None, False), ('false', False), ('true', True)])
def test_recovery_series_zero_filled_only_when_flag_on(value, expect_series):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {k: v for k, v in os.environ.items() if k != 'STT_FAILOVER_RECOVERY_ENABLED'}
    if value is not None:
        env['STT_FAILOVER_RECOVERY_ENABLED'] = value
    out = subprocess.run(
        [sys.executable, '-c', _RECOVERY_SERIES_PROBE],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert (int(out.stdout.strip()) > 0) is expect_series
