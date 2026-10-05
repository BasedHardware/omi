"""Canary regressions through real receiver, adapters and session supervision.

Synthetic PCM only; the long window first-text sample below deliberately
includes answered noise and silence, so it cannot be attributed to replay.
"""

import asyncio

import pytest
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401

from tests.unit.test_live_cost_router import controls  # noqa: F401
from tests.unit.test_parakeet_window_live import (  # noqa: F401
    runtime,
    Client,
    _fragment_session,
    _fragment_frame,
    _settled_fragment_silence,
    _observe_first_text_deadline_schedule,
)
from tests.unit.test_live_replay_provider_pairs import setup_receiver, stop, until
from tests.unit.test_live_recovery_shutdown_tail import (
    ClientSocket,
    make_runtime,
    stub_transcript_persistence,
    wire_providers,
)
from utils.stt import parakeet_window as window, streaming as st
from utils.stt.live_metrics import WINDOW_FIRST_TEXT, REPLAY_SKIPPED
from utils.stt.live_failure import send_live_stt_audio
from utils.stt.resilient_stream import ResilientAudio
from utils.stt.replay_delivery import ReplayTailSocket
from utils.stt import replay_delivery
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from config.live_stt_replay import ReplayLimits


@pytest.fixture(autouse=True)
def recovery_on(monkeypatch):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


@pytest.mark.asyncio
@pytest.mark.parametrize('code', [1000, 1001, 1006])
async def test_client_disconnect_without_provider_death_stays_cancelled(monkeypatch, code):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    stub_transcript_persistence(rt, [], monkeypatch)
    monkeypatch.setattr(rt.receiver, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(rt.receiver, '_capture', lambda *a, **k: None)
    raws, dials = [], []
    wire_providers(monkeypatch, rt, raws, dials)
    run = asyncio.create_task(rt.run())
    try:
        await until(lambda: rt.receiver.stt_socket is not None)
        ws.feed_audio(bytes(640 * 2))
        await until(lambda: rt.state.live_transcription_attempt is not None)
        finish = MagicMock(wraps=rt.state.live_transcription_attempt.finish)
        monkeypatch.setattr(rt.state.live_transcription_attempt, 'finish', finish)
        ws.disconnect(code)
        await asyncio.wait_for(run, timeout=10)
        assert not rt.state.stt_terminal_failure
        assert not rt.state.live_transcription_failed
        finish.assert_called_once_with('cancelled', phase='teardown')
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['soniox', 'modulate-velma-2'])
@pytest.mark.parametrize('recovered', [False, True])
async def test_buffered_client_burst_does_not_kill_healthy_paid_leg(monkeypatch, provider, recovered):
    order = ['parakeet-window', provider] if recovered else [provider]
    actual, _, raws, legs, _ = await setup_receiver(monkeypatch, order, source=None if recovered else provider)
    actual._window_replay_audio = ResilientAudio(16000, ring_seconds=90, strict_replay=True) if recovered else None
    actual._window_replay_started = False
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    try:
        if recovered:
            actual.stt_socket.raw.fail('connection_lost')
            assert await actual._failover_stt_socket()
            assert isinstance(actual.stt_socket, ReplayTailSocket)
        raw = raws[0]
        # Compress the 2,000-slot incident into four slots; this exercises
        # identical queue admission without spending CPU on 84s of PCM.
        raw._send_queue._maxsize = 4
        if recovered:
            assert raw._writer_pace is not None
            # Capture must continue independently while the paced wire is held.
            raw._ws.gate.clear()
            raw._ws.on_send = lambda: raw._stream_transcript(
                [{'text': 'Recovered.', 'start': 0, 'end': 0.04, 'speaker': 'speaker_0'}]
            )
        for n in range(16):
            actual._stt_buffer_start_sample = n * 640
            buffer = bytearray(b'\x01\x00' * 640)
            await asyncio.wait_for(actual._flush_stt_buffer(buffer, force=True), timeout=0.5)
            assert not raw.is_connection_dead, raw.typed_death_reason
            assert not actual.host.state.stt_terminal_failure
            assert not buffer
        if recovered:
            assert raw._ws.byte_count == 0
            assert len(actual.stt_socket.tail) == 16
            raw._ws.gate.set()
        await until(lambda: raw._ws.byte_count == 16 * 640 * 2)
        assert raw._ws.pcm == b'\x01\x00' * (16 * 640)
        assert len(raws) == 1
        assert raw._send_queue.high_water <= 3
    finally:
        actual.stt_socket.finish()
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['soniox', 'modulate-velma-2'])
async def test_stalled_paid_writer_keeps_bounded_capacity_failure(monkeypatch, provider):
    actual, _, raws, legs, _ = await setup_receiver(monkeypatch, [provider], source=provider)
    actual._window_replay_audio = None
    actual._window_replay_started = False
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raw = raws[0]
    raw.replay_limits = ReplayLimits(queue_wait_seconds=0.01)
    raw._ws.gate.clear()
    try:
        for n in range(4):
            actual._stt_buffer_start_sample = n * 640
            await actual._flush_stt_buffer(bytearray(b'\x01\x00' * 640), force=True)
        await until(lambda: actual.stt_socket.is_connection_dead)
        assert actual.stt_socket.typed_death_reason == 'capacity_full'
        await actual._monitor_stt_death()
        assert actual.host.state.stt_terminal_failure
        assert raw._send_queue.high_water <= 2
        # Local queue exhaustion is censored capacity evidence, not a
        # provider outage that should strand other healthy sessions.
        assert st._circuit_for_primary(actual.host.stt_service).state == 'closed'
    finally:
        actual.stt_socket.finish()
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('first,second', [('soniox', 'modulate-velma-2'), ('modulate-velma-2', 'soniox')])
@pytest.mark.parametrize('written_before_failure', [False, True])
async def test_ringless_failover_transfers_queued_empty_prefix_tail(monkeypatch, first, second, written_before_failure):
    actual, _, raws, legs, _ = await setup_receiver(monkeypatch, ['parakeet-window', first, second])
    actual._window_replay_audio = None
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    try:
        actual.stt_socket.raw.fail('connection_lost')
        assert await actual._failover_stt_socket()
        previous = actual.stt_socket
        assert isinstance(previous, ReplayTailSocket)
        raw = raws[0]
        raw._ws.gate.clear()
        frozen, release = asyncio.Event(), asyncio.Event()
        original_wait = replay_delivery.await_frozen_writes

        async def hold_confirmation(socket, deadline):
            if replay_delivery.raw_transport(socket) is raw:
                frozen.set()
                await release.wait()
            return await original_wait(socket, deadline)

        monkeypatch.setattr(replay_delivery, 'await_frozen_writes', hold_confirmation)
        data = [b'\x11\x00' * 640, b'\x22\x00' * 640]
        for n, packet in enumerate(data):
            actual._stt_buffer_start_sample = n * 640
            await actual._flush_stt_buffer(bytearray(packet), force=True)
        await until(lambda: raw._send_queue.inflight == 1)
        born = [packet.received for packet in previous.tail]
        assert len(born) == 2 and raw._ws.pcm == b''
        if written_before_failure:
            await frozen.wait()
            raw._ws.gate.set()
            await until(lambda: raw._send_queue.written_audio == 1)
            born = born[1:]
        source = 'soniox' if first == 'soniox' else 'modulate'
        successor = 'soniox' if second == 'soniox' else 'modulate'
        skipped = REPLAY_SKIPPED.labels(source=source, successor=successor)
        before = skipped._value.get()
        raw._mark_dead('synthetic failure', 'connection_lost')
        assert await actual._failover_stt_socket()
        assert not previous.tail
        assert [packet.received for packet in actual.stt_socket.tail] == born
        expected = b''.join(data[1:] if written_before_failure else data)
        await until(lambda: raws[-1]._ws.byte_count == len(expected))
        assert raws[-1]._ws.pcm == expected
        assert skipped._value.get() == before
        assert actual._window_ring() is None
    finally:
        actual.stt_socket.finish()
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['soniox', 'modulate-velma-2'])
async def test_initial_capacity_wait_does_not_delay_audio_or_disconnect(monkeypatch, provider):
    monkeypatch.setattr(st, 'stt_service_models', [provider])
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    rt.stt_service = st.STTService.soniox if provider == 'soniox' else st.STTService.modulate
    rt.stt_model = provider
    actual = rt.receiver
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    monkeypatch.setattr(actual, '_bounded_teardown', AsyncMock())
    raws, dials = [], []
    wire_providers(monkeypatch, rt, raws, dials)
    assert await actual.initialize_stt()
    entered, release = asyncio.Event(), asyncio.Event()

    async def wait_capacity(*args, **kwargs):
        entered.set()
        await release.wait()
        return True

    monkeypatch.setattr(actual.stt_socket, 'wait_send_capacity', wait_capacity)
    receive = asyncio.create_task(actual.receive_data())
    try:
        ws.feed_audio(b'\x11\x00' * 640)
        await asyncio.wait_for(entered.wait(), timeout=0.5)
        for _ in range(4):
            ws.feed_audio(b'\x22\x00' * 640)
        ws.disconnect(1006)
        await until(lambda: rt.state.close_code == 1006)
        assert not release.is_set()
        assert isinstance(actual.stt_socket, ReplayTailSocket)
        assert len(actual.stt_socket.tail) == 5
        assert raws[0]._ws.pcm == b''
    finally:
        receive.cancel()
        await asyncio.gather(receive, return_exceptions=True)
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('accepted', [False, True])
async def test_enqueue_capacity_cause_is_preserved_without_changing_flag_off(monkeypatch, enabled, accepted):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', str(enabled).lower())
    import utils.stt.live_failure as failure_module

    circuit = st._soniox_circuit
    circuit.record_success()
    socket = SimpleNamespace(is_connection_dead=False, typed_death_reason=None, death_reason=None)

    def send(_audio):
        socket.typed_death_reason = 'capacity_full'
        socket.is_connection_dead = True
        return accepted

    socket.send = send
    state = SimpleNamespace(active=True, stt_terminal_failure=False, receiver=SimpleNamespace(recovery_enabled=enabled))
    terminal = AsyncMock()
    monkeypatch.setattr(failure_module, 'terminate_live_stt_session', terminal)
    assert not await send_live_stt_audio(
        SimpleNamespace(), state, stt_socket=socket, audio=b'\x01\x00', provider='soniox', platform='ios'
    )
    assert terminal.await_args.kwargs['reason'] == ('capacity_full' if enabled else 'send_failed')


@pytest.mark.asyncio
async def test_window_first_text_over_thirty_seconds_can_include_answered_silence(monkeypatch):
    actual, base, previous, client, replayed, callbacks, clock, sample = await _fragment_session(monkeypatch)
    scheduled = _observe_first_text_deadline_schedule(monkeypatch, previous.raw)
    before_sum = WINDOW_FIRST_TEXT._sum.get()
    try:
        sample = await _settled_fragment_silence(actual, clock, sample, 8)
        sample = await _fragment_frame(actual, clock, sample, speech=True)
        first_speech = previous.raw._first_speech_at
        sample = await _settled_fragment_silence(actual, clock, sample, 125)
        assert previous.raw._stranded_fragment_answered
        assert previous.raw._first_text_timer is None
        # The fully answered 280ms blip forfeits its timer; quiet capture is
        # not a dead leg and must not be charged as stalled transcription.
        sample = await _settled_fragment_silence(actual, clock, sample, 1000, settled=True)
        client.payloads = [{'segments': [{'text': 'Resumed.', 'start': 0.24, 'end': 0.5}]}]
        sample = await _fragment_frame(actual, clock, sample, speech=True)
        resumed = previous.raw._deadline_speech_at
        sample = await _settled_fragment_silence(actual, clock, sample, 125)
        assert [segment['text'] for segment in base.emitted] == ['Resumed.']
        assert WINDOW_FIRST_TEXT._sum.get() - before_sum > 30
        assert clock[0] - first_speech > 30
        assert clock[0] - resumed < 12
        assert scheduled == [12, 12]
        assert not previous.is_connection_dead
        assert not replayed and not callbacks
    finally:
        await actual._drain_stt_sockets()
