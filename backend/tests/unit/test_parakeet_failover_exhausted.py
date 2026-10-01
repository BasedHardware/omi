"""Window recovery must survive an unhealthy first replacement; no network."""

import asyncio

import pytest

import routers.listen.receiver as receiver_module
from tests.unit.test_parakeet_window_live import Client, _flush_capture, _receiver_for_anchor_replay, runtime
from utils.stt import streaming as st
from utils.stt.live_session import LiveLegSocket


class Replacement:
    def __init__(self, callback):
        self.callback = callback
        self.is_connection_dead = False
        self.typed_death_reason = None
        self.death_reason = None
        self.sent = []

    def send(self, data):
        if self.is_connection_dead:
            return False
        self.sent.append(data)
        return True

    def finalize(self):
        pass

    def finish(self):
        self.is_connection_dead = True


async def setup_chain(monkeypatch):
    actual, base, previous, _, _ = await _receiver_for_anchor_replay(monkeypatch, Client(data={'text': ''}))
    actual.host.state.current_conversation_id = 'synthetic'
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox'])
    legs = {'modulate': [], 'soniox': []}

    def connector(name):
        async def connect(callback, *args, **kwargs):
            leg = Replacement(callback)
            legs[name].append(leg)
            return leg

        return connect

    monkeypatch.setattr(st, 'process_audio_modulate', connector('modulate'))
    monkeypatch.setattr(st, 'process_audio_soniox', connector('soniox'))
    pcm = b'\x01\x00' * 640
    for n in range(3):
        await _flush_capture(actual, pcm, n * 640)
    await asyncio.sleep(0)
    previous.raw.fail('first_text_deadline')
    return actual, base, previous, legs, pcm * 3


@pytest.mark.asyncio
async def test_delayed_modulate_death_replays_window_capture_on_soniox(monkeypatch, caplog):
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    try:
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.modulate
        modulate = legs['modulate'][0]
        assert b''.join(modulate.sent) == capture
        modulate.is_connection_dead = True
        modulate.typed_death_reason = 'modulate_serve_error'
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.soniox
        assert len(legs['modulate']) == len(legs['soniox']) == 1
        assert b''.join(legs['soniox'][0].sent) == capture
        assert not actual.host.state.stt_terminal_failure
        assert [r.message for r in caplog.records if 'component=stt_live_session' in r.message] == [
            'omi_fallback_event component=stt_live_session from=parakeet to=modulate '
            'reason=other outcome=degraded subtype=modulate_serve_error'
        ]
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_replacement_dying_at_final_liveness_check_continues_to_soniox(monkeypatch):
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)

    async def check(socket):
        if isinstance(socket, LiveLegSocket) and socket.service == st.STTService.modulate:
            socket.raw.is_connection_dead = True
            socket.raw.typed_death_reason = 'modulate_serve_error'
            return False
        return not socket.is_connection_dead

    monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', check)
    try:
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.soniox
        assert len(legs['modulate']) == len(legs['soniox']) == 1
        assert b''.join(legs['soniox'][0].sent) == capture
        assert not actual.host.state.stt_terminal_failure
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_open_modulate_circuit_skips_to_soniox_with_exact_window_replay(monkeypatch):
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    st._modulate_circuit.record_serve_failure()
    try:
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.soniox
        assert legs['modulate'] == []
        assert b''.join(legs['soniox'][0].sent) == capture
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_partial_replay_acceptance_without_text_does_not_discard_prefix(monkeypatch):
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    connect = st.process_audio_modulate

    async def reject_second(callback, *args, **kwargs):
        leg = await connect(callback, *args, **kwargs)
        send = leg.send

        def send_then_reject(data):
            if len(leg.sent) == 1:
                leg.is_connection_dead = True
                leg.typed_death_reason = 'modulate_serve_error'
                return False
            return send(data)

        leg.send = send_then_reject
        return leg

    monkeypatch.setattr(st, 'process_audio_modulate', reject_second)
    try:
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.soniox
        assert len(legs['modulate'][0].sent) == 1
        assert b''.join(legs['soniox'][0].sent) == capture
        assert base.emitted == []
        assert actual._window_ring().capture_bounds == (0, 1920)
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
@pytest.mark.parametrize('timeline_v2', [False, True])
async def test_emitted_prefix_trims_but_new_audio_and_late_callback_are_fenced(monkeypatch, timeline_v2):
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if timeline_v2 else 'false')
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    assert actual.capture_timeline_v2 is timeline_v2
    try:
        assert await actual._failover_stt_socket()
        modulate = legs['modulate'][0]
        modulate.callback([{'text': 'prefix', 'start': 0.0, 'end': 0.08}])
        assert [s['text'] for s in base.emitted] == ['prefix']
        assert actual._window_ring().capture_bounds == (1280, 1920)
        extra = b'\x02\x00' * 640
        await _flush_capture(actual, extra, 1920)
        assert actual._window_ring().capture_bounds == (1280, 2560)
        queued = []
        monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: queued.append((action, segments)))
        modulate.callback([{'text': 'queued duplicate', 'start': 0.08, 'end': 0.16}])
        assert len(queued) == 1
        modulate.is_connection_dead = True
        modulate.typed_death_reason = 'modulate_serve_error'
        assert await actual._failover_stt_socket()
        assert b''.join(legs['soniox'][0].sent) == capture[1280 * 2 :] + extra
        modulate.callback([{'text': 'late duplicate', 'start': 0.08, 'end': 0.16}])
        assert len(queued) == 1
        queued[0][0](queued[0][1])
        assert [s['text'] for s in base.emitted] == ['prefix']
        monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
        legs['soniox'][0].callback([{'text': 'tail', 'start': 0.0, 'end': 0.08}])
        assert [s['text'] for s in base.emitted] == ['prefix', 'tail']
        assert actual._window_ring().buffered_bytes == 0
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_five_minutes_on_replacement_trim_on_text_and_remain_bounded(monkeypatch):
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    try:
        assert await actual._failover_stt_socket()
        modulate = legs['modulate'][0]
        modulate.callback([{'text': 'initial', 'start': 0.0, 'end': 0.12}])
        assert actual._window_ring().buffered_bytes == 0
        pcm = b'\x02\x00' * 16000
        for second in range(300):
            await _flush_capture(actual, pcm, 1920 + second * 16000)
            end = 1.12 + second
            modulate.callback([{'text': 'part', 'start': 0.12 + second, 'end': end}])
            # Provider seconds are truncated to capture samples; binary float
            # rounding may leave exactly one sample awaiting the next segment.
            assert actual._window_ring().capture_bounds == (int(end * 16000), 1920 + (second + 1) * 16000)
            assert actual._window_ring().buffered_bytes == 2 * (1920 + (second + 1) * 16000 - int(end * 16000))
            assert actual.host.stt_service == st.STTService.modulate
        assert len(legs['modulate']) == 1
        assert legs['soniox'] == []
        assert len(base.emitted) == 301
        assert actual._window_ring().ring_seconds == 105
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_stalled_replacement_keeps_bounded_pending_capture_then_replays(monkeypatch):
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    try:
        assert await actual._failover_stt_socket()
        pcm = b'\x02\x00' * 16000
        for second in range(104):
            await _flush_capture(actual, pcm, 1920 + second * 16000)
        assert actual.host.stt_service == st.STTService.modulate
        assert actual._window_ring().buffered_bytes == len(capture) + 104 * len(pcm)
        await _flush_capture(actual, pcm, 1920 + 104 * 16000)
        assert actual.host.stt_service == st.STTService.soniox
        assert len(legs['soniox']) == 1
        assert b''.join(legs['soniox'][0].sent) == capture + pcm * 105
        assert actual._window_ring().ring_seconds == 120
        assert actual._window_ring().buffered_bytes == len(capture) + 105 * len(pcm)
        assert not actual.host.state.stt_terminal_failure
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_five_minutes_of_silence_on_replacement_keeps_recent_tail_and_forwards_every_byte(monkeypatch):
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    try:
        assert await actual._failover_stt_socket()
        modulate = legs['modulate'][0]
        modulate.callback([{'text': 'initial', 'start': 0.0, 'end': 0.12}])
        silence = bytes(16000 * 2)
        for second in range(300):
            await _flush_capture(actual, silence, 1920 + second * 16000)
        assert len(legs['modulate']) == 1
        assert legs['soniox'] == []
        assert actual._window_ring().buffered_bytes == 16 * 16000 * 2
        assert b''.join(modulate.sent) == capture + silence * 300
        assert not actual.host.state.stt_terminal_failure
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
@pytest.mark.parametrize('timeline_v2', [False, True])
async def test_enabled_soniox_reconnect_uses_full_window_obligation_not_fifteen_second_tail(monkeypatch, timeline_v2):
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', 'true')
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if timeline_v2 else 'false')
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    try:
        assert await actual._failover_stt_socket()
        pcm = b'\x02\x00' * 16000
        for second in range(20):
            await _flush_capture(actual, pcm, 1920 + second * 16000)
        legs['modulate'][0].is_connection_dead = True
        legs['modulate'][0].typed_death_reason = 'modulate_serve_error'
        assert await actual._failover_stt_socket()
        expected = capture + pcm * 20
        assert b''.join(legs['soniox'][0].sent) == expected
        legs['soniox'][0].is_connection_dead = True
        legs['soniox'][0].typed_death_reason = 'provider_5xx'
        assert await actual._failover_stt_socket()
        assert len(legs['soniox']) == 2
        assert b''.join(legs['soniox'][1].sent) == expected
        assert actual._resilient_audio._replayed_samples == len(expected) // 2
        legs['soniox'][0].callback([{'text': 'retired tail', 'start': 0.0, 'end': 20.12}])
        assert base.emitted == []
        assert actual._window_ring().capture_bounds == (0, 321920)
    finally:
        await actual._drain_stt_sockets()
