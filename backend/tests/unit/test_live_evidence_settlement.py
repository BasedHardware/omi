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
from tests.unit.test_live_stt_resilient_stream import receiver as make_receiver
from utils.metrics import OMI_FALLBACK_TOTAL
from utils.stt import live_chain, live_failure, live_health, live_session, resilient_stream, streaming as st
from config import live_stt_state
from config.live_stt_registry import DEFAULT_TARGETS
from utils.stt.live_gate import GateState, transition, HEALTHY_USERS, FAILURE_RESERVE
from utils.stt.live_metrics import COST_SETTLEMENTS, COST_EVIDENCE_ERRORS, COST_EMISSION_ACK_ERRORS, RECONNECT
from utils.stt.soniox import SafeSonioxSocket

SONIOX = next(t for t in DEFAULT_TARGETS if t.id == 'soniox')


@pytest.mark.parametrize('dead_before_close', [False, True])
@pytest.mark.parametrize('text', [False, True])
def test_pre_teardown_death_counts_but_post_teardown_death_does_not(dead_before_close, text):
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
    assert observed('soniox', 'provider_failure', 'connection_lost') == before + (46 if dead_before_close else 0)
    states = live_chain.health._cost_local.values()
    assert all(
        state.stage == 100 and state.failures == (3 if dead_before_close else 0) and state.n <= 3 for state in states
    )


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
    assert leg.leg_outcome.settled
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1
    leg.finish()


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
    assert leg.leg_outcome.settled
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1
    leg.finish()


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
        state = GateState.decode(json.loads(redis.data[live_stt_state.cost_key(SONIOX, lang)]))
        assert state.n == 3 and state.failures == (3 if failed else 0)
        assert state.stage == 100 and len(state.healthy_users) == 1
    now[0] = 1300
    await pods[0]._write_cost_result('soniox', 'ko', failed, None, 'a' * 16)
    state = GateState.decode(json.loads(redis.data[live_stt_state.cost_key(SONIOX, 'all')]))
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
    state = GateState.decode(json.loads(redis.data[live_stt_state.cost_key(SONIOX, 'all')]))
    assert state.n == state.failures == 3


def test_saturated_fairness_window_still_benches_eight_new_failures():
    users = tuple((f'{i:016x}', 3) for i in range(HEALTHY_USERS))
    state = GateState(n=512, healthy_window=3, healthy_users=users)
    assert transition(state, False, 1000, witness='f' * 16) == state
    assert transition(state, True, 1000, witness=users[0][0]) == state  # No budget refill.
    for i in range(8):
        state = transition(state, True, 1000, witness=f'{HEALTHY_USERS + i:016x}')
        assert len(state.healthy_users) <= HEALTHY_USERS
        assert len(state.overflow_failures) <= FAILURE_RESERVE
        assert GateState.decode(state.encode()) == state
    assert state.stage == 0 and state.failures == 8


def test_healthy_user_budget_is_bounded_without_eviction_or_raw_uid():
    users = tuple((f'{i:016x}', 1) for i in range(HEALTHY_USERS))
    state = GateState(n=512, healthy_window=3, healthy_users=users)
    assert transition(state, False, 1000, witness='f' * 16) == state
    assert GateState.decode(state.encode()) == state
    fresh = transition(state, True, 1300, witness='f' * 16)
    assert fresh.healthy_users == (('f' * 16, 1),)


@pytest.mark.asyncio
async def test_healthy_fairness_keys_expire_but_bench_and_trial_do_not():
    redis = MemoryRedis()
    pod = live_health.FleetHealth(redis_client=redis)
    key = ('soniox', 'all')
    await pod._cost_update(key, lambda _: GateState(n=1))
    assert redis.ttls[live_stt_state.cost_key(SONIOX, 'all')] == 900
    for stage in (0, 5, 25):
        await pod._cost_update(key, lambda _, stage=stage: GateState(stage=stage, generation=1))
        assert redis.ttls[live_stt_state.cost_key(SONIOX, 'all')] == 0  # Never silently reset a bench to 100%.


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

    listener = make_receiver(monkeypatch)
    old = serving_leg(family='soniox')
    old.raw.die('soniox_rotation')
    listener.stt_socket = old
    listener._resilient_audio.append(b'\x00\x00', 0)
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    new = serving_leg(family='soniox')
    new.raw.die('provider_5xx')
    listener._create_stt_socket = AsyncMock(return_value=new)
    monkeypatch.setattr(
        resilient_stream, 'fallback_socket_is_serving', AsyncMock(return_value=failure_point == 'replay')
    )
    before = observed('soniox', 'provider_failure', 'provider_5xx')
    assert not await resilient_stream.reconnect_live_stt_socket(listener)
    assert new.leg_outcome.settled
    new.finish()
    assert observed('soniox', 'provider_failure', 'provider_5xx') == before + 1


@pytest.mark.asyncio
async def test_cancelled_liveness_probe_closes_the_unadopted_raw_leg(monkeypatch):
    """Cancellation while vetting the fresh leg must not leak it (review P2)."""

    listener = make_receiver(monkeypatch)
    old = serving_leg(family='soniox')
    old.raw.die('soniox_rotation')
    listener.stt_socket = old
    listener._resilient_audio.append(b'\x00\x00', 0)
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    new = serving_leg(family='soniox')

    async def vetting_hang(raw):
        raise asyncio.CancelledError()

    listener._create_stt_socket = AsyncMock(return_value=new)
    monkeypatch.setattr(resilient_stream, 'fallback_socket_is_serving', vetting_hang)
    with pytest.raises(asyncio.CancelledError):
        await resilient_stream.reconnect_live_stt_socket(listener)
    assert new.leg_outcome.settled, 'unadopted raw leg must be closed on cancellation'


@pytest.mark.asyncio
async def test_owner_teardown_during_replay_is_classified_as_teardown(monkeypatch):
    """A replay rejection caused by owner teardown is not a provider send failure."""

    listener = make_receiver(monkeypatch)
    old = serving_leg(family='soniox')
    old.raw.die('soniox_rotation')
    listener.stt_socket = old
    listener._resilient_audio.append(b'\x00\x00', 0)
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    new = serving_leg(family='soniox')
    listener._create_stt_socket = AsyncMock(return_value=new)
    monkeypatch.setattr(resilient_stream, 'fallback_socket_is_serving', AsyncMock(return_value=True))

    async def teardown_mid_replay(*args, **kwargs):
        listener.host.state.active = False  # owner departs while replay is paced
        return False

    monkeypatch.setattr(listener, '_pump_replacement', teardown_mid_replay)
    reason = 'soniox_rotation'
    reconnect = RECONNECT.labels(provider='soniox', reason=reason, outcome='teardown')
    failed = RECONNECT.labels(provider='soniox', reason=reason, outcome='failed')
    reconnect_before, failed_before = reconnect._value.get(), failed._value.get()
    assert not await resilient_stream.reconnect_live_stt_socket(listener)
    assert reconnect._value.get() == reconnect_before + 1
    assert failed._value.get() == failed_before, 'teardown must not be recorded as a failed reconnect'
    assert new.leg_outcome.settled


@pytest.mark.asyncio
async def test_teardown_tail_send_cannot_recover_or_open_provider_circuit(monkeypatch):
    leg = serving_leg(family='soniox')
    leg.leg_outcome.owner_closing = True
    leg.raw.die('connection_lost')
    state = SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1000)
    client = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    recovery = AsyncMock(return_value=False)
    opened = []
    monkeypatch.setattr(live_failure, '_open_serving_provider_circuit', lambda *args: opened.append(args))
    assert not await live_failure.send_live_stt_audio(
        client,
        state,
        stt_socket=leg,
        audio=b'\x00\x00',
        provider='soniox',
        platform='ios',
        attempt_failover=recovery,
    )
    recovery.assert_not_awaited()
    client.close.assert_not_awaited()
    assert opened == [] and not state.stt_terminal_failure
    leg.finish()


@pytest.mark.asyncio
async def test_monitor_stops_before_observing_teardown_transport(monkeypatch):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    leg = managed_leg(receiver, ServingSocket(), family='soniox')
    receiver.stt_socket = leg
    leg.leg_outcome.owner_closing = True
    leg.raw.die('connection_lost')
    receiver._failover_stt_socket = AsyncMock(return_value=False)
    await receiver._monitor_stt_death()
    receiver._failover_stt_socket.assert_not_awaited()
    assert not receiver.host.state.stt_terminal_failure
    leg.finish()


def test_missing_observation_ack_is_a_reconciliation_error(monkeypatch):
    monkeypatch.setattr(live_session.health, 'record_session', lambda *args: False)
    leg = serving_leg()
    before = COST_EMISSION_ACK_ERRORS._value.get()
    leg.finish()
    leg.finish()
    assert COST_EMISSION_ACK_ERRORS._value.get() == before + 1


def test_out_of_order_writer_cannot_rewind_the_healthy_user_budget():
    state = GateState()
    for _ in range(3):
        state = transition(state, True, 1300, witness='a' * 16)
    for now in (1000, 1300) * 23:
        assert transition(state, True, now, witness='a' * 16) == state
    assert state.n == 3 and state.healthy_window == 4


@pytest.mark.asyncio
async def test_monitor_survives_retiring_a_claimed_leg_during_reconnect(monkeypatch):
    from utils.stt import resilient_stream

    listener = make_receiver(monkeypatch)
    old, new = serving_leg(family='soniox'), serving_leg(family='soniox')
    old.raw.die('soniox_rotation')
    listener.stt_socket = old
    listener._resilient_audio.append(b'\x00\x00', 0)
    listener._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 2)
    listener._wrap_legacy_stt_socket = lambda raw, epoch: raw
    listener.host.wait = AsyncMock(return_value=True)
    connecting, proceed = asyncio.Event(), asyncio.Event()

    async def connect(*args, **kwargs):
        connecting.set()
        await proceed.wait()
        return new

    listener._create_stt_socket = connect
    monkeypatch.setattr(resilient_stream, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    replacement = asyncio.create_task(listener._failover_stt_socket())
    await connecting.wait()
    assert old.leg_outcome.claimed and not old.leg_outcome.owner_closing
    monitor = asyncio.create_task(listener._monitor_stt_death())
    await asyncio.sleep(0)
    proceed.set()
    assert await replacement
    await monitor
    listener.host.wait.assert_awaited_once()  # The monitor followed the replacement.
    listener._settle_pending_live_failover_failure()
    new.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize('observer', ['monitor', 'send'])
async def test_teardown_winning_during_recovery_cannot_terminate_or_bench(monkeypatch, observer):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    leg = managed_leg(receiver, ServingSocket(), family='soniox')
    leg.raw.die('connection_lost')
    receiver.stt_socket = leg
    client = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    receiver.host.request.websocket = client
    opened = []
    monkeypatch.setattr(live_failure, '_open_serving_provider_circuit', lambda *args: opened.append(args))

    async def lose_to_teardown():
        leg.leg_outcome.owner_closing = True
        return False

    receiver._failover_stt_socket = lose_to_teardown
    if observer == 'monitor':
        await receiver._monitor_stt_death()
    else:
        await live_failure.send_live_stt_audio(
            client,
            receiver.host.state,
            stt_socket=leg,
            audio=b'\x00\x00',
            provider='soniox',
            platform='ios',
            attempt_failover=lose_to_teardown,
        )
    client.close.assert_not_awaited()
    assert not opened and not receiver.host.state.stt_terminal_failure
    leg.finish()


@pytest.mark.asyncio
async def test_cancelled_retry_settles_the_already_rejected_replacement(monkeypatch):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    raw = managed_leg(receiver, ServingSocket(), family='soniox')
    raw.raw.die('provider_5xx')
    before = observed('soniox', 'provider_failure', 'provider_5xx')

    async def cancelled(socket):
        raise asyncio.CancelledError()

    monkeypatch.setattr('routers.listen.receiver.abort_replay_socket', cancelled)
    with pytest.raises(asyncio.CancelledError):
        await receiver._reject_candidate(raw, None, None, None)
    assert raw.leg_outcome.settled
    assert observed('soniox', 'provider_failure', 'provider_5xx') == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'reason',
    [
        'soniox_request_timeout',
        'soniox_idle_timeout',
        'soniox_rotation',
        'soniox_invalid_hint',
        'vad_failed',
        'other',
        'allocation_rejected',
        'capability_mismatch',
    ],
)
async def test_censored_connect_rejections_never_accumulate_provider_circuit_failures(monkeypatch, reason):
    monkeypatch.setattr(
        live_chain, 'fallback_socket_is_serving', AsyncMock(side_effect=lambda raw: not raw.is_connection_dead)
    )
    for _ in range(4):
        leg = serving_leg(family='soniox')
        leg.raw.die(reason)
        _, service = await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=AsyncMock(return_value=leg),
            callbacks={st.STTService.modulate: AsyncMock(return_value=FakeSocket())},
            failed=set(),
            models=['soniox', 'modulate-velma-2'],
            routing_uid='synthetic',
            routing_language='en',
        )
        assert service == st.STTService.modulate
        assert leg.leg_outcome.settled
    assert st._soniox_circuit.state == 'closed' and st._soniox_circuit._failures == 0
    assert not live_chain.health._cost_local


@pytest.mark.asyncio
async def test_engine_mismatch_cannot_abandon_an_earlier_rejected_leg(monkeypatch):
    from config.live_stt_registry import DEFAULT_TARGETS

    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain, 'propose', lambda *args: list(DEFAULT_TARGETS[1:]))
    monkeypatch.setattr(
        live_chain, 'fallback_socket_is_serving', AsyncMock(side_effect=lambda raw: not raw.is_connection_dead)
    )
    source = serving_leg()
    source.routing_model = 'velma-2'
    source.raw.die('modulate_serve_error')
    mismatch = SimpleNamespace(
        is_connection_dead=False,
        finish=lambda: None,
        routing_target='soniox',
        routing_model='wrong',
        routing_endpoint=None,
    )
    before = observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error')
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(side_effect=[source, FakeSocket()]),
        callbacks={st.STTService.soniox: AsyncMock(side_effect=[mismatch, FakeSocket()])},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid='synthetic',
        routing_language='en',
        routing_models={'modulate': 'velma-2', 'soniox': 'soniox'},
    )
    assert service == st.STTService.soniox
    assert source.leg_outcome.settled
    assert observed('modulate-velma-2', 'provider_failure', 'modulate_serve_error') == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('missing_settlement', [False, True])
async def test_chain_handoff_oracle_detects_a_missing_settlement(monkeypatch, missing_settlement):
    from utils.stt.live_metrics import MANAGED_LEGS_OPENED, MANAGED_LEGS_SETTLED, MANAGED_LEGS_OPEN

    leg = serving_leg(family='soniox')
    metrics = [
        metric.labels(target='soniox') for metric in (MANAGED_LEGS_OPENED, MANAGED_LEGS_SETTLED, MANAGED_LEGS_OPEN)
    ]
    before = [metric._value.get() for metric in metrics]
    monkeypatch.setattr(st, 'stt_service_models', ['soniox'])
    socket, _ = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=AsyncMock(return_value=leg),
        callbacks={},
        failed=set(),
        models=['soniox'],
        routing_uid='synthetic',
        routing_language='en',
    )
    assert socket is leg
    assert [metric._value.get() - base for metric, base in zip(metrics, before)] == [1, 0, 1]
    ack_before = COST_EMISSION_ACK_ERRORS._value.get()
    if missing_settlement:
        monkeypatch.setattr(leg.leg_outcome, 'close', lambda _text: None)
    leg.finish()
    opened, settled, current = [metric._value.get() - base for metric, base in zip(metrics, before)]
    assert COST_EMISSION_ACK_ERRORS._value.get() == ack_before
    assert opened - settled - current == int(missing_settlement)
    assert current == 0
    leg.finish()
    assert metrics[2]._value.get() == before[2]


@pytest.mark.asyncio
async def test_connected_provider_death_still_invokes_failover():
    leg = serving_leg()
    leg.raw.die('modulate_serve_error')
    recover = AsyncMock(return_value=True)
    assert not leg.leg_outcome.owner_closing
    await live_failure.send_live_stt_audio(
        SimpleNamespace(send_json=AsyncMock(), close=AsyncMock()),
        SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1000),
        stt_socket=leg,
        audio=b'\x00\x00',
        provider='modulate',
        platform='ios',
        attempt_failover=recover,
    )
    recover.assert_awaited_once()
    leg.finish()


def test_saturated_outage_reserve_resets_on_success_and_cannot_be_filled_by_one_user():
    users = tuple((f'{i:016x}', 3) for i in range(HEALTHY_USERS))
    state = GateState(n=512, healthy_window=3, healthy_users=users)
    for i in range(46):
        state = transition(state, True, 1000, witness='f' * 16)
    assert state.stage == 100 and state.overflow_failures == ('f' * 16,)
    for burst in range(10):
        state = transition(state, False, 1000, witness='e' * 16)
        assert not state.overflow_failures
        for i in range(7):
            state = transition(state, True, 1000, witness=f'{HEALTHY_USERS + burst * 7 + i:016x}')
        assert state.stage == 100
    # Even after many overflow witnesses, a hard outage cannot exhaust reserve.
    state = transition(state, False, 1000, witness='e' * 16)
    for i in range(8):
        state = transition(state, True, 1000, witness=f'{10000 + i:016x}')
    assert state.stage == 0 and state.failures == 8


@pytest.mark.asyncio
async def test_saturated_fleet_window_benches_across_pods_and_preserves_bench_without_ttl():
    redis = MemoryRedis()
    pods = [live_health.FleetHealth(redis_client=redis) for _ in range(2)]
    users = tuple((f'{i:016x}', 3) for i in range(HEALTHY_USERS))
    await pods[0]._cost_update(('soniox', 'all'), lambda _: GateState(n=512, healthy_window=3, healthy_users=users))
    for i in range(8):
        await pods[i % 2]._write_cost_result('soniox', 'en', True, None, f'{HEALTHY_USERS + i:016x}')
    state = GateState.decode(json.loads(redis.data[live_stt_state.cost_key(SONIOX, 'all')]))
    assert state.stage == 0 and state.failures == 8
    assert not state.healthy_users and not state.overflow_failures
    assert redis.ttls[live_stt_state.cost_key(SONIOX, 'all')] == 0
