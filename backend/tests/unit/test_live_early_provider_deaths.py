"""Accepted provider deaths must reconcile even without a VAD speech sample."""

import asyncio
import json
import threading
from unittest.mock import AsyncMock

import pytest

from routers.listen import receiver as receiver_module
from tests.unit.test_live_cost_router import controls, MemoryRedis
from tests.unit.test_live_health_reason_reconciliation import ServingSocket, observed
from tests.unit.test_live_routing_health import SpeechGate
from tests.unit.test_stt_session_failover import FakeSocket, _receiver_with_dead_socket
from utils.async_tasks import WebSocketTaskSupervisor
from utils.metrics import OMI_FALLBACK_TOTAL
from utils.stt import live_failure, live_chain, live_session, streaming as st
from utils.stt.soniox import SafeSonioxSocket
from config.live_stt_registry import assigned
from utils.stt.live_gate import GateState


class ProviderWebSocket:
    def __init__(self):
        self.inbound = asyncio.Queue()
        self.sent = []

    async def send(self, value):
        self.sent.append(value)

    async def close(self):
        pass

    def __aiter__(self):
        async def frames():
            while True:
                value = await self.inbound.get()
                if value is None:
                    return
                yield json.dumps(value)

        return frames()


def managed_leg(receiver, raw, *, family='modulate', gate=None, uid='synthetic-health-witness'):
    receiver.host.request.uid = uid
    receiver.host.stt_service = st.STTService(family)
    receiver.host.stt_model = 'velma-2' if family == 'modulate' else family
    return live_session.LiveLegSocket(
        raw, gate, live_session.LiveChainSession(receiver), st.STTService(family), 16000, False, True
    )


def fallback_value(reason, outcome='recovered'):
    return OMI_FALLBACK_TOTAL.labels(
        component='stt_live_session', from_mode='modulate', to_mode='soniox', reason=reason, outcome=outcome
    )._value.get()


@pytest.mark.asyncio
@pytest.mark.parametrize('samples,speech', [(0, True), (8000, True), (19200, True), (19200, None), (19200, False)])
@pytest.mark.parametrize(
    'message,reason',
    [
        ('Internal server error', 'modulate_serve_error'),
        ('Unable to complete the request. Please try again.', 'modulate_serve_error'),
        (None, 'connection_lost'),
    ],
)
@pytest.mark.parametrize('settlement', ['recovered', 'exhausted'])
async def test_n_real_provider_deaths_reconcile_through_managed_leg_and_receiver(
    monkeypatch, samples, speech, message, reason, settlement
):
    monkeypatch.setattr(
        receiver_module, 'get_stt_service_for_language', lambda *_args, **_kw: (st.STTService.soniox, 'en', 'soniox')
    )
    monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    count = 4
    failures_before = observed('modulate-velma-2', 'provider_failure', reason)
    fallbacks_before = fallback_value(reason, settlement)
    other_reason = 'connection_lost' if reason == 'modulate_serve_error' else 'modulate_serve_error'
    other_before = observed('modulate-velma-2', 'provider_failure', other_reason)
    for index in range(count):
        receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket())
        ws = ProviderWebSocket()
        raw = st.SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
        gate = None if speech is None else SpeechGate(is_speech=speech)
        leg = managed_leg(receiver, raw, gate=gate, uid=f'synthetic-{index}')
        receiver.stt_socket = leg
        try:
            if samples:
                assert leg.send(b'\x01\x00' * samples)
                await asyncio.sleep(0)  # Provider send queue actually consumes the accepted audio.
                assert any(isinstance(value, bytes) for value in ws.sent)
            if speech is None or speech is False or samples == 0:
                assert leg._first_speech_at is None
            elif samples < 16000:
                assert leg._speech_ms_for_health < 1000
            await ws.inbound.put({'type': 'error', 'error': message} if message else None)
            await raw._recv_task  # The real Velma parser publishes the typed death.
            assert raw.typed_death_reason == ('modulate_serve_error' if message else None)
            assert leg.is_connection_dead
            assert await receiver._failover_stt_socket()
            if settlement == 'recovered':
                receiver._enqueue_stt_segments([{'text': 'synthetic', 'start': 0, 'end': 1}], provider='soniox')
            else:
                receiver._settle_pending_live_failover_failure()
            leg.finish()
            assert leg.is_connection_dead
            assert leg.normalized_death_reason == reason
        finally:
            leg.finish()
            await asyncio.gather(raw._recv_task, raw._send_task, return_exceptions=True)
    assert fallback_value(reason, settlement) - fallbacks_before == count
    assert observed('modulate-velma-2', 'provider_failure', reason) - failures_before == count
    assert observed('modulate-velma-2', 'provider_failure', other_reason) == other_before
    assert live_chain.health._cost_local[('modulate-velma-2', 'all')].failures == count


@pytest.mark.parametrize('speech', [None, False, True])
@pytest.mark.parametrize('text', [False, True])
def test_short_or_unscored_normal_close_is_never_a_provider_failure(monkeypatch, speech, text):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket())
    raw = ServingSocket()
    leg = managed_leg(receiver, raw, gate=None if speech is None else SpeechGate(is_speech=speech))
    assert leg.send(b'\x01\x00' * 8000)
    if text:
        leg.note_selection_transcript([{'text': 'synthetic'}])
    before = observed('modulate-velma-2', 'success', 'text')
    leg.finish()
    leg.finish()
    assert observed('modulate-velma-2', 'success', 'text') - before == int(text)
    assert leg.leg_outcome.settled
    assert all(state.failures == 0 for state in live_chain.health._cost_local.values())


@pytest.mark.asyncio
async def test_soniox_close_transport_symptom_after_owner_teardown_is_not_a_failure(monkeypatch):
    class ClosingSocket(ServingSocket):
        async def drain_and_close(self):
            self.die(raw='ws recv closed: synthetic intentional close')

    receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket())
    leg = managed_leg(receiver, ClosingSocket(), family='soniox')
    before = observed('soniox', 'provider_failure', 'connection_lost')
    await leg.drain_and_close()
    leg.finish()
    assert observed('soniox', 'provider_failure', 'connection_lost') == before
    assert not live_chain.health._cost_local


@pytest.mark.asyncio
async def test_last_soniox_death_settles_health_and_exhausted_fallback_together(monkeypatch):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    raw = ServingSocket()
    leg = managed_leg(receiver, raw, family='soniox')
    receiver.stt_socket = leg
    raw.die(raw='ws recv closed: synthetic provider transport failure')
    before = observed('soniox', 'provider_failure', 'connection_lost')
    monkeypatch.setattr(receiver_module, 'get_stt_service_for_language', lambda *_args, **_kw: (None, 'en', None))
    assert leg.is_connection_dead
    assert not await receiver._failover_stt_socket()
    assert receiver._pending_live_failover is None
    live_failure.settle_terminal_socket(leg, 'soniox', 'connection_lost')
    leg.finish()
    assert observed('soniox', 'provider_failure', 'connection_lost') == before + 1


@pytest.mark.asyncio
async def test_accepted_dead_leg_and_connect_rejection_are_one_health_observation(monkeypatch):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    raw = ServingSocket()
    leg = managed_leg(receiver, raw)
    raw.die('modulate_serve_error', 'synthetic serve error')
    before = observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error')
    connect_before = observed('modulate-velma-2', 'provider_failure', 'provider_5xx')
    monkeypatch.setattr(
        live_chain, 'fallback_socket_is_serving', AsyncMock(side_effect=lambda socket: not socket.is_connection_dead)
    )
    socket, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(return_value=leg),
        callbacks={st.STTService.soniox: AsyncMock(return_value=FakeSocket())},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid=receiver.host.request.uid,
        routing_language='en',
    )
    assert service == st.STTService.soniox
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1
    assert observed('modulate-velma-2', 'provider_failure', 'provider_5xx') == connect_before
    assert leg.leg_outcome.settled
    socket.finish()


@pytest.mark.asyncio
async def test_unaccepted_connect_failure_still_counts(monkeypatch):
    before = observed('modulate-velma-2', 'provider_failure', 'provider_5xx')
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(side_effect=OSError('synthetic transport connect failure')),
        callbacks={st.STTService.soniox: AsyncMock(return_value=FakeSocket())},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid='synthetic-health-witness',
        routing_language='en',
    )
    assert service == st.STTService.soniox
    assert observed('modulate-velma-2', 'provider_failure', 'provider_5xx') == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'frame,reason',
    [
        ({'error_code': 413, 'error_type': 'max_duration_reached'}, 'soniox_rotation'),
        ({'error_code': 400, 'error_message': 'No audio received'}, 'soniox_idle_timeout'),
        ({'error_code': 408, 'error_type': 'request_timeout'}, 'soniox_request_timeout'),
        ({'finished': True}, None),
    ],
)
async def test_real_soniox_rotation_idle_and_finished_never_become_transport_failures(monkeypatch, frame, reason):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    ws = ProviderWebSocket()
    raw = SafeSonioxSocket(ws, lambda _segments: None, asyncio.get_running_loop())
    leg = managed_leg(receiver, raw, family='soniox', gate=SpeechGate())
    assert leg.send(b'\x01\x00' * 19200)
    await asyncio.sleep(0)
    before = observed('soniox', 'provider_failure', 'connection_lost')
    try:
        await ws.inbound.put(frame)
        await raw._recv_task
        assert raw.typed_death_reason == reason
        assert leg.is_connection_dead == (reason is not None)
        if reason:
            assert leg.normalized_death_reason == reason
        await leg.drain_and_close()
        leg.finish()
        assert observed('soniox', 'provider_failure', 'connection_lost') == before
        assert not live_chain.health._cost_local
    finally:
        await raw.drain_and_close()


@pytest.mark.parametrize('early_signal', ['text', 'no_text_deadline'])
def test_early_transcript_or_deadline_does_not_consume_the_death_observation(monkeypatch, early_signal):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    raw = ServingSocket()
    leg = managed_leg(receiver, raw, gate=SpeechGate())
    assert leg.send(b'\x01\x00' * 8000)
    if early_signal == 'text':
        leg.note_selection_transcript([{'text': 'synthetic'}])
    else:
        leg._first_speech_at -= 60
        leg._check_no_text_deadline()
    assert not leg.leg_outcome.settled
    before = observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error')
    raw.die('modulate_serve_error', 'synthetic serve error')
    assert leg.is_connection_dead
    live_failure.settle_terminal_socket(leg, 'modulate', 'connection_lost')
    leg.finish()
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1
    assert leg.leg_outcome.settled


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', [('all',), ('en',), ('all', 'en')])
@pytest.mark.parametrize('in_trial', [True, False])
async def test_connect_death_counts_once_and_reaches_new_gate_generation(monkeypatch, changed, in_trial):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    raw = ServingSocket()
    leg = managed_leg(receiver, raw)
    uid = next(str(i) for i in range(1000) if assigned(str(i), 'stt-reentry:modulate-velma-2', 5) == in_trial)
    receiver.host.request.uid = uid
    leg.leg_outcome.uid = uid
    for language in changed:
        live_chain.health._cost_cached[('modulate-velma-2', language)] = GateState(stage=5, generation=1)
    raw.die('modulate_serve_error', 'synthetic serve error')
    before = observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error')
    monkeypatch.setattr(
        live_chain, 'fallback_socket_is_serving', AsyncMock(side_effect=lambda socket: not socket.is_connection_dead)
    )
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(return_value=leg),
        callbacks={st.STTService.soniox: AsyncMock(return_value=FakeSocket())},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid=uid,
        routing_language='en',
    )
    assert service == st.STTService.soniox
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1
    for language in ('all', 'en'):
        state = live_chain.health._cost_local.get(('modulate-velma-2', language), GateState())
        expected = int(language not in changed or in_trial)
        assert state.n == state.failures == expected
    assert leg.leg_outcome.generations is None  # No supplementary session writer exists.


class _ClientFrames:
    def __init__(self, frames, *, before_receive=None):
        self.frames = iter(frames)
        self.before_receive = before_receive

    async def receive(self):
        if self.before_receive is not None:
            callback, self.before_receive = self.before_receive, None
            callback()
        return next(self.frames)


class _ReceiverRawSocket(ServingSocket):
    def __init__(self):
        super().__init__()
        self.sent = []

    def send(self, audio):
        self.sent.append(bytes(audio))
        return super().send(audio)


def _receiver_for_close(monkeypatch, *, raw, frames, language='ko', close_code=1000, before_receive=None):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    receiver.host.language = language
    receiver.host.stt_service = st.STTService.soniox
    receiver.host.stt_model = 'soniox'
    receiver.host.request = type(
        'Request',
        (),
        {
            'uid': 'synthetic-health-witness',
            'websocket': _ClientFrames(frames, before_receive=before_receive),
            'codec': 'pcm',
            'sample_rate': 16000,
            'source': 'omi',
            'owner_persistence_blocked': threading.Event(),
        },
    )()
    receiver.host.state.active = True
    receiver.host.state.close_code = close_code
    receiver.host.state.first_audio_byte_timestamp = None
    receiver.host.state.last_usage_record_timestamp = None
    receiver.host.state.last_audio_received_time = None
    receiver.host.state.last_activity_time = None
    receiver.host.state.audio_ring_buffer = None
    receiver.host.state.fair_use_dg_budget_exhausted = False
    receiver.host.state.fair_use_track_dg_usage = False
    receiver.host.state.realtime_demand = type('Demand', (), {'totals': lambda _self: {}})()
    receiver.host.limits.ws_receive_timeout = 1.0
    receiver.host.is_multi_channel = False
    receiver.host.use_custom_stt = False
    receiver.host.audio_bytes_send = None
    receiver.host.client_device_context.platform = 'ios'
    receiver.vad_gate = None
    supervisor = WebSocketTaskSupervisor(uid='synthetic-health-witness', label='listen')
    receiver.host.task_supervisor = supervisor
    receiver.host.spawn = supervisor.create_task
    receiver.host.state.shutdown_event = supervisor.shutdown_event
    receiver.stt_socket = managed_leg(receiver, raw, family='soniox', gate=None)
    receiver.capture_timeline = None
    receiver._emit_realtime_demand = lambda *_args: None
    return receiver


@pytest.mark.asyncio
@pytest.mark.parametrize('close_code', [1000, 1001])
async def test_receiver_teardown_fences_late_transport_death_during_final_flush(monkeypatch, close_code):
    raw = _ReceiverRawSocket()
    receiver = _receiver_for_close(
        monkeypatch,
        raw=raw,
        frames=[{'bytes': b'\x01\x00' * 8}, {'type': 'websocket.disconnect', 'code': close_code}],
        close_code=close_code,
    )
    leg = receiver.stt_socket
    seen_flushes = []

    async def final_flush(buffer, *, force=False):
        if force:
            seen_flushes.append(bytes(buffer))
            assert leg.send(bytes(buffer))
            buffer.clear()
            await asyncio.sleep(0)
            raw.die(raw='synthetic raw transport close during owner teardown')

    receiver._flush_stt_buffer = final_flush
    before = observed('soniox', 'provider_failure', 'connection_lost')
    await receiver.receive_data()
    assert seen_flushes == [b'\x01\x00' * 8]
    assert raw.sent == [b'\x01\x00' * 8]
    assert observed('soniox', 'provider_failure', 'connection_lost') == before


@pytest.mark.asyncio
async def test_soniox_korean_no_frame_disconnect_reconnect_loop_is_censored(monkeypatch):
    before = observed('soniox', 'provider_failure', 'connection_lost')
    for _ in range(5):
        raw = _ReceiverRawSocket()
        receiver = _receiver_for_close(
            monkeypatch,
            raw=raw,
            frames=[{'type': 'websocket.disconnect', 'code': 1000}],
        )
        await receiver.receive_data()
        assert raw.sent == []
    assert observed('soniox', 'provider_failure', 'connection_lost') == before


@pytest.mark.asyncio
@pytest.mark.parametrize('serving_decision', [False, True])
async def test_latched_death_before_client_disconnect_counts_without_monitor_claim(monkeypatch, serving_decision):
    raw = _ReceiverRawSocket()
    observed_while_connected = []

    def provider_died():
        raw.die(raw='synthetic provider transport close')
        observed_while_connected.append(receiver.stt_socket.is_connection_dead)
        if serving_decision:
            live_failure.settle_terminal_socket(receiver.stt_socket, 'soniox', 'connection_lost')

    receiver = _receiver_for_close(
        monkeypatch,
        raw=raw,
        frames=[{'type': 'websocket.disconnect', 'code': 1000}],
        before_receive=provider_died,
    )
    before = observed('soniox', 'provider_failure', 'connection_lost')
    await receiver.receive_data()
    assert observed_while_connected == [True]
    assert observed('soniox', 'provider_failure', 'connection_lost') == before + 1
