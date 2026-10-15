"""Window recovery must survive an unhealthy first replacement; no network."""

import asyncio
import json

import pytest
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401

import routers.listen.receiver as receiver_module
from tests.unit.test_parakeet_window_live import Client, _flush_capture, _receiver_for_anchor_replay, runtime, window
from utils.stt import streaming as st
from utils.stt import provider_resilience, vad_gate
from utils.stt.live_session import LiveLegSocket
from utils.stt import live_session, live_chain, live_health, live_router
from utils.stt.live_router import connecting_target
from utils.stt.live_metrics import REPLAY_SKIPPED
from utils.stt.provider_resilience import ProviderCircuitBreaker
from tests.unit.test_live_cost_router import MemoryRedis


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


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
        assert not previous._tracks_window_replay
        assert actual.stt_socket._tracks_window_replay
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
            'reason=first_text_deadline outcome=degraded'
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
async def test_every_replacement_late_rejects_once_then_terminates_when_chain_exhausted(monkeypatch, caplog):
    initial_connections = []
    connect_window = window.connect_window

    def initial(callback, sample_rate):
        socket = connect_window(callback, sample_rate)
        initial_connections.append(socket)
        return socket

    monkeypatch.setattr(window, 'connect_window', initial)
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox', 'dg-nova-3'])
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'test')
    legs['deepgram'] = []

    async def deepgram(callback, *args, **kwargs):
        leg = Replacement(callback)
        legs['deepgram'].append(leg)
        return leg

    monkeypatch.setattr(st, 'process_audio_dg', deepgram)
    checked = []

    async def reject(socket):
        assert isinstance(socket, LiveLegSocket)
        checked.append(socket.service.value)
        socket.raw.is_connection_dead = True
        socket.raw.typed_death_reason = 'connection_lost'
        return False

    monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', reject)
    try:
        # Exercise the real supervisor's terminal path after recursive retries.
        await actual._monitor_stt_death()
        assert initial_connections == [previous.raw]
        assert checked == ['modulate', 'soniox', 'deepgram']
        assert len(legs['modulate']) == len(legs['soniox']) == len(legs['deepgram']) == 1
        assert actual._stt_failed_providers == {'parakeet', 'modulate', 'soniox', 'deepgram_cloud'}
        assert previous.raw.is_connection_dead
        assert all(leg.is_connection_dead for group in legs.values() for leg in group)
        assert base.emitted == []
        assert actual._window_ring().snapshot() == tuple(
            (n * 640, capture[n * 1280 : (n + 1) * 1280]) for n in range(3)
        )
        assert actual.host.state.stt_terminal_failure
        assert not actual.host.state.active
        actual.host.request.websocket.close.assert_awaited_once_with(
            code=1011, reason='transcription_service_unavailable'
        )
        events = actual.host.request.websocket.send_json.await_args_list
        assert len(events) == 1
        assert events[0].args[0]['status'] == 'stt_failed'
        assert [r.message for r in caplog.records if 'component=stt_live_session' in r.message] == [
            'omi_fallback_event component=stt_live_session from=parakeet to=modulate '
            'reason=first_text_deadline outcome=degraded',
            'omi_fallback_event component=stt_live_session from=modulate to=soniox '
            'reason=connection_lost outcome=degraded',
            'omi_fallback_event component=stt_live_session from=soniox to=deepgram '
            'reason=connection_lost outcome=exhausted',
            'omi_fallback_event component=stt_live_session from=deepgram to=unavailable '
            'reason=connection_lost outcome=exhausted',
        ]
        # An additional recovery attempt cannot loop or settle either hop again.
        assert not await actual._failover_stt_socket()
        assert initial_connections == [previous.raw]
        assert checked == ['modulate', 'soniox', 'deepgram']
        assert len(legs['modulate']) == len(legs['soniox']) == len(legs['deepgram']) == 1
        actual.host.request.websocket.close.assert_awaited_once()
        assert len([r for r in caplog.records if 'component=stt_live_session' in r.message]) == 4
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
@pytest.mark.parametrize('first_service', ['modulate', 'soniox'])
@pytest.mark.parametrize('timeline_v2', [False, True])
async def test_empty_snapshot_handoff_tracks_new_speech_and_replays_it_on_next_failure(
    monkeypatch, first_service, timeline_v2, virtual_clock
):
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if timeline_v2 else 'false')
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox', 'dg-nova-3'])
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'test')
    legs['deepgram'] = []

    async def deepgram(callback, *args, **kwargs):
        leg = Replacement(callback)
        legs['deepgram'].append(leg)
        return leg

    monkeypatch.setattr(st, 'process_audio_dg', deepgram)
    if first_service == 'soniox':
        st._modulate_circuit.record_serve_failure()
    second_service = 'soniox' if first_service == 'modulate' else 'modulate'
    try:
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service.value == first_service
        first = legs[first_service][0]
        assert b''.join(first.sent) == capture
        first.callback([{'text': 'settled', 'start': 0.0, 'end': 0.12}])
        ring = actual._window_ring()
        assert ring.snapshot() == ()
        assert ring.finalized_sample == 1920
        if first_service == 'soniox':
            # The previously open circuit is healthy again before this hop.
            monkeypatch.setattr(
                st,
                '_modulate_circuit',
                provider_resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30),
            )
        first.is_connection_dead = True
        first.typed_death_reason = 'connection_lost'
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service.value == second_service
        second = legs[second_service][0]
        assert second.sent == []
        assert ring.snapshot() == ()

        # Exceed the settled-silence retention horizon with actual speech.
        # The empty-snapshot replacement never answers any of these samples.
        pcm = b'\x02\x00' * 16000
        for n in range(32):
            await _flush_capture(actual, pcm, 1920 + n * 16000)
            # Real-time capture may exceed the ring's quiet retention horizon,
            # but must not be an instantaneous burst past the 26s tail cap.
            assert sum(map(len, second.sent)) == len(pcm) * (n + 1)
            # The fixture suppresses the owner's 1s monitor; observe the same
            # healthy dwell that releases a silent, connected production leg.
            actual.recovery.note_healthy_connection(actual._candidate_token)
        assert ring.capture_bounds == (1920, 513920)
        assert ring.buffered_bytes == 32 * len(pcm)
        assert actual.stt_socket._tracks_window_replay
        assert actual.stt_socket.has_untranscribed_speech()
        assert actual.stt_socket.window_replay_pending_sample() == 1920
        assert b''.join(second.sent) == pcm * 32
        # Place the fifth frame clearly beyond the 28s capture-age bound,
        # while the sixth is still fresh; avoid floating-point boundaries.
        fifth_born = actual._live_birth.lookup(1920 + 4 * 16000)
        sixth_born = actual._live_birth.lookup(1920 + 5 * 16000)
        assert fifth_born is not None and sixth_born is not None
        handoff_time = fifth_born + 28.5
        assert handoff_time >= virtual_clock.now
        assert handoff_time - sixth_born < 28
        virtual_clock.now = handoff_time
        skipped = REPLAY_SKIPPED.labels(source=second_service, successor='deepgram')
        skipped_before = skipped._value.get()
        second.is_connection_dead = True
        second.typed_death_reason = 'connection_lost'
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.deepgram
        assert len(legs['modulate']) == len(legs['soniox']) == len(legs['deepgram']) == 1
        replayed_pcm = b''.join(legs['deepgram'][0].sent)
        assert len(replayed_pcm) == len(pcm) * 27
        assert replayed_pcm == pcm * 27
        assert skipped._value.get() - skipped_before == 5
        assert ring.capture_bounds == (81920, 513920)
        assert [s['text'] for s in base.emitted] == ['settled']
        assert not actual.host.state.stt_terminal_failure
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_partial_replay_acceptance_without_text_does_not_discard_prefix(monkeypatch):
    monkeypatch.setattr("utils.stt.replay_delivery.REPLAY_PACKET_BYTES", 1280)
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
        assert actual._window_ring().ring_seconds == 90
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_stalled_replacement_keeps_bounded_pending_capture_then_replays(monkeypatch):
    from utils.stt import recovery_state

    monkeypatch.setattr(recovery_state, 'RECOVERY_EPISODE_SECONDS', 300.0)
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
        sent = b''.join(legs['soniox'][0].sent)
        expected_tail = capture + pcm * 105
        assert sent and expected_tail.endswith(sent)
        assert len(sent) <= (20 + 26) * len(pcm) + len(pcm)
        assert actual._window_ring().ring_seconds >= actual._window_ring()._base_ring_seconds
        assert actual._window_ring().buffered_bytes < len(expected_tail)
        assert actual._window_ring().capture_bounds[0] > 0
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
        ring_before = b''.join(data for _, data in actual._window_ring().snapshot())
        assert await actual._failover_stt_socket()
        assert len(legs['soniox']) == 2
        sent = b''.join(legs['soniox'][1].sent)
        assert sent and ring_before.endswith(sent)
        assert actual._resilient_audio._replayed_samples == len(sent) // 2
        legs['soniox'][0].callback([{'text': 'retired tail', 'start': 0.0, 'end': 20.12}])
        assert base.emitted == []
        bounds = actual._window_ring().capture_bounds
        assert bounds[0] > 0 and bounds[1] == 321920
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_window_replay_is_not_gated_again_when_replacement_vad_misses_source_speech(monkeypatch):
    # Source window admission has gain and a 300ms tail; emulate quiet speech
    # admitted there that the downstream gate would classify as silence.
    monkeypatch.setattr(vad_gate.VADStreamingGate, '_run_vad', lambda gate, _pcm: gate._hangover_ms == 300)
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    actual.host.request.vad_gate_override = 'enabled'
    try:
        assert await actual._failover_stt_socket()
        assert b''.join(legs['modulate'][0].sent) == capture
        legs['modulate'][0].is_connection_dead = True
        legs['modulate'][0].typed_death_reason = 'modulate_serve_error'
        assert await actual._failover_stt_socket()
        assert actual.stt_socket.gate.mode == 'active'
        assert not actual.stt_socket.gate._run_vad(capture)
        assert b''.join(legs['soniox'][0].sent) == capture
        assert actual._window_ring().capture_bounds == (0, 1920)
        # The caller's active gate still governs new capture after replay.
        await _flush_capture(actual, b'\x03\x00' * 640, 1920)
        assert b''.join(legs['soniox'][0].sent) == capture
        # Starting new speech may forward its new pre-roll, but must not
        # forward the already replayed source prefix a second time.
        monkeypatch.setattr(actual.stt_socket.gate, '_run_vad', lambda _pcm: True)
        await _flush_capture(actual, b'\x04\x00' * 640, 2560)
        assert b''.join(legs['soniox'][0].sent) == capture + b'\x03\x00' * 640 + b'\x04\x00' * 640
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_replay_tracking_survives_downstream_vad_fail_open(monkeypatch):
    actual, base, previous, legs, capture = await setup_chain(monkeypatch)
    try:
        assert await actual._failover_stt_socket()
        replacement = actual.stt_socket
        assert replacement._tracks_window_replay

        def broken(_pcm):
            raise RuntimeError('synthetic scoring failure')

        monkeypatch.setattr(replacement.gate, '_run_vad', broken)
        pcm = b'\x03\x00' * 640
        await _flush_capture(actual, pcm, 1920)
        assert replacement.gate is None
        await _flush_capture(actual, pcm, 2560)
        assert replacement._speech_capture_end == 3200
        assert b''.join(legs['modulate'][0].sent) == capture + pcm * 2
        legs['modulate'][0].is_connection_dead = True
        legs['modulate'][0].typed_death_reason = 'connection_lost'
        assert await actual._failover_stt_socket()
        assert b''.join(legs['soniox'][0].sent) == capture + pcm * 2
        assert actual._window_ring().capture_bounds == (0, 3200)
        assert base.emitted == []
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
@pytest.mark.parametrize('account_failure', [False, True])
async def test_mid_session_modulate_endpoint_failure_preserves_healthy_sibling(monkeypatch, account_failure):
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
                    'id': 'modulate-next',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'endpoint': 'wss://example.invalid/stream',
                },
                {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055},
                {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754},
            ]
        ),
    )
    actual, _, previous, legs, capture = await setup_chain(monkeypatch)
    await pod.refresh_cost_once()
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
        assert selected == ['modulate-next']
        dead = actual.stt_socket.raw
        dead.is_connection_dead = True
        dead.typed_death_reason = 'provider_budget_exhausted' if account_failure else 'modulate_serve_error'
        assert await actual._failover_stt_socket()
        if account_failure:
            assert actual.host.stt_service == st.STTService.soniox
            assert 'modulate' in actual._stt_failed_providers
            assert selected == ['modulate-next']
        else:
            assert actual.host.stt_service == st.STTService.modulate
            assert actual.stt_socket.routing_target == 'modulate-velma-2'
            assert selected == ['modulate-next', 'modulate-velma-2']
            assert 'modulate-next' in actual._stt_failed_targets
            assert 'modulate' not in actual._stt_failed_providers
        assert b''.join(actual.stt_socket.raw.sent) == capture
    finally:
        await actual._drain_stt_sockets()
