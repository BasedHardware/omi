"""Router hardening reproductions: withdrawals, shared benches, and trial fairness.

Synthetic evidence only: fake Redis, fake sockets, monkeypatched env. No network,
no live Redis/Firestore/provider clients, no real credentials.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config import live_stt_state
from config.live_stt_registry import DEFAULT_TARGETS, Target, assigned
from utils.stt import live_chain, live_health, live_router, streaming as st
from utils.stt.live_cost_health import CostHealthUnavailable
from utils.stt.live_gate import GateState, transition
from utils.stt.live_metrics import COST_DECISION, COST_LANGUAGE_STATE, COST_VOTES
from utils.stt.provider_resilience import ProviderCircuitBreaker


class MemoryPipeline:
    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def incr(self, key):
        self._ops.append(('incr', key))
        return self

    def expire(self, key, seconds):
        self._ops.append(('expire', key, seconds))
        return self

    def delete(self, *keys):
        self._ops.append(('delete', keys))
        return self

    async def execute(self):
        for op in self._ops:
            if op[0] == 'incr':
                self._redis.data[op[1]] = str(int(self._redis.data.get(op[1]) or 0) + 1)
            elif op[0] == 'delete':
                for key in op[1]:
                    self._redis.data.pop(key, None)
        self._ops.clear()
        return []


class MemoryRedis:
    def __init__(self, clock=None):
        self.data = {}
        self.clock = clock or (lambda: 1000)

    async def time(self):
        return (int(self.clock()), 0)

    async def get(self, key):
        return self.data.get(key)

    async def mget(self, keys):
        return [self.data.get(key) for key in keys]

    async def set(self, key, value, nx=False, **_kwargs):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def eval(self, script, _numkeys, *args):
        if script is live_health.BENCH_UPDATE:
            return self._bench_update(args[0], args[1], args[2], float(args[3]))
        if script is live_health.BENCH_CLEANUP:
            return self._bench_cleanup(args[0], args[1], args[2])
        key, expected, new, _ttl = args
        if self.data.get(key, '') != expected:
            return 0
        self.data[key] = new
        return 1

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
        return [value, '1']

    def _bench_cleanup(self, state_key, probe_key, expected):
        if self.data.get(state_key, '') != expected:
            return 0
        _, _, raw_until = expected.partition(':')
        if float(raw_until or 0) > self.clock():
            return 0
        self.data.pop(state_key, None)
        self.data.pop(probe_key, None)
        return 1

    def pipeline(self, *, transaction=False):
        return MemoryPipeline(self)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv('STT_ROUTING_TARGETS_JSON', raising=False)
    monkeypatch.delenv('STT_ROUTING_DISRUPTION_GATE', raising=False)
    monkeypatch.delenv('STT_ROUTING_MODE', raising=False)
    monkeypatch.delenv('STT_ROUTING_ON_PERCENT', raising=False)
    for family in ('parakeet', 'modulate', 'soniox', 'deepgram'):
        monkeypatch.setattr(st, f'_{family}_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30))
    monkeypatch.setattr(live_router, '_target_circuits', {})
    monkeypatch.setattr(live_router, '_capacity_until', {})
    pod = live_health.FleetHealth(redis_client=MemoryRedis())
    monkeypatch.setattr(pod, 'schedule', lambda coroutine: coroutine.close())
    monkeypatch.setattr(live_chain, 'health', pod)
    return pod


def _circuit():
    return SimpleNamespace(
        state='closed',
        allow_request=lambda **_: True,
        deferred_result_callbacks=lambda: (lambda: None, lambda: None),
        account_cooldown_elapsed=lambda: True,
        account_cooldown_seconds_remaining=0.0,
        record_failure=lambda: None,
        record_account_failure=lambda _seconds: None,
    )


def _prime_chain(monkeypatch, registry_entries, *, account_bench=False):
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps(registry_entries))
    if account_bench:
        state = live_health.ProviderState(score=0.9, samples=10, bench='account', bench_until=time.time() + 1800)
        monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_, **__: {'soniox': state})
    monkeypatch.setattr(st, '_circuit_for_primary', lambda _service: _circuit())
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))


async def _dial_soniox_only_chain(connect):
    return await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=connect,
        callbacks={},
        failed=set(),
        models=['soniox'],
        routing_uid='synthetic',
        routing_language='ko',
        routing_models={'soniox': 'soniox'},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,on_percent', [('on', '100'), ('shadow', '0'), ('off', '0')])
@pytest.mark.parametrize('exclusion', ['ramp_zero', 'account_bench', 'capability'])
async def test_excluded_target_is_never_dialed_in_any_mode(monkeypatch, mode, on_percent, exclusion):
    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', on_percent)
    entry = {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754}
    if exclusion == 'ramp_zero':
        entry['ramp_percent'] = 0
    elif exclusion == 'capability':
        entry['languages'] = ['en']
    _prime_chain(monkeypatch, [entry], account_bench=exclusion == 'account_bench')
    connect = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    with pytest.raises(RuntimeError):
        await _dial_soniox_only_chain(connect)
    assert connect.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [RuntimeError('synthetic router fault'), CostHealthUnavailable('synthetic outage')])
@pytest.mark.parametrize('exclusion', ['ramp_zero', 'account_bench'])
async def test_router_fault_never_dials_excluded_target(monkeypatch, error, exclusion):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    entry = {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754}
    if exclusion == 'ramp_zero':
        entry['ramp_percent'] = 0
    _prime_chain(monkeypatch, [entry], account_bench=exclusion == 'account_bench')
    monkeypatch.setattr(live_chain, 'propose', Mock(side_effect=error))
    connect = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    with pytest.raises(RuntimeError):
        await _dial_soniox_only_chain(connect)
    assert connect.await_count == 0


@pytest.mark.asyncio
async def test_stale_pod_cannot_replace_or_shorten_account_bench():
    redis = MemoryRedis(clock=lambda: 1000.0)
    pod_a = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    pod_b = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    key = live_stt_state.fleet_state_key('soniox', account=True)
    assert await pod_a._write_bench('soniox', 'account', 2800.0)
    await pod_b._write_bench('soniox', 'selection', 1030.0)
    assert redis.data[key] == 'account:2800.000'
    await pod_b._write_bench('soniox', 'account', 1030.0)
    assert redis.data[key] == 'account:2800.000'


@pytest.mark.asyncio
async def test_text_cleanup_delete_cannot_remove_a_renewed_bench():
    state_key = live_stt_state.fleet_state_key('soniox', account=True)
    probe_key = live_stt_state.fleet_probe_key('soniox', account=True)

    class RenewingRedis(MemoryRedis):
        async def get(self, key):
            value = await super().get(key)
            if key == state_key:
                self.data[key] = 'account:1900.000'
                self.data[probe_key] = '1'
            return value

    redis = RenewingRedis(clock=lambda: 1000.0)
    redis.data[state_key] = 'account:900.000'
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    await pod._write_result('soniox', 'en', 'text')
    assert redis.data[state_key] == 'account:1900.000'
    assert redis.data[probe_key] == '1'


def test_single_witness_cannot_promote_stage5():
    state = GateState(stage=5, generation=1)
    for index in range(90):
        state = transition(state, False, 2000.0 + index, witness='a' * 16)
    assert state.stage == 5
    assert state.n <= 3


def test_single_witness_cannot_promote_stage25():
    state = GateState(stage=25, generation=1)
    for index in range(90):
        state = transition(state, False, 2000.0 + index, witness='a' * 16)
    assert state.stage == 25
    assert state.n <= 3


def test_repeated_witness_outcomes_stop_counting_after_three():
    state = GateState(stage=5, generation=1)
    for index in range(3):
        state = transition(state, index == 0, 1000.0 + index, witness='a' * 16)
    assert state.n == 3
    for index in range(60):
        state = transition(state, index % 2 == 0, 2000.0 + index, witness='a' * 16)
    assert state.n <= 3
    assert state.stage == 5


async def _cost_write_keys(monkeypatch, env, target='soniox'):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    redis = MemoryRedis()
    pod = live_health.FleetHealth(redis_client=redis)
    await pod._cost_update((target, 'all'), lambda state: replace(state, n=1))
    return set(redis.data)


@pytest.mark.asyncio
async def test_cost_state_keys_differ_between_dev_and_prod(monkeypatch):
    base = {'STT_ROUTING_MODE': 'on', 'SONIOX_API_KEY': 'synthetic-credential'}
    dev = await _cost_write_keys(monkeypatch, {**base, 'OMI_ENV_STAGE': 'dev'})
    prod = await _cost_write_keys(monkeypatch, {**base, 'OMI_ENV_STAGE': 'prod'})
    assert dev.isdisjoint(prod)


@pytest.mark.asyncio
async def test_cost_state_keys_differ_per_endpoint_and_credential(monkeypatch):
    def targets(endpoint):
        return json.dumps(
            [
                {
                    'id': 'modulate-next',
                    'family': 'modulate',
                    'cost_per_audio_hour': 0.05,
                    'endpoint': endpoint,
                }
            ]
        )

    base = {'STT_ROUTING_MODE': 'on', 'OMI_ENV_STAGE': 'dev'}
    first = await _cost_write_keys(
        monkeypatch,
        {
            **base,
            'STT_ROUTING_TARGETS_JSON': targets('wss://one.invalid/stream'),
            'MODULATE_API_KEY': 'synthetic-a',
        },
        target='modulate-next',
    )
    second = await _cost_write_keys(
        monkeypatch,
        {
            **base,
            'STT_ROUTING_TARGETS_JSON': targets('wss://two.invalid/stream'),
            'MODULATE_API_KEY': 'synthetic-a',
        },
        target='modulate-next',
    )
    third = await _cost_write_keys(
        monkeypatch,
        {
            **base,
            'STT_ROUTING_TARGETS_JSON': targets('wss://one.invalid/stream'),
            'MODULATE_API_KEY': 'synthetic-b',
        },
        target='modulate-next',
    )
    assert first.isdisjoint(second)
    assert first.isdisjoint(third)


@pytest.mark.asyncio
async def test_fresh_global_snapshot_does_not_waive_unread_language_bench():
    now = [4000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    benched = GateState(stage=0, until=now[0] + 1800)
    redis.data[live_stt_state.cost_key(DEFAULT_TARGETS[2], 'ko')] = json.dumps(benched.encode())
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    await pod.refresh_cost_once()
    assert pod.cost_snapshot([DEFAULT_TARGETS[2]], 'ko')['soniox'].stage == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['on', 'shadow', 'off'])
@pytest.mark.parametrize('fail', [False, True])
async def test_custom_endpoint_replaces_withdrawn_default_only_on_canary(monkeypatch, mode, fail):
    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    _prime_chain(
        monkeypatch,
        [
            {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055, 'ramp_percent': 0},
            {
                'id': 'modulate-next',
                'family': 'modulate',
                'cost_per_audio_hour': 0.05,
                'endpoint': 'wss://next.invalid/stream',
            },
        ],
    )
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda targets, _lang: {t.id: GateState() for t in targets})
    seen = []

    async def connect():
        target = live_router.connecting_target.get()
        seen.append(target.id if target is not None else None)
        if fail:
            raise ConnectionError('synthetic connect failure')
        return SimpleNamespace(is_connection_dead=False)

    if mode != 'on':
        with pytest.raises(live_chain.NoPermittedTarget):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.modulate,
                connect_primary=connect,
                callbacks={},
                failed=set(),
                models=['modulate-velma-2'],
                routing_uid='synthetic',
                routing_language='en',
            )
        assert seen == []
        return
    if fail:
        with pytest.raises(RuntimeError):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.modulate,
                connect_primary=connect,
                callbacks={},
                failed=set(),
                models=['modulate-velma-2'],
                routing_uid='synthetic',
                routing_language='en',
            )
        assert seen == ['modulate-next']
        return
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=connect,
        callbacks={},
        failed=set(),
        models=['modulate-velma-2'],
        routing_uid='synthetic',
        routing_language='en',
    )
    assert service == st.STTService.modulate and seen == ['modulate-next']


@pytest.mark.asyncio
async def test_router_error_restores_only_permitted_static_routes(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    _prime_chain(
        monkeypatch,
        [
            {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754, 'ramp_percent': 0},
            {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055},
        ],
    )
    proposal = Mock(side_effect=RuntimeError('synthetic router fault'))
    monkeypatch.setattr(live_chain, 'propose', proposal)
    seen = []

    def connector(service):
        async def connect():
            seen.append(service.value)
            return SimpleNamespace(is_connection_dead=False)

        return connect

    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=connector(st.STTService.soniox),
        callbacks={st.STTService.modulate: connector(st.STTService.modulate)},
        failed=set(),
        models=['soniox', 'modulate-velma-2'],
        routing_uid='synthetic',
        routing_language='en',
    )
    proposal.assert_called_once()
    assert service == st.STTService.modulate and seen == ['modulate']


@pytest.mark.asyncio
async def test_account_snapshot_malfunction_fails_closed(monkeypatch):
    _prime_chain(monkeypatch, [{'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754}])
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', Mock(side_effect=RuntimeError('synthetic cache fault')))
    connect = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    with pytest.raises(live_chain.ProviderChainUnavailable):
        await _dial_soniox_only_chain(connect)
    assert connect.await_count == 0


def _target(**overrides):
    return Target(
        id=overrides.pop('id', 'x-target'),
        family=overrides.pop('family', 'modulate'),
        cost_per_audio_hour=overrides.pop('cost_per_audio_hour', 0.01),
        **overrides,
    )


def test_streaming_feature_is_mandatory_for_any_dial():
    assert not live_router.permitted_target(_target(features=()), 'user', 'en')


def test_explicit_languages_cannot_expand_family_capability():
    restricted = _target(languages=('zz',))
    assert not live_router.permitted_target(restricted, 'user', 'zz')
    assert not live_router.permitted_target(_target(languages=('en',)), 'user', None)


def test_language_none_keeps_legacy_unrestricted_modulate():
    assert live_router.permitted_target(_target(), None, None)


def test_unregistered_deepgram_keeps_expected_languages_tail_and_account_bench():
    deepgram = _target(id='dg-nova-3', family='deepgram')
    assert live_router.permitted_target(deepgram, None, 'en', required_languages=('en', 'fr'))
    bench = live_health.ProviderState(bench='account', bench_until=time.time() + 60)
    assert not live_router.permitted_target(
        deepgram, None, 'en', required_languages=('en', 'fr'), account_states={'deepgram': bench}
    )


def test_rnnt_engine_is_english_only_but_window_is_multilingual(monkeypatch):
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    engines = {'parakeet': 'parakeet'}
    rnnt = _target(id='parakeet', family='parakeet')
    assert not live_router.permitted_target(rnnt, None, 'fr', engine_models=engines)
    assert live_router.permitted_target(rnnt, None, 'en', engine_models=engines)
    window = _target(id='parakeet-window', family='parakeet')
    assert live_router.permitted_target(window, 'user', 'fr', engine_models={'parakeet': 'parakeet-window'})


@pytest.mark.asyncio
async def test_no_op_cost_write_caches_the_read_state():
    now = [1000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    modulate = next(t for t in DEFAULT_TARGETS if t.id == 'modulate-velma-2')
    benched = GateState(stage=0, until=2000.0, generation=7)
    redis.data[live_stt_state.cost_key(modulate, 'all')] = json.dumps(benched.encode())
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    written = await pod._cost_update(('modulate-velma-2', 'all'), lambda state: state)
    assert written.stage == 0
    assert pod.cost_snapshot([modulate], 'en')['modulate-velma-2'].stage == 0
    assert pod.cost_generations('modulate-velma-2', 'en')['all'] == 7


@pytest.mark.asyncio
async def test_capped_trial_outcome_counts_user_cap_not_window_full():
    redis = MemoryRedis(clock=lambda: 1000.0)
    modulate = next(t for t in DEFAULT_TARGETS if t.id == 'modulate-velma-2')
    trial = GateState(stage=5, generation=1, trial_users=(('a' * 16, 3, 3),))
    redis.data[live_stt_state.cost_key(modulate, 'all')] = json.dumps(trial.encode())
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    labels = {'target': 'modulate-velma-2', 'scope': 'global'}
    user_cap = COST_VOTES.labels(**labels, result='user_cap')._value.get()
    window_full = COST_VOTES.labels(**labels, result='window_full')._value.get()
    await pod._write_cost_result('modulate-velma-2', 'en', False, None, 'a' * 16)
    assert COST_VOTES.labels(**labels, result='user_cap')._value.get() == user_cap + 1
    assert COST_VOTES.labels(**labels, result='window_full')._value.get() == window_full


@pytest.mark.asyncio
async def test_refresh_reads_full_vocabulary_and_prunes_stale_freshness():
    now = [1000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    soniox = DEFAULT_TARGETS[2]
    benched = GateState(stage=0, until=2000.0, generation=1)
    redis.data[live_stt_state.cost_key(soniox, 'ko')] = json.dumps(benched.encode())
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    pod._cost_fresh[('retired-target', 'en')] = now[0]
    await pod.refresh_cost_once()
    expected = {
        (target.id, language) for target in DEFAULT_TARGETS for language in ('all', *live_stt_state.ROUTED_LANGUAGES)
    }
    assert expected <= set(pod._cost_fresh)
    assert ('retired-target', 'en') not in pod._cost_fresh
    assert pod.cost_snapshot(DEFAULT_TARGETS, 'ko')['soniox'].stage == 0


def test_unread_language_counts_unknown_and_raises():
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=MemoryRedis())
    pod._cost_fresh.update({(target.id, 'all'): 1000.0 for target in DEFAULT_TARGETS})
    before = COST_LANGUAGE_STATE.labels(target='soniox', comparison='unknown')._value.get()
    with pytest.raises(CostHealthUnavailable):
        pod.cost_snapshot(DEFAULT_TARGETS, 'ko')
    assert COST_LANGUAGE_STATE.labels(target='soniox', comparison='unknown')._value.get() == before + 1


def test_stale_language_read_counts_stale_not_unknown():
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=MemoryRedis())
    pod._cost_fresh.update({(target.id, lang): 1000.0 for target in DEFAULT_TARGETS for lang in ('all', 'en')})
    pod._cost_fresh[('soniox', 'en')] = 900.0
    before = COST_LANGUAGE_STATE.labels(target='soniox', comparison='stale')._value.get()
    pod.cost_snapshot(DEFAULT_TARGETS, 'en')
    assert COST_LANGUAGE_STATE.labels(target='soniox', comparison='stale')._value.get() == before + 1


@pytest.mark.asyncio
async def test_language_restricted_and_global_restricted_metric_comparisons():
    now = [1000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    soniox, modulate = DEFAULT_TARGETS[2], DEFAULT_TARGETS[1]
    bench = GateState(stage=0, until=2000.0, generation=1)
    redis.data[live_stt_state.cost_key(soniox, 'ko')] = json.dumps(bench.encode())
    redis.data[live_stt_state.cost_key(modulate, 'all')] = json.dumps(bench.encode())
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    await pod.refresh_cost_once()
    before_lang = COST_LANGUAGE_STATE.labels(target='soniox', comparison='language_restricted')._value.get()
    before_global = COST_LANGUAGE_STATE.labels(target='modulate-velma-2', comparison='global_restricted')._value.get()
    pod.cost_snapshot(DEFAULT_TARGETS, 'ko')
    assert COST_LANGUAGE_STATE.labels(target='soniox', comparison='language_restricted')._value.get() == before_lang + 1
    assert (
        COST_LANGUAGE_STATE.labels(target='modulate-velma-2', comparison='global_restricted')._value.get()
        == before_global + 1
    )


@pytest.mark.asyncio
async def test_stale_writer_completion_never_populates_a_new_identity(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    gate = asyncio.Event()
    started = asyncio.Event()

    class PausedRedis(MemoryRedis):
        async def time(self):
            started.set()
            await gate.wait()
            return await super().time()

    redis = PausedRedis(clock=lambda: 1000.0)
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    identity = pod._check_identity()
    task = asyncio.create_task(pod._write_cost_result('soniox', 'en', True, None, 'a' * 16, expected_identity=identity))
    await started.wait()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    pod._check_identity()
    gate.set()
    await task
    assert not any(':prod:' in key for key in redis.data)
    assert ('soniox', 'all') not in pod._cost_cached
    assert ('soniox', 'en') not in pod._cost_cached


@pytest.mark.asyncio
async def test_queued_observation_is_rejected_after_stage_change(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    redis = MemoryRedis(clock=lambda: 1000.0)
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    identity = pod._check_identity()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    pod._check_identity()
    with pytest.raises(RuntimeError):
        await pod._cost_update(('soniox', 'all'), lambda state: state, expected_identity=identity)
    assert redis.data == {}


def test_ramp_and_cost_edits_keep_identity_and_benches(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    entry = {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055, 'ramp_percent': 50}
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([entry]))
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=MemoryRedis())
    pod._check_identity()
    pod._benches['soniox'] = ('account', 5000.0)
    pod._cost_cached[('soniox', 'all')] = GateState(stage=0)
    identity = pod._identity
    entry['ramp_percent'] = 10
    entry['cost_per_audio_hour'] = 0.04
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([entry]))
    pod._check_identity()
    assert pod._identity == identity
    assert pod._benches['soniox'] == ('account', 5000.0)
    assert ('soniox', 'all') in pod._cost_cached


def test_endpoint_edit_resets_views_but_keeps_in_flight_bench(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    entry = {
        'id': 'modulate-velma-2',
        'family': 'modulate',
        'cost_per_audio_hour': 0.055,
        'endpoint': 'wss://one.invalid/stream',
    }
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([entry]))
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=MemoryRedis())
    old_identity = pod._check_identity()
    pod._benches['soniox'] = ('account', 5000.0)
    pod._cost_cached[('soniox', 'all')] = GateState(stage=0)
    pod._bench_providers_in_flight['soniox'] = old_identity
    pod._pending_benches[('soniox', 'account')] = 6000.0
    entry['endpoint'] = 'wss://two.invalid/stream'
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([entry]))
    pod._check_identity()
    assert pod._identity != old_identity
    assert not pod._benches and not pod._cost_cached
    assert pod._bench_providers_in_flight.get('soniox') == old_identity
    pod._pending_benches[('soniox', 'account')] = 6000.0
    task = SimpleNamespace(cancelled=lambda: False, result=lambda: True)
    pod._bench_write_done('soniox', 'account', 6000.0, old_identity, task)
    assert pod._pending_benches[('soniox', 'account')] == 6000.0
    assert 'soniox' not in pod._bench_providers_in_flight


@pytest.mark.asyncio
@pytest.mark.parametrize('pause_on', ['get', 'exec'])
async def test_write_result_identity_change_stops_cleanup_and_new_scope_writes(monkeypatch, pause_on):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-credential')
    monkeypatch.setenv('SONIOX_WS_URL', 'wss://old.invalid/ws')
    dropped = live_health.FLEET_HEALTH_WRITE_DROPPED.labels(kind='result')._value.get()

    class PausedRedis(MemoryRedis):
        def __init__(self, clock=None):
            super().__init__(clock=clock)
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self._paused = False

        async def _maybe_pause(self, point):
            if pause_on == point and not self._paused:
                self._paused = True
                self.started.set()
                await self.release.wait()

        async def get(self, key):
            await self._maybe_pause('get')
            return await super().get(key)

        def pipeline(self, *, transaction=False):
            redis = self

            class Pipe(MemoryPipeline):
                async def execute(self):
                    await redis._maybe_pause('exec')
                    return await super().execute()

            return Pipe(self)

    redis = PausedRedis(clock=lambda: 1000.0)
    old_prefix = live_stt_state.fleet_prefix('soniox')
    account_state = live_stt_state.fleet_state_key('soniox', account=True)
    account_probe = live_stt_state.fleet_probe_key('soniox', account=True)
    redis.data[account_state] = 'account:900.000'
    redis.data[account_probe] = '1'
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    task = asyncio.create_task(pod._write_result('soniox', 'en', 'text'))
    await asyncio.wait_for(redis.started.wait(), 1)
    monkeypatch.setenv('SONIOX_WS_URL', 'wss://new.invalid/ws')
    new_prefix = live_stt_state.fleet_prefix('soniox')
    assert new_prefix != old_prefix
    redis.release.set()
    await task
    assert redis.data[account_state] == 'account:900.000'
    assert redis.data[account_probe] == '1'
    assert not any(key.startswith(new_prefix) for key in redis.data)
    written = [key for key in redis.data if key not in (account_state, account_probe)]
    if pause_on == 'get':
        assert not written
    else:
        assert written and all(key.startswith(old_prefix) for key in written)
    assert live_health.FLEET_HEALTH_WRITE_DROPPED.labels(kind='result')._value.get() - dropped == 1
    assert not pod._local and not pod._benches and not pod._cached_benches


def test_identity_keys_preserve_exact_wire_endpoint(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-credential')
    modulate_a = _target(id='modulate-a', endpoint='wss://x.invalid/stream')
    modulate_b = _target(id='modulate-a', endpoint='wss://x.invalid/stream/')
    assert live_stt_state.cost_key(modulate_a, 'en') != live_stt_state.cost_key(modulate_b, 'en')
    soniox = _target(id='soniox', family='soniox')
    monkeypatch.setenv('SONIOX_WS_URL', 'wss://sx.invalid/ws')
    plain = live_stt_state.cost_key(soniox, 'en')
    monkeypatch.setenv('SONIOX_WS_URL', 'wss://sx.invalid/ws/')
    assert live_stt_state.cost_key(soniox, 'en') != plain
    deepgram = _target(id='dg-x', family='deepgram')
    monkeypatch.delenv('DEEPGRAM_SELF_HOSTED_ENABLED', raising=False)
    monkeypatch.delenv('DEEPGRAM_SELF_HOSTED_URL', raising=False)
    cloud = live_stt_state.cost_key(deepgram, 'en')
    monkeypatch.setenv('DEEPGRAM_SELF_HOSTED_URL', 'wss://dg.invalid/socket')
    assert live_stt_state.cost_key(deepgram, 'en') == cloud
    monkeypatch.setenv('DEEPGRAM_SELF_HOSTED_ENABLED', 'true')
    assert live_stt_state.cost_key(deepgram, 'en') != cloud


def test_missing_or_invalid_stage_never_defaults_to_prod(monkeypatch):
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.delenv('PROVIDER_MODE', raising=False)
    assert live_stt_state.stage() == 'unknown'
    monkeypatch.setenv('OMI_ENV_STAGE', 'staging')
    assert live_stt_state.stage() == 'unknown'
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert live_stt_state.stage() == 'prod'


@pytest.mark.asyncio
async def test_engine_mismatch_static_retry_keeps_restricted_family_denied(monkeypatch):
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
                {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055, 'languages': ['en']},
                {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754},
            ]
        ),
    )
    monkeypatch.setattr(st, '_circuit_for_primary', lambda _service: _circuit())
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    chosen = next(target for target in live_chain.registry() if target.id == 'modulate-next')
    propose_mock = Mock(return_value=[chosen])
    monkeypatch.setattr(live_chain, 'propose', propose_mock)
    seen_targets = []

    async def modulate_connect():
        seen_targets.append(live_router.connecting_target.get())
        return SimpleNamespace(
            is_connection_dead=False,
            routing_model='modulate-velma-2',
            routing_endpoint='wss://elsewhere.invalid/stream',
            routing_target='modulate-other',
        )

    async def soniox_connect():
        seen_targets.append(live_router.connecting_target.get())
        return SimpleNamespace(is_connection_dead=False)

    _socket, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=modulate_connect,
        callbacks={st.STTService.soniox: soniox_connect},
        failed=set(),
        models=['modulate', 'soniox'],
        routing_uid='cohort',
        routing_language='en',
        routing_languages=('en', 'hi'),
        routing_models={'modulate': 'modulate-next', 'soniox': 'soniox'},
    )
    assert service == st.STTService.soniox
    assert seen_targets[0] is chosen and seen_targets[1] is None
    assert propose_mock.call_count == 1


@pytest.mark.asyncio
async def test_engine_mismatch_static_retry_still_serves_partial_ramp_cohort(monkeypatch):
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
                {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055, 'ramp_percent': 25},
            ]
        ),
    )
    monkeypatch.setattr(st, '_circuit_for_primary', lambda _service: _circuit())
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    chosen = next(target for target in live_chain.registry() if target.id == 'modulate-next')
    propose_mock = Mock(return_value=[chosen])
    monkeypatch.setattr(live_chain, 'propose', propose_mock)
    uid = next(uid for uid in map(str, range(2000)) if assigned(uid, 'modulate-velma-2', 25))
    seen_targets = []

    async def modulate_connect():
        seen_targets.append(live_router.connecting_target.get())
        if live_router.connecting_target.get() is not None:
            return SimpleNamespace(
                is_connection_dead=False,
                routing_model='modulate-velma-2',
                routing_endpoint='wss://elsewhere.invalid/stream',
                routing_target='modulate-other',
            )
        return SimpleNamespace(is_connection_dead=False)

    _socket, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=modulate_connect,
        callbacks={},
        failed=set(),
        models=['modulate'],
        routing_uid=uid,
        routing_language='en',
        routing_models={'modulate': 'modulate-next'},
    )
    assert service == st.STTService.modulate
    assert seen_targets[0] is chosen and seen_targets[1] is None
    assert propose_mock.call_count == 1


def test_reset_fleet_provider_help_needs_no_redis():
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'stt' / 'reset_fleet_provider.py'
    result = subprocess.run([sys.executable, str(script), '--help'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and 'execute' in result.stdout


def test_reset_fleet_provider_dry_run_uses_namespaced_keys(monkeypatch, capsys):
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'stt' / 'reset_fleet_provider.py'
    spec = importlib.util.spec_from_file_location('reset_fleet_provider', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scanned = []

    class FakeRedis:
        def scan_iter(self, match, count=0):
            scanned.append(match)
            return iter(())

        def delete(self, *_keys):
            raise AssertionError('dry run must not delete')

    monkeypatch.setenv('REDIS_DB_HOST', '127.0.0.1')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-credential')
    monkeypatch.setattr(module, 'redis', SimpleNamespace(Redis=lambda **_kw: FakeRedis()))
    monkeypatch.setattr(sys, 'argv', ['reset_fleet_provider.py', 'soniox'])
    assert module.main() == 0
    assert 'omi:live-stt:fleet-v2:dev:' in scanned[0]
    assert 'matching_keys=4' in capsys.readouterr().out


@pytest.mark.parametrize('stage,required,breadth,dwell', [(5, 30, 10, 300), (25, 60, 20, 600)])
def test_trial_promotion_needs_admitted_breadth_and_dwell(stage, required, breadth, dwell):
    start = 1000.0
    state = GateState(stage=stage, generation=1, trial_started_at=start)
    for user in range(breadth - 1):
        for _ in range(3):
            state = transition(state, False, start + 10, witness=f'{user:016x}')
    assert state.stage == stage and state.n == 3 * (breadth - 1)
    for _ in range(3):
        state = transition(state, False, start + dwell - 1, witness=f'{breadth - 1:016x}')
    assert state.n == required and state.stage == stage
    state = transition(state, False, start + dwell, witness=f'{breadth:016x}')
    assert state.stage == (25 if stage == 5 else 100)


def test_held_window_reset_retains_trial_dwell_start():
    start = 1000.0
    state = GateState(stage=5, generation=1, trial_started_at=start)
    for index in range(4 * 30):
        state = transition(state, False, start + 100, witness=f'{index // 3:016x}')
    assert state.stage == 5 and state.n == 0 and state.trial_started_at == start


def test_threshold_reset_starts_trial_clock_for_recovery_stages():
    shifted = GateState(threshold=0.5, stage=5)
    assert transition(shifted, False, 2000.0, witness='a' * 16).trial_started_at == 2000.0
    shifted = GateState(threshold=0.5, stage=25)
    assert transition(shifted, False, 2000.0, witness='a' * 16).trial_started_at == 2000.0
    shifted = GateState(threshold=0.5)
    assert transition(shifted, False, 2000.0, witness='a' * 16).trial_started_at == 0.0


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1.0, 'early'])
def test_trial_started_at_decode_is_strict(value):
    raw = GateState(stage=5, trial_started_at=100.0).encode()
    raw['trial_started_at'] = value
    with pytest.raises(ValueError):
        GateState.decode(raw)


@pytest.mark.asyncio
async def test_two_pods_share_trial_breadth_dwell_and_user_cap(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    now = [1700.0]
    redis = MemoryRedis(clock=lambda: now[0])
    pods = [live_health.FleetHealth(clock=lambda: now[0], redis_client=redis) for _ in range(2)]
    soniox = DEFAULT_TARGETS[2]
    key = live_stt_state.cost_key(soniox, 'all')
    redis.data[key] = json.dumps(GateState(stage=5, generation=1, trial_started_at=1500.0).encode())
    for index in range(30):
        await pods[index % 2]._write_cost_result('soniox', 'en', False, None, f'{index % 10:016x}')
    state = GateState.decode(json.loads(redis.data[key]))
    assert state.stage == 5 and len(state.trial_users) == 10 and state.n == 30
    now[0] = 1800.0
    await pods[0]._write_cost_result('soniox', 'en', False, None, f'{99:016x}')
    state = GateState.decode(json.loads(redis.data[key]))
    assert state.stage == 25 and state.trial_started_at == 1800.0
    for index in range(5):
        await pods[index % 2]._write_cost_result('soniox', 'en', False, None, 'b' * 16)
    state = GateState.decode(json.loads(redis.data[key]))
    assert dict((user[0], user[1]) for user in state.trial_users)['b' * 16] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('paused_op', ['time', 'get', 'eval', 'mget'])
async def test_env_change_during_await_never_publishes_under_new_identity(monkeypatch, paused_op):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    started = asyncio.Event()
    gate = asyncio.Event()
    op_name = paused_op

    class SwitchRedis(MemoryRedis):
        async def _pause(self, op):
            if op == op_name:
                started.set()
                await gate.wait()

        async def time(self):
            await self._pause('time')
            return await super().time()

        async def get(self, key):
            await self._pause('get')
            return await super().get(key)

        async def eval(self, *args):
            await self._pause('eval')
            return await super().eval(*args)

        async def mget(self, keys):
            await self._pause('mget')
            return await super().mget(keys)

    redis = SwitchRedis(clock=lambda: 1000.0)
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    pod._check_identity()
    if paused_op == 'mget':
        task = asyncio.create_task(pod.refresh_cost_once())
    else:
        task = asyncio.create_task(pod._write_cost_result('soniox', 'en', True, None, 'a' * 16))
    await started.wait()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    gate.set()
    await task
    assert not any(':prod:' in key for key in redis.data)
    assert ('soniox', 'all') not in pod._cost_cached
    assert ('soniox', 'en') not in pod._cost_cached


@pytest.mark.asyncio
@pytest.mark.parametrize('paused_op', ['mget', 'set'])
async def test_fleet_refresh_mid_await_never_publishes_under_new_identity(monkeypatch, paused_op):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    started = asyncio.Event()
    gate = asyncio.Event()
    op_name = paused_op

    class SwitchRedis(MemoryRedis):
        async def _pause(self, op):
            if op == op_name:
                started.set()
                await gate.wait()

        async def mget(self, keys):
            await self._pause('mget')
            return await super().mget(keys)

        async def set(self, key, value, **kwargs):
            await self._pause('set')
            return await super().set(key, value, **kwargs)

    redis = SwitchRedis(clock=lambda: 1000.0)
    if paused_op == 'set':
        redis.data[live_stt_state.fleet_state_key('soniox', account=True)] = 'account:500.000'
    pod = live_health.FleetHealth(clock=lambda: 1000.0, redis_client=redis)
    pod._check_identity()
    task = asyncio.create_task(pod.refresh_once())
    await started.wait()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    gate.set()
    await task
    assert not any(':prod:' in key for key in redis.data)
    assert not pod._cached_benches and not pod._cached_scores
    assert pod._cache_at is None
    assert not pod._probe_ready and not pod._probe_pending


def test_permission_reasons_map_to_closed_decision_labels(monkeypatch):
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps(
            [
                {'id': 'soniox', 'family': 'soniox', 'cost_per_audio_hour': 0.0754, 'ramp_percent': 0},
                {'id': 'modulate-velma-2', 'family': 'modulate', 'cost_per_audio_hour': 0.055},
            ]
        ),
    )
    bench = live_health.ProviderState(bench='account', bench_until=time.time() + 60)
    health = SimpleNamespace(
        cached_snapshot=lambda _families, _lang: {'modulate': bench, 'soniox': live_health.ProviderState()},
        cost_snapshot=lambda targets, _lang: {target.id: GateState() for target in targets},
        prefer_recovery=lambda *_args: None,
    )
    ramp_before = COST_DECISION.labels(target='soniox', reason='ramp_skip')._value.get()
    cap_before = COST_DECISION.labels(target='soniox', reason='capability')._value.get()
    bench_before = COST_DECISION.labels(target='modulate-velma-2', reason='benched_skip')._value.get()
    live_router.propose(health, ['soniox', 'modulate'], 'synthetic', 'en', 'soniox')
    assert COST_DECISION.labels(target='soniox', reason='ramp_skip')._value.get() == ramp_before + 1
    assert COST_DECISION.labels(target='soniox', reason='capability')._value.get() == cap_before
    assert COST_DECISION.labels(target='modulate-velma-2', reason='benched_skip')._value.get() == bench_before + 1


@pytest.mark.asyncio
async def test_static_parakeet_without_engine_context_uses_legacy_rnnt(monkeypatch):
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0')
    seen = []

    async def connect():
        target = live_router.connecting_target.get()
        seen.append(target.id if target is not None else None)
        return SimpleNamespace(is_connection_dead=False)

    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.parakeet,
        connect_primary=connect,
        callbacks={},
        failed=set(),
        models=['parakeet-window'],
        routing_uid=None,
        routing_language='en',
        routing_models=None,
    )
    assert service == st.STTService.parakeet and seen == [None]

    denied = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))
    with pytest.raises(live_chain.NoPermittedTarget):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.parakeet,
            connect_primary=denied,
            callbacks={},
            failed=set(),
            models=['parakeet-window'],
            routing_uid=None,
            routing_language='en',
            routing_models={'parakeet': 'parakeet-window'},
        )
    assert denied.await_count == 0


def test_fleet_keys_separate_endpoint_state_from_shared_account(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-credential')
    monkeypatch.delenv('SONIOX_WS_URL', raising=False)
    endpoint_state = live_stt_state.fleet_state_key('soniox')
    endpoint_probe = live_stt_state.fleet_probe_key('soniox')
    endpoint_scores = live_stt_state.fleet_score_keys('soniox', 'en', 7)
    account_state = live_stt_state.fleet_state_key('soniox', account=True)
    assert endpoint_state != account_state
    monkeypatch.setenv('SONIOX_WS_URL', 'wss://rotated.invalid/transcribe')
    assert live_stt_state.fleet_state_key('soniox') != endpoint_state
    assert live_stt_state.fleet_probe_key('soniox') != endpoint_probe
    assert live_stt_state.fleet_score_keys('soniox', 'en', 7) != endpoint_scores
    assert live_stt_state.fleet_state_key('soniox', account=True) == account_state


@pytest.mark.asyncio
async def test_selection_and_account_benches_retain_both_deadlines():
    now = [1000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    endpoint_key = live_stt_state.fleet_state_key('soniox')
    account_key = live_stt_state.fleet_state_key('soniox', account=True)
    assert await pod._write_bench('soniox', 'selection', 2800.0)
    assert await pod._write_bench('soniox', 'account', 1030.0)
    assert redis.data[endpoint_key] == 'selection:2800.000'
    assert redis.data[account_key] == 'account:1030.000'
    await pod._write_bench('soniox', 'selection', 2900.0)
    assert redis.data[endpoint_key] == 'selection:2800.000'
    await pod._write_bench('soniox', 'account', 1010.0)
    assert redis.data[account_key] == 'account:1030.000'


@pytest.mark.asyncio
async def test_active_account_dominates_then_expired_account_yields_to_selection(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    now = [1000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    redis.data[live_stt_state.fleet_state_key('soniox')] = 'selection:1800.000'
    redis.data[live_stt_state.fleet_state_key('soniox', account=True)] = 'account:1030.000'
    pod.cached_snapshot(['soniox'], 'en')
    await pod.refresh_once()
    state = pod.cached_snapshot(['soniox'], 'en')['soniox']
    assert state.bench == 'account' and state.bench_until == 1030.0
    now[0] = 1031.0
    await pod.refresh_once()
    state = pod.cached_snapshot(['soniox'], 'en')['soniox']
    assert state.bench == 'selection' and state.bench_until == 1800.0


@pytest.mark.asyncio
async def test_expired_account_cleanup_never_deletes_active_selection_state():
    now = [1000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    endpoint_key = live_stt_state.fleet_state_key('soniox')
    account_key = live_stt_state.fleet_state_key('soniox', account=True)
    account_probe = live_stt_state.fleet_probe_key('soniox', account=True)
    redis.data[endpoint_key] = 'selection:1800.000'
    redis.data[account_key] = 'account:900.000'
    redis.data[account_probe] = '1'
    await pod._write_result('soniox', 'en', 'text')
    assert account_key not in redis.data and account_probe not in redis.data
    assert redis.data[endpoint_key] == 'selection:1800.000'


@pytest.mark.asyncio
async def test_endpoint_rotation_keeps_credential_shared_account_bench(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-credential')
    monkeypatch.delenv('SONIOX_WS_URL', raising=False)
    now = [1000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    pod.cached_snapshot(['soniox'], 'en')
    await pod.refresh_once()
    assert await pod._write_bench('soniox', 'account', 1800.0)
    monkeypatch.setenv('SONIOX_WS_URL', 'wss://rotated.invalid/transcribe')
    await pod.refresh_once()
    state = pod.cached_snapshot(['soniox'], 'en')['soniox']
    assert state.bench == 'account' and state.bench_until == 1800.0


@pytest.mark.parametrize('stage,required,breadth,dwell', [(5, 30, 10, 300.0), (25, 60, 20, 600.0)])
@pytest.mark.parametrize('failed', [False, True])
def test_capped_witness_promotes_trial_only_once_dwell_elapses(stage, required, breadth, dwell, failed):
    start = 1000.0
    capped = f'{0:016x}'
    state = GateState(stage=stage, generation=1, trial_started_at=start)
    for user in range(breadth):
        for _ in range(3):
            state = transition(state, False, start + 10, witness=f'{user:016x}')
    assert state.stage == stage and state.n == required
    before = transition(state, failed, start + dwell - 1, witness=capped)
    assert before == state
    promoted = transition(state, failed, start + dwell, witness=capped)
    assert promoted.stage == (25 if stage == 5 else 100)
    assert promoted.generation == state.generation + 1 and promoted.trial_started_at == start + dwell
    shallow = GateState(stage=stage, generation=1, trial_started_at=start)
    for user in range(breadth - 3):
        for _ in range(3):
            shallow = transition(shallow, False, start + 10, witness=f'{user:016x}')
    assert shallow.n < required
    assert transition(shallow, failed, start + dwell, witness='f' * 16).stage == stage
    solo = GateState(stage=stage, generation=1, trial_started_at=start)
    for _ in range(3):
        solo = transition(solo, False, start + 10, witness='a' * 16)
    for extra in range(8):
        solo = transition(solo, failed, start + dwell + extra, witness='a' * 16)
    assert solo.stage == stage and solo.n <= 3


@pytest.mark.asyncio
async def test_capped_witness_clock_promotion_counts_user_cap_vote(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    now = [1700.0]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    soniox = DEFAULT_TARGETS[2]
    key = live_stt_state.cost_key(soniox, 'all')
    users = tuple((f'{index:016x}', 3, 0) for index in range(10))
    redis.data[key] = json.dumps(
        GateState(stage=5, generation=1, trial_started_at=1500.0, n=30, trial_users=users).encode()
    )
    applied = COST_VOTES.labels(target='soniox', scope='global', result='applied')._value.get()
    capped = COST_VOTES.labels(target='soniox', scope='global', result='user_cap')._value.get()
    now[0] = 1800.0
    await pod._write_cost_result('soniox', 'en', False, None, '0' * 16)
    state = GateState.decode(json.loads(redis.data[key]))
    assert state.stage == 25 and state.trial_started_at == 1800.0 and state.generation == 2
    assert COST_VOTES.labels(target='soniox', scope='global', result='user_cap')._value.get() == capped + 1
    assert COST_VOTES.labels(target='soniox', scope='global', result='applied')._value.get() == applied


def _reset_module():
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'stt' / 'reset_fleet_provider.py'
    spec = importlib.util.spec_from_file_location('reset_fleet_provider', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reset_fleet_provider_rejects_unknown_stage_before_redis(monkeypatch):
    module = _reset_module()
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.delenv('PROVIDER_MODE', raising=False)
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-credential')
    monkeypatch.setenv('REDIS_DB_HOST', '127.0.0.1')
    monkeypatch.setattr(
        module, 'redis', SimpleNamespace(Redis=lambda **_kw: (_ for _ in ()).throw(AssertionError('no client')))
    )
    monkeypatch.setattr(sys, 'argv', ['reset_fleet_provider.py', 'soniox'])
    with pytest.raises(SystemExit):
        module.main()


def test_reset_fleet_provider_rejects_missing_credential_before_redis(monkeypatch):
    module = _reset_module()
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('SONIOX_API_KEY', raising=False)
    monkeypatch.setenv('REDIS_DB_HOST', '127.0.0.1')
    monkeypatch.setattr(
        module, 'redis', SimpleNamespace(Redis=lambda **_kw: (_ for _ in ()).throw(AssertionError('no client')))
    )
    monkeypatch.setattr(sys, 'argv', ['reset_fleet_provider.py', 'soniox'])
    with pytest.raises(SystemExit):
        module.main()


def test_reset_fleet_provider_rejects_parakeet_without_endpoint_before_redis(monkeypatch):
    module = _reset_module()
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('HOSTED_PARAKEET_API_URL', raising=False)
    monkeypatch.setenv('REDIS_DB_HOST', '127.0.0.1')
    monkeypatch.setattr(
        module, 'redis', SimpleNamespace(Redis=lambda **_kw: (_ for _ in ()).throw(AssertionError('no client')))
    )
    monkeypatch.setattr(sys, 'argv', ['reset_fleet_provider.py', 'parakeet'])
    with pytest.raises(SystemExit):
        module.main()
