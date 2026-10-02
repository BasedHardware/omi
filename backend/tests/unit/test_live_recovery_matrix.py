"""Directed live-STT recovery matrix: every ordered provider pair x ring depth.

Fixture contract: the capture obligation is injected through
``_window_replay_audio`` — a controlled session fixture, not a claim that
every initial paid production source retains a ring. Shipped defaults (20s
prefix wall / 60s episode / 28s live residence) are restored explicitly so an
autouse override elsewhere cannot leak into the ordinary qualification.
"""

import asyncio

import pytest
from starlette.websockets import WebSocketState
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401

from tests.unit.test_live_cost_router import controls  # noqa: F401
from tests.unit.test_parakeet_window_live import Client, runtime, window  # noqa: F401
from tests.unit.test_live_replay_provider_pairs import (
    SafeModulateSocket,
    SafeSonioxSocket,
    setup_receiver,
    stop,
    until,
)
from utils.stt import live_session, streaming as st
from utils.stt.resilient_stream import ResilientAudio
import json

from config.live_stt_replay import ReplayLimits
from routers.listen.runtime import ListenSessionRuntime
from tests.unit.test_live_cost_router import MemoryRedis
from tests.unit.test_live_replay_provider_pairs import Transport
from tests.unit.test_live_session_transcript_outcome import _runtime
from tests.unit.test_parakeet_failover_exhausted import Replacement, setup_chain
from utils.stt import live_chain, live_health, live_router, recovery_state, replay_delivery
from utils.stt.live_metrics import LIVE_SESSION_TERMINAL_AFTER_TEXT
from utils.stt.live_router import connecting_target
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.recovery_state import RecoveryState, current_recovery
from utils.stt.replay_delivery import BIRTH_LEDGER_MAX, BirthLedger, enable_recovery_writer_pace
from utils.stt.send_queue import AudioSendQueue

BYTES_PER_SECOND = 16000 * 2
PREFIX_SECONDS = 20


@pytest.fixture(autouse=True)
def shipped_defaults(monkeypatch):
    """Ordinary qualification always runs the shipped 20s/60s/28s budgets;
    full-span stress opts in explicitly inside the test that needs it."""

    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 20.0)
    monkeypatch.setattr(replay_delivery, 'TAIL_RESIDENCE_SECONDS', 28.0)
    monkeypatch.setattr(recovery_state, 'RECOVERY_EPISODE_SECONDS', 60.0)


PAIRS = [
    ('parakeet-window', 'soniox'),
    ('parakeet-window', 'modulate-velma-2'),
    ('soniox', 'modulate-velma-2'),
    ('soniox', 'parakeet-window'),
    ('modulate-velma-2', 'soniox'),
    ('modulate-velma-2', 'parakeet-window'),
]

DURATIONS = [0, 12, 60, 90, 135]


def sized_ring(seconds: int) -> ResilientAudio:
    """``seconds`` of dense capture in 30ms packets."""
    ring = ResilientAudio(16000, ring_seconds=150, strict_replay=True)
    chunk = b'\x01\x00' * 480
    for n in range(seconds * 16000 // 480):
        ring.append(chunk, n * 480)
    return ring


def kill_source(actual, source: str) -> None:
    leg = actual.stt_socket
    if source == 'parakeet-window':
        leg.raw.fail('first_text_deadline')
    else:
        leg.raw._mark_dead('synthetic provider death', typed_reason='modulate_serve_error')


@pytest.mark.asyncio
@pytest.mark.parametrize('source,successor', PAIRS)
@pytest.mark.parametrize('duration', DURATIONS)
async def test_directed_recovery_matrix(monkeypatch, source, successor, duration, virtual_clock):

    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 20.0)
    monkeypatch.setattr(replay_delivery, 'TAIL_RESIDENCE_SECONDS', 28.0)
    monkeypatch.setattr(recovery_state, 'RECOVERY_EPISODE_SECONDS', 60.0)

    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, [source, successor], source=source)
    window_client = Client(data={'text': ''})
    monkeypatch.setattr(window, 'get_stt_client', lambda: window_client)
    ring = sized_ring(duration)
    actual._window_replay_audio = ring
    actual._window_replay_started = True
    kill_source(actual, source)
    captured = b''.join(data for _, data in ring.snapshot())
    kept = captured[-min(len(captured), PREFIX_SECONDS * BYTES_PER_SECOND) :]
    tail = b'\x23\x01' * 480
    try:
        failover = asyncio.create_task(actual._failover_stt_socket())
        await until(lambda: len(raws) > 1 or failover.done())
        if successor != 'parakeet-window' and kept:
            start = len(captured) // 2
            actual.capture_timeline.accept(tail, 1135, 136)
            actual._stt_buffer_start_sample = start
            monkeypatch.setattr(actual, '_capture', lambda *args, **kwargs: None)
            buffer = bytearray(tail)
            await actual._flush_stt_buffer(buffer, force=True)
            assert buffer == b''
        assert await failover

        successor_leg = actual.stt_socket
        assert not successor_leg.is_connection_dead
        actual.host.request.websocket.close.assert_not_awaited()

        if successor != 'parakeet-window':
            raw = raws[-1]
            assert isinstance(raw, SafeSonioxSocket if successor == 'soniox' else SafeModulateSocket)
            expected = kept + (tail if kept else b'')
            await until(lambda: raw._ws.byte_count == len(expected))
            assert raw._ws.pcm == expected
            raw._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 1.0, 'speaker': 'speaker_0'}])
            assert len(base.emitted) == 1
        else:
            assert not successor_leg.is_connection_dead
    finally:
        await actual._drain_stt_sockets()
        for raw in raws:
            for task in (raw._send_task, raw._recv_task):
                if task is not None and not task.done():
                    task.cancel()
            if getattr(raw, '_ws', None) is not None:
                assert raw._ws.closed or raw._send_task.done()
        await stop(raws)


@pytest.mark.asyncio
async def test_writer_pause_resume_paces_real_wire_timestamps(virtual_clock):
    """Stalled transport resume cannot burst: each write starts no earlier
    than previous_start + audio_duration, so wire times stay at <=1x sustained
    plus bounded queue+in-flight jitter (<=3 frames total)."""

    transport = Transport()
    transport.timer = virtual_clock
    raw = SafeSonioxSocket(transport, lambda _: None, asyncio.get_running_loop())
    enable_recovery_writer_pace(raw, 16000, ReplayLimits(), lambda: None)
    frame = b'\x01\x00' * 480  # 30 ms of 16kHz/16-bit audio
    frames = 40
    max_backlog = 0
    try:
        raw._send_queue = AudioSendQueue(maxsize=2)
        sent = 0
        while sent < frames:
            if raw._send_queue.qsize() < 2 and raw.send(frame):
                sent += 1
            max_backlog = max(max_backlog, raw._send_queue.qsize() + raw._send_queue.inflight)
            await asyncio.sleep(0)
        await until(lambda: len(transport.sent_at) >= frames)
        assert max_backlog <= 3
        starts = transport.sent_at
        audio_seconds = len(frame) / (2 * 16000)
        for earlier, later in zip(starts, starts[1:]):
            assert later - earlier >= audio_seconds - 1e-9
        assert starts[-1] - starts[0] >= (frames - 1) * audio_seconds - 1e-9
    finally:
        raw.finish()
        await stop([raw])


@pytest.mark.asyncio
async def test_eos_and_finalize_stay_behind_occupied_queue():
    """EOS/finalize ordered behind accepted audio even while the queue is
    occupied and the transport is stalled: no premature end-of-audio frame."""

    transport = Transport()
    transport.gate.clear()
    raw = SafeSonioxSocket(transport, lambda _: None, asyncio.get_running_loop())
    audio = b'\x02\x00' * 960
    try:
        assert raw.send(audio)
        assert raw.send(audio)
        raw.finalize()
        raw.finish()
        assert transport.sent == []
        transport.gate.set()
        await until(lambda: transport.closed or transport.sent.count('') == 1)
        audio_frames = [frame for frame in transport.sent if isinstance(frame, bytes)]
        assert b''.join(audio_frames) == audio + audio
        tail = [frame for frame in transport.sent if not isinstance(frame, bytes)]
        assert tail[-1] == ''
        assert transport.sent.index('') > max(transport.sent.index(frame) for frame in audio_frames)
    finally:
        raw.finish()
        await stop([raw])


@pytest.mark.asyncio
async def test_client_disconnect_and_flap_mid_replay_cannot_resurrect(monkeypatch, virtual_clock):
    """A client DISCONNECTED during replay latches departure; the later
    active False->True flap must not reopen admission or retry a dial."""
    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', 'soniox'])
    actual._window_replay_started = True
    source = actual.stt_socket
    source.raw.fail('first_text_deadline')
    try:
        failover = asyncio.create_task(actual._failover_stt_socket())
        await until(lambda: bool(raws))
        actual.host.request.websocket.client_state = WebSocketState.DISCONNECTED
        actual.host.state.active = False
        await failover
        assert actual.recovery.client_has_left()
        actual.host.state.active = True
        assert actual.recovery.client_has_left()
        assert not await actual._failover_stt_socket()
        assert len(raws) == 1
    finally:
        try:
            await actual._drain_stt_sockets()
        except asyncio.CancelledError:
            pass
        await stop(raws)


@pytest.mark.asyncio
async def test_second_failover_request_during_replay_adopts_one_candidate(monkeypatch, virtual_clock):
    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', 'soniox'])
    source = actual.stt_socket
    source.raw.fail('first_text_deadline')
    try:
        first = asyncio.create_task(actual._failover_stt_socket())
        second = asyncio.create_task(actual._failover_stt_socket())
        assert await first
        assert await second
        assert len(raws) == 1
        assert isinstance(raws[-1], SafeSonioxSocket)
    finally:
        await actual._drain_stt_sockets()
        await stop(raws)


@pytest.mark.asyncio
async def test_four_distinct_modulate_targets_reach_healthy_fourth(monkeypatch, virtual_clock):
    """Capacity-saturated targets are skipped without spending a dial; the
    healthy fourth is reached inside the same episode — a per-chain outer
    clip or family-wide bench would have stopped before it."""

    monkeypatch.setattr(live_router, '_target_circuits', {})
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    monkeypatch.setattr(pod, 'schedule', lambda coro: coro.close())
    monkeypatch.setattr(live_chain, 'health', pod)
    monkeypatch.setattr(live_session, 'health', pod)
    for family in ('parakeet', 'modulate', 'soniox', 'deepgram'):
        monkeypatch.setattr(st, f'_{family}_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30))
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps(
            [
                {'id': 'parakeet-window', 'family': 'parakeet', 'cost_per_audio_hour': 0.02},
                {
                    'id': 'modulate-a',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'endpoint': 'wss://mod-a.invalid/stream',
                    'capacity_env': 'MOD_CAP_A',
                },
                {
                    'id': 'modulate-b',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'endpoint': 'wss://mod-b.invalid/stream',
                },
                {
                    'id': 'modulate-c',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'endpoint': 'wss://mod-c.invalid/stream',
                },
                {
                    'id': 'modulate-d',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'endpoint': 'wss://mod-d.invalid/stream',
                },
                {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754},
            ]
        ),
    )
    monkeypatch.setenv('MOD_CAP_A', 'true')
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    selected = []

    async def connect(callback, *args, **kwargs):
        target = connecting_target.get()
        selected.append(target.id)
        raw = Replacement(callback)
        raw.routing_endpoint = target.endpoint
        legs['modulate'].append(raw)
        return raw

    monkeypatch.setattr(live_session, 'connect_modulate', connect)
    try:
        assert await actual._failover_stt_socket()
        assert selected == ['modulate-b']
        for dead_target in ('modulate-b', 'modulate-c'):
            actual.stt_socket.raw.is_connection_dead = True
            actual.stt_socket.raw.typed_death_reason = 'modulate_serve_error'
            assert await actual._failover_stt_socket()
        assert selected == ['modulate-b', 'modulate-c', 'modulate-d']
        assert actual.host.stt_service == st.STTService.modulate
        assert actual.stt_socket.routing_target == 'modulate-d'
        actual.host.request.websocket.close.assert_not_awaited()
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_episode_deadline_clamps_dials_then_exhausts(monkeypatch, virtual_clock):
    """A complete 60s episode bounds total recovery work: dials stop once the
    deadline passes and only then the episode exhausts."""

    monkeypatch.setattr(live_router, '_target_circuits', {})
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    monkeypatch.setattr(pod, 'schedule', lambda coro: coro.close())
    monkeypatch.setattr(live_chain, 'health', pod)
    monkeypatch.setattr(live_session, 'health', pod)
    for family in ('parakeet', 'modulate', 'soniox', 'deepgram'):
        monkeypatch.setattr(st, f'_{family}_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30))
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    targets = [
        {'id': 'parakeet-window', 'family': 'parakeet', 'cost_per_audio_hour': 0.02},
        {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.05},
    ] + [
        {
            'id': f'modulate-{letter}',
            'family': 'modulate',
            'cost_per_audio_hour': 0.05,
            'endpoint': f'wss://mod-{letter}.invalid/stream',
        }
        for letter in 'abcdef'
    ]
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps(targets))
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    selected = []

    async def connect(callback, *args, **kwargs):
        target = connecting_target.get()
        selected.append(target.id)
        await virtual_clock.sleep(20)
        raw = Replacement(callback)
        raw.is_connection_dead = True
        raw.typed_death_reason = 'modulate_serve_error'
        legs['modulate'].append(raw)
        return raw

    monkeypatch.setattr(live_session, 'connect_modulate', connect)

    async def slow_dead_tail(callback, *args, **kwargs):
        await virtual_clock.sleep(20)
        raw = Replacement(callback)
        raw.is_connection_dead = True
        raw.typed_death_reason = 'provider_5xx'
        legs['soniox'].append(raw)
        return raw

    monkeypatch.setattr(st, 'process_audio_soniox', slow_dead_tail)
    try:
        assert not await actual._failover_stt_socket()
        assert len(selected) + len(legs['soniox']) == 3

        assert actual.recovery.state is RecoveryState.exhausted
    finally:
        try:
            await actual._drain_stt_sockets()
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_ptt_and_initial_legs_never_get_recovery_pacing():
    """PTT/ordinary legs: no recovery context, no writer pace, plain send."""

    assert current_recovery.get() is None
    raw = SafeSonioxSocket(Transport(), lambda _: None, asyncio.get_running_loop())
    try:
        assert raw._writer_pace is None
        assert current_recovery.get() is None
    finally:
        raw.finish()
        await stop([raw])


def test_terminal_after_text_counter_only_when_delivered_then_failed():

    soniox_counter = LIVE_SESSION_TERMINAL_AFTER_TEXT.labels(provider='soniox')
    before = soniox_counter._value.get()
    runtime = _runtime(delivered=True, terminal=True)
    runtime.stt_service = st.STTService.soniox
    ListenSessionRuntime._record_session_transcript_outcome(runtime)
    ListenSessionRuntime._record_session_transcript_outcome(runtime)
    assert soniox_counter._value.get() == before + 1

    for delivered, terminal in [(True, False), (False, True), (False, False)]:
        runtime = _runtime(delivered=delivered, terminal=terminal)
        runtime.stt_service = st.STTService.soniox
        ListenSessionRuntime._record_session_transcript_outcome(runtime)
    assert soniox_counter._value.get() == before + 1


def test_birth_ledger_stays_bounded_and_looks_up_containing_intervals(virtual_clock):

    ledger = BirthLedger()
    born = virtual_clock.now
    for n in range(10_000):
        ledger.note(n * 480, (n + 1) * 480, born + n * 0.03)
    ledger.note(100 * 480 + 10, 100 * 480 + 20, born + 9999.0)  # interior: keeps earliest
    assert len(ledger) <= BIRTH_LEDGER_MAX
    found = ledger.lookup(500 * 480 + 5)
    assert found is not None and found <= born + 500 * 0.03
    ledger.prune_before(9000 * 480)
    assert all(entry[1] > 9000 * 480 for entry in ledger._iv)
    assert ledger.lookup(9500 * 480 + 5) is not None
