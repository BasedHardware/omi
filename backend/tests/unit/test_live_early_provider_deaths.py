"""Accepted provider deaths must reconcile even without a VAD speech sample."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from routers.listen import receiver as receiver_module
from tests.unit.test_live_cost_router import controls, MemoryRedis
from tests.unit.test_live_health_reason_reconciliation import ServingSocket, observed
from tests.unit.test_live_routing_health import SpeechGate
from tests.unit.test_stt_session_failover import FakeSocket, _receiver_with_dead_socket
from utils.metrics import OMI_FALLBACK_TOTAL
from utils.stt import live_chain, live_session, streaming as st
from utils.stt.soniox import SafeSonioxSocket
from config.live_stt_registry import assigned
from utils.stt.live_gate import GateState
from utils.stt.live_cost_health import PREFIX


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


def managed_leg(receiver, raw, *, family='modulate', gate=None):
    receiver.host.request.uid = 'synthetic-health-witness'
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
    for _ in range(count):
        receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket())
        ws = ProviderWebSocket()
        raw = st.SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
        gate = None if speech is None else SpeechGate(is_speech=speech)
        leg = managed_leg(receiver, raw, gate=gate)
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
    assert not leg._cost_recorded or text
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
async def test_last_soniox_death_has_health_evidence_without_a_failover_hop(monkeypatch):
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
    assert leg.cost_observation_recorded
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
    assert not leg.cost_observation_recorded
    before = observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error')
    raw.die('modulate_serve_error', 'synthetic serve error')
    assert leg.is_connection_dead
    leg.finish()
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1
    assert leg.cost_observation_recorded


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', [('all',), ('en',), ('all', 'en')])
@pytest.mark.parametrize('in_trial', [True, False])
async def test_connect_death_counts_once_and_reaches_new_gate_generation(monkeypatch, changed, in_trial):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    raw = ServingSocket()
    leg = managed_leg(receiver, raw)
    uid = next(str(i) for i in range(1000) if assigned(str(i), 'stt-reentry:modulate-velma-2', 5) == in_trial)
    receiver.host.request.uid = uid
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
    assert leg.cost_observation.generations == {'all': 0, 'en': 0}


@pytest.mark.asyncio
@pytest.mark.parametrize('remote_generation', [0, 1])
@pytest.mark.parametrize('write_order', ['forward', 'reverse', 'concurrent'])
@pytest.mark.parametrize('promote', [False, True])
async def test_session_and_supplementary_connect_writes_count_once_in_redis(
    monkeypatch, remote_generation, write_order, promote
):
    class YieldingRedis(MemoryRedis):
        async def get(self, key):
            await asyncio.sleep(0)
            return await super().get(key)

        async def eval(self, *args):
            await asyncio.sleep(0)
            return await super().eval(*args)

    redis = YieldingRedis()
    pod = live_chain.health
    monkeypatch.setattr(pod, '_client', redis)
    # Use the real bounded Redis writer with a controlled session/connect task
    # order: the newer epoch may be visible only remotely, not yet in this pod.
    tasks = []
    monkeypatch.setattr(pod, 'schedule', tasks.append)
    uid = next(str(i) for i in range(1000) if assigned(str(i), 'stt-reentry:modulate-velma-2', 5))
    for language in ('all', 'en'):
        state = GateState(
            stage=5 if promote else 100,
            n=29 if promote else 0,
            generation=remote_generation,
            trial_users=tuple((f'{i:016x}', 1, 0) for i in range(29)) if promote else (),
        )
        redis.data[f'{PREFIX}:modulate-velma-2:{language}'] = json.dumps(state.encode())
        if promote:
            pod._cost_local[('modulate-velma-2', language)] = state
    before = observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error')
    receipt = pod.record_session('modulate-velma-2', 'en', 'failover', {'all': 0, 'en': 0}, uid, 'modulate_serve_error')
    pod.record_connect_failure('modulate-velma-2', 'en', uid, 'modulate_serve_error', observed=receipt)
    assert len(tasks) == 2
    if promote:
        assert all(state.stage == 25 and state.n == 0 for state in pod._cost_local.values())
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1
    if write_order == 'reverse':
        tasks.reverse()
    try:
        if write_order == 'concurrent':
            await asyncio.gather(*tasks)
        else:
            for task in tasks:
                await task
    finally:
        for task in tasks:
            task.close()
    for language in ('all', 'en'):
        state = GateState.decode(json.loads(redis.data[f'{PREFIX}:modulate-velma-2:{language}']))
        if promote:
            assert state.stage == 25 and state.n == 0
        else:
            assert state.n == state.failures == 1
