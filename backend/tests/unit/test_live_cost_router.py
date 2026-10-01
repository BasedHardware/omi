"""Cost gates and recovery with synthetic session outcomes and fake Redis only."""

import asyncio
import json
import random
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.live_stt_registry import DEFAULT_TARGETS, Target, assigned, registry, routing_on
from utils.stt import live_chain, live_health, live_session, streaming as st
from utils.stt.live_gate import GateState, begin_trial, transition
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.live_router import select, connecting_target
from utils.stt.live_rollout import window_allocation
from utils.stt.live_metrics import COST_SHADOW


@pytest.fixture(autouse=True)
def controls(monkeypatch):
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '0')
    monkeypatch.delenv('STT_ROUTING_TARGETS_JSON', raising=False)
    monkeypatch.delenv('STT_ROUTING_DISRUPTION_GATE', raising=False)
    # Scope every new test's process state; do not poison another module's circuits.
    for family in ('parakeet', 'modulate', 'soniox', 'deepgram'):
        monkeypatch.setattr(st, f'_{family}_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30))
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    monkeypatch.setattr(pod, 'schedule', lambda coroutine: coroutine.close())
    monkeypatch.setattr(live_chain, 'health', pod)
    monkeypatch.setattr(live_session, 'health', pod)


def test_cost_capability_and_stable_ties():
    targets = [
        Target('soniox', 'soniox', 0.0754),
        Target('cheap', 'modulate', 0.02, languages=('en',)),
        Target('same-cost', 'modulate', 0.02),
        Target('parakeet-window', 'parakeet', 0.01),
    ]
    assert [t.id for t in select(targets, {}, 'u', 'en')] == ['parakeet-window', 'cheap', 'same-cost', 'soniox']
    assert [t.id for t in select(targets, {}, 'u', 'ja')] == ['same-cost', 'soniox']
    assert select(targets, {}, 'u', 'en', features=frozenset({'unsupported'})) == []


def test_all_traffic_cheapest_no_diversification():
    for uid in map(str, range(3000)):
        assert select(DEFAULT_TARGETS, {}, uid, 'en')[0].id == 'parakeet-window'


@pytest.mark.parametrize('warmup', [0, 100, 700, 1020])
def test_hard_outage_detection_samples(warmup):
    state = GateState()
    for _ in range(warmup):
        state = transition(state, False, 0)
    for detected in range(1, 20):
        state = transition(state, True, 0)
        if state.stage == 0:
            break
    assert detected <= 15
    assert state.stage == 0


def test_three_percent_false_positive_and_simulation(capsys):
    benches = 0
    runs, sessions = 200, 5000
    for seed in range(runs):
        rng, state = random.Random(seed), GateState()
        for _ in range(sessions):
            state = transition(state, rng.random() < 0.03, 0)
            if state.stage == 0:
                benches += 1
                break
    print(f'3% baseline: {benches}/{runs} runs benched across {runs * sessions} synthetic sessions')
    assert benches == 0


def test_staged_recovery_and_exponential_backoff():
    state = GateState()
    for _ in range(8):
        state = transition(state, True, 0)
    assert state.stage == 0 and state.until == 300
    assert begin_trial(state, 299) == state
    state = begin_trial(state, 300)
    assert state.stage == 5
    for _ in range(30):
        state = transition(state, False, 300)
    assert state.stage == 25 and state.n == 0
    for _ in range(60):
        state = transition(state, False, 300)
    assert state.stage == 100
    for _ in range(8):
        state = transition(state, True, 300)
    assert state.until == 900  # retained strike until a full healthy evidence block
    state = begin_trial(state, 900)
    for _ in range(8):
        state = transition(state, True, 900)
    assert state.stage == 0 and state.until == 2100
    chronic = replace(state, strikes=10, stage=5)
    for _ in range(8):
        chronic = transition(chronic, True, 0)
    assert chronic.until == 14400


def test_failed_trial_rebenches_at_fixed_sample_even_without_early_rejection():
    state = GateState(stage=5)
    for index in range(30):
        state = transition(state, index in (4, 14, 24), 0)
    assert state.stage == 0 and state.failures == 3


def test_expensive_bench_no_probes_and_cheaper_preferred():
    recovery = []
    states = {'soniox': GateState(stage=0)}
    assert select(DEFAULT_TARGETS, states, 'u', 'en', recovery=lambda *x: recovery.append(x))[0].id == 'parakeet-window'
    assert recovery == []
    states['parakeet-window'] = GateState(stage=0)
    assert (
        select(DEFAULT_TARGETS, states, 'u', 'en', recovery=lambda *x: recovery.append(x))[0].id == 'modulate-velma-2'
    )
    assert recovery == [('parakeet-window', 'en')]


def test_sticky_ramp_cohort_and_router_gate(monkeypatch):
    uids = list(map(str, range(1000)))
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '25')
    for uid in uids:
        assert assigned(uid, 'parakeet-window', 25) == window_allocation(uid)
    assert 210 < sum(window_allocation(uid) for uid in uids) < 290
    cohorts = [{uid for uid in uids if assigned(uid, 'new-modulate', share)} for share in (5, 25, 50, 100)]
    assert cohorts[0] < cohorts[1] < cohorts[2] < cohorts[3]
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    assert not any(routing_on(uid) for uid in uids)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '25')
    assert 210 < sum(routing_on(uid) for uid in uids) < 290
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    assert all(routing_on(uid) for uid in uids)
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    assert not any(routing_on(uid) for uid in uids)


class MemoryRedis:
    def __init__(self):
        self.data = {}
        self.leases = []

    async def get(self, key):
        return self.data.get(key)

    async def mget(self, keys):
        return [self.data.get(key) for key in keys]

    async def set(self, key, value, nx=False, **kwargs):
        if nx and key in self.data:
            return False
        self.data[key] = value
        self.leases.append(key)
        return True

    async def eval(self, _script, _numkeys, key, expected, new):
        if self.data.get(key, '') != expected:
            return 0
        self.data[key] = new
        return 1


@pytest.mark.asyncio
async def test_fleet_counts_recovery_lease_and_stale_generation(monkeypatch):
    redis, now = MemoryRedis(), [0]
    pods = [live_health.FleetHealth(redis_client=redis, clock=lambda: now[0]) for _ in range(2)]
    for pod in pods:
        pod.cost_snapshot(DEFAULT_TARGETS, 'en')
    for i in range(8):
        await pods[i % 2]._write_cost_result('parakeet-window', 'en', True, None)
    await asyncio.gather(*(pod.refresh_cost_once() for pod in pods))
    assert all(pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 0 for pod in pods)
    now[0] = 300
    for pod in pods:
        pod.prefer_recovery('parakeet-window', 'en')
    await asyncio.gather(*(pod.refresh_cost_once() for pod in pods))
    await asyncio.gather(*(pod.refresh_cost_once() for pod in pods))
    assert all(pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 5 for pod in pods)
    assert len(redis.leases) == 2  # global and language coordinators, never one per pod
    for _ in range(30):
        await pods[0]._write_cost_result('parakeet-window', 'en', False, {'all': 1, 'en': 1})
    # generation 1 was bench; trial has generation 2. Old completions cannot promote.
    await pods[0].refresh_cost_once()
    assert pods[0].cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 5
    for _ in range(30):
        await pods[0]._write_cost_result('parakeet-window', 'en', False, {'all': 2, 'en': 2})
    await pods[0].refresh_cost_once()
    assert pods[0].cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 25


@pytest.mark.asyncio
async def test_redis_down_local_health_and_no_independent_trials(monkeypatch):
    class DownRedis:
        async def mget(self, _keys):
            raise ConnectionError('down')

    pod = live_health.FleetHealth(redis_client=DownRedis(), clock=lambda: 1000)
    monkeypatch.setattr(pod, 'schedule', lambda coroutine: coroutine.close())
    for _ in range(8):
        pod.record_session('parakeet-window', 'en', 'failover')
    states = pod.cost_snapshot(DEFAULT_TARGETS, 'en')
    await pod.refresh_cost_once()
    assert select(DEFAULT_TARGETS, states, 'u', 'en')[0].id == 'modulate-velma-2'
    assert states['parakeet-window'].stage == 0
    assert not pod._cost_preferred
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'mode,percent,expected', [('shadow', '100', 'soniox'), ('on', '0', 'soniox'), ('on', '100', 'modulate')]
)
async def test_modes_static_shadow_and_on_percent(monkeypatch, mode, percent, expected):
    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', percent)
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(
        st,
        '_circuit_for_primary',
        lambda _: SimpleNamespace(
            state='closed',
            allow_request=lambda **_: True,
            deferred_result_callbacks=lambda: (lambda: None, lambda: None),
        ),
    )
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    sock = SimpleNamespace(is_connection_dead=False)
    result, actual = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=AsyncMock(return_value=sock),
        callbacks={st.STTService.modulate: AsyncMock(return_value=sock)},
        failed=set(),
        models=['soniox', 'modulate-velma-2'],
        routing_uid='u',
        routing_language='en',
    )
    assert actual.value == expected


def test_synthetic_outage_and_brownout_replay():
    rng, state = random.Random(20261001), GateState()
    detection = []
    for failure_rate in (0.03, 1.0, 0.03, 0.25):
        if state.stage == 0:
            state = begin_trial(state, state.until)
            for _ in range(90):
                state = transition(state, False, 20000)
        for index in range(1500):
            state = transition(state, rng.random() < failure_rate, 20000)
            if state.stage == 0:
                detection.append((failure_rate, index + 1))
                break
    print(f'Synthetic detection (speech sessions): {detection}')
    assert len(detection) == 2 and detection[0][0] == 1.0 and detection[0][1] <= 8
    assert detection[1][0] == 0.25 and detection[1][1] < 1000


def test_registry_override_second_modulate(monkeypatch):
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps(
            [
                {
                    'id': 'modulate-next',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'ramp_percent': 5,
                    'endpoint': 'wss://example.invalid/stream',
                },
                {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754},
            ]
        ),
    )
    assert registry()[0].endpoint == 'wss://example.invalid/stream'
    uid = next(str(i) for i in range(1000) if assigned(str(i), 'modulate-next', 5))
    assert select(registry(), {}, uid, 'en')[0].id == 'modulate-next'


@pytest.mark.asyncio
async def test_router_exception_fails_open_and_no_network_on_connect(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', '{broken')
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, '_redis', lambda: pytest.fail('network on connect'))
    monkeypatch.setattr(
        st,
        '_circuit_for_primary',
        lambda _: SimpleNamespace(
            state='closed',
            allow_request=lambda **_: True,
            deferred_result_callbacks=lambda: (lambda: None, lambda: None),
        ),
    )
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    sock = SimpleNamespace(is_connection_dead=False)
    _, chosen = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=AsyncMock(return_value=sock),
        callbacks={st.STTService.modulate: AsyncMock(return_value=sock)},
        failed=set(),
        models=['soniox', 'modulate-velma-2'],
        routing_uid='u',
        routing_language='en',
    )
    assert chosen == st.STTService.soniox


@pytest.mark.asyncio
async def test_fleet_bench_holds_against_local_half_open_and_last_resort(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda *_: {'soniox': GateState(stage=0, until=1e20)})
    connect = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    with pytest.raises(RuntimeError, match='chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=connect,
            callbacks={},
            failed=set(),
            models=['soniox'],
            routing_uid='u',
            routing_language='en',
        )
    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_modulate_targets_failover_and_independent_identity(monkeypatch):
    from utils.stt import live_router

    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps(
            [
                {
                    'id': 'modulate-next',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'endpoint': 'wss://example.invalid/stream',
                },
                {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055},
            ]
        ),
    )
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'quarantine', lambda *_: None)
    monkeypatch.setattr(
        st,
        '_circuit_for_primary',
        lambda _: SimpleNamespace(
            state='closed',
            allow_request=lambda **_: True,
            deferred_result_callbacks=lambda: (lambda: None, lambda: None),
        ),
    )
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    seen = []

    async def connect():
        target = connecting_target.get()
        seen.append(target.id)
        if target.id == 'modulate-next':
            raise ConnectionError('synthetic outage')
        return SimpleNamespace(is_connection_dead=False)

    failed = set()
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=connect,
        callbacks={},
        failed=failed,
        models=['modulate-velma-2'],
        routing_uid='u',
        routing_language='en',
    )
    assert service == st.STTService.modulate
    assert seen == ['modulate-next', 'modulate-velma-2']
    assert failed == {'modulate-next'}
    assert connecting_target.get() is None


@pytest.mark.asyncio
async def test_modulate_endpoint_uses_existing_protocol_socket(monkeypatch):
    from utils.stt import live_target_connect

    target = Target('modulate-next', 'modulate', 0.05, endpoint='wss://example.invalid/stream')
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-key')
    connect = AsyncMock(return_value=object())
    monkeypatch.setattr(live_target_connect.websockets, 'connect', connect)
    constructor = lambda *args: args
    monkeypatch.setattr(st, 'SafeModulateSocket', constructor)
    token = connecting_target.set(target)
    try:
        result = await live_target_connect.connect_modulate(lambda *_: None, 16000, 'en')
    finally:
        connecting_target.reset(token)
    url = connect.call_args.args[0]
    assert url.startswith('wss://example.invalid/stream?') and 'sample_rate=16000' in url and 'language=en' in url
    assert result[0] is connect.return_value


def test_capacity_skip_keeps_cost_order(monkeypatch):
    monkeypatch.setenv('TEST_TARGET_AT_CAPACITY', 'true')
    targets = [replace(DEFAULT_TARGETS[0], capacity_env='TEST_TARGET_AT_CAPACITY'), *DEFAULT_TARGETS[1:]]
    assert select(targets, {}, 'u', 'en')[0].id == 'modulate-velma-2'


def test_health_session_is_once_and_late_failure_after_text_counts(monkeypatch):
    from tests.unit.test_live_routing_health import _leg, SpeechGate

    seen = []
    monkeypatch.setattr(live_session.health, 'record', lambda *_: None)
    monkeypatch.setattr(live_session.health, 'record_session', lambda *args: seen.append(args))
    good = _leg()
    good.send(b'\x01\x00' * 16000)
    good.note_selection_transcript([{'text': 'synthetic'}])
    assert seen == []
    good.finish()
    good.finish()
    assert [args[2] for args in seen] == ['text']
    failed = _leg()
    failed.send(b'\x01\x00' * 16000)
    failed.note_selection_transcript([{'text': 'synthetic'}])
    failed._dead = True
    assert failed.is_connection_dead
    failed.finish()
    assert [args[2] for args in seen] == ['text', 'failover']
    no_text = _leg()
    no_text.send(b'\x01\x00' * 16000)
    no_text._first_speech_at = time.monotonic() - 60
    no_text._check_no_text_deadline()
    no_text.finish()
    assert [args[2] for args in seen] == ['text', 'failover', 'no_text']
    silent = _leg(SpeechGate(is_speech=False))
    silent.send(b'\x00\x00' * 16000)
    silent.finish()
    assert len(seen) == 3


@pytest.mark.asyncio
async def test_unknown_health_redis_down_restores_static_order(monkeypatch):
    class Down:
        async def mget(self, _keys):
            raise ConnectionError('synthetic Redis outage')

    pod = live_health.FleetHealth(redis_client=Down(), clock=lambda: 1000)
    pod.cost_snapshot(DEFAULT_TARGETS, 'en')
    await pod.refresh_cost_once()
    monkeypatch.setattr(live_chain, 'health', pod)
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    sock = SimpleNamespace(is_connection_dead=False)
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=AsyncMock(return_value=sock),
        callbacks={st.STTService.modulate: AsyncMock(return_value=sock)},
        failed=set(),
        models=['soniox', 'modulate-velma-2'],
        routing_uid='u',
        routing_language='en',
    )
    assert service == st.STTService.soniox


@pytest.mark.asyncio
async def test_language_only_outage_keeps_other_languages(monkeypatch):
    redis = MemoryRedis()
    pod = live_health.FleetHealth(redis_client=redis, clock=lambda: 1000)
    pod.cost_snapshot(DEFAULT_TARGETS, 'fr')
    pod.cost_snapshot(DEFAULT_TARGETS, 'en')
    for _ in range(500):
        await pod._write_cost_result('modulate-velma-2', 'en', False, None)
    for _ in range(8):
        for _ in range(99):
            await pod._write_cost_result('modulate-velma-2', 'en', False, None)
        await pod._write_cost_result('modulate-velma-2', 'fr', True, None)
    await pod.refresh_cost_once()
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'fr')['modulate-velma-2'].stage == 0
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['modulate-velma-2'].stage == 100
