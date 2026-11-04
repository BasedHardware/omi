"""Offline HPA sensitivity search using the unchanged regression replay engines.

Run with backend/.venv/bin/python from any directory. This evaluates model
helpers, not pytest; qualify the chosen chart through backend/test.sh as well.
The older 24h engine does not faithfully implement downscale policy. Results
from a changed window/policy are diagnostics, not stockout qualification.
"""

import argparse
import importlib.util
import itertools
import json
from pathlib import Path

FULL_VOLUME_SCALE = 3.7  # Synthetic fleet-total multiplier, not observed traffic.
ROOT = Path(__file__).resolve().parents[2]


def module(name):
    s = importlib.util.spec_from_file_location(
        name, ROOT / f'backend/tests/unit/test_batch_pipeline_hpa_{name}_replay.py'
    )
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


r = module('retune')
m = module('max')
cfg = r._config()
series = r._load()
column = r._served_chain_column()
epochs, _, chain, pool = m._load_series()
ts = list(range(epochs[0], epochs[-1] + 1, 60))
cs = [m._interp(chain, t) for t in ts]
qs = [m._interp(pool, t) for t in ts]
full = {k: [x if k == 'epoch' or x is None else x * FULL_VOLUME_SCALE for x in v] for k, v in series.items()}


def max_stats(c):
    def recs(vals, target):
        return [m._recommendation(x, target, c) for x in vals]

    rr, cr = recs(qs, c['ready_target']), recs(cs, c['chain_target'])

    def replay(recs):
        return m._replay(
            {'epoch': epochs, 'metrics': [lambda t: recs[(t - ts[0]) // 60]]}, dict(c, down_pods=1, down_period=600)
        )

    a = replay(rr)
    b = replay([max(x or 0, y or 0) or None for x, y in zip(rr, cr)])
    return {
        'mean': sum(n for _, n in b) / len(b),
        'max': max(n for _, n in b),
        'starved': sum(n * m.CHAIN_CEILING_PER_WORKER < (x or 0) for (_, n), x in zip(b, cs)),
        'dominance': all(nb >= na for (_, na), (_, nb), q in zip(a, b, rr) if (q or 0) > c['min_replicas']),
        'chain_binds': any((x or 0) > (y or 0) for x, y in zip(cr, rr)),
        'backlog_binds': any((q or 0) > c['min_replicas'] for q in rr),
        'ready_starved': sum(n * m.CHAIN_CEILING_PER_WORKER < (x or 0) for (_, n), x in zip(a, cs)),
    }


def stats(s, c):
    t = r._replay(s, r._metrics(c, column), c)
    return {
        'mean': sum(t) / len(t),
        'max': max(t),
        'hot': sum(x is not None and x > r.HOT_CHAIN_PER_WORKER * n for n, x in zip(t, s['chain_5m_per_pod'])),
        'floor': c['min_replicas'] in t,
    }


def evaluate(ready, busy, stab):
    c = dict(cfg, ready_target=ready, chain_target=busy, down_stab=stab)
    a = stats(series, c)
    f = stats(full, c)
    mx = max_stats(c)
    shed = r._replay(series, r._metrics(c, column), c, start=12)
    worst, caught = r._step_load(ready, 10, c)
    bw, bc = r._step_load(16, 2, dict(c, chain_target=0.5))
    reasons = []
    if a['mean'] > 5.5 or a['max'] > 7 or a['hot']:
        reasons.append('3h')
    if next((i for i, x in enumerate(shed) if x <= 5), 999) > 60 or c['min_replicas'] not in shed or shed[-1] > 6:
        reasons.append('shed')
    if worst > bw + 1 or caught is None or caught > bc + 2:
        reasons.append('step')
    if (
        mx['starved']
        or not mx['dominance']
        or not mx['chain_binds']
        or not mx['backlog_binds']
        or not mx['ready_starved']
    ):
        reasons.append('24h')
    return {
        'ready': ready,
        'busy': busy,
        'stab': stab,
        'current': a,
        'full_model': f,
        'measured24h': mx,
        'step': [worst, caught],
        'full_step': r._step_load(ready, 10, c, base=4.05, high=12),
        'fail': reasons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grid', choices=['coarse', 'refined', 'all'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    candidates = set()
    if args.grid in ('coarse', 'all'):
        candidates.update(
            itertools.product(
                range(16, 65, 4),
                [0.45, 0.48, 0.5, 0.52, 0.54, 0.55, 0.56, 0.57, 0.58, 0.6, 0.65, 0.7, 0.8],
                [60, 300, 600, 900, 1200, 1800, 2400, 3600],
            )
        )
    if args.grid in ('refined', 'all'):
        candidates.update(
            itertools.product(
                range(36, 45),
                [0.55, 0.555, 0.56, 0.561, 0.565, 0.57],
                range(60, 1801, 60),
            )
        )
    # Always report baseline, reverted shape, shipped candidate, and boundaries.
    candidates.update(
        [(32, 0.5, 1800), (40, 0.6, 1800), (41, 0.56, 1800), (41, 0.56, 60), (41, 0.561, 1800), (42, 0.56, 1800)]
    )
    results = [evaluate(*candidate) for candidate in sorted(candidates)]
    # Policy sensitivity is only a 3h diagnostic. The unchanged 24h model and
    # chart tests do not qualify alternate policies. Restore model constants.
    sensitivity = []
    original_policy = r.DOWN_PODS, r.DOWN_PERIOD
    try:
        for pods, period in [(1, 60), (1, 300), (1, 600), (1, 1200), (2, 600)]:
            r.DOWN_PODS, r.DOWN_PERIOD = pods, period
            result = evaluate(41, 0.56, 60)
            sensitivity.append(
                {
                    'pods': pods,
                    'period': period,
                    'current': result['current'],
                    'full_model': result['full_model'],
                    'shed_pass': 'shed' not in result['fail'],
                }
            )
    finally:
        r.DOWN_PODS, r.DOWN_PERIOD = original_policy
    payload = {
        'synthetic_full_volume_scale': FULL_VOLUME_SCALE,
        'candidates': results,
        'policy_sensitivity_3h_only': sensitivity,
    }
    args.output.write_text(json.dumps(payload, indent=2) + '\n')
    good = [x for x in results if not x['fail']]
    eligible = [x for x in good if x['stab'] == 1800 and x['full_model']['hot'] <= 7]
    order = lambda x: (x['current']['mean'], x['full_model']['mean'], x['measured24h']['mean'])
    print(
        json.dumps(
            {
                'searched': len(results),
                'model_pass': len(good),
                'lowest_model_mean': min(good, key=order),
                'lowest_with_stockout_window_and_full_hot_budget': min(eligible, key=order),
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
