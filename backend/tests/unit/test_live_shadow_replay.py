"""Content-free provider calibration and replays with measured shadow floors."""

import json
import math
import random
import statistics
from collections import Counter
from functools import lru_cache

import pytest

from config.live_stt_registry import DEFAULT_TARGETS, Target, assigned
from utils.stt import live_cost_health, live_failure, live_chain, live_health, live_router, streaming as st
from config import live_stt_state
from utils.stt.live_gate import GateState, begin_trial, transition, gate_rate
from utils.stt.live_signal import provider_observation
from utils.stt.live_metrics import COST_STAGE, COST_STATE_KNOWN, COST_EVENTS, COST_SNAPSHOT_AT, COST_ALL_DEGRADED
from tests.unit.test_live_cost_router import MemoryRedis, controls


@pytest.mark.parametrize('sessions', [2000, pytest.param(20000, marks=pytest.mark.slow)])
@pytest.mark.parametrize('floor', [0.05, 0.07, 0.10])
@pytest.mark.parametrize('seed', range(20))
def test_audio_noise_floor_cannot_bench_provider(floor, seed, sessions):
    rng, state = random.Random(seed), GateState()
    for n in range(sessions):
        outcome = 'no_text' if rng.random() < floor else 'text'
        failed = provider_observation(outcome)
        if failed is not None:
            state = transition(state, failed, n, witness=f'{n:016x}')
        assert state.stage == 100
    assert state.failures == 0 and 0.85 * sessions < state.n <= sessions


@pytest.mark.parametrize(
    'reason',
    [
        'first_text_deadline',
        'empty_streak',
        'vad_failed',
        'capacity_full',
        'soniox_rotation',
        'soniox_idle_timeout',
        'provider_auth_rejected',
        'other',
        None,
    ],
)
def test_audio_client_capacity_and_account_reasons_are_not_gate_failures(reason):
    assert provider_observation('failover', reason) is None


@lru_cache(maxsize=16)
def healthy_warmup(gate):
    state = GateState(threshold=gate)
    for n in range(500):
        state = transition(state, False, n, witness=f'{n:016x}')
    return state  # immutable; every experiment transitions to its own new state


def detect_provider(rate, seed, floor=0.10):
    rng, state, failures = random.Random(seed), healthy_warmup(gate_rate()), 0
    for n in range(1, 5001):
        draw = rng.random()
        outcome = 'failover' if draw < rate else 'no_text' if draw < rate + floor else 'text'
        failed = provider_observation(outcome, 'modulate_serve_error')
        if failed is not None:
            failures += failed
            state = transition(state, failed, n, witness=f'{n + 500:016x}')
        if state.stage == 0:
            return n, failures
    return 5001, failures


@pytest.mark.parametrize(
    'rate,median_limit,p95_session_limit,p95_failed_limit', [(1.0, 8, 8, 8), (0.6, 20, 25, 10), (0.4, 30, 50, 20)]
)
def test_provider_outage_and_modulate_brownout_detection(rate, median_limit, p95_session_limit, p95_failed_limit):
    samples = [detect_provider(rate, seed) for seed in range(200)]
    assert statistics.median(n for n, _ in samples) <= median_limit
    assert sorted(n for n, _ in samples)[189] <= p95_session_limit
    assert sorted(failures for _, failures in samples)[189] <= p95_failed_limit


@pytest.mark.parametrize('sessions', [1200, pytest.param(17900, marks=pytest.mark.slow)])
def test_24_hour_measured_floors_replay_has_no_healthy_benches_or_empty_proposals(monkeypatch, sessions):
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '25')
    rng = random.Random(20261002)
    states = {target.id: GateState() for target in DEFAULT_TARGETS}
    events, shares = [], Counter()
    first_modulate_bench = None
    for i in range(sessions):
        now, uid = i * 86400 / sessions, str(i)
        hour = int(now // 3600)
        preferred = set()
        language = 'ja' if i % 10 == 0 else 'en'
        chain = live_router.select(
            DEFAULT_TARGETS, states, uid, language, recovery=lambda target, _: preferred.add(target)
        )
        assert chain
        shares[chain[0].id] += 1
        for target in DEFAULT_TARGETS:
            old = states[target.id]
            state = begin_trial(old, now) if target.id in preferred else old
            if state.stage and assigned(uid, 'stt-reentry:' + target.id, state.stage):
                rate = {'parakeet': 0.003, 'soniox': 0.01, 'modulate': 0.40}[target.family]
                floor = (0.06 + (hour % 5) * 0.01) if target.family == 'parakeet' else (0.03 + (hour % 6) * 0.01)
                draw = rng.random()
                outcome = 'failover' if draw < rate else 'no_text' if draw < rate + floor else 'text'
                failed = provider_observation(
                    outcome, 'modulate_serve_error' if target.family == 'modulate' else 'connection_lost'
                )
                if failed is not None:
                    state = transition(state, failed, now, witness=f'{i:016x}')
            if old.stage != state.stage:
                events.append((target.id, i, state.stage))
            states[target.id] = state
            if target.family != 'modulate':
                assert state.stage == 100
            elif state.stage == 0 and first_modulate_bench is None:
                first_modulate_bench = i + 1
    assert first_modulate_bench is not None and first_modulate_bench <= 50
    assert shares['parakeet-window'] > 0.195 * sessions
    assert shares['soniox'] > 0.67 * sessions
    assert events and all(target == 'modulate-velma-2' for target, _, _ in events)


def test_no_text_does_not_fill_trial_or_mask_later_provider_failure(monkeypatch):
    from tests.unit.test_live_routing_health import _leg

    health = live_chain.health
    for i in range(100):
        health.record_session('modulate-velma-2', 'en', 'no_text', uid=str(i))
    assert not health._cost_local
    leg = _leg()
    leg.send(b'\x01\x00' * 16000)
    leg._first_speech_at -= 60
    leg._check_no_text_deadline()
    assert not leg.leg_outcome.settled
    leg._replay_failure_reason = 'modulate_serve_error'
    leg._dead = True
    live_failure.settle_terminal_socket(leg, 'modulate', 'connection_lost')
    leg.finish()
    leg.finish()
    assert health._cost_local[('modulate-velma-2', 'all')].failures == 1


def test_deadline_only_failover_is_censored_even_with_vad_speech():
    from tests.unit.test_live_routing_health import _leg

    leg = _leg()
    leg.send(b'\x01\x00' * 16000)
    leg._replay_failure_reason = 'first_text_deadline'
    leg._dead = True
    live_failure.settle_terminal_socket(leg, 'modulate', 'connection_lost')
    leg.finish()
    assert not live_chain.health._cost_local


def test_late_text_after_diagnostic_deadline_counts_completed_success():
    from tests.unit.test_live_routing_health import _leg

    leg = _leg()
    leg.send(b'\x01\x00' * 16000)
    leg._first_speech_at -= 60
    leg._check_no_text_deadline()
    leg.note_selection_transcript([{'text': 'synthetic'}])
    leg.finish()
    state = live_chain.health._cost_local[('modulate-velma-2', 'all')]
    assert state.n == 1 and state.failures == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('family', ['soniox', 'modulate'])
async def test_provider_connect_failure_counts_once_but_capacity_does_not(monkeypatch, family):
    async def connect():
        raise ConnectionError('synthetic connect failure')

    with pytest.raises(RuntimeError, match='chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService(family),
            connect_primary=connect,
            callbacks={},
            failed=set(),
            models=['soniox' if family == 'soniox' else 'modulate-velma-2'],
            routing_uid='synthetic',
            routing_language='en',
            routing_models={family: 'velma-2' if family == 'modulate' else 'soniox'},
        )
    target = next(target for target in DEFAULT_TARGETS if target.family == family).id
    state = live_chain.health._cost_local[(target, 'all')]
    assert state.n == state.failures == 1
    live_chain.health.record_session(target, 'en', 'connect_failure', uid='synthetic', reason='capacity_full')
    assert live_chain.health._cost_local[(target, 'all')] == state


def test_rnnt_outcomes_cannot_alias_window_health():
    live_chain.health.record_session('parakeet', 'en', 'text', uid='synthetic')
    assert not live_chain.health._cost_local


def test_trial_terminal_remains_a_failover_leg_when_cheaper_healthy_target_exists():
    health = live_chain.health
    health._cost_local[('soniox', 'all')] = GateState(stage=5)
    health._cost_fresh.update({(t.id, lang): 0.0 for t in DEFAULT_TARGETS for lang in ('all', 'en')})
    uid = next(str(i) for i in range(1000) if not assigned(str(i), 'stt-reentry:soniox', 5))
    tail = []
    chain = live_router.propose(health, ['modulate', 'soniox'], uid, 'en', 'modulate', last_resorts=tail)
    assert [target.id for target in chain] == ['modulate-velma-2']
    assert [target.id for target in tail] == ['soniox']


def test_terminal_share_is_unrestricted_and_all_degraded_chain_uses_health_order():
    target = DEFAULT_TARGETS[-1]
    for stage in (0, 5, 25):
        for uid in map(str, range(100)):
            assert live_router.select([target], {target.id: GateState(stage=stage)}, uid, 'en') == [target]
    states = {
        'parakeet-window': GateState(stage=0, n=8, failures=8),
        'modulate-velma-2': GateState(stage=5, n=30, failures=15),
        'soniox': GateState(stage=25, n=60, failures=3),
    }
    metric = COST_ALL_DEGRADED.labels(target='soniox')
    before = metric._value.get()
    uid = next(
        str(i)
        for i in range(1000)
        if not any(assigned(str(i), 'stt-reentry:' + t.id, states[t.id].stage) for t in DEFAULT_TARGETS)
    )
    assert [target.id for target in live_router.select(DEFAULT_TARGETS, states, uid, 'en')] == [
        'soniox',
        'modulate-velma-2',
        'parakeet-window',
    ]
    assert metric._value.get() == before + 1
    states = {target.id: GateState(stage=0, n=100, failures=10) for target in DEFAULT_TARGETS}
    states['soniox'] = GateState(stage=0, n=100, failures=1)
    assert live_router.select(DEFAULT_TARGETS, states, uid, 'en')[0].id == 'soniox'


@pytest.mark.asyncio
async def test_idle_pods_refresh_global_gauges_and_unknown_is_not_healthy():
    now = [1000]
    redis = MemoryRedis(clock=lambda: now[0])
    pods = [live_health.FleetHealth(redis_client=redis, clock=lambda: now[0]) for _ in range(2)]
    target = DEFAULT_TARGETS[0]
    redis.data[live_stt_state.cost_key(target, 'all')] = json.dumps(GateState(stage=5, generation=2).encode())
    for pod in pods:
        assert not pod._cost_interests
        await pod.refresh_cost_once()
        assert COST_STAGE.labels(target=target.id)._value.get() == 5
        assert COST_STATE_KNOWN.labels(target=target.id)._value.get() == 1
        assert math.isnan(COST_STAGE.labels(target='soniox')._value.get())
    now[0] += 5
    redis.data[live_stt_state.cost_key(target, 'all')] = json.dumps(GateState(stage=25, generation=3).encode())
    for pod in pods:
        await pod.refresh_cost_once()
        assert pod._cost_cached[(target.id, 'all')].stage == 25
        assert COST_STAGE.labels(target=target.id)._value.get() == 25
        assert COST_SNAPSHOT_AT._value.get() == now[0]


@pytest.mark.asyncio
async def test_initialised_transition_counters_count_global_and_language_cas(monkeypatch):
    target = Target('shadow-test', 'modulate', 0.055)
    pod = live_chain.health
    monkeypatch.setattr(live_cost_health, 'registry', lambda: (target,))
    pod._init_cost_metrics([target])
    for scope, lang in (('global', 'all'), ('language', 'ja')):
        metric = COST_EVENTS.labels(target=target.id, event='bench', scope=scope)
        assert metric._value.get() == 0
        await pod._cost_update((target.id, lang), lambda _: GateState(stage=0, generation=1))
        assert metric._value.get() == 1
        await pod._cost_update((target.id, lang), lambda state: state)
        assert metric._value.get() == 1
