"""Replay proof that the batch worker HPA returns to its floor at 25% load (batchretune, 2026-11-02).

At 02:30Z on 2026-11-02 the batch pool held 8 L4 nodes at ~2% GPU. Two faults in
the max-of-two shape (#24256) combine there:

* Every worker pod is scraped by two jobs (``batch-pipeline-worker-metrics`` and
  the in-cluster guards' PodMonitoring), so a plain ``sum(rate(...))`` of
  ``worker_flight`` reads twice the real chain demand (2.16 vs 1.07 s/s, 02:40Z).
* Both signals are minute-scale sawtooths at 25%: ready units flap 0 <-> 128 and
  2m chain demand spikes to 5.8 s/s while the 10m rate never passes 3.0. The
  1800s scale-down window keeps the highest recommendation it saw, so a target
  that reacts to one-minute bursts pins the fleet near its burst size.

The fixture is the measured 1-min fleet window 2026-11-01T23:41Z..2026-11-02T02:41Z
(ro-prod Prometheus; aggregates only). The test reads the chart's targets and the
adapter's chain rule, picks the fixture column that rule would serve, and replays
the autoscaling/v2 controller over it.
"""

import json
import math
import re
from pathlib import Path

import yaml

CHARTS = Path(__file__).resolve().parents[2] / 'charts'
CHART = CHARTS / 'batch-pipeline-worker'
ADAPTER = CHARTS / 'monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml'
FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'batch_pipeline_hpa_retune_replay_3h.json'
STEP_SECONDS = 60
UP_PODS = 2  # per 60s, no scale-up stabilization
DOWN_PODS, DOWN_PERIOD = 1, 600
TOLERANCE = 0.1  # controller default
# Per-worker chain demand above this means queueing: the busiest pod in the
# window measured 0.93 s/s over 5m.
HOT_CHAIN_PER_WORKER = 0.85
# Step-load model (measured 30 min to 02:38Z): 0.72 leases/s at 0.98 chain s/s,
# and L4 pods serve about five minutes after the HPA adds them.
UNITS_PER_CHAIN_SECOND = 0.73
POD_CHAIN_CEILING = 0.93
PROVISION_MINUTES = 5


def _config():
    autoscaling = yaml.safe_load((CHART / 'values.yaml').read_text())['autoscaling']
    prod = yaml.safe_load((CHART / 'prod_omi_batch-pipeline-worker_values.yaml').read_text())['autoscaling']
    return {
        'ready_target': int(autoscaling['targetQueuedUnitsPerWorker']),
        'chain_target': float(autoscaling['targetChainBusyPerWorker']),
        'down_stab': int(autoscaling['scaleDownStabilizationSeconds']),
        'min_replicas': int(prod['minReplicas']),
        'max_replicas': int(prod['maxReplicas']),
    }


def _served_chain_column():
    """The fixture column the live adapter would serve for the chain metric."""
    rules = yaml.safe_load(ADAPTER.read_text())['rules']['external']
    rule = next(r for r in rules if r['name']['as'] == 'omi_batch_pipeline_gpu_chain_busy_seconds')
    query = rule['metricsQuery']
    window = re.search(r'stage="worker_flight"\}\[(\d+m)\]\)', query).group(1)
    if 'max by (namespace, pod)' not in query:
        assert window == '2m', 'the fixture only measured the undeduplicated sum at 2m'
        return 'chain_2m_both_scrape_jobs'
    return f'chain_{window}_per_pod'


def _load():
    payload = json.loads(FIXTURE.read_text())
    columns = payload['columns']
    return {name: [row[i] for row in payload['rows']] for i, name in enumerate(columns)}


def _recommendation(total, target, config, current):
    if total is None:
        return None
    if total <= 0:
        return config['min_replicas']
    if abs(total / (target * current) - 1) <= TOLERANCE:
        return current
    return max(config['min_replicas'], min(config['max_replicas'], math.ceil(total / target)))


def _replay(series, metrics, config, start=None):
    """autoscaling/v2 at 60s steps.

    Each metric keeps the current size while within the controller's 10%
    tolerance. Scale-down uses the highest recommendation inside the
    stabilization window and sheds DOWN_PODS per DOWN_PERIOD; scale-up adds
    UP_PODS per step. A missing sample blocks scale-down, as a failed external
    metric does.
    """
    current = start or config['min_replicas']
    history, trace, last_down = [], [], None
    for step, epoch in enumerate(series['epoch']):
        per_metric = [_recommendation(series[name][step], target, config, current) for name, target in metrics]
        valid = [r for r in per_metric if r is not None]
        rec = max(valid) if valid else current
        if len(valid) < len(per_metric):
            rec = max(rec, current)
        history.append((epoch, rec))
        stabilized = max(r for stamp, r in history if stamp > epoch - config['down_stab'])
        if rec > current:
            current = min(rec, current + UP_PODS, config['max_replicas'])
        elif stabilized < current and (last_down is None or epoch - last_down >= DOWN_PERIOD):
            current, last_down = max(stabilized, current - DOWN_PODS), epoch
        trace.append(current)
    return trace


def _metrics(config, chain_column):
    return [('ready_units', config['ready_target']), (chain_column, config['chain_target'])]


def test_fixture_reproduces_the_pinned_pool():
    # The shipped #24256 shape (ready 16, undeduplicated 2m chain) on this
    # window pins the fleet near its ceiling, which is what the live pool did
    # once the chain metric was served.
    series = _load()
    config = dict(_config(), ready_target=16, chain_target=0.5, down_stab=1800)
    trace = _replay(series, _metrics(config, 'chain_2m_both_scrape_jobs'), config)
    assert len(trace) >= 180
    assert sum(trace[-60:]) / 60 >= 14


def test_chart_and_adapter_return_to_the_floor_without_queueing():
    config = _config()
    series = _load()
    chain_column = _served_chain_column()
    trace = _replay(series, _metrics(config, chain_column), config)
    mean = sum(trace) / len(trace)
    # Measured at 25%: GPU work averages ~1.1 chain s/s, about two workers at
    # target. The fleet should sit at or just above the floor of 4.
    assert mean <= 5.5, (chain_column, mean)
    assert max(trace) <= 7, (chain_column, max(trace))
    # Timeliness: per-worker 5m chain demand stays below the hot line in every
    # minute, so a smaller fleet never queues flights behind each other.
    hot = [
        (epoch, replicas, demand)
        for epoch, replicas, demand in zip(series['epoch'], trace, series['chain_5m_per_pod'])
        if demand is not None and demand > HOT_CHAIN_PER_WORKER * replicas
    ]
    assert hot == []


def test_fleet_held_at_the_live_size_sheds_to_the_floor():
    # The live HPA sat at desired 12 when the chain metric came back.
    config = _config()
    series = _load()
    trace = _replay(series, _metrics(config, _served_chain_column()), config, start=12)
    assert next(i for i, replicas in enumerate(trace) if replicas <= 5) <= 60
    assert config['min_replicas'] in trace
    assert trace[-1] <= 6


def _step_load(ready_target, chain_window, config, minutes=90, step_at=10, base=1.1, high=5.8):
    """Worst backlog wait (minutes) and minutes to catch up after demand steps base -> high chain s/s.

    Ready units accrue from unserved chain demand; the chain signal is the
    trailing mean of served work over the adapter's rate window.
    """
    current, serving, backlog, served = 4, [4] * PROVISION_MINUTES, 0.0, []
    worst, caught = 0.0, None
    for minute in range(minutes):
        demand = high if minute >= step_at else base
        capacity = serving[0] * POD_CHAIN_CEILING
        done = min(capacity, demand + backlog / 60)
        backlog = max(0.0, backlog + (demand - done) * 60)
        served.append(done)
        chain = sum(served[-chain_window:]) / len(served[-chain_window:])
        rec = max(
            _recommendation(backlog * UNITS_PER_CHAIN_SECOND, ready_target, config, current),
            _recommendation(chain, config['chain_target'], config, current),
        )
        if rec > current:
            current = min(rec, current + UP_PODS, config['max_replicas'])
        serving = serving[1:] + [current]
        worst = max(worst, backlog / capacity / 60)
        if minute > step_at and caught is None and backlog < 1:
            caught = minute - step_at
    return worst, caught


def test_sustained_load_step_is_absorbed_about_as_fast_as_before():
    # A smoothed chain rate answers a sustained step late; the ready backlog,
    # which only builds when capacity is short, is the fast path.
    config = _config()
    window = int(re.search(r'(\d+)m$', _served_chain_column().replace('_per_pod', '')).group(1))
    worst, caught = _step_load(config['ready_target'], window, config)
    before_worst, before_caught = _step_load(16, 2, dict(config, chain_target=0.5))
    assert worst <= before_worst + 1, (worst, before_worst)
    assert caught is not None and caught <= before_caught + 2, (caught, before_caught)
