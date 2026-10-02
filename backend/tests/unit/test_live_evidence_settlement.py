"""Serving-owner decisions, teardown races and fleet-wide evidence budgets."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.test_live_cost_router import controls, MemoryRedis
from tests.unit.test_live_health_reason_reconciliation import ServingSocket, serving_leg, observed
from tests.unit.test_live_early_provider_deaths import managed_leg, ProviderWebSocket
from tests.unit.test_stt_session_failover import _receiver_with_dead_socket, FakeSocket
from utils.metrics import OMI_FALLBACK_TOTAL
from utils.stt import live_chain, live_failure, live_health, live_session, streaming as st
from utils.stt.live_cost_health import PREFIX
from utils.stt.live_gate import GateState, transition
from utils.stt.live_metrics import COST_SETTLEMENTS, COST_EVIDENCE_ERRORS
from utils.stt.soniox import SafeSonioxSocket


@pytest.mark.parametrize('dead_before_close', [False, True])
@pytest.mark.parametrize('text', [False, True])
def test_46_soniox_reconnect_teardowns_never_vote_failure(dead_before_close, text):
    before = observed('soniox', 'provider_failure', 'connection_lost')
    for _ in range(46):
        leg = serving_leg(family='soniox')
        if text:
            leg.note_selection_transcript([{'text': 'synthetic'}])
        if dead_before_close:
            leg.raw.die(raw='ws recv closed: synthetic abandoned client')
            assert leg.is_connection_dead  # Read-only, even before owner close.
        leg.finish()
        leg.raw.die(raw='ws send closed after our finish')
        assert leg.is_connection_dead
        leg.finish()
    assert observed('soniox', 'provider_failure', 'connection_lost') == before
    states = live_chain.health._cost_local.values()
    assert all(state.stage == 100 and state.failures == 0 and state.n <= 3 for state in states)


@pytest.mark.asyncio
async def test_pending_source_cannot_wait_for_silent_successor_forever(monkeypatch):
    callbacks = []
    loop = asyncio.get_running_loop()
    real_call_later = loop.call_later

    def later(delay, callback, *args, **kwargs):
        if delay == 30:
            callbacks.append(callback)
        return real_call_later(delay, callback, *args, **kwargs)

    monkeypatch.setattr(loop, 'call_later', later)
    leg = serving_leg()
    leg.raw.die('modulate_serve_error')
    before = observed(leg.routing_target, 'provider_failure', 'modulate_serve_error')
    fallback = OMI_FALLBACK_TOTAL.labels(
        component='stt_live_session',
        from_mode='modulate',
        to_mode='soniox',
        reason='modulate_serve_error',
        outcome='degraded',
    )
    fallbacks_before = fallback._value.get()
    hop = live_failure.PendingLiveFailover.from_socket(leg, 'modulate', 'soniox')
    leg.finish()
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == before
    assert len(callbacks) == 1
    callbacks[0]()  # Advance only the production settlement timer, no sleep.
    hop.note_transcript([{'text': 'synthetic late recovery'}])
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == before + 1
    assert fallback._value.get() == fallbacks_before + 1
    assert hop._settlement_timer is None


@pytest.mark.asyncio
async def test_cancelled_failover_settles_source_and_never_blames_cancelled_successor(monkeypatch):
    from routers.listen import receiver as receiver_module

    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    leg = managed_leg(receiver, ServingSocket())
    receiver.stt_socket = leg
    leg.raw.die('modulate_serve_error')
    receiver._create_stt_socket = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(
        receiver_module, 'get_stt_service_for_language', lambda *a, **kw: (st.STTService.soniox, 'en', 'soniox')
    )
    before = observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error')
    with pytest.raises(asyncio.CancelledError):
        await receiver._failover_stt_socket()
    leg.finish()
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1


@pytest.mark.asyncio
async def test_monitor_exhaustion_emits_the_same_failure_as_health(monkeypatch):
    from routers.listen import receiver as receiver_module

    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    leg = managed_leg(receiver, ServingSocket(), family='soniox')
    receiver.stt_socket = leg
    leg.raw.die(raw='ws recv closed: synthetic')
    monkeypatch.setattr(receiver_module, 'get_stt_service_for_language', lambda *a, **kw: (None, 'en', None))
    receiver.host.request.websocket.send_json = AsyncMock()
    receiver.host.request.websocket.close = AsyncMock()
    fallback = OMI_FALLBACK_TOTAL.labels(
        component='stt_live_session',
        from_mode='soniox',
        to_mode='unavailable',
        reason='connection_lost',
        outcome='exhausted',
    )
    before, fb = observed('soniox', 'provider_failure', 'connection_lost'), fallback._value.get()
    await receiver._monitor_stt_death()
    receiver.finish()
    assert observed('soniox', 'provider_failure', 'connection_lost') == before + 1
    assert fallback._value.get() == fb + 1


@pytest.mark.asyncio
async def test_send_exhaustion_is_settled_even_before_first_audio():
    leg = serving_leg()
    leg.raw.die('modulate_serve_error')
    state = SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1000)
    client = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    before = observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error')
    assert not await live_failure.send_live_stt_audio(
        client,
        state,
        stt_socket=leg,
        audio=b'\x00\x00',
        provider='modulate',
        platform='ios',
        attempt_failover=AsyncMock(return_value=False),
    )
    leg.finish()
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1


@pytest.mark.asyncio
async def test_rejected_replacement_settles_before_transport_cleanup(monkeypatch):
    from routers.listen import receiver as receiver_module

    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    source = managed_leg(receiver, ServingSocket())
    source.raw.die('modulate_serve_error')
    successor = managed_leg(receiver, ServingSocket(), family='soniox')
    successor.raw.die('provider_5xx')
    receiver.host.stt_service = st.STTService.modulate
    receiver.stt_socket = source
    receiver._create_stt_socket = AsyncMock(return_value=successor)
    monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', AsyncMock(return_value=False))
    selections = iter([(st.STTService.soniox, 'en', 'soniox'), (None, 'en', None)])
    monkeypatch.setattr(receiver_module, 'get_stt_service_for_language', lambda *a, **kw: next(selections))
    before = observed('soniox', 'provider_failure', 'provider_5xx')
    assert not await receiver._failover_stt_socket()
    assert successor.leg_outcome.settled
    assert observed('soniox', 'provider_failure', 'provider_5xx') == before + 1
    receiver.finish()
    assert observed('soniox', 'provider_failure', 'provider_5xx') == before + 1


def test_recorder_fault_is_visible_without_breaking_fallback(monkeypatch):
    def broken(*args):
        raise RuntimeError('synthetic recorder fault')

    monkeypatch.setattr(live_session.health, 'record_session', broken)
    leg = serving_leg()
    leg.raw.die('modulate_serve_error')
    metric = COST_SETTLEMENTS.labels(
        target=leg.routing_target, outcome='provider_failure', reason='modulate_serve_error', path='failover'
    )
    before, errors = metric._value.get(), COST_EVIDENCE_ERRORS._value.get()
    live_failure.settle_terminal_socket(leg, 'modulate', 'connection_lost')
    assert metric._value.get() == before + 1
    assert COST_EVIDENCE_ERRORS._value.get() == errors + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failed', [False, True])
async def test_46_events_across_pods_get_three_votes_in_redis(failed):
    now = [1000]
    redis = MemoryRedis(clock=lambda: now[0])
    pods = [live_health.FleetHealth(redis_client=redis) for _ in range(2)]
    for i in range(46):
        await pods[i % 2]._write_cost_result('soniox', 'ko', failed, None, 'a' * 16)
    for lang in ('all', 'ko'):
        state = GateState.decode(json.loads(redis.data[f'{PREFIX}:soniox:{lang}']))
        assert state.n == 3 and state.failures == (3 if failed else 0)
        assert state.stage == 100 and len(state.healthy_users) == 1
    now[0] = 1300
    await pods[0]._write_cost_result('soniox', 'ko', failed, None, 'a' * 16)
    state = GateState.decode(json.loads(redis.data[f'{PREFIX}:soniox:all']))
    assert state.n == 4 and state.healthy_users == (('a' * 16, 1),)


@pytest.mark.asyncio
async def test_concurrent_cas_cannot_spend_a_user_budget_twice():
    class ContendedRedis(MemoryRedis):
        async def get(self, key):
            value = await super().get(key)
            await asyncio.sleep(0)
            return value

    redis = ContendedRedis()
    pods = [live_health.FleetHealth(redis_client=redis) for _ in range(2)]
    for _ in range(8):
        await asyncio.gather(*(pod._write_cost_result('soniox', 'ko', True, None, 'a' * 16) for pod in pods))
    state = GateState.decode(json.loads(redis.data[f'{PREFIX}:soniox:all']))
    assert state.n == state.failures == 3


def test_healthy_user_budget_is_bounded_without_eviction_or_raw_uid():
    state = GateState()
    for i in range(512):
        state = transition(state, False, 1000, witness=f'{i:016x}')
    for i in range(512, 560):
        assert transition(state, True, 1000, witness=f'{i:016x}') == state
    assert len(state.healthy_users) == 512
    decoded = GateState.decode(state.encode())
    assert decoded == state
    fresh = transition(state, True, 1300, witness='f' * 16)
    assert fresh.n == 513 and fresh.healthy_users == (('f' * 16, 1),)


@pytest.mark.asyncio
@pytest.mark.parametrize('family', ['modulate', 'soniox'])
async def test_local_queue_full_is_capacity_not_provider_fault(monkeypatch, family):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    ws = ProviderWebSocket()
    cls = st.SafeModulateSocket if family == 'modulate' else SafeSonioxSocket
    raw = cls(ws, lambda _: None, asyncio.get_running_loop())
    raw._send_queue = asyncio.Queue(maxsize=1)
    raw._send_queue.put_nowait(b'\x00\x00')
    leg = managed_leg(receiver, raw, family=family)
    try:
        assert not leg.send(b'\x00\x00')
        assert leg.normalized_death_reason == 'capacity_full'
        live_failure.settle_terminal_socket(leg, family, 'send_failed')
        assert not live_chain.health._cost_local
    finally:
        raw._recv_task.cancel()
        raw._send_task.cancel()
        await asyncio.gather(raw._recv_task, raw._send_task, return_exceptions=True)
        leg.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_point', ['liveness', 'replay'])
async def test_same_provider_reconnect_settles_rejected_successor(monkeypatch, failure_point):
    from utils.stt import resilient_stream
    from tests.unit.test_live_stt_resilient_stream import receiver as make_receiver

    listener = make_receiver(monkeypatch)
    old = serving_leg(family='soniox')
    old.raw.die('soniox_rotation')
    listener.stt_socket = old
    listener._resilient_audio.append(b'\x00\x00', 0)
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    new = serving_leg(family='soniox')
    new.raw.die('provider_5xx')
    listener._create_stt_socket = AsyncMock(return_value=new)
    listener._wrap_legacy_stt_socket = lambda raw, epoch: raw
    monkeypatch.setattr(
        resilient_stream, 'fallback_socket_is_serving', AsyncMock(return_value=failure_point == 'replay')
    )
    before = observed('soniox', 'provider_failure', 'provider_5xx')
    assert not await resilient_stream.reconnect_live_stt_socket(listener)
    new.finish()
    assert new.leg_outcome.settled
    assert observed('soniox', 'provider_failure', 'provider_5xx') == before + 1
