"""Directed live-STT recovery matrix: every ordered provider pair x ring depth.

Fixture contract: the capture obligation is injected through
``_window_replay_audio`` — a controlled session fixture, not a claim that
every initial paid production source retains a ring. Shipped defaults (20s
prefix wall / 60s episode / 28s live residence) are restored explicitly so an
autouse override elsewhere cannot leak into the ordinary qualification.
"""

import asyncio
import contextlib
import io
import wave
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import numpy as np
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
from utils.audio_timeline import CaptureTimeline
from utils.stt import live_session, streaming as st
from utils.stt.resilient_stream import ResilientAudio
import json

from config.live_stt_replay import ReplayLimits, parse_replay_limits
from routers.listen.runtime import ListenSessionRuntime
from tests.unit.test_live_cost_router import MemoryRedis
from tests.unit.test_live_replay_provider_pairs import Transport
from tests.unit.test_live_health_reason_reconciliation import serving_leg
from tests.unit.test_live_session_transcript_outcome import _runtime
from tests.unit.test_live_stt_resilient_stream import receiver as make_receiver
from tests.unit.test_parakeet_failover_exhausted import Replacement, setup_chain
from tests.unit.test_modulate_capacity_failover import dead_receiver
from utils.stt.soniox import SonioxRateLimitError
from utils.stt import live_chain, live_health, live_router, recovery_state, replay_delivery, resilient_stream
from utils.stt.connect_backoff import ConnectRefusalBackoff
from utils.stt import soniox as soniox_module
from utils.stt.live_failure import live_stt_terminal_reason
from utils.stt.live_metrics import LIVE_SESSION_TERMINAL_AFTER_TEXT, REPLAY_AUDIO, REPLAY_SKIPPED
from utils.stt.live_router import connecting_target
from utils.stt.live_signal import provider_observation
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.recovery_state import RecoveryState, current_recovery
from utils.stt.replay_delivery import (
    BIRTH_LEDGER_MAX,
    WRITER_SLOT_SECONDS,
    AudioDeliveryExpired,
    BirthLedger,
    RecoveryWriterPace,
    ReplayPacer,
    ReplayTailSocket,
    abort_replay_socket,
    enable_recovery_writer_pace,
)
from utils.stt.send_queue import AudioSendQueue, audio_send_deadline


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


BYTES_PER_SECOND = 16000 * 2
PREFIX_SECONDS = 20
SAMPLE_RATE = 16000


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


def marker_chunk(n: int) -> bytes:
    """A 30ms packet whose int16 samples are all the value ``n``."""
    return n.to_bytes(2, 'little') * 480


def sized_ring(seconds: int) -> ResilientAudio:
    """``seconds`` of dense capture in 30ms packets with distinguishable PCM."""
    ring = ResilientAudio(16000, ring_seconds=150, strict_replay=True)
    for n in range(seconds * 16000 // 480):
        ring.append(marker_chunk(n + 1), n * 480)
    return ring


def kill_source(actual, source: str) -> None:
    leg = actual.stt_socket
    if source == 'parakeet-window':
        leg.raw.fail('first_text_deadline')
    elif source == 'soniox':
        leg.raw._mark_dead('synthetic provider death', typed_reason='connection_lost')
    else:
        leg.raw._mark_dead('synthetic provider death', typed_reason='modulate_serve_error')


class CoverageClient(Client):
    """Window STT client that answers each POST with one unfinished synthetic
    segment (no terminal punctuation) so held text flushes only at force."""

    def __init__(self):
        super().__init__(data={'text': ''})
        self.posted: list[tuple[bytes, int]] = []

    async def post(self, url, **kwargs):
        payload = kwargs['files']['file'][1]
        with wave.open(io.BytesIO(payload)) as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
            self.posted.append((wav.readframes(frames), rate))
        return httpx.Response(
            200,
            json={'segments': [{'text': 'synthetic', 'start': 0.0, 'end': frames / rate}]},
            request=httpx.Request('POST', url),
        )


def posted_marker_ids(client: CoverageClient) -> list[list[int]]:
    """Run-length-encoded marker id sequence per POST (silence runs dropped)."""
    runs = []
    for pcm, rate in client.posted:
        assert rate == SAMPLE_RATE
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.int64)
        if not len(samples):
            runs.append([])
            continue
        edges = np.concatenate([[True], np.diff(samples) != 0])
        runs.append([int(v) for v in samples[edges] if v > 0])
    return runs


def assert_legs_drained(legs, observations) -> None:
    assert all(leg.leg_outcome.settled for leg in legs), [
        (leg.service.value, leg.leg_outcome.claimed, leg.leg_outcome.settled, leg.leg_outcome.reason) for leg in legs
    ]
    assert len(observations) == len(legs)
    for leg in legs:
        raw_leg = leg.raw
        pump = getattr(raw_leg, '_pump_task', None)
        if pump is not None:
            assert pump.done()
        transport = getattr(raw_leg, '_ws', None)
        if transport is not None:
            assert transport.closed
        for name in ('_send_task', '_recv_task'):
            task = getattr(raw_leg, name, None)
            if task is not None:
                assert task.done()


@pytest.mark.asyncio
@pytest.mark.parametrize('source,successor', PAIRS)
@pytest.mark.parametrize('duration', DURATIONS)
async def test_directed_recovery_matrix(monkeypatch, source, successor, duration, virtual_clock):

    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 20.0)
    monkeypatch.setattr(replay_delivery, 'TAIL_RESIDENCE_SECONDS', 28.0)
    monkeypatch.setattr(recovery_state, 'RECOVERY_EPISODE_SECONDS', 60.0)

    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, [source, successor], source=source)
    window_client = CoverageClient()
    monkeypatch.setattr(window, 'get_stt_client', lambda: window_client)
    monkeypatch.setattr(window, 'posted_window_gain', lambda pcm, tail_bytes: 1.0)
    ring = sized_ring(duration)
    actual._window_replay_audio = ring
    actual._window_replay_started = True
    captured = b''.join(data for _, data in ring.snapshot())
    actual.capture_timeline = CaptureTimeline(sample_rate=SAMPLE_RATE)
    if captured:
        start, end, _ = actual.capture_timeline.accept(captured, 1000.0, 1.0)
        assert (start, end) == (0, duration * SAMPLE_RATE)
    dead_leg = actual.stt_socket
    kill_source(actual, source)
    source_family = {'parakeet-window': 'parakeet', 'soniox': 'soniox', 'modulate-velma-2': 'modulate'}[source]
    successor_family = (
        'soniox' if successor == 'soniox' else 'modulate' if successor.startswith('modulate') else 'parakeet'
    )
    labels = dict(source=source_family, successor=successor_family)
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    audio_before = REPLAY_AUDIO.labels(**labels)._value.get()
    kept = captured[-min(len(captured), PREFIX_SECONDS * BYTES_PER_SECOND) :]
    tail = marker_chunk(duration * SAMPLE_RATE // 480 + 1)
    try:
        failover = asyncio.create_task(actual._failover_stt_socket())
        await until(lambda: len(raws) > 1 or failover.done())
        tail_start, tail_end, _ = actual.capture_timeline.accept(tail, 1000.0 + duration, 1.0 + duration)
        assert (tail_start, tail_end) == (len(captured) // 2, len(captured) // 2 + 480)
        actual._stt_buffer_start_sample = tail_start
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
            expected = kept + tail
            await until(lambda: raw._ws.byte_count == len(expected))
            assert raw._ws.pcm == expected
            assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == pytest.approx(
                max(duration - PREFIX_SECONDS, 0)
            )
            assert REPLAY_AUDIO.labels(**labels)._value.get() - audio_before == pytest.approx(
                min(duration, PREFIX_SECONDS)
            )
            send_map = legs[-1]._send_tracker.send_map
            last = send_map.last_provider_sample
            assert last == len(expected) // 2
            emit_end = last / SAMPLE_RATE
            raw._stream_transcript([{'text': 'synthetic', 'start': 0.0, 'end': emit_end, 'speaker': 'speaker_0'}])
            assert len(base.emitted) == 1
            assert legs[0].leg_outcome.settled
            assert actual.recovery.deadline is None
            assert actual.recovery.state is RecoveryState.recovered
            segment = base.emitted[-1]
            interval = send_map.map_interval(0, last)
            assert interval is not None
            kept_origin = len(captured) // 2 - len(kept) // 2
            assert interval == (kept_origin, kept_origin + len(expected) // 2)
            assert segment['_capture_abs_start'] == pytest.approx(actual.capture_timeline.wall(interval[0]))
            assert segment['_capture_abs_end'] == pytest.approx(actual.capture_timeline.wall(interval[1]))
            assert segment['speaker_id_scope'] == legs[-1].speaker_provider_epoch.current_scope
            dead_leg.raw._stream_transcript([{'text': 'late', 'start': 0, 'end': 0.5, 'speaker': 'speaker_0'}])
            assert len(base.emitted) == 1

        await actual._drain_stt_sockets()
        if successor == 'parakeet-window':
            for url, kwargs in window_client.requests:
                assert url.endswith('/v1/transcribe')
                assert kwargs['headers'] == {'X-Omi-STT-Surface': 'live-window'}
            assert all(rate == SAMPLE_RATE for _, rate in window_client.posted)
            for run in posted_marker_ids(window_client):
                assert run == sorted(run)
                assert len(run) == len(set(run))
            if duration:
                assert window_client.posted[-1][0] == kept + tail
            else:
                runs = posted_marker_ids(window_client)
                covered = {marker for run in runs for marker in run}
                if runs:
                    assert duration * SAMPLE_RATE // 480 + 1 in covered
                else:
                    assert successor_leg.raw._received_bytes >= len(tail)
        assert_legs_drained(legs, observations)
    finally:
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
@pytest.mark.parametrize('frame_bytes', [960, 16 * 1024])
async def test_writer_pause_resume_paces_real_wire_timestamps(virtual_clock, kind, frame_bytes):
    """A genuinely stalled transport cannot burst on resume: writes restart at
    previous_start + audio_duration on the wire clock, the declared
    queue+in-flight bound is never exceeded, and the leg stays alive."""

    transport = Transport()
    transport.timer = virtual_clock
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    limits = ReplayLimits()
    enable_recovery_writer_pace(raw, SAMPLE_RATE, limits, lambda: None)
    raw.replay_send = lambda data, start: raw.send(data)
    pacer = ReplayPacer(SAMPLE_RATE, 'soniox', raw, limits=limits)
    frame = b'\x01\x00' * (frame_bytes // 2)
    frame_seconds = frame_bytes / (2 * SAMPLE_RATE)
    total = 4 if frame_bytes == 16 * 1024 else 10

    async def produce():
        for n in range(total):
            assert await pacer.send(raw, frame, n * (frame_bytes // 2), lambda: True, replay=True)

    transport.gate.clear()
    producer = asyncio.create_task(produce())
    try:
        await until(lambda: raw._send_queue.qsize() + raw._send_queue.inflight >= limits.queue_packets)
        assert transport.sent == [] and not producer.done()
        resume = asyncio.create_task(virtual_clock.sleep(0.6))
        await resume
        transport.gate.set()
        await until(lambda: producer.done() and len(transport.sent_at) >= total)
        starts = transport.sent_at
        assert starts[0] >= 0.6
        assert starts[-1] - starts[0] >= (total - limits.queue_packets) * frame_seconds - 1e-9
        assert raw._send_queue.high_water <= limits.queue_packets
        assert not raw.is_connection_dead
        await abort_replay_socket(raw)
        assert transport.closed and raw._send_task.done() and raw._recv_task.done()
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
        await stop([raw])


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_eos_and_finalize_stay_behind_occupied_queue(kind):
    """Graceful drain: accepted audio occupies the queue behind a held gate,
    then the drain flushes byte-exact PCM first and ends with the empty text
    EOS frame — never an end-of-audio write ahead of queued audio."""

    transport = Transport()
    transport.gate.clear()
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    audio = b'\x02\x00' * 960
    try:
        assert raw.send(audio)
        assert raw.send(audio)
        drain = asyncio.create_task(raw.drain_and_close())
        await asyncio.sleep(0)
        assert transport.sent == []
        transport.gate.set()
        await asyncio.wait_for(drain, timeout=5)
        audio_frames = [frame for frame in transport.sent if isinstance(frame, bytes)]
        assert b''.join(audio_frames) == audio + audio
        assert transport.sent[-1] == ''
        assert transport.closed
        assert raw._send_task.done() and raw._recv_task.done()
        assert raw.typed_death_reason != 'capacity_full'
    finally:
        raw.finish()
        await stop([raw])


@pytest.mark.asyncio
@pytest.mark.parametrize('cause', ['client_disconnected', 'app_disconnected', 'active_flap'])
async def test_client_departure_mid_replay_latches_and_cannot_resurrect(monkeypatch, virtual_clock, cause):
    """Each departure authority — client socket state, application socket
    state, or an active=False flap while the socket stays CONNECTED — latches
    leaving mid-prefix. Nothing reopens admission, no 1011 is sent, and the
    episode never reports exhaustion for a departed client."""
    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', 'soniox'])
    actual._window_replay_started = True
    source = actual.stt_socket
    source.raw.fail('first_text_deadline')
    entered = asyncio.Event()
    released = asyncio.Event()
    original = live_session.LiveLegSocket.wait_send_capacity

    async def held_capacity(leg, *args, **kwargs):
        entered.set()
        await released.wait()
        return await original(leg, *args, **kwargs)

    monkeypatch.setattr(live_session.LiveLegSocket, 'wait_send_capacity', held_capacity)
    failover = asyncio.create_task(actual._failover_stt_socket())
    try:
        await entered.wait()
        websocket = actual.host.request.websocket
        if cause == 'client_disconnected':
            websocket.client_state = WebSocketState.DISCONNECTED
        elif cause == 'app_disconnected':
            websocket.application_state = WebSocketState.DISCONNECTED
        else:
            actual.host.state.active = False
            assert actual.recovery.client_has_left()
            actual.host.state.active = True
        released.set()
        assert not await failover
        assert actual.recovery.client_has_left()
        assert actual.recovery.state is RecoveryState.client_leaving
        assert not actual.recovery.exhausted
        assert not await actual._failover_stt_socket()
        assert len(raws) == 1
        actual.host.request.websocket.close.assert_not_awaited()
        with contextlib.suppress(asyncio.CancelledError):
            await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
        released.set()
        failover.cancel()
        await asyncio.gather(failover, return_exceptions=True)
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
        raws[-1]._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 1.0, 'speaker': 'speaker_0'}])
        assert legs[0].leg_outcome.settled
        await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
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


class BurstClosingTransport(Transport):
    """Reject wire writes whose cumulative PCM outruns elapsed wire time by
    more than one armed frame of jitter — a real-transport back-pressure fake
    that closes on catch-up bursts, not a queue-size proxy."""

    def __init__(self, jitter_seconds: float, start_held: bool = False):
        super().__init__()
        self.jitter_seconds = jitter_seconds
        self.first_write_at = None
        self.pcm_seconds = 0.0
        if start_held:
            self.gate.clear()

    async def send(self, data):
        await self.gate.wait()
        if isinstance(data, bytes) and data and self.timer is not None:
            if self.first_write_at is None:
                self.first_write_at = self.timer.now
            self.pcm_seconds += len(data) / (2 * SAMPLE_RATE)
            elapsed = self.timer.now - self.first_write_at
            if self.pcm_seconds > elapsed + self.jitter_seconds + 1e-6:
                raise OSError('burst rejected: wire audio outran elapsed time')
        await super().send(data)


def _inject_inbound_once(raw, payload: str) -> None:
    delivered = []

    def hook():
        if not delivered:
            delivered.append(True)
            raw._ws.inbound.put_nowait(payload)
            raw._ws.on_send = lambda: None

    raw._ws.on_send = hook


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'bad,good,frame,reason',
    [
        (
            'soniox',
            'modulate-velma-2',
            json.dumps({'error_code': 402, 'error_type': 'organization_balance_exhausted'}),
            'provider_budget_exhausted',
        ),
        (
            'soniox',
            'modulate-velma-2',
            json.dumps({'error_code': 429, 'error_type': 'concurrency_limit_exceeded'}),
            'provider_rate_limited',
        ),
        (
            'modulate-velma-2',
            'soniox',
            json.dumps({'type': 'error', 'error': 'Internal server error'}),
            'modulate_serve_error',
        ),
    ],
)
async def test_provider_error_frame_mid_prefix_walks_to_next_target(
    monkeypatch, virtual_clock, bad, good, frame, reason
):
    """Real provider error frames arriving mid-prefix carry typed reasons and
    walk to the next capable target — no 1011, one outcome per leg."""

    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', bad, good])
    ring = sized_ring(135)
    actual._window_replay_audio = ring
    actual._window_replay_started = True
    actual.capture_timeline = CaptureTimeline(sample_rate=SAMPLE_RATE)
    captured = b''.join(data for _, data in ring.snapshot())
    actual.capture_timeline.accept(captured, 1000.0, 1.0)
    kill_source(actual, 'parakeet-window')
    bad_kind = SafeSonioxSocket if bad == 'soniox' else SafeModulateSocket
    try:
        failover = asyncio.create_task(actual._failover_stt_socket())
        await until(lambda: bool(raws))
        bad_raw = raws[-1]
        assert isinstance(bad_raw, bad_kind)
        _inject_inbound_once(bad_raw, frame)
        await failover
        await until(lambda: bad_raw.is_connection_dead)
        assert bad_raw.typed_death_reason == reason
        assert await actual._failover_stt_socket()
        good_raw = raws[-1]
        assert len([raw for raw in raws if isinstance(raw, bad_kind)]) == 1
        good_raw._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 0.5, 'speaker': 'speaker_0'}])
        assert actual.recovery.state is RecoveryState.recovered
        actual.host.request.websocket.close.assert_not_awaited()
        bad_observations = [entry for entry in observations if entry[0] == legs[1].routing_target]
        assert bad_observations and bad_observations[-1][5] == reason
        await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_paced_writer_survives_burst_closing_transport(virtual_clock, kind):
    """A correctly paced recovery writer never outruns one max-frame of wire
    jitter on a transport that physically closes on catch-up bursts."""

    transport = BurstClosingTransport(jitter_seconds=16 * 1024 / (2 * SAMPLE_RATE))
    transport.timer = virtual_clock
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    limits = ReplayLimits()
    enable_recovery_writer_pace(raw, SAMPLE_RATE, limits, lambda: None)
    raw.replay_send = lambda data, start: raw.send(data)
    pacer = ReplayPacer(SAMPLE_RATE, 'soniox', raw, limits=limits)
    frame = b'\x01\x00' * 480
    try:
        for n in range(8):
            assert await pacer.send(raw, frame, n * 480, lambda: True, replay=True)
        await until(lambda: len(transport.sent_at) >= 8)
        assert not raw.is_connection_dead

        strict = BurstClosingTransport(jitter_seconds=0.030)
        strict.timer = virtual_clock
        unyielding = kind(strict, lambda _: None, asyncio.get_running_loop())
        for _ in range(4):
            unyielding.send(frame)
        await until(lambda: unyielding.is_connection_dead)
        await stop([unyielding])
        await abort_replay_socket(raw)
    finally:
        await stop([raw])


@pytest.mark.asyncio
@pytest.mark.parametrize('successor', ['soniox', 'modulate-velma-2'])
async def test_directed_recovery_under_burst_closing_transport(monkeypatch, virtual_clock, successor):
    """The real paced failover pipeline stays alive under a transport that
    closes on catch-up bursts: 135s source, shipped 20s suffix + live input."""

    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', successor])
    ring = sized_ring(135)
    actual._window_replay_audio = ring
    actual._window_replay_started = True
    actual.capture_timeline = CaptureTimeline(sample_rate=SAMPLE_RATE)
    captured = b''.join(data for _, data in ring.snapshot())
    actual.capture_timeline.accept(captured, 1000.0, 1.0)
    kill_source(actual, 'parakeet-window')
    kind = SafeSonioxSocket if successor == 'soniox' else SafeModulateSocket
    connector = 'process_audio_soniox' if successor == 'soniox' else 'process_audio_modulate'

    async def connect(callback, *args, **kwargs):
        transport = BurstClosingTransport(jitter_seconds=16 * 1024 / (2 * SAMPLE_RATE))
        transport.timer = virtual_clock
        raw = kind(transport, callback, asyncio.get_running_loop())
        raws.append(raw)
        return raw

    monkeypatch.setattr(st, connector, connect)
    labels = dict(source='parakeet', successor='soniox' if successor == 'soniox' else 'modulate')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    kept = captured[-PREFIX_SECONDS * BYTES_PER_SECOND :]
    tail = marker_chunk(135 * SAMPLE_RATE // 480 + 1)
    try:
        failover = asyncio.create_task(actual._failover_stt_socket())
        await until(lambda: len(raws) >= 1 or failover.done())
        tail_start, _, _ = actual.capture_timeline.accept(tail, 1135.0, 136.0)
        actual._stt_buffer_start_sample = tail_start
        buffer = bytearray(tail)
        await actual._flush_stt_buffer(buffer, force=True)
        assert await failover
        raw = raws[-1]
        await until(lambda: raw._ws.byte_count == len(kept) + len(tail))
        assert raw._ws.pcm == kept + tail
        assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == pytest.approx(115.0)
        assert not raw.is_connection_dead
        actual.host.request.websocket.close.assert_not_awaited()
        await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
        await stop(raws)


@pytest.mark.asyncio
async def test_strict_burst_transport_rejects_paused_leg_and_next_target_serves(monkeypatch, virtual_clock):
    """A deliberately stricter-than-contract fake (one 30ms frame of jitter)
    rejects a leg whose writer stalled 0.6s; the next capable target takes
    over — the walk is bounded, not terminal."""

    actual, base, raws, legs, observations = await setup_receiver(
        monkeypatch, ['parakeet-window', 'soniox', 'modulate-velma-2']
    )
    ring = sized_ring(135)
    actual._window_replay_audio = ring
    actual._window_replay_started = True
    actual.capture_timeline = CaptureTimeline(sample_rate=SAMPLE_RATE)
    captured = b''.join(data for _, data in ring.snapshot())
    actual.capture_timeline.accept(captured, 1000.0, 1.0)
    kill_source(actual, 'parakeet-window')

    async def stalled_soniox(callback, *args, **kwargs):
        transport = BurstClosingTransport(jitter_seconds=0.030, start_held=True)
        transport.timer = virtual_clock
        raw = SafeSonioxSocket(transport, callback, asyncio.get_running_loop())
        raws.append(raw)
        return raw

    monkeypatch.setattr(st, 'process_audio_soniox', stalled_soniox)
    kept = captured[-PREFIX_SECONDS * BYTES_PER_SECOND :]
    try:
        failover = asyncio.create_task(actual._failover_stt_socket())
        await until(lambda: len(raws) >= 1 or failover.done())
        stalled_raw = raws[-1]
        assert isinstance(stalled_raw, SafeSonioxSocket)
        await virtual_clock.sleep(0.6)
        stalled_raw._ws.gate.set()
        await until(lambda: stalled_raw.is_connection_dead)
        await failover
        assert await actual._failover_stt_socket()
        good = raws[-1]
        assert isinstance(good, SafeModulateSocket)
        await until(lambda: good._ws.byte_count == len(kept))
        assert good._ws.pcm == kept
        actual.host.request.websocket.close.assert_not_awaited()
        await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad,good', [('soniox', 'modulate-velma-2'), ('modulate-velma-2', 'soniox')])
async def test_paid_successor_dies_mid_prefix_and_next_replays_after_emitted(monkeypatch, virtual_clock, bad, good):
    """A paid successor dying mid-prefix after first text: the next target
    replays only capture past the emitted boundary, the retired candidate's
    late callback cannot emit, and each candidate's proof is its own."""

    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', bad, good])
    ring = sized_ring(135)
    actual._window_replay_audio = ring
    actual._window_replay_started = True
    actual.capture_timeline = CaptureTimeline(sample_rate=SAMPLE_RATE)
    captured = b''.join(data for _, data in ring.snapshot())
    actual.capture_timeline.accept(captured, 1000.0, 1.0)
    kill_source(actual, 'parakeet-window')
    kept = captured[-PREFIX_SECONDS * BYTES_PER_SECOND :]
    tail = marker_chunk(135 * SAMPLE_RATE // 480 + 1)
    emitted = []
    try:
        failover = asyncio.create_task(actual._failover_stt_socket())
        await until(lambda: bool(raws))
        bad_raw = raws[-1]

        def first_text_then_die():
            if emitted or bad_raw._ws.byte_count < 6400:
                return
            emitted.append(True)
            bad_raw._stream_transcript([{'text': 'first', 'start': 0, 'end': 0.2, 'speaker': 'speaker_0'}])
            bad_raw._ws.fail_after = len(bad_raw._ws.sent)
            bad_raw._ws.on_send = lambda: None

        bad_raw._ws.on_send = first_text_then_die
        await failover
        await until(lambda: bad_raw.is_connection_dead)
        assert [segment['text'] for segment in base.emitted] == ['first']
        assert await actual._failover_stt_socket()
        good_raw = raws[-1]
        tail_start, _, _ = actual.capture_timeline.accept(tail, 1135.0, 136.0)
        actual._stt_buffer_start_sample = tail_start
        buffer = bytearray(tail)
        await actual._flush_stt_buffer(buffer, force=True)
        expected = kept[6400:] + tail
        await until(lambda: good_raw._ws.byte_count == len(expected))
        assert good_raw._ws.pcm == expected
        good_raw._stream_transcript(
            [{'text': 'rest', 'start': 0, 'end': len(expected) / BYTES_PER_SECOND, 'speaker': 'speaker_0'}]
        )
        assert [segment['text'] for segment in base.emitted] == ['first', 'rest']
        assert actual.recovery.state is RecoveryState.recovered
        assert actual.recovery.deadline is None
        bad_raw._stream_transcript([{'text': 'late', 'start': 0, 'end': 0.5, 'speaker': 'speaker_0'}])
        assert len(base.emitted) == 2
        await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
        await stop(raws)


@pytest.mark.asyncio
async def test_real_dials_each_get_the_full_per_dial_budget(monkeypatch, virtual_clock):
    """Three real managed dials that each take 4 virtual seconds all complete:
    no outer-5s starvation resets, the third healthy target serves."""

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
                {'id': 'modulate-a', 'family': 'modulate', 'cost_per_audio_hour': 0.05},
                {'id': 'modulate-b', 'family': 'modulate', 'cost_per_audio_hour': 0.05},
                {'id': 'modulate-c', 'family': 'modulate', 'cost_per_audio_hour': 0.05},
            ]
        ),
    )
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    selected = []
    dialed = []

    async def dial(callback, *args, **kwargs):
        target = connecting_target.get()
        selected.append(target.id)
        await virtual_clock.sleep(4.0)
        transport = Transport()
        transport.timer = virtual_clock
        raw = SafeModulateSocket(transport, callback, asyncio.get_running_loop())
        dialed.append(raw)
        if target.id != 'modulate-c':
            raw._mark_dead('synthetic serve failure', typed_reason='modulate_serve_error')
        return raw

    monkeypatch.setattr(st, 'process_audio_modulate', dial)
    try:
        assert await actual._failover_stt_socket()
        assert selected == ['modulate-a', 'modulate-b', 'modulate-c']
        assert virtual_clock.now < 60
        assert not actual.recovery.exhausted
        assert not actual.stt_socket.is_connection_dead
        actual.host.request.websocket.close.assert_not_awaited()
        for raw in dialed[:2]:
            assert raw._ws.closed
            assert raw._send_task.done() and raw._recv_task.done()
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            await actual._drain_stt_sockets()
        await stop(dialed)


@pytest.mark.asyncio
async def test_wall_dial_cap_cancels_hung_connect_and_walks(monkeypatch, virtual_clock):
    """A connect that never answers is cancelled at the real dial budget and
    the next capable target still serves — two reservations, no exhaustion."""

    monkeypatch.setattr(live_router, '_target_circuits', {})
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    monkeypatch.setattr(pod, 'schedule', lambda coro: coro.close())
    monkeypatch.setattr(live_chain, 'health', pod)
    monkeypatch.setattr(live_session, 'health', pod)
    for family in ('parakeet', 'modulate', 'soniox', 'deepgram'):
        monkeypatch.setattr(st, f'_{family}_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30))
    monkeypatch.setattr(recovery_state, 'RECOVERY_DIAL_SECONDS', 0.001)
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps(
            [
                {'id': 'parakeet-window', 'family': 'parakeet', 'cost_per_audio_hour': 0.02},
                {'id': 'modulate-a', 'family': 'modulate', 'cost_per_audio_hour': 0.05},
                {'id': 'modulate-b', 'family': 'modulate', 'cost_per_audio_hour': 0.05},
            ]
        ),
    )
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    selected = []
    cancelled = []
    dialed = []

    async def dial(callback, *args, **kwargs):
        target = connecting_target.get()
        selected.append(target.id)
        if target.id == 'modulate-a':
            transport = Transport()
            transport.timer = virtual_clock
            raw = SafeModulateSocket(transport, callback, asyncio.get_running_loop())
            dialed.append(raw)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(target.id)
                await abort_replay_socket(raw)
                raise
        transport = Transport()
        transport.timer = virtual_clock
        raw = SafeModulateSocket(transport, callback, asyncio.get_running_loop())
        dialed.append(raw)
        return raw

    monkeypatch.setattr(st, 'process_audio_modulate', dial)
    try:
        assert await actual._failover_stt_socket()
        assert cancelled == ['modulate-a']
        assert selected == ['modulate-a', 'modulate-b']
        assert not actual.recovery.exhausted
        assert not actual.stt_socket.is_connection_dead
        assert dialed[0]._ws.closed
        assert dialed[0]._send_task.done() and dialed[0]._recv_task.done()
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            await actual._drain_stt_sockets()
        await stop(dialed)


@pytest.mark.asyncio
async def test_connect_reject_settles_every_constructed_leg_once(monkeypatch, virtual_clock):
    """A last-connect 402 rejection settles each constructed leg's outcome
    exactly once and closes every probed transport — no abandoned legs."""

    monkeypatch.setattr(live_router, '_target_circuits', {})
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    monkeypatch.setattr(pod, 'schedule', lambda coro: coro.close())
    monkeypatch.setattr(live_chain, 'health', pod)
    monkeypatch.setattr(live_session, 'health', pod)
    for family in ('parakeet', 'modulate', 'soniox', 'deepgram'):
        monkeypatch.setattr(st, f'_{family}_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30))
    observations = []
    monkeypatch.setattr(pod, 'record_session', lambda *args, **kwargs: observations.append(args) or True)
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps(
            [
                {'id': 'parakeet-window', 'family': 'parakeet', 'cost_per_audio_hour': 0.02},
                {'id': 'modulate-a', 'family': 'modulate', 'cost_per_audio_hour': 0.05},
                {'id': 'modulate-b', 'family': 'modulate', 'cost_per_audio_hour': 0.05},
            ]
        ),
    )
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    dialed = []

    async def dial(callback, *args, **kwargs):
        transport = Transport()
        transport.timer = virtual_clock
        raw = SafeModulateSocket(transport, callback, asyncio.get_running_loop())
        dialed.append(raw)
        raw._mark_dead('payment required', typed_reason='provider_budget_exhausted')
        return raw

    monkeypatch.setattr(st, 'process_audio_modulate', dial)
    try:
        assert await actual._failover_stt_socket()
        assert len(dialed) == 1
        assert len(legs['soniox']) == 1
        for raw in dialed:
            assert raw._ws.closed
            assert raw._send_task.done() and raw._recv_task.done()
        with contextlib.suppress(asyncio.CancelledError):
            await actual._drain_stt_sockets()
        targets = [entry[0] for entry in observations]
        assert targets.count('modulate-a') == 1
        assert targets.count('parakeet-window') == 1
        assert len(targets) == 2
    finally:
        await stop(dialed)


def test_replay_limits_boundaries():
    for bad in (
        {'rate': True},
        {'rate': float('nan')},
        {'rate': float('inf')},
        {'rate': 0},
        {'rate': 1.5},
        {'rate': 'fast'},
        {'max_frame_bytes': 8193},
        {'max_frame_bytes': 2.0},
        {'queue_packets': 0},
        {'queue_packets': 3},
        {'queue_packets': True},
        {'queue_wait_seconds': 0},
        {'queue_wait_seconds': 3},
        {'queue_wait_seconds': float('nan')},
        'not-a-mapping',
        {'unknown': 1},
    ):
        with pytest.raises(ValueError):
            parse_replay_limits(bad)
    parsed = parse_replay_limits({'rate': 0.5, 'max_frame_bytes': 8192, 'queue_packets': 1, 'queue_wait_seconds': 0.5})
    assert parsed == ReplayLimits(rate=0.5, max_frame_bytes=8192, queue_packets=1, queue_wait_seconds=0.5)


@pytest.mark.asyncio
async def test_selected_target_declared_limits_shape_prefix(monkeypatch, virtual_clock):
    """A target declaring rate 0.5 / 8KiB frames / one outstanding packet is
    paced by its own declaration, not the requested family's 1x default."""

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
                    'id': 'modulate-slow',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'replay': {
                        'rate': 0.5,
                        'max_frame_bytes': 8192,
                        'queue_packets': 1,
                        'queue_wait_seconds': 0.5,
                    },
                },
            ]
        ),
    )
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    ring = sized_ring(135)
    actual._window_replay_audio = ring
    actual.capture_timeline = CaptureTimeline(sample_rate=SAMPLE_RATE)
    captured = b''.join(data for _, data in ring.snapshot())
    actual.capture_timeline.accept(captured, 1000.0, 1.0)
    dialed = []

    async def dial(callback, *args, **kwargs):
        target = connecting_target.get()
        transport = Transport()
        transport.timer = virtual_clock
        raw = SafeModulateSocket(transport, callback, asyncio.get_running_loop())
        raw._routing_target_entry = target
        dialed.append(raw)
        return raw

    monkeypatch.setattr(st, 'process_audio_modulate', dial)
    labels = dict(source='parakeet', successor='modulate')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    try:
        assert await actual._failover_stt_socket()
        raw = dialed[-1]
        expected = captured[-10 * BYTES_PER_SECOND :]
        await until(lambda: raw._ws.byte_count == len(expected))
        assert raw._ws.pcm == expected
        assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == pytest.approx(125.0)
        assert all(len(frame) <= 8192 for frame in raw._ws.sent if isinstance(frame, bytes))
        assert raw._send_queue.high_water <= 1
        assert raw._ws.sent_at[1] - raw._ws.sent_at[0] >= 0.5
        assert not raw.is_connection_dead
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            await actual._drain_stt_sockets()
        await stop(dialed)


def test_birth_ledger_gapped_bound_overlap_prune_and_single_meter(virtual_clock):
    """Hard bound holds for ANY interval shape; overlap extends with the first
    admission; pruning clips the leading start; expiry meters exactly once."""

    ledger = BirthLedger()
    for n in range(BIRTH_LEDGER_MAX + 1):
        ledger.note(n * 960, n * 960 + 480, virtual_clock.now)
    assert len(ledger) <= BIRTH_LEDGER_MAX

    overlap = BirthLedger()
    assert overlap.note(0, 480, born=5.0) == 5.0
    assert overlap.note(240, 960, born=9.0) == 5.0
    assert overlap.lookup(700) == 5.0

    clipped = BirthLedger()
    clipped.note(0, 960, born=1.0)
    clipped.prune_before(480)
    assert clipped.lookup(481) == 1.0

    ring = ResilientAudio(16000, ring_seconds=150, strict_replay=True)
    ring.append(b'\x01\x00' * 480, 0)
    labels = dict(source='parakeet', successor='soniox')
    before = REPLAY_SKIPPED.labels(**labels)._value.get()
    assert replay_delivery.bounded_snapshot(ring, 'parakeet', 'soniox', wall_seconds=0) == ()
    delta = REPLAY_SKIPPED.labels(**labels)._value.get() - before
    assert delta == pytest.approx(0.03)
    assert replay_delivery.bounded_snapshot(ring, 'parakeet', 'soniox', wall_seconds=0) == ()
    assert REPLAY_SKIPPED.labels(**labels)._value.get() - before == pytest.approx(0.03)

    expired = ResilientAudio(16000, ring_seconds=150, strict_replay=True)
    for n in range(4):
        expired.append(marker_chunk(n + 1), n * 480)
    births = BirthLedger()
    born = virtual_clock.now
    for n in range(4):
        births.note(n * 480, (n + 1) * 480, born - 60.0)
    before = REPLAY_SKIPPED.labels(**labels)._value.get()
    assert replay_delivery.bounded_snapshot(expired, 'parakeet', 'soniox', birth=births) == ()
    delta = REPLAY_SKIPPED.labels(**labels)._value.get() - before
    assert delta == pytest.approx(4 * 0.03)
    replay_delivery.bounded_snapshot(expired, 'parakeet', 'soniox', birth=births)
    assert REPLAY_SKIPPED.labels(**labels)._value.get() - before == pytest.approx(4 * 0.03)


@pytest.mark.slow
def test_bounded_recovery_capture_caps_bytes_and_entries(virtual_clock):
    """A 200s oversized burst inside blocked setup still lands under the
    recovery capture caps, and every dropped byte is reported for metering."""

    ring = ResilientAudio(16000, ring_seconds=150, strict_replay=True)
    packets = 200 * SAMPLE_RATE // 480
    dropped = 0
    for n in range(packets):
        dropped += ring.append_bounded(marker_chunk(n + 1), n * 480)
    assert ring.buffered_bytes <= 150 * BYTES_PER_SECOND
    assert len(ring.snapshot()) <= BIRTH_LEDGER_MAX
    retained = sum(len(data) for _, data in ring.snapshot())
    assert dropped + retained == packets * 960

    huge = ResilientAudio(16000, ring_seconds=150, strict_replay=True)
    dropped = huge.append_bounded(b'\x01\x00' * (160 * SAMPLE_RATE), 0)
    assert dropped == (160 - 150) * BYTES_PER_SECOND
    assert huge.buffered_bytes == 150 * BYTES_PER_SECOND


def tail_host():
    return SimpleNamespace(
        state=SimpleNamespace(active=True, stt_terminal_failure=False),
        spawn=lambda coro, name=None: asyncio.create_task(coro),
    )


def live_send_compat(raw):
    send = raw.send
    raw.send = lambda data, start_sample=None: send(data)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
@pytest.mark.parametrize('budget', [lambda: None, lambda: 45.0])
async def test_queued_live_frame_never_writes_past_capture_age_deadline(monkeypatch, virtual_clock, kind, budget):
    """A frame born at capture time 0 and admitted at 27.5s cannot complete a
    wire write after its 28s residence bound — even when the episode budget
    itself is unlimited or already released by proof text."""

    monkeypatch.setattr(st, 'clock', lambda: virtual_clock.now)
    monkeypatch.setattr(soniox_module, 'clock', lambda: virtual_clock.now)
    transport = Transport()
    transport.timer = virtual_clock
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    live_send_compat(raw)
    enable_recovery_writer_pace(raw, SAMPLE_RATE, ReplayLimits(), budget)
    birth = BirthLedger()
    delivery = ReplayTailSocket(
        raw,
        ReplayPacer(SAMPLE_RATE, 'soniox' if kind is SafeSonioxSocket else 'modulate', raw),
        deque(),
        tail_host(),
        birth=birth,
    )
    try:
        assert birth.note(0, 1600) == 0.0
        virtual_clock.now = 27.5
        transport.gate.clear()
        assert delivery.send(b'\x01\x00' * 1600, 0)
        delivery.start_tail()
        await until(lambda: raw._send_queue.inflight == 1)
        asyncio.create_task(virtual_clock.sleep(1.0))
        await asyncio.sleep(0.7)
        assert raw.typed_death_reason == 'capacity_full'
        assert transport.pcm == b''
        assert all(stamp <= 28.0 for stamp in transport.sent_at)
        assert raw.is_connection_dead
        assert live_stt_terminal_reason(raw, 'send_failed') == 'capacity_full'
        assert provider_observation('failover', 'capacity_full') is None
    finally:
        transport.gate.set()
        await abort_replay_socket(delivery)
        assert transport.closed
        assert raw._send_task.done() and raw._recv_task.done()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_expired_tail_packet_retires_once_and_fresh_suffix_continues(virtual_clock, kind):
    """A tail packet whose residence bound passes before admission is retired
    through the metered cut exactly once; a younger packet still ships."""

    transport = Transport()
    transport.timer = virtual_clock
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    live_send_compat(raw)
    enable_recovery_writer_pace(raw, SAMPLE_RATE, ReplayLimits(), lambda: None)
    birth = BirthLedger()
    retired = []
    successor = 'soniox' if kind is SafeSonioxSocket else 'modulate'
    delivery = ReplayTailSocket(
        raw,
        ReplayPacer(SAMPLE_RATE, successor, raw),
        deque(),
        tail_host(),
        birth=birth,
        retire_interval=lambda end: retired.append(end) or 0,
    )
    labels = dict(source=delivery.source, successor=successor)
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    old = b'\x01\x00' * 1600
    fresh = b'\x02\x00' * 1600
    try:
        assert birth.note(0, 1600) == 0.0
        assert delivery.send(old, 0)
        virtual_clock.now = 28.1
        assert delivery.send(fresh, 3200)
        delivery.start_tail()
        await until(lambda: transport.pcm == fresh)
        assert retired == [1600]
        assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == pytest.approx(
            len(old) / BYTES_PER_SECOND
        )
        assert not raw.is_connection_dead
        assert raw.typed_death_reason != 'capacity_full'
    finally:
        await abort_replay_socket(delivery)
        assert raw._send_task.done() and raw._recv_task.done()


def test_birth_lookup_inside_a_partially_pruned_chunk_keeps_first_stamp(virtual_clock):
    births = BirthLedger()
    assert births.note(0, 6400, born=0.0) == 0.0
    births.prune_before(3200)
    assert births.lookup(4000) == 0.0
    virtual_clock.now = 10.0
    assert births.note(3200, 6400) == 0.0
    assert births.lookup(5000) == 0.0


@pytest.mark.asyncio
async def test_half_rate_pacer_drops_a_slot_past_the_packet_deadline(virtual_clock):
    transport = Transport()
    transport.timer = virtual_clock
    raw = SafeSonioxSocket(transport, lambda _: None, asyncio.get_running_loop())
    raw.replay_send = lambda data, start: raw.send(data)
    live_send_compat(raw)
    limits = ReplayLimits(rate=0.5)
    pacer = ReplayPacer(SAMPLE_RATE, 'soniox', raw, limits=limits)
    frame = b'\x01\x00' * 16384
    try:
        assert await pacer.send(raw, frame, 0, lambda: True, replay=True)
        driver = asyncio.create_task(virtual_clock.sleep(0.5))
        assert not await pacer.send(raw, frame, 16384, lambda: True, replay=False, deadline=virtual_clock.now + 0.4)
        await driver
        assert len([data for data in transport.sent if isinstance(data, bytes)]) == 1
    finally:
        await abort_replay_socket(raw)


def test_send_queue_deadline_metadata_only_tracks_successful_audio_puts():
    queue = AudioSendQueue(maxsize=2)
    queue.put_nowait(b'\x01\x00')
    assert list(queue._deadlines) == [None]
    token = audio_send_deadline.set(28.0)
    try:
        queue.put_nowait(b'\x02\x00')
        with pytest.raises(asyncio.QueueFull):
            queue.put_nowait(b'\x03\x00')
    finally:
        audio_send_deadline.reset(token)
    assert list(queue._deadlines) == [None, 28.0]
    assert len(queue._deadlines) == queue.qsize() == 2
    queue.get_nowait()
    assert queue.inflight_deadline is None
    queue.get_nowait()
    assert queue.inflight_deadline == 28.0
    queue.note_written(b'\x02\x00')
    assert queue.inflight_deadline is None
    assert len(queue._deadlines) == queue.qsize() == 0
    token = audio_send_deadline.set(28.0)
    try:
        queue.put_nowait('{"type":"finalize"}')
    finally:
        audio_send_deadline.reset(token)
    assert list(queue._deadlines) == [None]


@pytest.mark.asyncio
async def test_abort_replay_socket_spends_one_budget_across_held_cleanup(virtual_clock):
    class HeldTransport(Transport):
        def __init__(self):
            super().__init__()
            self.aborted = False
            self.close_calls = 0

        async def close(self):
            self.close_calls += 1
            await asyncio.Event().wait()

        def abort(self):
            self.aborted = True
            self.closed = True

    transport = HeldTransport()
    raw = SafeSonioxSocket(transport, lambda _: None, asyncio.get_running_loop())
    await until(lambda: raw._send_task is not None and raw._recv_task is not None)
    await abort_replay_socket(raw, timeout=0.001)
    assert transport.aborted
    assert transport.closed
    await until(lambda: raw._send_task.done() and raw._recv_task.done())


@pytest.mark.asyncio
async def test_abort_replay_socket_closes_transport_when_finish_raises(virtual_clock):
    class HeldTransport(Transport):
        async def close(self):
            await asyncio.Event().wait()

        def abort(self):
            self.closed = True

    transport = HeldTransport()
    raw = SafeModulateSocket(transport, lambda _: None, asyncio.get_running_loop())
    raw.finish = lambda: (_ for _ in ()).throw(RuntimeError('synthetic finish failure'))
    await abort_replay_socket(raw, timeout=0.001)
    assert transport.closed
    await until(lambda: raw._send_task.done() and raw._recv_task.done())


@pytest.mark.asyncio
async def test_write_bound_returns_exact_positive_bound(virtual_clock):
    """Sub-millisecond remaining budget/deadline returns the exact bound —
    never rounded up into a send that outlives the packet's deadline."""
    pace = RecoveryWriterPace(SAMPLE_RATE, 1.0)
    assert pace.write_bound() == WRITER_SLOT_SECONDS

    bounded = RecoveryWriterPace(SAMPLE_RATE, 1.0, budget=lambda: 0.5)
    assert bounded.write_bound() == 0.5
    tight = RecoveryWriterPace(SAMPLE_RATE, 1.0, budget=lambda: 0.0004)
    assert tight.write_bound() == 0.0004
    assert tight.write_bound() < 0.001

    deadline_pace = RecoveryWriterPace(SAMPLE_RATE, 1.0)
    assert deadline_pace.write_bound(deadline=virtual_clock.now + 0.0004) == 0.0004
    budgeted = RecoveryWriterPace(SAMPLE_RATE, 1.0, budget=lambda: 1.5)
    assert budgeted.write_bound(deadline=virtual_clock.now + 0.25) == 0.25


@pytest.mark.asyncio
async def test_write_bound_rejects_spent_budget_and_deadline(virtual_clock):
    spent = RecoveryWriterPace(SAMPLE_RATE, 1.0, budget=lambda: 0.0)
    with pytest.raises(TimeoutError):
        spent.write_bound()
    overdrawn = RecoveryWriterPace(SAMPLE_RATE, 1.0, budget=lambda: -1.0)
    with pytest.raises(TimeoutError):
        overdrawn.write_bound()

    pace = RecoveryWriterPace(SAMPLE_RATE, 1.0)
    with pytest.raises(AudioDeliveryExpired):
        pace.write_bound(deadline=virtual_clock.now)
    with pytest.raises(AudioDeliveryExpired):
        pace.write_bound(deadline=virtual_clock.now - 0.001)


@pytest.mark.parametrize('terminal', [RecoveryState.exhausted, RecoveryState.client_leaving])
def test_late_candidate_text_never_releases_terminal_episode(terminal):
    """A retired leg's late transcript must not flip a settled terminal or
    departing episode back to recovered."""
    host = SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)
    controller = recovery_state.LiveRecoveryController(host)
    token = object()
    controller.begin(family='modulate')
    controller.set_candidate(token)
    controller.adopted(token)
    controller.state = terminal
    controller.note_transcript(True, candidate=token)
    assert controller.state is terminal
    assert controller.deadline is not None


def test_late_transcript_during_client_departure_latches_leaving():
    """Candidate text arriving while the owner is leaving latches
    client_leaving — it must never settle the episode as recovered."""
    host = SimpleNamespace(state=SimpleNamespace(active=False, shutdown_event=None), request=None)
    controller = recovery_state.LiveRecoveryController(host)
    token = object()
    controller.begin(family='modulate')
    controller.set_candidate(token)
    controller.adopted(token)
    controller.note_transcript(True, candidate=token)
    assert controller.state is RecoveryState.client_leaving
    assert controller.deadline is not None


def test_exhaust_does_not_overwrite_a_departed_client():
    """A departure that wins the episode-deadline race stays client_leaving;
    a terminal exhausted decision still stands if the client leaves after."""
    host = SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)

    departed = recovery_state.LiveRecoveryController(host)
    departed.begin(family='modulate')
    host.state.active = False
    departed.exhaust()
    assert departed.state is RecoveryState.client_leaving

    leaving = recovery_state.LiveRecoveryController(
        SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)
    )
    leaving.begin(family='modulate')
    leaving.mark_client_leaving()
    leaving.exhaust()
    assert leaving.state is RecoveryState.client_leaving

    settled = recovery_state.LiveRecoveryController(
        SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)
    )
    settled.begin(family='modulate')
    settled.exhaust()
    assert settled.state is RecoveryState.exhausted
    settled.mark_client_leaving()
    assert settled.state is RecoveryState.exhausted


@pytest.mark.asyncio
async def test_abort_replay_socket_falls_back_to_inner_transport_abort(virtual_clock):
    """A real websockets connection exposes ``.transport.abort()`` instead of
    a top-level ``abort``; a refused/late close still aborts within the same
    total cleanup deadline."""

    class RealShapeTransport(Transport):
        def __init__(self):
            super().__init__()
            self.inner_aborted = False
            self.transport = SimpleNamespace(abort=lambda: setattr(self, 'inner_aborted', True))

        async def close(self):
            raise OSError('synthetic close failure')

    transport = RealShapeTransport()
    raw = SafeSonioxSocket(transport, lambda _: None, asyncio.get_running_loop())
    await until(lambda: raw._send_task is not None and raw._recv_task is not None)
    await abort_replay_socket(raw, timeout=0.001)
    assert transport.inner_aborted
    await until(lambda: raw._send_task.done() and raw._recv_task.done())


def _reconnect_receiver(monkeypatch):
    listener = make_receiver(monkeypatch)
    old = serving_leg(family='soniox')
    old.raw.die('soniox_rotation')
    listener.stt_socket = old
    listener._resilient_audio.append(b'\x00\x00', 0)
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    return listener, old


@pytest.mark.asyncio
async def test_same_provider_reconnect_hung_dial_cancels_inside_dial_budget(monkeypatch):
    """A hung connect is cancelled by the episode's dial budget; the failed
    reconnect reports and returns False so the caller walks on."""
    listener, old = _reconnect_receiver(monkeypatch)
    monkeypatch.setattr(recovery_state, 'RECOVERY_DIAL_SECONDS', 0.001)

    async def hang(*args, **kwargs):
        await asyncio.Event().wait()

    hung = AsyncMock(side_effect=hang)
    listener._create_stt_socket = hung
    try:
        assert not await resilient_stream.reconnect_live_stt_socket(listener)
        hung.assert_awaited_once()
    finally:
        old.finish()


@pytest.mark.asyncio
async def test_same_provider_reconnect_serving_check_shares_dial_budget(monkeypatch, virtual_clock):
    """The connect and the serving probe draw one episode-bound budget: with
    the episode nearly spent a hung serving check is refused, and the episode
    deadline is never reset."""
    listener, old = _reconnect_receiver(monkeypatch)
    listener.recovery.begin(old, 'soniox')
    deadline = listener.recovery.deadline
    virtual_clock.now = deadline - 0.2
    assert listener.recovery.dial_budget() == pytest.approx(0.2)
    new = serving_leg(family='soniox')
    listener._create_stt_socket = AsyncMock(return_value=new)
    listener._wrap_legacy_stt_socket = lambda raw, epoch: raw

    async def hang(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(resilient_stream, 'fallback_socket_is_serving', hang)
    try:
        assert not await resilient_stream.reconnect_live_stt_socket(listener)
        listener._create_stt_socket.assert_awaited_once()
        assert listener.recovery.deadline == deadline
    finally:
        old.finish()
        new.finish()


def _seam_controller(ticks):
    host = SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)
    return recovery_state.LiveRecoveryController(host, clock=lambda: ticks[0])


def test_healthy_connection_releases_only_at_five_seconds_adopted_dwell():
    """The dwell boundary is exact: 4.999s holds the deadline, 5.0s releases."""
    ticks = [0.0]
    controller = _seam_controller(ticks)
    token = object()
    controller.begin(family='soniox')
    controller.set_candidate(token)
    controller.adopted(token)
    ticks[0] = 4.999
    controller.note_healthy_connection(token)
    assert controller.deadline is not None
    assert controller.state is not RecoveryState.recovered
    ticks[0] = 5.0
    controller.note_healthy_connection(token)
    assert controller.deadline is None
    assert controller.state is RecoveryState.recovered


def test_stale_candidate_health_and_unadopted_health_never_release():
    ticks = [0.0]
    controller = _seam_controller(ticks)
    current, stale = object(), object()
    controller.begin(family='soniox')
    controller.set_candidate(current)
    controller.adopted(current)
    ticks[0] = 60.0
    controller.note_healthy_connection(stale)
    assert controller.deadline is not None
    assert controller.state is not RecoveryState.recovered

    unadopted = _seam_controller(ticks)
    unadopted.begin(family='soniox')
    unadopted.set_candidate(current)
    unadopted.note_healthy_connection(current)
    assert unadopted.deadline is not None
    assert unadopted.state is not RecoveryState.recovered


def test_set_candidate_restarts_the_adoption_dwell():
    ticks = [0.0]
    controller = _seam_controller(ticks)
    first, second = object(), object()
    controller.begin(family='soniox')
    controller.set_candidate(first)
    controller.adopted(first)
    ticks[0] = 4.0
    controller.set_candidate(second)
    controller.adopted(second)
    ticks[0] = 8.999
    controller.note_healthy_connection(second)
    assert controller.deadline is not None
    ticks[0] = 9.0
    controller.note_healthy_connection(second)
    assert controller.state is RecoveryState.recovered


def test_idempotent_adoption_does_not_extend_the_dwell():
    ticks = [0.0]
    controller = _seam_controller(ticks)
    token = object()
    controller.begin(family='soniox')
    controller.set_candidate(token)
    controller.adopted(token)
    ticks[0] = 4.0
    controller.adopted(token)
    ticks[0] = 5.0
    controller.note_healthy_connection(token)
    assert controller.state is RecoveryState.recovered


def test_departure_and_terminal_states_win_over_healthy_release():
    ticks = [0.0]
    leaving = _seam_controller(ticks)
    token = object()
    leaving.begin(family='soniox')
    leaving.set_candidate(token)
    leaving.adopted(token)
    leaving.mark_client_leaving()
    ticks[0] = 30.0
    leaving.note_healthy_connection(token)
    assert leaving.state is RecoveryState.client_leaving
    assert leaving.deadline is not None

    exhausted = _seam_controller(ticks)
    exhausted.begin(family='soniox')
    exhausted.set_candidate(token)
    exhausted.adopted(token)
    exhausted.exhaust()
    exhausted.note_healthy_connection(token)
    assert exhausted.state is RecoveryState.exhausted
    assert exhausted.deadline is not None


def test_healthy_release_keeps_session_attempt_and_reentry_state():
    """Episode budget resets per fresh death; the session's unique-target
    ledger, dial count and one Soniox repeat grant carry across episodes."""
    ticks = [0.0]
    controller = _seam_controller(ticks)
    token = object()
    controller.begin(family='parakeet')
    assert controller.episode_count == 1
    controller.set_candidate(token)
    controller.reserve('soniox', 'soniox')
    controller.grant_soniox_reentry('soniox')
    controller.adopted(token)
    ticks[0] = 6.0
    controller.note_healthy_connection(token)
    assert controller.state is RecoveryState.recovered
    controller.begin(family='soniox')
    assert controller.episode_count == 2
    assert controller.attempted_targets == {'soniox'}
    assert controller.dial_attempts == 1
    assert controller.can_attempt('soniox')


def test_episode_cap_exhausts_a_new_episode_without_dialing(monkeypatch):
    """The 20-episode session bound refuses a further fresh deadline; opening
    it exhausts rather than spending another dial."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_EPISODES', 2)
    ticks = [0.0]
    controller = _seam_controller(ticks)
    token = object()
    for _ in range(2):
        controller.begin(family='soniox')
        controller.set_candidate(token)
        controller.adopted(token)
        controller.note_transcript(True, candidate=token)
        assert controller.state is RecoveryState.recovered
    assert controller.episode_count == 2
    controller.begin(family='soniox')
    assert controller.episode_count == 2
    assert controller.state is RecoveryState.exhausted
    assert not controller.can_attempt('modulate-velma-2')
    assert not controller.admission_open()

    departed = _seam_controller(ticks)
    departed.begin(family='soniox')
    departed.set_candidate(token)
    departed.adopted(token)
    departed.note_transcript(True, candidate=token)
    departed.mark_client_leaving()
    departed.begin(family='soniox')
    assert departed.state is RecoveryState.client_leaving


@pytest.mark.asyncio
@pytest.mark.parametrize('successor,follower', [('soniox', 'modulate-velma-2'), ('modulate-velma-2', 'soniox')])
async def test_silent_adopted_successor_recovers_on_healthy_dwell_then_walks_on_death(
    monkeypatch, virtual_clock, successor, follower
):
    """Luna's silent-successor regression: an adopted successor that emits no
    transcript still proves recovery after five connected seconds — the real
    death monitor observes the live socket — and its later death opens a
    FRESH episode that dials the untried provider."""

    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', successor, follower])
    actual._window_replay_started = True
    websocket = actual.host.request.websocket
    websocket.client_state = WebSocketState.CONNECTED
    websocket.application_state = WebSocketState.CONNECTED
    kept = b''.join(data for _, data in actual._window_replay_audio.snapshot())[-PREFIX_SECONDS * BYTES_PER_SECOND :]

    async def wait(seconds):
        await virtual_clock.sleep(seconds)
        return False

    actual.host.wait = wait
    monitor = asyncio.create_task(actual._monitor_stt_death())
    successor_kind = SafeSonioxSocket if successor == 'soniox' else SafeModulateSocket
    follower_kind = SafeSonioxSocket if follower == 'soniox' else SafeModulateSocket
    try:
        kill_source(actual, 'parakeet-window')
        assert await actual._failover_stt_socket()
        successor_raw = raws[-1]
        assert isinstance(successor_raw, successor_kind)
        original_deadline = actual.recovery.deadline
        assert original_deadline is not None
        assert actual.recovery.episode_count == 1
        await until(lambda: successor_raw._ws.byte_count == len(kept))
        assert successor_raw._ws.pcm == kept
        assert websocket.client_state is WebSocketState.CONNECTED
        assert websocket.application_state is WebSocketState.CONNECTED
        await virtual_clock.sleep(5.0)
        await until(lambda: actual.recovery.deadline is None)
        assert actual.recovery.state is RecoveryState.recovered
        assert not legs[0].leg_outcome.settled
        await virtual_clock.sleep(56.0)
        assert virtual_clock.now >= original_deadline
        assert actual.recovery.state is RecoveryState.recovered
        assert actual.host.state.active
        websocket.close.assert_not_awaited()
        dead_at = virtual_clock.now
        kill_source(actual, successor)
        assert await actual._failover_stt_socket()
        follower_raw = raws[-1]
        assert isinstance(follower_raw, follower_kind)
        assert actual.recovery.episode_count == 2
        assert actual.recovery.deadline - dead_at == pytest.approx(60.0, abs=1.0)
        assert actual.recovery.deadline > original_deadline
        await until(lambda: follower_raw._ws.byte_count == len(kept))
        assert follower_raw._ws.pcm == kept
        assert websocket.client_state is WebSocketState.CONNECTED
        assert websocket.application_state is WebSocketState.CONNECTED
        assert not actual.stt_socket.is_connection_dead
        assert not actual.host.state.stt_terminal_failure
        follower_raw._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 0.5, 'speaker': 'speaker_0'}])
        assert actual.recovery.state is RecoveryState.recovered
        await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
        actual.host.state.active = False
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('successor,follower', [('soniox', 'modulate-velma-2'), ('modulate-velma-2', 'soniox')])
async def test_successor_death_before_healthy_dwell_shares_the_original_episode(
    monkeypatch, virtual_clock, successor, follower
):
    """Inverse of the healthy-dwell case: a successor dying two seconds after
    adoption keeps the ORIGINAL deadline and episode count — the walk to the
    next provider spends the same budget, never a fresh 60s."""

    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', successor, follower])
    actual._window_replay_started = True
    websocket = actual.host.request.websocket
    websocket.client_state = WebSocketState.CONNECTED
    websocket.application_state = WebSocketState.CONNECTED
    follower_kind = SafeSonioxSocket if follower == 'soniox' else SafeModulateSocket
    try:
        kill_source(actual, 'parakeet-window')
        assert await actual._failover_stt_socket()
        original_deadline = actual.recovery.deadline
        assert original_deadline is not None
        assert websocket.client_state is WebSocketState.CONNECTED
        assert websocket.application_state is WebSocketState.CONNECTED
        await virtual_clock.sleep(2.0)
        kill_source(actual, successor)
        assert await actual._failover_stt_socket()
        assert isinstance(raws[-1], follower_kind)
        assert actual.recovery.episode_count == 1
        assert actual.recovery.deadline == original_deadline
        assert websocket.client_state is WebSocketState.CONNECTED
        assert websocket.application_state is WebSocketState.CONNECTED
        assert not actual.stt_socket.is_connection_dead
        assert not actual.host.state.stt_terminal_failure
        raws[-1]._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 0.5, 'speaker': 'speaker_0'}])
        assert actual.recovery.state is RecoveryState.recovered
        await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
        await stop(raws)


@pytest.mark.asyncio
async def test_receiver_returns_false_when_episode_cap_refuses_a_fresh_episode(monkeypatch, virtual_clock):
    """Cap-1 session: once the first episode releases, the next real dead
    socket cannot open a new one — _failover_stt_socket returns False
    before touching reconnect or rebuild."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_EPISODES', 1)
    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', 'soniox'])
    actual._window_replay_started = True
    try:
        kill_source(actual, 'parakeet-window')
        assert await actual._failover_stt_socket()
        raws[-1]._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 0.5, 'speaker': 'speaker_0'}])
        assert actual.recovery.episode_count == 1
        assert actual.recovery.deadline is None

        reconnect = AsyncMock(return_value=True)
        rebuild = AsyncMock(return_value=True)
        monkeypatch.setattr(actual, '_reconnect_stt_socket_locked', reconnect)
        monkeypatch.setattr(actual, '_rebuild_stt_socket_locked', rebuild)
        kill_source(actual, 'soniox')
        assert await actual._failover_stt_socket() is False
        assert actual.recovery.state is RecoveryState.exhausted
        reconnect.assert_not_awaited()
        rebuild.assert_not_awaited()
        await actual._drain_stt_sockets()
        assert_legs_drained(legs, observations)
    finally:
        await stop(raws)


@pytest.mark.asyncio
async def test_departed_receiver_latches_leaving_before_the_episode_cap(monkeypatch, virtual_clock):
    """Owner departure evidence wins on the cap boundary: begin latches
    client_leaving rather than exhausted."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_EPISODES', 1)
    actual = dead_receiver()
    actual.host.state.active = False
    reconnect = AsyncMock(return_value=True)
    rebuild = AsyncMock(return_value=True)
    monkeypatch.setattr(actual, '_reconnect_stt_socket_locked', reconnect)
    monkeypatch.setattr(actual, '_rebuild_stt_socket_locked', rebuild)
    assert await actual._failover_stt_socket() is False
    assert actual.recovery.state is RecoveryState.client_leaving
    reconnect.assert_not_awaited()
    rebuild.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('rejection', ['exception', 'frame'])
async def test_soniox_429_surge_rejected_sessions_walk_once_without_shared_bench(monkeypatch, virtual_clock, rejection):
    """40 dead Modulate sources surge behind a full Parakeet window: all 40
    dial Soniox once behind one barrier; a deterministic 20 are refused with
    transient 429s (connect exception, or a real post-upgrade error frame)
    and each takes exactly one extra Deepgram dial inside the same episode,
    while the other 20 serve on Soniox. No shared selection bench or
    quarantine is raised for a 429, so a NEW session still dials Soniox.

    This is a capacity-error recovery proof over fake providers — not a
    claim that the production Deepgram account is funded for the wave."""

    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '0')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '8')
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'test')
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox', 'dg-nova-3'])
    monkeypatch.setattr(live_chain.health, 'has_fresh_fleet_snapshot', lambda: False)
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *args: {})
    monkeypatch.setattr(live_router, '_capacity_until', {})
    admission = window.WindowAdmission()
    monkeypatch.setattr(window, 'admission', admission)
    releases = [admission.acquire() for _ in range(8)]
    window_connect = AsyncMock(side_effect=AssertionError('full window must be skipped'))
    monkeypatch.setattr(window, 'connect_window', window_connect)
    quarantined = []
    monkeypatch.setattr(live_chain.health, 'quarantine', lambda *args, **kwargs: quarantined.append(args) or True)

    soniox_dials = {}
    episode_deadlines = {}
    dg_dials = {}
    soniox_raws = []
    started = asyncio.Event()
    barrier = asyncio.Event()
    wave = [0]

    async def soniox(callback, *args, **kwargs):
        controller = current_recovery.get()
        index = wave[0]
        wave[0] += 1
        soniox_dials.setdefault(controller, []).append(index)
        episode_deadlines[controller] = controller.deadline
        if wave[0] == 40:
            started.set()
        await barrier.wait()
        rejected = index < 40 and index % 2 == 0
        if rejected and rejection == 'exception':
            raise SonioxRateLimitError('transient')
        raw = SafeSonioxSocket(Transport(), callback, asyncio.get_running_loop())
        soniox_raws.append(raw)
        if rejected:
            raw._ws.inbound.put_nowait(json.dumps({'error_code': 429, 'error_type': 'concurrency_limit_exceeded'}))
            await until(lambda: raw.is_connection_dead)
            assert raw.typed_death_reason == 'provider_rate_limited'
        return raw

    async def deepgram(callback, *args, **kwargs):
        controller = current_recovery.get()
        dg_dials.setdefault(controller, []).append(1)
        return Replacement(callback)

    monkeypatch.setattr(st, 'process_audio_soniox', soniox)
    monkeypatch.setattr(st, 'process_audio_dg', deepgram)

    actuals = [dead_receiver() for _ in range(40)]
    tasks = []
    try:
        for actual in actuals:
            websocket = actual.host.request.websocket
            websocket.client_state = WebSocketState.CONNECTED
            websocket.application_state = WebSocketState.CONNECTED
            actual.recovery.mark_attempted('modulate-velma-2')
        tasks = [asyncio.create_task(actual._failover_stt_socket()) for actual in actuals]
        await until(lambda: started.is_set() or all(task.done() for task in tasks))
        barrier.set()
        assert await asyncio.gather(*tasks) == [True] * 40
        assert len(soniox_dials) == 40
        assert all(len(dials) == 1 for dials in soniox_dials.values())
        assert sum(len(dials) for dials in dg_dials.values()) == 20
        assert all(len(dials) == 1 for dials in dg_dials.values())
        window_connect.assert_not_called()
        assert not [call for call in quarantined if call and call[0] == 'soniox']
        for actual in actuals:
            websocket = actual.host.request.websocket
            assert websocket.client_state is WebSocketState.CONNECTED
            assert websocket.application_state is WebSocketState.CONNECTED
            websocket.close.assert_not_awaited()
            controller = actual.recovery
            assert not actual.host.state.stt_terminal_failure
            assert controller.episode_count == 1
            assert not actual.stt_socket.is_connection_dead
            assert len(soniox_dials.get(controller, ())) == 1
            assert controller.deadline == episode_deadlines[controller]
            assert controller.deadline - virtual_clock.now > 0
            if dg_dials.get(controller):
                assert actual.host.stt_service == st.STTService.deepgram
                assert controller.dial_attempts == 3, sorted(controller.attempted_targets)
            else:
                assert actual.host.stt_service == st.STTService.soniox
                assert controller.dial_attempts == 2, sorted(controller.attempted_targets)
        assert st._soniox_circuit.state == 'closed'
        assert st._soniox_circuit._failures == 0
        fresh = dead_receiver()
        fresh.host.request.websocket.client_state = WebSocketState.CONNECTED
        fresh.host.request.websocket.application_state = WebSocketState.CONNECTED
        fresh.recovery.mark_attempted('modulate-velma-2')
        actuals.append(fresh)
        assert await fresh._failover_stt_socket()
        assert fresh.host.stt_service == st.STTService.soniox
        assert len(soniox_dials.get(fresh.recovery, ())) == 1
        assert wave[0] == 41
    finally:
        barrier.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for actual in actuals:
            actual.stt_socket.finish()
            await actual._drain_stt_sockets()
        await stop(soniox_raws)
        for raw in soniox_raws:
            assert raw._send_task.done() and raw._recv_task.done()
            assert raw._ws.closed
        for release in releases:
            release()


@pytest.mark.asyncio
async def test_sustained_soniox_429_storm_skips_then_probe_recovers(monkeypatch, virtual_clock):
    """A sustained post-upgrade 429 storm opens the per-target connect backoff:
    a fresh session skips the Soniox dial entirely (no recovery dial budget is
    spent on it), and after the short cooldown one exclusive probe re-tests
    Soniox; its success resets the gate so the next session dials it again."""

    backoff = ConnectRefusalBackoff(clock=lambda: virtual_clock.now)
    monkeypatch.setattr(live_chain, 'connect_backoff', lambda: backoff)
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '0')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '8')
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'test')
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox', 'dg-nova-3'])
    monkeypatch.setattr(live_chain.health, 'has_fresh_fleet_snapshot', lambda: False)
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *args: {})
    monkeypatch.setattr(live_router, '_capacity_until', {})
    admission = window.WindowAdmission()
    monkeypatch.setattr(window, 'admission', admission)
    releases = [admission.acquire() for _ in range(8)]
    window_connect = AsyncMock(side_effect=AssertionError('full window must be skipped'))
    monkeypatch.setattr(window, 'connect_window', window_connect)

    soniox_raws = []
    soniox_dials = {}

    async def soniox(callback, *args, **kwargs):
        controller = current_recovery.get()
        soniox_dials.setdefault(controller, []).append(1)
        raw = SafeSonioxSocket(Transport(), callback, asyncio.get_running_loop())
        soniox_raws.append(raw)
        if len(soniox_dials) <= 3:
            raw._ws.inbound.put_nowait(json.dumps({'error_code': 429, 'error_type': 'concurrency_limit_exceeded'}))
            await until(lambda: raw.is_connection_dead)
            assert raw.typed_death_reason == 'provider_rate_limited'
        return raw

    async def deepgram(callback, *args, **kwargs):
        return Replacement(callback)

    monkeypatch.setattr(st, 'process_audio_soniox', soniox)
    monkeypatch.setattr(st, 'process_audio_dg', deepgram)

    def fresh_receiver():
        actual = dead_receiver()
        websocket = actual.host.request.websocket
        websocket.client_state = WebSocketState.CONNECTED
        websocket.application_state = WebSocketState.CONNECTED
        actual.recovery.mark_attempted('modulate-velma-2')
        return actual

    actuals = [fresh_receiver() for _ in range(6)]
    try:
        for actual in actuals[:3]:
            assert await actual._failover_stt_socket()
            assert actual.host.stt_service == st.STTService.deepgram
            assert len(soniox_dials[actual.recovery]) == 1
            assert actual.recovery.dial_attempts == 3

        skipped = actuals[3]
        assert await skipped._failover_stt_socket()
        assert skipped.host.stt_service == st.STTService.deepgram
        assert skipped.recovery not in soniox_dials
        assert skipped.recovery.dial_attempts == 2
        assert skipped.recovery.attempted_targets == {'modulate-velma-2', 'deepgram'}

        virtual_clock.now += 1.0
        still_skipped = actuals[4]
        assert await still_skipped._failover_stt_socket()
        assert still_skipped.host.stt_service == st.STTService.deepgram
        assert still_skipped.recovery not in soniox_dials

        virtual_clock.now += 1.0
        probe = actuals[5]
        assert await probe._failover_stt_socket()
        assert probe.host.stt_service == st.STTService.soniox
        assert len(soniox_dials[probe.recovery]) == 1

        recovered = fresh_receiver()
        actuals.append(recovered)
        assert await recovered._failover_stt_socket()
        assert recovered.host.stt_service == st.STTService.soniox
        assert len(soniox_dials[recovered.recovery]) == 1
        for actual in actuals:
            assert not actual.host.state.stt_terminal_failure
            actual.host.request.websocket.close.assert_not_awaited()
    finally:
        for actual in actuals:
            if actual.stt_socket is not None:
                actual.stt_socket.finish()
            await actual._drain_stt_sockets()
        await stop(soniox_raws)
        for release in releases:
            release()


def skipped_totals() -> dict:
    return {
        tuple(sorted(sample.labels.items())): sample.value
        for family in REPLAY_SKIPPED.collect()
        for sample in family.samples
        if sample.name.endswith('_total')
    }


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize('successor', ['soniox', 'modulate-velma-2'])
async def test_exact_1x_live_stream_survives_oversleeping_pacing_timers(monkeypatch, virtual_clock, successor):
    """180 virtual seconds of exact-1x live PCM behind a 6s seeded ring while
    every positive pacing timer lands 15ms late. The adopted successor must
    hold a bounded tail on one dial with zero skipped audio and byte-exact
    prefix+live ordering; clock-anchored pacing fills the 26s tail, dies
    capacity_full, and exhausts the remaining targets."""

    monkeypatch.setattr(
        replay_delivery,
        'sleep',
        lambda seconds: virtual_clock.sleep(seconds + 0.015) if seconds > 0 else virtual_clock.sleep(seconds),
    )
    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', successor])
    ring = sized_ring(6)
    actual._window_replay_audio = ring
    actual._window_replay_started = True
    actual.capture_timeline = CaptureTimeline(sample_rate=SAMPLE_RATE)
    captured = b''.join(data for _, data in ring.snapshot())
    actual.capture_timeline.accept(captured, 1000.0, 1.0)
    kill_source(actual, 'parakeet-window')
    monkeypatch.setattr(actual, '_capture', lambda *args, **kwargs: None)
    frames = 180 * SAMPLE_RATE // 480
    skipped_before = skipped_totals()
    produced = bytearray()
    peak_tail = [0]
    emitted_end = [0.0]

    async def produce():
        raw = None
        for n in range(frames):
            chunk = marker_chunk(n + 1)
            start, _, _ = actual.capture_timeline.accept(chunk, 1006.0 + n * 0.03, 7.0 + n * 0.03)
            actual._stt_buffer_start_sample = start
            buffer = bytearray(chunk)
            await actual._flush_stt_buffer(buffer, force=True)
            produced.extend(chunk)
            if len(raws):
                raw = raws[-1]
                peak_tail[0] = max(
                    peak_tail[0],
                    actual._replay_tail_bytes + getattr(actual.stt_socket, '_tail_bytes', 0),
                )
                if n % 150 == 149 and raw._ws.byte_count // 2 > emitted_end[0] * SAMPLE_RATE:
                    emitted_end[0] = raw._ws.byte_count // 2 / SAMPLE_RATE
                    raw._stream_transcript(
                        [{'text': 'synthetic', 'start': 0.0, 'end': emitted_end[0], 'speaker': 'speaker_0'}]
                    )
            await virtual_clock.sleep(0.03)

    failover = asyncio.create_task(actual._failover_stt_socket())
    producer = asyncio.create_task(produce())
    try:
        await producer
        assert await failover
        assert len(raws) == 1
        raw = raws[-1]
        assert isinstance(raw, SafeSonioxSocket if successor == 'soniox' else SafeModulateSocket)
        assert not actual.host.state.stt_terminal_failure
        assert not actual.stt_socket.is_connection_dead
        actual.host.request.websocket.close.assert_not_awaited()
        assert raw._send_queue.high_water <= 2
        assert peak_tail[0] <= replay_delivery.LIVE_TAIL_SECONDS * SAMPLE_RATE * 2
        assert actual.recovery.state is RecoveryState.recovered
        assert actual.recovery.deadline is None
        assert len(base.emitted) >= 1
        expected = captured + bytes(produced)
        actual.host.state.active = False
        await actual._drain_stt_sockets()
        assert raw._ws.pcm == expected
        skips = {
            key: value - skipped_before.get(key, 0.0)
            for key, value in skipped_totals().items()
            if value - skipped_before.get(key, 0.0) > 1e-9
        }
        assert skips == {}, skips
        assert_legs_drained(legs, observations)
    finally:
        producer.cancel()
        failover.cancel()
        await asyncio.gather(producer, failover, return_exceptions=True)
        if actual.stt_socket is not None:
            actual.stt_socket.finish()
        await stop(raws)
