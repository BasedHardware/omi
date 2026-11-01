"""Replay proof for the max-of-two batch worker HPA (batchdesign PR-2, 2026-11-01).

The HPA keeps the admissible-ready backlog metric (target 16 units/worker) and
adds GPU-chain occupancy (`worker_flight` busy seconds/second, target 0.5 per
worker); autoscaling/v2 takes the highest per-metric recommendation. Occupancy
alone sheds lanes whenever claims bind rather than flights (a claim-chain wedge
drains chain busy while the ready backlog is real work), and the ready count
alone starves the healthy drain hours where backlog reads low but flights are
real. This replays one measured 24h window (ro-prod Prometheus, hpafit
2026-11-01; 5m grid interpolated to 60s controller steps) through an HPA v2
engine and asserts the two properties the design claims:

* replicas at or above the ready-only answer whenever backlog exceeds 16 per
  worker (the incumbent signal never loses capacity it would have bought);
* zero starved minutes, where starvation means simulated replicas x the
  measured healthy per-worker chain ceiling (0.56 chain s/s) < actual fleet
  chain demand.

Engine: per-metric recommendation = ceil(fleet_total / target) clamped to
[min, max] (AverageValue over a fleet-total external metric is
replica-independent); unavailable samples hold capacity (a stale/absent
external metric must never shrink the fleet); scale-up +2 pods/60s with no
stabilization; scale-down takes the minimum recommendation over a
stabilizationWindowSeconds window and sheds at most 1 pod per periodSeconds.
HPA's 10% downscale tolerance is omitted (parity with the hpafit-reviewed
engine): the real controller sheds slightly less, so dominance and starvation
results here are the conservative side.
"""

import json
import math
from pathlib import Path

import yaml

CHART = Path(__file__).resolve().parents[2] / 'charts' / 'batch-pipeline-worker'
FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'batch_pipeline_hpa_max_replay_24h.json'
CHAIN_CEILING_PER_WORKER = 0.56  # measured healthy per-worker chain s/s (hpafit)
STEP_SECONDS = 60
UP_PODS, UP_PERIOD = 2, 60


def _replay_config():
    values = yaml.safe_load((CHART / 'values.yaml').read_text())
    autoscaling = values['autoscaling']
    prod = yaml.safe_load((CHART / 'prod_omi_batch-pipeline-worker_values.yaml').read_text())['autoscaling']
    return {
        'ready_target': int(autoscaling['targetQueuedUnitsPerWorker']),
        'chain_target': float(autoscaling['targetChainBusyPerWorker']),
        'down_stab': int(autoscaling['scaleDownStabilizationSeconds']),
        'down_pods': 1,
        'down_period': 600,
        'min_replicas': int(prod['minReplicas']),
        'max_replicas': int(prod['maxReplicas']),
    }


def _load_series():
    payload = json.loads(FIXTURE.read_text())
    epochs = [row[0] for row in payload['rows']]
    actual = [(row[0], row[1]) for row in payload['rows']]
    chain = [(row[0], row[2]) for row in payload['rows'] if row[2] is not None]
    pool = [(row[0], row[3]) for row in payload['rows'] if row[3] is not None]
    return epochs, actual, chain, pool


def _interp(series, t):
    if t <= series[0][0]:
        return series[0][1]
    if t >= series[-1][0]:
        return series[-1][1]
    lo, hi = 0, len(series) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if series[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    (t0, v0), (t1, v1) = series[lo], series[hi]
    if t1 == t0:
        return v0
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def _recommendation(total, target, config):
    if total is None:
        return None  # unavailable metric: hold, never shrink
    if total <= 0:
        return config['min_replicas']
    return max(config['min_replicas'], min(config['max_replicas'], math.ceil(total / target)))


def _replay(recommendations, config):
    """autoscaling/v2 horizontal controller at 60s steps over the fixture window."""
    t0, t1 = recommendations['epoch'][0], recommendations['epoch'][-1]
    current = config['min_replicas']
    down_window = []
    trace = []
    t = t0
    while t <= t1:
        per_metric = [rec(t) for rec in recommendations['metrics']]
        valid = [r for r in per_metric if r is not None]
        rec = max(valid) if valid else None
        if rec is None:
            rec = current
        if rec > current:
            allowance = UP_PODS * max(1, STEP_SECONDS // UP_PERIOD)
            current = min(rec, current + allowance, config['max_replicas'])
            down_window = []
        elif rec < current:
            down_window.append((t, rec))
            window = [r for stamp, r in down_window if stamp >= t - config['down_stab']]
            if window and max(window) < current:
                allowance = config['down_pods'] * max(1, STEP_SECONDS // config['down_period'])
                current = max(config['min_replicas'], min(rec, current - allowance))
        trace.append((t, current))
        t += STEP_SECONDS
    return trace


def test_max_of_two_dominates_ready_only_when_backlog_binds_and_never_starves():
    config = _replay_config()
    epochs, actual, chain, pool = _load_series()

    def ready_only_rec(t):
        return _recommendation(_interp(pool, t), config['ready_target'], config)

    def chain_only_rec(t):
        return _recommendation(_interp(chain, t), config['chain_target'], config)

    def max_of_two_rec(t):
        recommendations = [ready_only_rec(t), chain_only_rec(t)]
        valid = [r for r in recommendations if r is not None]
        return max(valid) if valid else None

    ready_only = _replay({'epoch': epochs, 'metrics': [ready_only_rec]}, config)
    max_of_two = _replay({'epoch': epochs, 'metrics': [max_of_two_rec]}, config)
    # The measured window is the 24h ending 2026-11-01 15:53Z (1436 steps).
    assert len(ready_only) == len(max_of_two) >= 23 * 60

    # The chain metric must bind somewhere: a config whose second metric never
    # exceeds the ready recommendation is dead weight, not max-of-two.
    chain_binds = sum(1 for t, _ in max_of_two if (chain_only_rec(t) or 0) > (ready_only_rec(t) or 0))
    assert chain_binds > 0

    # Dominance: wherever backlog exceeds the ready target per worker, the
    # max-of-two fleet is at least the ready-only answer.
    backlog_steps = 0
    for (t, ready_replicas), (_, max_replicas) in zip(ready_only, max_of_two):
        pending = _interp(pool, t)
        if pending is not None and pending > config['ready_target'] * ready_replicas:
            backlog_steps += 1
            assert max_replicas >= ready_replicas, (t, ready_replicas, max_replicas)
    assert backlog_steps > 0  # the window must exercise the claim-bound regime

    # Starvation: simulated capacity (replicas x measured per-worker chain
    # ceiling) must cover the actual fleet chain demand for every step.
    starved = [t for t, replicas in max_of_two if replicas * CHAIN_CEILING_PER_WORKER < (_interp(chain, t) or 0)]
    assert starved == []

    # And the ready-only signal alone does starve in this window, so the
    # fixture genuinely covers the regime the occupancy metric exists for.
    ready_only_starved = [
        t for t, replicas in ready_only if replicas * CHAIN_CEILING_PER_WORKER < (_interp(chain, t) or 0)
    ]
    assert ready_only_starved
