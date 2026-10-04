"""Deterministic paid-transport lifecycle using real gate and Soniox loops."""

import asyncio
import json
from collections import deque
from types import SimpleNamespace

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from config.soniox_idle import idle_close_seconds
from utils.stt import soniox, soniox_idle, vad_gate, live_metrics, live_session, replay_delivery
from utils.stt.streaming import STTService
from utils.stt.soniox import SafeSonioxSocket
from utils.stt.soniox_idle import IdleSonioxSocket
from utils.stt.vad_gate import GatedSTTSocket, VADStreamingGate
from utils.stt.live_failure import send_live_stt_audio


class Peer:
    def __init__(self):
        self.sent = []
        self.frames = asyncio.Queue()
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        frame = await self.frames.get()
        if frame is None:
            raise StopAsyncIteration
        return json.dumps(frame)

    async def send(self, data):
        self.sent.append(data)
        if data == '':
            self.frames.put_nowait({'finished': True})
        elif data == '{"type": "finalize"}':
            self.frames.put_nowait({'tokens': [{'text': '<fin>', 'is_final': True}]})

    async def close(self):
        self.closed = True
        self.frames.put_nowait(None)


def build(monkeypatch, seconds=2, fail=False):
    tick = [100.0]
    monkeypatch.setattr(soniox_idle.time, 'monotonic', lambda: tick[0])
    monkeypatch.setattr(vad_gate, '_get_ort_session', lambda: None)
    monkeypatch.setattr(VADStreamingGate, '_run_vad', lambda self, data: data[0] == 1)
    peers = [Peer()]
    seen = []
    raw = SafeSonioxSocket(peers[0], seen.extend, asyncio.get_running_loop())

    async def connect(callback):
        if fail:
            raise RuntimeError('dial failed')
        peer = Peer()
        peers.append(peer)
        return SafeSonioxSocket(peer, callback, asyncio.get_running_loop())

    idle = IdleSonioxSocket(raw, connect, seen.extend, 16000, seconds)
    gate = VADStreamingGate(sample_rate=16000, mode='active', hangover_ms=0)
    return GatedSTTSocket(idle, gate), idle, gate, peers, seen, tick


async def settle():
    # No wall sleeps or ONNX work: deterministic event-loop scheduling only.
    for _ in range(12):
        await asyncio.sleep(0)


@pytest.mark.parametrize('recovery', ['false', 'true'])
def test_silence_close_onset_exact_and_timestamp_continuity(monkeypatch, recovery):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', recovery)

    async def run():
        socket, idle, gate, peers, seen, tick = build(monkeypatch)
        speech = b'\x01\x00' * 1600
        silence = b'\x00\x00' * 1600
        assert socket.send(speech, wall_time=100, start_sample=0)
        idle._transport._handle_tokens([{'text': 'first ', 'is_final': True, 'start_ms': 0, 'end_ms': 100}])
        socket.send(silence, wall_time=100.1, start_sample=1600)
        tick[0] += 3
        socket.send(silence, wall_time=103.1, start_sample=49600)
        await idle._close_task
        assert peers[0].closed
        assert not socket.is_connection_dead
        assert socket.death_reason is None
        assert socket.typed_death_reason is None
        assert peers[0].sent[-2:] == ['{"type": "finalize"}', '']
        # The gate already holds the last silence PCM. Onset includes it once,
        # before the new speech frame, without decoder/resampler edits.
        pre_roll = b''.join(data for data, _ in gate._pre_roll)
        tick[0] += 20
        assert socket.send(speech, wall_time=123.1, start_sample=369600)
        assert len(peers) == 1
        assert await socket.complete_send()
        await settle()
        assert [x for x in peers[1].sent if isinstance(x, bytes)] == [pre_roll + speech]
        idle._transport._handle_tokens([{'text': 'next ', 'is_final': True, 'start_ms': 0, 'end_ms': 100}])
        gate.remap_segments(seen)
        assert seen[1]['start'] >= seen[0]['end']
        assert seen[1]['start'] > 20
        await idle.drain_and_close()
        assert not socket.is_connection_dead

    asyncio.run(run())


def test_failed_reopen_uses_normal_send_failover_boundary(monkeypatch):
    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch, fail=True)
        silence = b'\x00\x00' * 1600
        socket.send(silence, wall_time=100)
        tick[0] += 3
        socket.send(silence, wall_time=103)
        await idle._close_task
        fallback = []

        async def failover():
            fallback.append(True)
            return True

        state = SimpleNamespace(active=True, stt_terminal_failure=False)
        sent = await send_live_stt_audio(
            None,
            state,
            stt_socket=socket,
            audio=b'\x01\x00' * 1600,
            provider='soniox',
            platform='desktop',
            attempt_failover=failover,
        )
        assert not sent
        assert fallback == [True]
        assert idle.is_connection_dead
        assert not state.stt_terminal_failure
        assert len(peers) == 1
        await idle.drain_and_close()

    asyncio.run(run())


def test_end_while_idle_closed_never_reopens(monkeypatch):
    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103)
        await idle._close_task
        socket.finalize()
        socket.finish()
        await idle.drain_and_close()
        assert len(peers) == 1
        assert peers[0].closed
        assert not idle.is_connection_dead

    asyncio.run(run())


@pytest.mark.parametrize('value', ['', '0', '-1', 'nan', 'inf', 'invalid'])
def test_off_values_are_inert(monkeypatch, value):
    monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', value)
    assert idle_close_seconds() == 0


def test_off_returns_original_adapter_and_no_idle_series(monkeypatch):
    monkeypatch.setenv('SONIOX_API_KEY', 'fake')
    monkeypatch.delenv('SONIOX_IDLE_CLOSE_SECONDS', raising=False)
    registry = CollectorRegistry()
    monkeypatch.setattr(live_metrics, '_soniox_idle_metrics', None)
    monkeypatch.setattr(live_metrics, 'Counter', lambda *a, **kw: pytest.fail('off registered metric'))
    peers = []

    async def dial(*args, **kwargs):
        peer = Peer()
        peers.append(peer)
        return peer

    monkeypatch.setattr(soniox.websockets, 'connect', dial)

    async def run():
        socket = await soniox.process_audio_soniox(lambda _: None, 16000, 'en')
        assert type(socket) is SafeSonioxSocket
        socket.send(b'\x01\x00')
        socket.finalize()
        await socket.drain_and_close()
        assert peers[0].sent[1:] == [b'\x01\x00', '{"type": "finalize"}', '']

    asyncio.run(run())
    assert b'omi_soniox_idle' not in generate_latest(registry)


def test_shutdown_during_dial_cancels_and_reaps_owned_task(monkeypatch):
    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103)
        await idle._close_task
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def connect(callback):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        idle._connect = connect
        assert socket.send(b'\x01\x00' * 1600, wall_time=104)
        completion = asyncio.create_task(socket.complete_send())
        await entered.wait()
        await idle.drain_and_close()
        await asyncio.gather(completion, return_exceptions=True)
        assert cancelled.is_set()
        assert len(peers) == 1
        assert idle._reopen_task.done()
        assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    asyncio.run(run())


def test_failed_dial_preserves_preroll_through_actual_buffer_retry(monkeypatch):
    async def run():
        socket, idle, gate, _, _, tick = build(monkeypatch, fail=True)
        silence = b'\x00\x00' * 1600
        socket.send(silence, wall_time=100, start_sample=0)
        tick[0] += 3
        socket.send(silence, wall_time=103, start_sample=48000)
        await idle._close_task
        prefix = b''.join(data for data, _ in gate._pre_roll)
        delivered = []
        replacement = SimpleNamespace(
            is_connection_dead=False,
            send_admitted_audio=lambda data, spans: delivered.append((data, spans)) or True,
        )

        class Receiver:
            stt_socket = socket

            async def failover(self):
                self.stt_socket = replacement
                return True

        owner = Receiver()
        state = SimpleNamespace(active=True, stt_terminal_failure=False)
        onset = b'\x01\x00' * 1600
        assert not await send_live_stt_audio(
            None,
            state,
            stt_socket=owner.stt_socket,
            audio=onset,
            start_sample=49600,
            provider='soniox',
            platform='desktop',
            attempt_failover=owner.failover,
        )
        assert await send_live_stt_audio(
            None,
            state,
            stt_socket=owner.stt_socket,
            audio=onset,
            start_sample=49600,
            provider='soniox',
            platform='desktop',
            attempt_failover=owner.failover,
        )
        assert delivered[0][0] == prefix + onset
        assert len(delivered) == 1
        assert owner._idle_onset_retry is None
        await idle.drain_and_close()

    asyncio.run(run())


@pytest.mark.parametrize('recovery', ['false', 'true'])
def test_managed_idle_close_does_not_claim_health_or_breaker(monkeypatch, recovery):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', recovery)
    monkeypatch.setenv('STT_ROUTING_MODE', 'off')

    async def run():
        socket, idle, gate, _, _, tick = build(monkeypatch)
        host = SimpleNamespace(
            language='en', request=SimpleNamespace(uid='idle-unit'), state=SimpleNamespace(active=True)
        )
        owner = SimpleNamespace(host=host, recovery=None, _telemetry_platform=lambda: 'desktop')
        session = live_session.LiveChainSession(owner)
        leg = live_session.LiveLegSocket(idle, gate, session, STTService.soniox, 16000, False, False)
        for method in ('record', 'quarantine', 'quarantine_target'):
            monkeypatch.setattr(live_session.health, method, lambda *a, **kw: pytest.fail('idle health side effect'))
        leg.send(b'\x00\x00' * 1600, start_sample=0)
        tick[0] += 3
        leg.send(b'\x00\x00' * 1600, start_sample=48000)
        await idle._close_task
        assert not leg.is_connection_dead
        assert not leg.leg_outcome.claimed
        assert not leg.leg_outcome.death_observed
        assert not leg._target_death_recorded
        assert not leg._open_gauge_released
        await leg.drain_and_close()
        assert not leg.leg_outcome.claimed

    asyncio.run(run())


def test_replay_tail_pump_completes_idle_reopen(monkeypatch):
    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103)
        await idle._close_task
        host = SimpleNamespace(
            spawn=lambda coro, **kw: asyncio.create_task(coro),
            state=SimpleNamespace(active=True, stt_terminal_failure=False),
        )
        tail = replay_delivery.ReplayTailSocket(
            socket, replay_delivery.ReplayPacer(16000, 'soniox', socket), deque(), host, source='soniox'
        )
        onset = b'\x01\x00' * 1600
        assert tail.send(onset, start_sample=48000)
        tail.start_tail()
        await tail._task
        await settle()
        assert len(peers) == 2
        assert b''.join(x for x in peers[1].sent if isinstance(x, bytes)).endswith(onset)
        assert not tail.is_connection_dead
        await idle.drain_and_close()

    asyncio.run(run())
