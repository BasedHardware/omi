"""Deterministic CUSUM calibration and capped recovery traffic; no services."""

import heapq
import random
import statistics
from collections import Counter

import pytest

from config.live_stt_registry import assigned
from utils.stt.live_gate import GateState, begin_trial, transition


@pytest.fixture(autouse=True)
def default_gate(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_DISRUPTION_GATE', '0.08')


@pytest.fixture(scope='module')
def baseline_counts():
    counts = Counter()
    yield counts
    # 4 million baseline sessions represent about 222 days at 18k/day.
    # Require no false bench in this seeded baseline; bound higher-rate
    # calibration separately so the reported sensitivity does not drift.
    assert counts[0.03] == 0
    assert counts[0.05] <= 4
    assert counts[0.075] <= 32


# The fast lane keeps a 10-seed sample; the full 200-seed sweep (4M sessions per
# rate, ~5 minutes on a CI runner) runs in the slow guardrail lane.
_BASELINE_SEEDS = [seed if seed < 10 else pytest.param(seed, marks=pytest.mark.slow) for seed in range(200)]


@pytest.mark.parametrize('rate', [0.03, 0.05, 0.075])
@pytest.mark.parametrize('seed', _BASELINE_SEEDS)
def test_twenty_thousand_session_baseline(rate, seed, baseline_counts):
    rng, state = random.Random(seed), GateState()
    for n in range(20000):
        state = transition(state, rng.random() < rate, n, witness=f'{n:016x}')
        if state.stage == 0:
            baseline_counts[rate] += 1
            state = GateState()
    assert state.n <= 20000


def detect(rate, seed, *, warmup=500, horizon=5000):
    rng, state = random.Random(seed), GateState()
    for _ in range(warmup):
        state = transition(state, False, 0)
    failures = 0
    for n in range(1, horizon + 1):
        failed = rng.random() < rate
        failures += failed
        state = transition(state, failed, n, witness=f'{n:016x}')
        if state.stage == 0:
            return n, failures
    return horizon + 1, failures


@pytest.mark.parametrize('rate,limit', [pytest.param(0.12, 1500, marks=pytest.mark.slow), (0.16, 300)])
def test_brownout_median_detection(rate, limit):
    # A run that has not detected by the limit cannot lower the median below it,
    # so stopping there proves the same bound without running undetected seeds on.
    samples = [detect(rate, seed, horizon=limit)[0] for seed in range(30)]
    assert statistics.median(samples) <= limit


@pytest.mark.parametrize('warmup', [0, 100, 1020, 20000])
@pytest.mark.parametrize('phase', range(5))
def test_sustained_sixty_percent_outage_within_ten_failed_sessions(warmup, phase):
    state = GateState()
    for _ in range(warmup):
        state = transition(state, False, 0)
    failures = 0
    for n in range(1, 40):
        failed = (n + phase) % 5 < 3
        failures += failed
        state = transition(state, failed, n, witness=f'{n:016x}')
        if state.stage == 0:
            break
    assert state.stage == 0 and failures <= 10


def trial_day(seed, rate=0.61, sessions=17900, *, outcome_delay=30, cache_delay=15):
    rng = random.Random(seed)
    state = GateState(stage=0, strikes=1, until=300)
    visible = state
    pending = []
    refresh_at = 0
    trials = disruptions = 0
    for i in range(sessions):
        now = i * 86400 / sessions
        while pending and pending[0][0] <= now:
            finished, generation, failed, witness = heapq.heappop(pending)
            if generation == state.generation:
                state = transition(state, failed, finished, witness=witness)
        if now >= refresh_at:
            state = begin_trial(state, now)
            visible = state
            refresh_at = now + cache_delay
        if visible.stage == 0 or not assigned(str(i), 'stt-reentry:modulate-velma-2', visible.stage):
            continue
        failed = rng.random() < rate
        trials += 1
        disruptions += failed
        heapq.heappush(pending, (now + outcome_delay, visible.generation, failed, f'{i:016x}'))
    return trials, disruptions


@pytest.mark.parametrize(
    'seed', [seed if seed < 10 else pytest.param(seed, marks=pytest.mark.slow) for seed in range(100)]
)
def test_chronic_modulate_daily_trial_disruption_budget(seed):
    trials, disruptions = trial_day(seed)
    assert disruptions + 10 < 100  # include an initial hard-outage detection allowance
    assert trials < 200
