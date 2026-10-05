"""Cost gates and recovery with synthetic session outcomes and fake Redis only."""

import asyncio
import json
import math
import random
import time
from collections import deque
from contextlib import suppress
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import live_stt_state
from config.live_stt_registry import DEFAULT_TARGETS, Target, assigned, registry, routing_on
from utils.stt import (
    connect_backoff as connect_backoff_module,
    live_failure,
    live_chain,
    live_health,
    live_session,
    live_router,
    soniox as soniox_module,
    streaming as st,
)
from utils.stt.live_cost_health import CostHealthUnavailable
from utils.stt.live_gate import GateState, begin_trial, transition
from utils.stt.live_signal import PROVIDER_FAILURE_REASONS, provider_observation
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.live_router import select, connecting_target
from utils.stt.live_rollout import window_allocation
from utils.stt.live_metrics import COST_SHADOW, COST_DECISION, CONNECT_BACKOFF


@pytest.fixture(autouse=True)
def controls(monkeypatch):
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '0')
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    monkeypatch.delenv('STT_ROUTING_TARGETS_JSON', raising=False)
    monkeypatch.delenv('STT_ROUTING_DISRUPTION_GATE', raising=False)
    # Scope every new test's process state; do not poison another module's circuits.
    for family in ('parakeet', 'modulate', 'soniox', 'deepgram'):
        monkeypatch.setattr(st, f'_{family}_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30))
    monkeypatch.setattr(live_router, '_target_circuits', {})
    monkeypatch.setattr(live_router, '_capacity_until', {})
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    monkeypatch.setattr(pod, 'schedule', lambda coroutine: coroutine.close())
    monkeypatch.setattr(live_chain, 'health', pod)
    monkeypatch.setattr(live_session, 'health', pod)
    monkeypatch.setattr(st, 'health', pod)
    monkeypatch.setattr(live_health, 'health', pod)
    monkeypatch.setattr(live_chain, '_recent_connect_failures', deque(maxlen=1000))
    monkeypatch.setattr(soniox_module, '_rate_limit_events', [])
    monkeypatch.setattr(soniox_module, '_last_rate_limit_error_log', float('-inf'))
    monkeypatch.setattr(
        connect_backoff_module,
        '_shared',
        connect_backoff_module.ConnectRefusalBackoff(on_event=live_chain._connect_backoff_event),
    )


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
    before = COST_DECISION.labels(target='soniox', reason='failover')._value.get()
    for uid in map(str, range(3000)):
        assert select(DEFAULT_TARGETS, {}, uid, 'en')[0].id == 'parakeet-window'
    assert COST_DECISION.labels(target='soniox', reason='failover')._value.get() == before


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


def test_staged_recovery_and_exponential_backoff():
    state = GateState()
    for i in range(8):
        state = transition(state, True, 0, witness=f'{i:016x}')
    assert state.stage == 0 and state.until == 300
    assert begin_trial(state, 299) == state
    state = begin_trial(state, 300)
    assert state.stage == 5
    for i in range(30):
        state = transition(state, False, 600, witness=f'{i % 10:016x}')
    assert state.stage == 25 and state.n == 0
    for i in range(60):
        state = transition(state, False, 1200, witness=f'{i % 20:016x}')
    assert state.stage == 100
    for i in range(8):
        state = transition(state, True, 1200, witness=f'{i:016x}')
    assert state.until == 1800  # retained strike until a full healthy evidence block
    state = begin_trial(state, 1800)
    for i in range(8):
        state = transition(state, True, 1800, witness=f'{i:016x}')
    assert state.stage == 0 and state.until == 3000
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
    def __init__(self, clock=None):
        self.data = {}
        self.leases = []
        self.ttls = {}
        self.expires_at = {}
        self.clock = clock or (lambda: 1000)

    def _expire_keys(self):
        now = self.clock()
        for key in [key for key, deadline in self.expires_at.items() if deadline <= now]:
            self.expires_at.pop(key, None)
            self.data.pop(key, None)

    async def time(self):
        return (int(self.clock()), 0)

    async def get(self, key):
        self._expire_keys()
        return self.data.get(key)

    async def mget(self, keys):
        self._expire_keys()
        return [self.data.get(key) for key in keys]

    async def set(self, key, value, nx=False, ex=None, **kwargs):
        self._expire_keys()
        if nx and key in self.data:
            return False
        self.data[key] = value
        self.expires_at.pop(key, None)
        if ex:
            self.expires_at[key] = self.clock() + ex
        self.leases.append(key)
        return True

    @staticmethod
    def _bench_deadline(raw, kind):
        head, _, tail = raw.partition(':')
        if head != kind:
            return 0.0
        try:
            return float(tail)
        except ValueError:
            return 0.0

    def _bench_update(self, endpoint_key, account_key, kind, incoming):
        self._expire_keys()
        endpoint = self.data.get(endpoint_key, '')
        account = self.data.get(account_key, '')
        now = self.clock()
        account_until = self._bench_deadline(account, 'account')
        if incoming <= now:
            return [account if account_until > now else endpoint, '0']
        if kind == 'selection' and account_until > now:
            return [account, '0']
        key = account_key if kind == 'account' else endpoint_key
        raw = account if kind == 'account' else endpoint
        until_at = self._bench_deadline(raw, kind)
        if until_at >= incoming:
            return [raw, '0']
        retained = max(until_at, incoming)
        value = f'{kind}:{retained:.3f}'
        self.data[key] = value
        self.expires_at[key] = now + math.ceil(retained - now) + 300
        return [value, '1']

    async def eval(self, script, _numkeys, *args):
        self._expire_keys()
        if script is live_health.BENCH_UPDATE:
            return self._bench_update(args[0], args[1], args[2], float(args[3]))
        if script is live_health.BENCH_CLEANUP:
            state_key, probe_key, expected = args
            if self.data.get(state_key, '') != expected:
                return 0
            _, _, raw_until = expected.partition(':')
            if float(raw_until or 0) > self.clock():
                return 0
            self.data.pop(state_key, None)
            self.data.pop(probe_key, None)
            self.expires_at.pop(state_key, None)
            self.expires_at.pop(probe_key, None)
            return 1
        key, expected, new, ttl = args
        if self.data.get(key, '') != expected:
            return 0
        self.data[key] = new
        self.expires_at.pop(key, None)
        if int(ttl) > 0:
            self.expires_at[key] = self.clock() + int(ttl)
        self.ttls[key] = ttl
        return 1

    def pipeline(self, *, transaction=False):
        redis = self

        class Pipe:
            def __init__(self):
                self.ops = []

            def incr(self, key):
                self.ops.append(('incr', key))
                return self

            def expire(self, key, seconds):
                self.ops.append(('expire', key, seconds))
                return self

            def delete(self, *keys):
                self.ops.append(('delete', keys))
                return self

            async def execute(self):
                redis._expire_keys()
                for op in self.ops:
                    if op[0] == 'incr':
                        redis.data[op[1]] = str(int(redis.data.get(op[1]) or 0) + 1)
                    elif op[0] == 'expire':
                        redis.expires_at[op[1]] = redis.clock() + op[2]
                    elif op[0] == 'delete':
                        for key in op[1]:
                            redis.data.pop(key, None)
                            redis.expires_at.pop(key, None)
                self.ops.clear()
                return []

        return Pipe()


@pytest.mark.asyncio
async def test_memory_redis_ttl_expiry_set_reset_and_persist():
    now = [0.0]
    redis = MemoryRedis(clock=lambda: now[0])
    score_ttl = live_health.SCORE_BUCKET_SECONDS * (live_health.SCORE_BUCKETS + 1)
    pipe = redis.pipeline()
    pipe.incr('score')
    pipe.expire('score', score_ttl)
    await pipe.execute()
    assert redis.expires_at['score'] == score_ttl
    now[0] = score_ttl - 1
    assert await redis.get('score') == '1'
    now[0] = score_ttl
    assert await redis.get('score') is None
    assert await redis.mget(['score']) == [None]
    await redis.set('bench', 'selection:100.000', ex=10)
    await redis.set('bench', 'selection:200.000')
    now[0] = score_ttl + 20
    assert await redis.get('bench') == 'selection:200.000'
    await redis.set('cost', 'healthy', ex=900)
    await redis.eval('cas', 1, 'cost', 'healthy', 'promoted', 0)
    now[0] = score_ttl + 20 + 1000
    assert await redis.get('cost') == 'promoted'
    await redis.set('expired', 'x', ex=1)
    now[0] += 2
    pipe = redis.pipeline()
    pipe.incr('expired')
    await pipe.execute()
    assert redis.data['expired'] == '1'


def seed_cost_interest(pod, targets, *languages):
    for language in languages:
        with suppress(CostHealthUnavailable):
            pod.cost_snapshot(targets, language)


def mark_cost_read(pod, targets=DEFAULT_TARGETS):
    pod._cost_fresh.update({(t.id, lang): 0.0 for t in targets for lang in ('all', *live_stt_state.ROUTED_LANGUAGES)})


def healthy_cost_snapshot(targets, _language):
    return {target.id: GateState() for target in targets}


@pytest.mark.asyncio
async def test_fleet_counts_recovery_lease_and_stale_generation(monkeypatch):
    now = [0]
    redis = MemoryRedis(clock=lambda: now[0])
    pods = [live_health.FleetHealth(redis_client=redis, clock=lambda: now[0]) for _ in range(2)]
    for pod in pods:
        seed_cost_interest(pod, DEFAULT_TARGETS, 'en')
    for i in range(8):
        await pods[i % 2]._write_cost_result('parakeet-window', 'en', True, None, f'{i:016x}')
    await asyncio.gather(*(pod.refresh_cost_once() for pod in pods))
    assert all(pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 0 for pod in pods)
    now[0] = 300
    for pod in pods:
        pod.prefer_recovery('parakeet-window', 'en')
    await asyncio.gather(*(pod.refresh_cost_once() for pod in pods))
    await asyncio.gather(*(pod.refresh_cost_once() for pod in pods))
    assert all(pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 5 for pod in pods)
    assert len(redis.leases) == 2  # global and language coordinators, never one per pod
    for i in range(30):
        await pods[0]._write_cost_result('parakeet-window', 'en', False, {'all': 1, 'en': 1}, f'{i:016x}')
    # generation 1 was bench; trial has generation 2. Old completions cannot promote.
    await pods[0].refresh_cost_once()
    assert pods[0].cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 5
    now[0] = 600
    for i in range(30):
        await pods[0]._write_cost_result('parakeet-window', 'en', False, {'all': 2, 'en': 2}, f'{i:016x}')
    await pods[0].refresh_cost_once()
    assert pods[0].cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 25


@pytest.mark.asyncio
async def test_redis_down_local_health_and_no_independent_trials(monkeypatch):
    class DownRedis:
        async def mget(self, _keys):
            raise ConnectionError('down')

    pod = live_health.FleetHealth(redis_client=DownRedis(), clock=lambda: 1000)
    monkeypatch.setattr(pod, 'schedule', lambda coroutine: coroutine.close())
    for i in range(8):
        pod.record_session('parakeet-window', 'en', 'failover', reason='connection_lost', uid=str(i))
    mark_cost_read(pod)
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
    fallbacks = []
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **event: fallbacks.append(event))
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
    assert fallbacks == []  # A policy-selected primary is not a failed connection.


def test_synthetic_outage_and_brownout_replay():
    rng, state = random.Random(20261001), GateState()
    detection = []
    for failure_rate in (0.03, 1.0, 0.03, 0.25):
        if state.stage == 0:
            state = begin_trial(state, state.until)
            now = state.trial_started_at + 300
            for i in range(30):
                state = transition(state, False, now, witness=f'{i % 10:016x}')
            now = state.trial_started_at + 600
            for i in range(60):
                state = transition(state, False, now, witness=f'{i % 20:016x}')
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
    modulate = AsyncMock(return_value=sock)
    with pytest.raises(live_chain.ProviderChainUnavailable):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=AsyncMock(return_value=sock),
            callbacks={st.STTService.modulate: modulate},
            failed=set(),
            models=['soniox', 'modulate-velma-2'],
            routing_uid='u',
            routing_language='en',
        )
    modulate.assert_not_awaited()
    _, chosen = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=AsyncMock(return_value=sock),
        callbacks={st.STTService.modulate: modulate},
        failed=set(),
        models=['soniox', 'modulate-velma-2'],
        routing_uid=None,
        routing_language='en',
    )
    assert chosen == st.STTService.soniox


@pytest.mark.asyncio
async def test_all_fleet_benched_fails_open_to_configured_order(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda *_: {'soniox': GateState(stage=0, until=1e20)})
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    connect = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    _, actual = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=connect,
        callbacks={},
        failed=set(),
        models=['soniox'],
        routing_uid='u',
        routing_language='en',
    )
    assert actual == st.STTService.soniox
    connect.assert_awaited_once()


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
    fallbacks = []
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **event: fallbacks.append(event))

    async def connect():
        target = connecting_target.get()
        seen.append(target.id)
        if target.id == 'modulate-next':
            raise ConnectionError('synthetic outage')
        return SimpleNamespace(is_connection_dead=False)

    failed, failed_targets = set(), set()
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=connect,
        callbacks={},
        failed=failed,
        failed_targets=failed_targets,
        models=['modulate-velma-2'],
        routing_uid='u',
        routing_language='en',
    )
    assert service == st.STTService.modulate
    assert seen == ['modulate-next', 'modulate-velma-2']
    assert not failed
    assert failed_targets == {'modulate-next'}
    assert connecting_target.get() is None
    assert [(event['from_mode'], event['to_mode'], event['outcome']) for event in fallbacks] == [
        ('modulate', 'modulate', 'recovered')
    ]


@pytest.mark.asyncio
async def test_modulate_endpoint_uses_existing_protocol_socket(monkeypatch):
    from utils.stt import live_target_connect

    target = Target('modulate-next', 'modulate', 0.05, endpoint='wss://example.invalid/stream')
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-key')
    connect = AsyncMock(return_value=object())
    monkeypatch.setattr(live_target_connect.websockets, 'connect', connect)
    constructor = lambda *args: SimpleNamespace(ws=args[0])
    monkeypatch.setattr(st, 'SafeModulateSocket', constructor)
    token = connecting_target.set(target)
    try:
        result = await live_target_connect.connect_modulate(lambda *_: None, 16000, 'en')
    finally:
        connecting_target.reset(token)
    url = connect.call_args.args[0]
    assert url.startswith('wss://example.invalid/stream?') and 'sample_rate=16000' in url and 'language=en' in url
    assert result.ws is connect.return_value
    assert result.routing_endpoint == target.endpoint


def test_capacity_skip_keeps_cost_order(monkeypatch):
    monkeypatch.setenv('TEST_TARGET_AT_CAPACITY', 'true')
    targets = [replace(DEFAULT_TARGETS[0], capacity_env='TEST_TARGET_AT_CAPACITY'), *DEFAULT_TARGETS[1:]]
    assert select(targets, {}, 'u', 'en')[0].id == 'modulate-velma-2'


@pytest.mark.asyncio
async def test_capacity_escape_dials_when_other_candidate_circuit_is_open(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('TEST_CAPACITY_ESCAPE_A', 'true')
    candidate_a = replace(DEFAULT_TARGETS[1], capacity_env='TEST_CAPACITY_ESCAPE_A')
    candidate_b = DEFAULT_TARGETS[-1]
    targets = [candidate_a, candidate_b]
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([target.__dict__ for target in targets]))
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain, 'propose', lambda *args: targets)
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(
        st,
        '_circuit_for_primary',
        lambda service: SimpleNamespace(
            state='open' if service == st.STTService.soniox else 'closed',
            allow_request=lambda **_: service != st.STTService.soniox,
            deferred_result_callbacks=lambda: (lambda: None, lambda: None),
        ),
    )
    seen = []

    async def connect_a():
        seen.append(connecting_target.get().id)
        return SimpleNamespace(is_connection_dead=False)

    async def connect_b():
        seen.append(connecting_target.get().id)
        return SimpleNamespace(is_connection_dead=False)

    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=connect_a,
        callbacks={st.STTService.soniox: connect_b},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid='synthetic',
        routing_language='en',
    )

    assert service == st.STTService.modulate
    assert seen == [candidate_a.id]


@pytest.mark.asyncio
async def test_admitted_non_capacity_candidate_dial_suppresses_capacity_escape(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('TEST_CAPACITY_ESCAPE_A', 'true')
    candidate_a = replace(DEFAULT_TARGETS[1], capacity_env='TEST_CAPACITY_ESCAPE_A')
    candidate_b = DEFAULT_TARGETS[-1]
    targets = [candidate_a, candidate_b]
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([target.__dict__ for target in targets]))
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain, 'propose', lambda *args: targets)
    seen = []

    async def connect_a():
        seen.append(connecting_target.get().id)
        return SimpleNamespace(is_connection_dead=False)

    async def connect_b():
        seen.append(connecting_target.get().id)
        raise ConnectionError('synthetic candidate failure')

    with pytest.raises(RuntimeError, match='chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=connect_a,
            callbacks={st.STTService.soniox: connect_b},
            failed=set(),
            models=['modulate-velma-2', 'soniox'],
            routing_uid='synthetic',
            routing_language='en',
        )

    assert seen == [candidate_b.id]


def _cooldown_targets():
    return [
        Target('modulate-a', 'modulate', 0.04, endpoint='wss://mod-a.invalid/stream'),
        Target('modulate-b', 'modulate', 0.05, endpoint='wss://mod-b.invalid/stream'),
        Target('modulate-velma-2', 'modulate', 0.055),
    ]


def _seed_backoff_cooldowns(*identities: str) -> None:
    backoff = connect_backoff_module.connect_backoff()
    for identity in identities:
        for _ in range(3):
            backoff.acquire(identity, provider='modulate').finish(refused=True)


@pytest.mark.asyncio
async def test_backoff_escape_dials_the_earliest_cooled_target_id_once(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    targets = _cooldown_targets()
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([target.__dict__ for target in targets]))
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain, 'propose', lambda *args: targets)
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    _seed_backoff_cooldowns('modulate-a', 'modulate-b', 'modulate-velma-2')
    escapes_before = CONNECT_BACKOFF.labels(provider='modulate', event='escape')._value.get()
    seen = []

    async def connect():
        seen.append(connecting_target.get().id)
        return SimpleNamespace(is_connection_dead=False)

    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=connect,
        callbacks={},
        failed=set(),
        models=['modulate-velma-2'],
        routing_uid='u',
        routing_language='en',
    )

    assert service == st.STTService.modulate
    assert seen == ['modulate-a']
    assert CONNECT_BACKOFF.labels(provider='modulate', event='escape')._value.get() == escapes_before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('exclusion', ['account', 'failed_targets'])
async def test_backoff_escape_never_bypasses_hard_exclusions(monkeypatch, exclusion):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    targets = _cooldown_targets()
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([target.__dict__ for target in targets]))
    if exclusion == 'account':
        monkeypatch.setattr(
            live_chain.health,
            'cached_snapshot',
            lambda *_: {'modulate': live_health.ProviderState(bench='account', bench_until=time.time() + 600)},
        )
        failed_targets = set()
    else:
        monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
        failed_targets = {target.id for target in targets}
    monkeypatch.setattr(live_chain, 'propose', lambda *args: targets)
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    _seed_backoff_cooldowns('modulate-a', 'modulate-b', 'modulate-velma-2')
    connect = AsyncMock(side_effect=AssertionError('no cooled route may be force-dialed'))
    with pytest.raises(RuntimeError, match='chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=connect,
            callbacks={},
            failed=set(),
            failed_targets=failed_targets,
            models=['modulate-velma-2'],
            routing_uid='u',
            routing_language='en',
        )
    connect.assert_not_called()


@pytest.mark.parametrize('mode', ['dirty', 'clean'])
def test_process_singletons_start_fresh_each_test(monkeypatch, mode):
    backoff = connect_backoff_module.connect_backoff()
    assert backoff is live_chain.connect_backoff()
    if mode == 'dirty':
        monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
        for _ in range(3):
            backoff.acquire('soniox', provider='soniox').finish(refused=True)
        live_chain._recent_connect_failures.append((time.monotonic(), 'soniox'))
        live_router.note_capacity_full('modulate-velma-2')
        live_router.target_circuit(Target('custom', 'modulate', 0.05, endpoint='wss://x.invalid'))
        live_chain.health.quarantine('soniox', 'selection', 60)
        soniox_module._rate_limit_events.append(time.monotonic())
        assert backoff._states
        assert live_chain._recent_connect_failures
        assert live_router._capacity_until
        assert live_router._target_circuits
        assert live_chain.health._benches
        assert soniox_module._rate_limit_events
        return
    assert not backoff._states
    assert not live_chain._recent_connect_failures
    assert not live_router._capacity_until
    assert not live_router._target_circuits
    assert not soniox_module._rate_limit_events
    pod = live_chain.health
    assert pod is live_session.health is st.health is live_health.health
    assert not pod._benches


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
    live_failure.settle_terminal_socket(failed, 'modulate', 'connection_lost')
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
    assert [args[2] for args in seen] == ['text', 'failover', 'no_text', 'no_text']


def test_send_exception_is_provider_failure_but_vad_exception_stays_censored(monkeypatch):
    from tests.unit.test_live_routing_health import SpeechGate, _leg

    seen = []
    monkeypatch.setattr(live_session.health, 'record', lambda *_: None)
    monkeypatch.setattr(live_session.health, 'record_session', lambda *args: seen.append(args))

    send_failed = _leg()

    def raise_connection_error(_audio):
        raise ConnectionError('provider transport unavailable')

    send_failed.raw.send = raise_connection_error
    assert send_failed.send(b'\x01\x00' * 16000) is False
    live_failure.settle_terminal_socket(send_failed, 'modulate', 'send_failed')
    assert len(seen) == 1
    assert seen[0][2] == 'failover'
    assert seen[0][5] in PROVIDER_FAILURE_REASONS
    assert provider_observation(seen[0][2], seen[0][5]) is True

    class FailingGate(SpeechGate):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def process_audio(self, audio, wall, score_pcm=None, *, start_sample=None):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError('VAD failed')
            return super().process_audio(audio, wall, score_pcm, start_sample=start_sample)

    vad_failed = _leg(FailingGate())
    vad_failed.window = True
    assert vad_failed.send(b'\x01\x00' * 16000)
    assert vad_failed.send(b'\x01\x00' * 16000) is False
    live_failure.settle_terminal_socket(vad_failed, 'parakeet', 'connection_lost')
    assert len(seen) == 2
    assert seen[1][2] == 'failover'
    assert seen[1][5] == 'vad_failed'
    assert provider_observation(seen[1][2], seen[1][5]) is None


@pytest.mark.asyncio
async def test_unknown_health_redis_down_restores_static_order(monkeypatch):
    class Down:
        async def mget(self, _keys):
            raise ConnectionError('synthetic Redis outage')

    pod = live_health.FleetHealth(redis_client=Down(), clock=lambda: 1000)
    seed_cost_interest(pod, DEFAULT_TARGETS, 'en')
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
    seed_cost_interest(pod, DEFAULT_TARGETS, 'fr', 'en')
    for i in range(40):
        await pod._write_cost_result('modulate-velma-2', 'en', False, None, f'{i:016x}')
    for i in range(8):
        for j in range(15):
            await pod._write_cost_result('modulate-velma-2', 'en', False, None, f'{j:016x}')
        await pod._write_cost_result('modulate-velma-2', 'fr', True, None, f'{i:016x}')
    await pod.refresh_cost_once()
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'fr')['modulate-velma-2'].stage == 0
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['modulate-velma-2'].stage == 100


def test_redis_fault_retains_language_specific_bench():
    pod = live_health.FleetHealth(redis_client=MemoryRedis(), clock=lambda: 1000)
    pod._cost_cached[('modulate-velma-2', 'fr')] = GateState(stage=0, until=2000)
    pod._redis_retry_at = 1010
    mark_cost_read(pod)
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'fr')['modulate-velma-2'].stage == 0
    # The known French bench must not contaminate an unrelated healthy English view.
    pod._cost_local[('modulate-velma-2', 'en')] = GateState(n=50)
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['modulate-velma-2'].stage == 100


def test_gate_config_change_starts_fresh_evidence_generation(monkeypatch):
    old = GateState(n=500, failures=15, generation=3)
    monkeypatch.setenv('STT_ROUTING_DISRUPTION_GATE', '0.12')
    new = transition(old, False, 0)
    assert new.threshold == 0.12 and new.n == 1 and new.failures == 0 and new.generation == 4
    benched = replace(old, stage=0, until=100)
    new = transition(benched, False, 0)
    assert new.stage == 0 and new.until == 100 and new.threshold == 0.12


def test_invalid_shared_gate_state_is_rejected():
    with pytest.raises(ValueError, match='invalid cost gate state'):
        GateState.decode({'stage': 50})


def test_learned_language_capabilities_cannot_be_overridden_by_cost():
    assert select(DEFAULT_TARGETS, {}, 'u', 'en', required_languages=('hi', 'en'))[0].id == 'modulate-velma-2'
    assert select(DEFAULT_TARGETS, {}, 'u', 'en', required_languages=('fr', 'en'))[0].id == 'parakeet-window'
    restricted = [Target('restricted', 'modulate', 0.01, languages=('en',)), DEFAULT_TARGETS[2]]
    assert select(restricted, {}, 'u', 'en', required_languages=('ja', 'en'))[0].id == 'soniox'


@pytest.mark.asyncio
async def test_expected_languages_flow_through_dispatcher_to_cost_selection(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox'])
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    sock = SimpleNamespace(is_connection_dead=False)
    parakeet = AsyncMock(return_value=sock)
    _, service = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.parakeet,
        connect_primary=parakeet,
        connect_modulate=AsyncMock(return_value=sock),
        use_config=True,
        routing_uid='u',
        routing_language='en',
        routing_languages=('hi', 'en'),
    )
    assert service == st.STTService.modulate
    parakeet.assert_not_awaited()


def test_custom_endpoint_serve_failure_does_not_poison_default_endpoint(monkeypatch):
    from tests.unit.test_live_routing_health import _leg
    from utils.stt import live_failure, live_router

    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    target = Target('modulate-next', 'modulate', 0.05, endpoint='wss://example.invalid/stream')
    monkeypatch.setattr(live_router, '_target_circuits', {})
    leg = _leg()
    leg._routing_target_entry = target
    leg.routing_target = target.id
    leg.raw.typed_death_reason = st.MODULATE_DEATH_SERVE_ERROR
    assert live_failure.note_typed_provider_death(leg, 'modulate')
    assert live_failure.note_typed_provider_death(leg, 'modulate')
    assert st._modulate_circuit.state == 'closed'
    assert live_router.target_circuit(target, st._modulate_circuit).state == 'open'


@pytest.mark.parametrize('mode', ['shadow', 'on'])
def test_early_client_abort_cannot_poison_cost_health_or_serving_circuit(monkeypatch, mode):
    from tests.unit.test_live_routing_health import _leg

    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    seen = []
    monkeypatch.setattr(live_session.health, 'record', lambda *_: None)
    monkeypatch.setattr(live_session.health, 'record_session', lambda *args: seen.append(args))
    for _ in range(12):
        leg = _leg()
        leg.send(b'\x01\x00' * 16000)
        leg.finish()
        leg.finish()
    assert len(seen) == 12 and all(args[2] == 'no_text' for args in seen)
    assert st._modulate_circuit.state == 'closed'


@pytest.mark.asyncio
@pytest.mark.parametrize('text_during_drain', [False, True])
async def test_client_drain_censors_missing_text_but_counts_real_text(monkeypatch, text_during_drain):
    from tests.unit.test_live_routing_health import _leg

    seen = []
    monkeypatch.setattr(live_session.health, 'record', lambda *_: None)
    monkeypatch.setattr(live_session.health, 'record_session', lambda *args: seen.append(args))
    leg = _leg()
    leg.send(b'\x01\x00' * 16000)

    async def drain(raw):
        if text_during_drain:
            leg.note_selection_transcript([{'text': 'synthetic'}])
        raw.finish()

    monkeypatch.setattr(st, 'drain_stt_socket', drain)
    await leg.drain_and_close()
    leg.finish()
    assert [args[2] for args in seen] == (['text'] if text_during_drain else ['no_text'])


@pytest.mark.asyncio
async def test_one_uid_cannot_bench_and_small_cohort_can_promote():
    redis = MemoryRedis()
    pods = [live_health.FleetHealth(redis_client=redis, clock=lambda: 1000) for _ in range(2)]
    for pod in pods:
        seed_cost_interest(pod, DEFAULT_TARGETS, 'en')
    for i in range(100):
        await pods[i % 2]._write_cost_result('parakeet-window', 'en', True, None, '0' * 16)
    await pods[0].refresh_cost_once()
    assert pods[0].cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 100
    for i in range(1, 4):
        await pods[i % 2]._write_cost_result('parakeet-window', 'en', False, None, f'{i:016x}')
    await pods[0].refresh_cost_once()
    assert pods[0].cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 100
    for i in range(1, 4):
        await pods[i % 2]._write_cost_result('parakeet-window', 'en', True, None, f'{i:016x}')
    await pods[0].refresh_cost_once()
    state = pods[0].cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window']
    assert state.stage == 100  # Repeated caller votes were capped, not banked.
    for i in range(8):
        await pods[0]._write_cost_result('parakeet-window', 'en', True, None, f'{i + 100:016x}')
    await pods[0].refresh_cost_once()
    state = pods[0].cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window']
    assert state.stage == 0
    state = begin_trial(state, state.until)
    for i in range(30):
        state = transition(state, False, state.trial_started_at + 300, witness=f'{i % 10:016x}')
    assert state.stage == 25
    for i in range(60):
        state = transition(state, False, state.trial_started_at + 600, witness=f'{i % 20:016x}')
    assert state.stage == 100
    warm = GateState()
    for i in range(100):
        warm = transition(warm, i % 32 == 0, 0, witness=f'{i:016x}')
    for _ in range(100):
        warm = transition(warm, True, 0, witness='f' * 16)
        assert warm.stage == 100


def test_fleet_writer_requires_an_authenticated_uid():
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    pod.record_session('parakeet-window', 'en', 'failover')
    assert pod._cost_local == {}


@pytest.mark.parametrize(
    'field,value',
    [
        ('languages', 'en'),
        ('languages', [1]),
        ('features', 'streaming'),
        ('features', [False]),
        ('capacity_env', []),
        ('capacity_env', 'not a variable'),
        ('endpoint', 123),
        ('endpoint', 'wss://'),
        ('endpoint', 'wss://example.invalid/#'),
        ('endpoint', 'wss://example.invalid/?'),
        ('endpoint', 'wss://bad host/stream'),
        ('endpoint', 'wss://user:secret@example.invalid/stream'),
        ('ramp_percent', True),
        ('cost_per_audio_hour', '0.05'),
    ],
)
def test_malformed_registry_fields_fail_open_instead_of_selecting_bad_targets(monkeypatch, field, value):
    entry = {'id': 'modulate-next', 'family': 'modulate', 'cost_per_audio_hour': 0.05, field: value}
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([entry]))
    with pytest.raises(ValueError):
        registry()


@pytest.mark.asyncio
async def test_local_bench_is_reconciled_before_redis_recovery_can_unbench(monkeypatch):
    now = [1000]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(redis_client=redis, clock=lambda: now[0])
    pod._redis_retry_at = 1010
    monkeypatch.setattr(pod, 'schedule', lambda coroutine: coroutine.close())
    for i in range(8):
        pod.record_session('parakeet-window', 'en', 'failover', reason='connection_lost', uid=str(i))
    mark_cost_read(pod)
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 0
    now[0] = 1010
    await pod.refresh_cost_once()
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 0
    parakeet = next(t for t in DEFAULT_TARGETS if t.id == 'parakeet-window')
    stored = json.loads(redis.data[live_stt_state.cost_key(parakeet, 'all')])
    assert stored['stage'] == 0 and stored['until'] == 1300
    now[0] = 1300
    pod.prefer_recovery('parakeet-window', 'en')
    await pod.refresh_cost_once()
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 5


@pytest.mark.asyncio
async def test_healthy_fleet_is_not_benched_by_an_isolated_pod_local_rate():
    redis = MemoryRedis()
    pod = live_health.FleetHealth(redis_client=redis, clock=lambda: 1000)
    parakeet = next(t for t in DEFAULT_TARGETS if t.id == 'parakeet-window')
    for lang in ('all', 'en'):
        healthy = GateState(n=200)
        redis.data[live_stt_state.cost_key(parakeet, lang)] = json.dumps(healthy.encode())
        pod._cost_local[('parakeet-window', lang)] = GateState(stage=0, generation=1, until=1300)
    seed_cost_interest(pod, DEFAULT_TARGETS, 'en')
    await pod.refresh_cost_once()
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 100
    assert not pod._cost_unreconciled
    pod._redis_retry_at = 1010
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 0
    pod._redis_retry_at = 0
    await pod._write_cost_result('parakeet-window', 'en', False, {'all': 0, 'en': 0}, '0' * 16)
    pod._redis_retry_at = 1010
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].stage == 100


def test_generation_capture_uses_the_same_backoff_view_as_selection():
    pod = live_health.FleetHealth(redis_client=MemoryRedis(), clock=lambda: 1000)
    mark_cost_read(pod)
    pod._redis_retry_at = 1010
    for lang in ('all', 'en'):
        pod._cost_local[('parakeet-window', lang)] = GateState(generation=2)
        pod._cost_cached[('parakeet-window', lang)] = GateState(generation=1)
    assert pod.cost_generations('parakeet-window', 'en') == {'all': 2, 'en': 2}
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].generation == 2
    for lang in ('all', 'en'):
        pod._cost_cached[('parakeet-window', lang)] = GateState(stage=5, generation=3)
    assert pod.cost_generations('parakeet-window', 'en') == {'all': 3, 'en': 3}
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['parakeet-window'].generation == 3


def test_unregistered_targets_do_not_create_cost_health_state():
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    pod.record_session('deepgram', 'en', 'failover', reason='connection_lost', uid='synthetic')
    assert pod._cost_local == {}


@pytest.mark.asyncio
async def test_withdrawn_registered_endpoint_cannot_return_as_configured_tail(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps(
            [
                {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055, 'ramp_percent': 0},
                {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754},
            ]
        ),
    )
    modulate = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    with pytest.raises(RuntimeError, match='chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=modulate,
            callbacks={st.STTService.soniox: AsyncMock(side_effect=ConnectionError('synthetic'))},
            failed=set(),
            models=['modulate-velma-2', 'soniox'],
            routing_uid='synthetic',
            routing_language='en',
        )
    modulate.assert_not_awaited()


@pytest.mark.parametrize('accessor_raises', [False, True])
def test_target_circuit_hook_errors_cannot_interrupt_failover(monkeypatch, accessor_raises):
    from utils.stt import live_failure

    class Broken:
        typed_death_reason = st.MODULATE_DEATH_SERVE_ERROR

        @property
        def record_target_death(self):
            if accessor_raises:
                raise RuntimeError('synthetic accessor failure')

            def fail(_reason):
                raise RuntimeError('synthetic hook failure')

            return fail

    seen = []
    monkeypatch.setattr(
        live_failure, '_open_serving_provider_circuit', lambda *args, **kwargs: seen.append((args, kwargs)) or True
    )
    assert live_failure.note_typed_provider_death(Broken(), 'modulate')
    assert seen == [((st.MODULATE_DEATH_SERVE_ERROR, 'modulate'), {'endpoint': None})]


@pytest.mark.asyncio
@pytest.mark.parametrize('stage,required', [(5, 30), (25, 60)])
async def test_static_out_of_cohort_sessions_cannot_accelerate_reentry(stage, required):
    redis = MemoryRedis()
    state = GateState(stage=stage, generation=1)
    parakeet = next(t for t in DEFAULT_TARGETS if t.id == 'parakeet-window')
    for lang in ('all', 'en'):
        redis.data[live_stt_state.cost_key(parakeet, lang)] = json.dumps(state.encode())
    pod = live_health.FleetHealth(redis_client=redis, clock=lambda: 1000)
    seed_cost_interest(pod, DEFAULT_TARGETS, 'en')
    await pod.refresh_cost_once()
    pending = []
    pod.schedule = pending.append
    inside = [str(i) for i in range(1000) if assigned(str(i), 'stt-reentry:parakeet-window', stage)][:20]
    outside = next(str(i) for i in range(1000) if not assigned(str(i), 'stt-reentry:parakeet-window', stage))

    async def record(uid):
        pod.record_session('parakeet-window', 'en', 'text', {'all': 1, 'en': 1}, uid)
        await pending.pop()

    for _ in range(required):
        await record(outside)
    assert pod._cost_cached[('parakeet-window', 'all')].n == 0
    for i in range(required):
        await record(inside[i % 20])
    assert pod._cost_cached[('parakeet-window', 'all')].stage == (25 if stage == 5 else 100)


@pytest.mark.asyncio
async def test_same_provider_reconnect_retains_target_identity_and_kill_switch(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic')
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps([{'id': 'soniox-canary', 'family': 'soniox', 'cost_per_audio_hour': 0.0754}]),
    )
    monkeypatch.setattr(st, 'stt_service_models', ['soniox'])
    monkeypatch.setattr(live_session, 'should_initialize_vad_gate', lambda **kwargs: False)
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', healthy_cost_snapshot)
    seen = []

    async def connect(*args, **kwargs):
        target = connecting_target.get()
        seen.append(target.id if target else None)
        return SimpleNamespace(is_connection_dead=False, finish=lambda: None)

    monkeypatch.setattr(st, 'process_audio_soniox', connect)
    recv = SimpleNamespace(
        host=SimpleNamespace(
            request=SimpleNamespace(uid='synthetic'),
            language='en',
            stt_language='en',
            multi_lang_enabled=False,
            language_profile=None,
            stt_model='soniox',
            stt_service=st.STTService.soniox,
            vocabulary=[],
        ),
        _stt_failed_providers=set(),
        vad_gate=None,
    )
    session = live_session.LiveChainSession(recv)
    first = await session.connect(16000)
    first.finish()
    second = await session.connect(16000, same_provider=True)
    assert second.routing_target == 'soniox-canary'
    assert second._routing_active
    second.finish()
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '0')
    third = await session.connect(16000, same_provider=True)
    assert not third._routing_active
    third.finish()
    assert seen == ['soniox-canary', 'soniox-canary', None]
    assert connecting_target.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['empty', 'deepgram-only', 'unknown-tail', 'benched-tail'])
async def test_router_never_removes_configured_serviceability(monkeypatch, scenario):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    primary = st.STTService.deepgram if scenario == 'deepgram-only' else st.STTService.soniox
    seen = []

    def connector(service, fails=False):
        async def connect():
            seen.append(service.value)
            if fails:
                raise ConnectionError('synthetic connect failure')
            return SimpleNamespace(is_connection_dead=False)

        return connect

    callbacks = {}
    models = ['dg-nova-3'] if scenario == 'deepgram-only' else ['soniox']
    if scenario == 'empty':
        monkeypatch.setattr(live_chain, 'propose', lambda *args: [])
    elif scenario == 'unknown-tail':
        callbacks[st.STTService.deepgram] = connector(st.STTService.deepgram)
        models.append('dg-nova-3')
    elif scenario == 'benched-tail':
        callbacks[st.STTService.modulate] = connector(st.STTService.modulate)
        models.append('modulate-velma-2')
        monkeypatch.setattr(
            live_chain.health,
            'cost_snapshot',
            lambda *_: {
                'soniox': GateState(),
                'modulate-velma-2': GateState(stage=0, until=1e20),
            },
        )
    _, service = await live_chain.connect_configured_chain(
        primary_service=primary,
        connect_primary=connector(primary, scenario in ('unknown-tail', 'benched-tail')),
        callbacks=callbacks,
        failed=set(),
        models=models,
        routing_uid='synthetic',
        routing_language='en',
    )
    expected = (
        st.STTService.deepgram
        if scenario == 'unknown-tail'
        else (st.STTService.modulate if scenario == 'benched-tail' else primary)
    )
    assert service == expected
    assert seen == ([primary.value, expected.value] if expected != primary else [primary.value])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'requested,resolved,model,endpoint',
    [
        ('multi', 'multi', 'parakeet-window', 'https://example.invalid'),
        ('en', 'en', 'parakeet-window', ''),
        ('en', 'en', 'parakeet', 'https://example.invalid'),
    ],
)
async def test_session_engine_choice_is_the_router_eligibility(monkeypatch, requested, resolved, model, endpoint):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', endpoint)
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic')
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'parakeet', 'soniox'])
    monkeypatch.setattr(st, 'parakeet_is_configured_fallback', lambda _: model == 'parakeet')
    monkeypatch.setattr(st, 'deepgram_fallback_model', lambda _: None)
    monkeypatch.setattr(live_session, 'should_initialize_vad_gate', lambda **kwargs: False)
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', healthy_cost_snapshot)
    seen = []

    def connector(engine):
        async def connect(*args, **kwargs):
            seen.append((engine, connecting_target.get()))
            return SimpleNamespace(is_connection_dead=False, finish=lambda: None)

        return connect

    monkeypatch.setattr(st, 'process_audio_parakeet', connector('parakeet'))
    monkeypatch.setattr(st, 'process_audio_soniox', connector('soniox'))
    recv = SimpleNamespace(
        host=SimpleNamespace(
            request=SimpleNamespace(uid='synthetic'),
            language=requested,
            stt_language=resolved,
            language_profile=None,
            stt_service=st.STTService.parakeet,
            stt_model=model,
            vocabulary=[],
        ),
        _stt_failed_providers=set(),
        vad_gate=None,
    )
    socket = await live_session.LiveChainSession(recv).connect(16000)
    assert socket.routing_target != 'parakeet-window'
    assert all(target is None or target.id != 'parakeet-window' for _, target in seen)
    assert socket.routing_target == 'soniox'
    socket.finish()


@pytest.mark.asyncio
async def test_connect_engine_mismatch_restores_configured_order_and_counts(monkeypatch):
    from utils.stt.live_metrics import COST_FAIL_OPEN

    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', healthy_cost_snapshot)
    calls = []
    before = COST_FAIL_OPEN.labels(reason='engine_mismatch')._value.get()

    async def connect():
        target = connecting_target.get()
        calls.append(target.id if target else None)
        return SimpleNamespace(
            is_connection_dead=False,
            finish=lambda: None,
            routing_target='parakeet-window',
            routing_model='parakeet',
            routing_endpoint=None,
        )

    _, actual = await live_chain.connect_configured_chain(
        primary_service=st.STTService.parakeet,
        connect_primary=connect,
        callbacks={},
        failed=set(),
        models=['parakeet-window'],
        routing_uid='synthetic',
        routing_language='en',
        routing_models={'parakeet': 'parakeet-window'},
    )
    assert actual == st.STTService.parakeet and calls == ['parakeet-window', None]
    assert COST_FAIL_OPEN.labels(reason='engine_mismatch')._value.get() == before + 1


@pytest.mark.asyncio
async def test_three_user_language_outage_does_not_bench_other_languages():
    now = [1000]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(redis_client=redis, clock=lambda: now[0])
    seed_cost_interest(pod, DEFAULT_TARGETS, 'fr', 'en')
    for i in range(18):
        now[0] = 1000 if i < 9 else 1300
        await pod._write_cost_result('modulate-velma-2', 'fr', True, None, f'{i % 3:016x}')
    await pod.refresh_cost_once()
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'fr')['modulate-velma-2'].stage == 0
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['modulate-velma-2'].stage == 100
    assert pod._cost_cached[('modulate-velma-2', 'all')].stage == 100


@pytest.mark.asyncio
async def test_server_clock_controls_deadlines_despite_sixty_second_pod_skew():
    now = [1000]
    redis = MemoryRedis(clock=lambda: now[0])
    pods = [live_health.FleetHealth(redis_client=redis, clock=lambda skew=skew: now[0] + skew) for skew in (-60, 60)]
    for pod in pods:
        seed_cost_interest(pod, DEFAULT_TARGETS, 'en')
    for i in range(8):
        await pods[i % 2]._write_cost_result('modulate-velma-2', 'en', True, None, f'{i:016x}')
    modulate = next(t for t in DEFAULT_TARGETS if t.id == 'modulate-velma-2')
    assert json.loads(redis.data[live_stt_state.cost_key(modulate, 'all')])['until'] == 1300
    now[0] = 1299
    for pod in pods:
        pod.prefer_recovery('modulate-velma-2', 'en')
        await pod.refresh_cost_once()
        assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['modulate-velma-2'].stage == 0
    now[0] = 1300
    for pod in pods:
        pod.prefer_recovery('modulate-velma-2', 'en')
        await pod.refresh_cost_once()
        assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['modulate-velma-2'].stage == 5


@pytest.mark.asyncio
async def test_ten_minute_redis_outage_remains_usable_then_reconciles(monkeypatch):
    now = [1000]

    class FlappingRedis(MemoryRedis):
        down = True

        async def time(self):
            if self.down:
                raise ConnectionError('synthetic ten minute outage')
            return await super().time()

    redis = FlappingRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(redis_client=redis, clock=lambda: now[0])
    monkeypatch.setattr(pod, 'schedule', lambda coro: coro.close())
    for i in range(8):
        pod.record_session('modulate-velma-2', 'en', 'failover', reason='connection_lost', uid=str(i))
        await pod._write_cost_result('modulate-velma-2', 'en', True, None, f'{i:016x}')
    mark_cost_read(pod)
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain, 'health', pod)
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    connect = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    for seconds in range(0, 600, 10):
        now[0] = 1000 + seconds
        await pod.refresh_cost_once()
        states = pod.cost_snapshot(DEFAULT_TARGETS, 'en')
        assert select(DEFAULT_TARGETS, states, 'synthetic', 'en')[0].id == 'parakeet-window'
        assert states['modulate-velma-2'].stage == 0
        _, actual = await live_chain.connect_configured_chain(
            primary_service=st.STTService.parakeet,
            connect_primary=connect,
            callbacks={},
            failed=set(),
            models=['parakeet-window'],
            routing_uid='synthetic',
            routing_language='en',
            routing_models={'parakeet': 'parakeet-window'},
        )
        assert actual == st.STTService.parakeet
    assert connect.await_count == 60
    now[0] = 1600
    redis.down = False
    await pod.refresh_cost_once()
    modulate = next(t for t in DEFAULT_TARGETS if t.id == 'modulate-velma-2')
    state = json.loads(redis.data[live_stt_state.cost_key(modulate, 'all')])
    assert state['stage'] == 0 and state['failures'] == 8
    assert not pod._cost_unreconciled
    assert (
        select(DEFAULT_TARGETS, pod.cost_snapshot(DEFAULT_TARGETS, 'en'), 'synthetic', 'en')[0].id == 'parakeet-window'
    )


def test_default_target_id_equal_to_family_has_separate_failure_namespaces(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    socket = SimpleNamespace(_routing_active=True, routing_target='soniox', typed_death_reason='provider_5xx')
    recv = SimpleNamespace(
        host=SimpleNamespace(request=SimpleNamespace(uid='synthetic')), stt_socket=socket, _stt_failed_providers=set()
    )
    assert live_router.note_failed_route(recv, 'soniox') == 1
    assert recv._stt_failed_targets == {'soniox'} and not recv._stt_failed_providers
    socket.typed_death_reason = 'provider_auth_rejected'
    assert live_router.note_failed_route(recv, 'soniox') == 2
    assert recv._stt_failed_providers == {'soniox'}


def test_single_user_failed_recovery_step_holds_without_fleet_strike():
    state = GateState(stage=5, strikes=1)
    for i in range(30):
        state = transition(state, i % 3 != 0, 1000, witness='f' * 16)
    assert state.stage == 5 and state.strikes == 1 and state.until == 0


@pytest.mark.parametrize('stage,required', [(5, 30), (25, 60)])
def test_two_user_failed_trial_holds_then_healthy_window_promotes(stage, required):
    state = GateState(stage=stage, strikes=2, generation=4)
    language = state
    for i in range(4 * required):
        # Sixteen failures by session 30, from two equally affected callers.
        failed = i % 30 < 16
        uid = f'{i % 2:016x}'
        state = transition(state, failed, 1000, witness=uid)
        language = transition(language, failed, 1000, witness=uid, language_only=True)
        assert state.stage == stage and state.strikes == 2 and state.generation == 4
    assert state.n == 6 and state.failures == 6  # bounded trial rate window
    assert language.stage == stage and language.n == 6  # repeated callers have capped trial evidence
    for i in range(required - 6):
        state = transition(state, False, 1000, witness=f'{100 + i:016x}')
    assert state.stage == (25 if stage == 5 else 100) and state.strikes == 2


@pytest.mark.parametrize('stage,required', [(5, 30), (25, 60)])
def test_broad_fixed_boundary_trial_rejection_spends_one_fleet_strike(stage, required):
    state = GateState(stage=stage, strikes=1, generation=4)
    # No sequential alarm: rejection at the boundary itself must check breadth.
    breadth = 10 if stage == 5 else 20
    failing_positions = {u + r * 2 * breadth for u in range(4) for r in range(2)}
    for i in range(required):
        state = transition(state, i in failing_positions, 1000, witness=f'{i % breadth:016x}')
        if i < required - 1:
            assert state.stage == stage
    assert state.stage == 0 and state.strikes == 2 and state.until == 1600 and state.generation == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'family,target_id',
    [
        ('parakeet', 'parakeet-window'),
        ('modulate', 'modulate-velma-2'),
        ('modulate', 'modulate-alias'),
    ],
)
@pytest.mark.parametrize('signalled', [True, False])
async def test_terminal_capacity_is_filtered_and_rejections_have_local_cooldown(
    monkeypatch, family, target_id, signalled
):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('TEST_TERMINAL_CAPACITY', str(signalled).lower())
    terminal = replace(
        next(t for t in DEFAULT_TARGETS if t.family == family), id=target_id, capacity_env='TEST_TERMINAL_CAPACITY'
    )
    healthy = DEFAULT_TARGETS[2]
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([terminal.__dict__, healthy.__dict__]))
    monkeypatch.setattr(
        live_chain.health,
        'cost_snapshot',
        lambda *_: {
            terminal.id: GateState(stage=0, strikes=1, until=1e20),
            'soniox': GateState(),
        },
    )
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'quarantine', lambda *args: pytest.fail('capacity must not bench health'))
    monkeypatch.setattr(st, '_soniox_circuit', ProviderCircuitBreaker(failure_threshold=1000, cooldown_seconds=30))
    if family == 'parakeet':
        monkeypatch.setattr(
            st, '_modulate_circuit', ProviderCircuitBreaker(failure_threshold=1000, cooldown_seconds=30)
        )
    now, attempts = [1000.0], []
    monkeypatch.setattr(live_router, '_capacity_clock', lambda: now[0])

    async def full():
        attempts.append(now[0])
        raise live_chain.RejectedStream('capacity_full')

    async def fails():
        raise ConnectionError('synthetic healthy candidate connect failure')

    async def connect():
        callbacks = {st.STTService(family): full}
        models = ['soniox', next(t.id for t in DEFAULT_TARGETS if t.family == family)]
        if family == 'parakeet':
            callbacks[st.STTService.modulate] = fails
            models.append('modulate-velma-2')
        with pytest.raises(RuntimeError, match='chain exhausted'):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.soniox,
                connect_primary=fails,
                callbacks=callbacks,
                failed=set(),
                models=models,
                routing_uid='synthetic',
                routing_language='en',
                routing_models={'parakeet': 'parakeet-window'},
            )

    for _ in range(20):
        await connect()
    assert attempts == ([] if signalled else [1000.0])
    now[0] += 4.999
    await connect()
    assert len(attempts) == (0 if signalled else 1)
    now[0] += 0.001
    await connect()
    assert len(attempts) == (0 if signalled else 2)
    assert getattr(st, f'_{family}_circuit').state == 'closed'
    assert live_router.target_circuit(terminal, getattr(st, f'_{family}_circuit')).state == 'closed'
    assert live_chain.health.cost_snapshot(DEFAULT_TARGETS, 'en')[terminal.id].strikes == 1


@pytest.mark.asyncio
async def test_empty_proposal_cannot_force_a_capacity_cooled_terminal(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain, 'propose', lambda *args: [])
    live_router.note_capacity_full('modulate-velma-2')
    circuit = st._modulate_circuit
    for _ in range(3):
        circuit.record_failure()
    connector = AsyncMock()
    with pytest.raises(RuntimeError, match='chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=connector,
            callbacks={},
            failed=set(),
            models=['modulate-velma-2'],
            routing_uid='synthetic',
            routing_language='en',
        )
    connector.assert_not_called()


@pytest.mark.asyncio
async def test_new_endpoint_only_registry_keeps_configured_endpoint_tail(monkeypatch):
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
            ]
        ),
    )
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', healthy_cost_snapshot)
    seen = []

    async def connect():
        target = connecting_target.get()
        seen.append(target.id if target else None)
        if target is not None:
            raise ConnectionError('synthetic new endpoint failure')
        return SimpleNamespace(is_connection_dead=False)

    _, actual = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=connect,
        callbacks={},
        failed=set(),
        models=['modulate-velma-2'],
        routing_uid='synthetic',
        routing_language='en',
    )
    assert actual == st.STTService.modulate and seen == ['modulate-next', None]


@pytest.mark.parametrize('language_only', [False, True])
def test_two_failing_users_and_healthy_majority_recover_after_trial_dwell(language_only):
    state = GateState(stage=5, strikes=2)
    completed = 0
    for stage, required, users, dwell in ((5, 30, 26, 300), (25, 60, 25, 600)):
        assert state.stage == stage
        now = state.trial_started_at + dwell
        for i in range(required):
            failed = i < 6
            uid = f'{i % 2:016x}' if failed else f'{2 + (i - 6) % (users - 2):016x}'
            state = transition(state, failed, now, witness=uid, language_only=language_only)
            completed += 1
            if i < required - 1:
                assert state.stage == stage and state.strikes == 2
        assert state.stage == (25 if stage == 5 else 100)
    assert state.stage == 100 and completed <= 360 and state.strikes == 2


def test_trial_majority_uses_admitted_user_outcomes_and_broad_late_failure_rejects():
    state = GateState(stage=5)
    # First three samples from each user pass, but a later outage dominates.
    for i in range(12):
        state = transition(state, False, 0, witness=f'{i % 4:016x}')
    for i in range(24):
        state = transition(state, True, 0, witness=f'{4 + i % 8:016x}')
    assert state.stage == 0 and state.strikes == 1


def test_trial_user_state_roundtrip_and_bounded_validation():
    state = GateState(stage=5)
    for i in range(29):
        state = transition(state, True, 0, witness=f'{i % 2:016x}')
    assert len(state.trial_users) == 2
    assert GateState.decode(json.loads(json.dumps(state.encode()))) == state
    for invalid in (
        [['x', 1, 0]],
        [['0' * 16, 241, 0]],
        [['0' * 16, 1, 2]],
        [['0' * 16, True, 0]],
        [['0' * 16, 1, 0], ['0' * 16, 1, 0]],
    ):
        with pytest.raises(ValueError):
            GateState.decode({**state.encode(), 'trial_users': invalid})


@pytest.mark.asyncio
@pytest.mark.parametrize('signalled', [False, True])
async def test_last_candidate_is_served_when_capacity_clears_during_cooldown(monkeypatch, signalled):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('TEST_ONLY_CAPACITY', str(signalled).lower())
    target = replace(DEFAULT_TARGETS[2], capacity_env='TEST_ONLY_CAPACITY')
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([target.__dict__]))
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    live_router.note_capacity_full(target.id)
    connector = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    sock, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=connector,
        callbacks={},
        failed=set(),
        models=['soniox'],
        routing_uid='synthetic',
        routing_language='en',
    )
    assert service == st.STTService.soniox and sock.is_connection_dead is False
    connector.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_capacity_refusals_escape_once_per_session_in_least_recent_order(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    targets = [replace(t, capacity_env='TEST_ALL_CAPACITY') for t in DEFAULT_TARGETS[1:]]
    monkeypatch.setenv('TEST_ALL_CAPACITY', 'true')
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([t.__dict__ for t in targets]))
    now = [1000.0]
    monkeypatch.setattr(live_router, '_capacity_clock', lambda: now[0])
    live_router.note_capacity_full('modulate-velma-2')
    now[0] = 1001
    live_router.note_capacity_full('soniox')
    seen = []

    def connector(name):
        async def connect():
            seen.append(name)
            raise live_chain.RejectedStream('capacity_full')

        return connect

    for i in range(4):
        now[0] += 1
        with pytest.raises(RuntimeError, match='chain exhausted'):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.modulate,
                connect_primary=connector('modulate'),
                callbacks={st.STTService.soniox: connector('soniox')},
                failed=set(),
                models=['modulate-velma-2', 'soniox'],
                routing_uid='synthetic',
                routing_language='en',
            )
        assert len(seen) == i + 1
    assert seen == ['modulate', 'soniox', 'modulate', 'soniox']


def test_shadow_pairs_are_bounded_and_global_stage_does_not_follow_language():
    from utils.stt.live_metrics import COST_STAGE, COST_EVENTS

    pod = live_chain.health
    target = DEFAULT_TARGETS[1]
    pod._cost_local[(target.id, 'all')] = GateState(stage=25)
    pod._cost_local[(target.id, 'fr')] = GateState(stage=0)
    mark_cost_read(pod)
    assert pod.cost_snapshot([target], 'fr')[target.id].stage == 0
    assert COST_STAGE.labels(target=target.id)._value.get() == 25
    labels = dict(agreement='disagree', static_primary='soniox', proposed_primary=target.id)
    before = COST_SHADOW.labels(**labels)._value.get()
    live_router.propose(
        pod,
        ['modulate', 'soniox'],
        next(str(i) for i in range(1000) if assigned(str(i), 'stt-reentry:' + target.id, 25)),
        'en',
        'soniox',
    )
    assert COST_SHADOW.labels(**labels)._value.get() == before + 1
    for event, old, new in (
        ('bench', GateState(), GateState(stage=0)),
        ('stage', GateState(stage=0), GateState(stage=5)),
        ('unbench', GateState(stage=25), GateState(generation=1)),
    ):
        metric = COST_EVENTS.labels(target=target.id, event=event, scope='global')
        before = metric._value.get()
        pod._cost_event(target.id, 'fr', old, new)
        assert metric._value.get() == before
        pod._cost_event(target.id, 'all', old, new)
        assert metric._value.get() == before + 1
        assert COST_STAGE.labels(target=target.id)._value.get() == new.stage
    labels = dict(agreement='disagree', static_primary='unregistered', proposed_primary='unavailable')
    before = COST_SHADOW.labels(**labels)._value.get()
    live_router.propose(pod, ['deepgram'], 'synthetic', 'en', 'arbitrary-unregistered-model')
    assert COST_SHADOW.labels(**labels)._value.get() == before + 1


@pytest.mark.asyncio
async def test_v8_starts_fresh_without_reinterpreting_teardown_contaminated_v7():
    redis = MemoryRedis()
    old_key = 'omi:live-stt:cost-v7:modulate-velma-2:all'
    old_evidence = json.dumps(GateState(stage=0, n=20, failures=20, generation=3, until=9999).encode())
    redis.data[old_key] = old_evidence
    pod = live_health.FleetHealth(redis_client=redis)
    await pod.refresh_cost_once()
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'en')['modulate-velma-2'].stage == 100
    await pod._write_cost_result('modulate-velma-2', 'en', True, None, '0123456789abcdef')
    assert redis.data[old_key] == old_evidence
    modulate = next(t for t in DEFAULT_TARGETS if t.id == 'modulate-velma-2')
    fresh = GateState.decode(json.loads(redis.data[live_stt_state.cost_key(modulate, 'all')]))
    assert fresh.n == fresh.failures == 1 and fresh.stage == 100
