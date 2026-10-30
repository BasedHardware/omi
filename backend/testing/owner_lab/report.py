"""Offline report over a results JSONL: per-arm table, paired bootstrap CIs, gates.

No LLM, no network, no identifiers — it reads aggregate metrics rows only. The
paired statistics compare each arm against a named baseline on the same (case,
repeat) pair: a resampled bootstrap over pairs, seeded so a rerun on the same
rows reproduces the same interval. The noise floor is the same statistic on the
baseline's repeat 1 vs repeat 0, which is how much a rerun of *unchanged* code
moves; an arm within that floor matches the baseline.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

METRICS = ('cost', 'rejections', 'lookups', 'turns')
# The conv-structure card (mirrored and pinned by utils/llm/notes_agent_policy).
PRICES = (0.10, 0.01, 0.60)
BOOTSTRAP_ITERATIONS = 4000
BOOTSTRAP_SEED = 7


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def arm_names(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        if row['arm'] not in seen:
            seen.append(row['arm'])
    return seen


def per_arm(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One aggregate row per arm, in first-seen order. Aggregates only, no ids."""
    out = []
    for arm in arm_names(rows):
        runs = [r for r in rows if r['arm'] == arm]
        n = len(runs)
        forced = sum(1 for r in runs if r['forced'])
        prompt = sum(r.get('prompt_tokens') or 0 for r in runs)
        cached = sum(r.get('cached_tokens') or 0 for r in runs)
        out.append(
            {
                'arm': arm,
                'runs': n,
                'conversations': len({r['id'] for r in runs}),
                'forced': forced,
                'forced_share': forced / n if n else 0.0,
                'forced_reasons': dict(Counter(r['reason'] or 'unknown' for r in runs if r['forced'])),
                'lookups_per_run': sum(r.get('lookups') or 0 for r in runs) / n if n else 0.0,
                'rejections_per_run': sum(r.get('rejections') or 0 for r in runs) / n if n else 0.0,
                'cost_per_run': sum(r.get('cost') or 0 for r in runs) / n if n else 0.0,
                'cache_share': cached / prompt if prompt else 0.0,
                'turns_per_run': sum(r.get('turns') or 0 for r in runs) / n if n else 0.0,
                'packet_bytes': sum(r.get('packet_bytes') or 0 for r in runs) / n if n else 0.0,
            }
        )
    return out


def _pairs_by_key(
    rows: Sequence[Mapping[str, Any]], baseline: str, arm: str
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    by: dict[tuple[str, int, str], Mapping[str, Any]] = {(r['id'], r['repeat'], r['arm']): r for r in rows}
    return [(by[key], by[(key[0], key[1], arm)]) for key in by if key[2] == baseline and (key[0], key[1], arm) in by]


def bootstrap_ratio(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    key: str,
    rng: random.Random,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> tuple[float, float, float]:
    """(ratio, 95% CI) of sum(arm)/sum(baseline) over resampled pairs."""
    point = sum(float(p[1][key]) for p in pairs) / sum(float(p[0][key]) for p in pairs)
    stats = []
    for _ in range(iterations):
        sample = [rng.choice(pairs) for _ in pairs]
        stats.append(sum(float(p[1][key]) for p in sample) / sum(float(p[0][key]) for p in sample))
    stats.sort()
    return point, stats[int(0.025 * iterations)], stats[int(0.975 * iterations)]


def paired_ratios(
    rows: Sequence[Mapping[str, Any]],
    baseline: str,
    *,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Bootstrap CIs per non-baseline arm (alphabetical) and metric, then the noise floor.

    Call order is fixed so the seeded stream is reproducible: alphabetical arms,
    metric order cost/rejections/lookups/turns, noise floor last.
    """
    rng = random.Random(seed)
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for arm in sorted(set(arm_names(rows)) - {baseline}):
        pairs = _pairs_by_key(rows, baseline, arm)
        metrics: dict[str, dict[str, Any]] = {}
        for key in METRICS:
            if key == 'rejections' and not sum(float(p[0][key]) for p in pairs):
                continue
            point, lo, hi = bootstrap_ratio(pairs, key, rng, iterations)
            metrics[key] = {'ratio': point, 'ci_low': lo, 'ci_high': hi, 'pairs': len(pairs)}
        result[arm] = metrics
    by = {(r['id'], r['repeat'], r['arm']): r for r in rows}
    floor_pairs = [
        (by[(case, 0, baseline)], by[(case, 1, baseline)])
        for (case, repeat, arm) in by
        if arm == baseline and repeat == 0 and (case, 1, baseline) in by
    ]
    if floor_pairs:
        point, lo, hi = bootstrap_ratio(floor_pairs, 'cost', rng, iterations)
        result['noise_floor'] = {'cost': {'ratio': point, 'ci_low': lo, 'ci_high': hi, 'pairs': len(floor_pairs)}}
    return result


def cost_split(
    rows: Sequence[Mapping[str, Any]], baseline: str, prices: tuple[float, float, float] = PRICES
) -> list[dict[str, Any]]:
    """Per-arm cost split into token volume vs cache-hit share, at the baseline's cache share."""
    price_in, price_cached, price_out = prices
    base_rows = [r for r in rows if r['arm'] == baseline]
    base_ratio = (
        sum(r.get('cached_tokens') or 0 for r in base_rows) / sum(r.get('prompt_tokens') or 0 for r in base_rows)
        if base_rows and sum(r.get('prompt_tokens') or 0 for r in base_rows)
        else 0.0
    )
    out = []
    for arm in arm_names(rows):
        runs = [r for r in rows if r['arm'] == arm]
        n = len(runs) or 1
        p = sum(r.get('prompt_tokens') or 0 for r in runs) / n
        c = sum(r.get('cached_tokens') or 0 for r in runs) / n
        o = sum(r.get('completion_tokens') or 0 for r in runs) / n
        out.append(
            {
                'arm': arm,
                'runs': len(runs),
                'prompt_tokens': p,
                'cached_share': c / p if p else 0.0,
                'completion_tokens': o,
                'cost_per_run': ((p - c) * price_in + c * price_cached + o * price_out) / 1e6,
                'cost_at_baseline_cache_share': (
                    (p - p * base_ratio) * price_in + p * base_ratio * price_cached + o * price_out
                )
                / 1e6,
            }
        )
    return out


def evaluate_gates(
    arms: Sequence[Mapping[str, Any]],
    ratios: Mapping[str, dict[str, dict[str, Any]]],
    *,
    max_cost_per_run: float | None = None,
    no_worse: Sequence[str] = (),
    tolerance: float = 1e-9,
) -> list[dict[str, str]]:
    """Acceptance gates. ``no-worse`` fails only when a metric's CI sits entirely above 1."""
    gates: list[dict[str, str]] = []
    if max_cost_per_run is not None:
        for arm in arms:
            cost = arm['cost_per_run']
            verdict = 'PASS' if cost <= max_cost_per_run else 'FAIL'
            gates.append(
                {
                    'gate': f'max-cost-per-run {arm["arm"]}',
                    'verdict': verdict,
                    'detail': f'${cost:.5f}/run vs ${max_cost_per_run:.5f} ceiling',
                }
            )
    for arm_name in sorted(ratios):
        if arm_name == 'noise_floor':
            continue
        for metric in no_worse:
            entry = ratios[arm_name].get(metric)
            if entry is None:
                continue
            worse = entry['ci_low'] > 1.0 + tolerance
            gates.append(
                {
                    'gate': f'no-worse {metric} {arm_name} vs baseline',
                    'verdict': 'FAIL' if worse else 'PASS',
                    'detail': f"ratio {entry['ratio']:.3f} CI [{entry['ci_low']:.3f}, {entry['ci_high']:.3f}]",
                }
            )
    return gates


def render_markdown(
    rows: Sequence[Mapping[str, Any]],
    baseline: str,
    arms: Sequence[Mapping[str, Any]],
    ratios: Mapping[str, dict[str, dict[str, Any]]],
    split: Sequence[Mapping[str, Any]],
    gates: Sequence[dict[str, str]],
) -> str:
    lines = ['# Owner-lab replay bench report', '', f'Baseline arm: {baseline}. Aggregates only; no ids.', '']
    lines += [
        '| Arm | Runs | Forced share | Lookups/run | Rejections/run | Est cost/run | Cache share |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for arm in arms:
        lines.append(
            f"| {arm['arm']} | {arm['runs']} | {arm['forced_share']:.1%} ({arm['forced']}/{arm['runs']}) "
            f"| {arm['lookups_per_run']:.2f} | {arm['rejections_per_run']:.3f} | ${arm['cost_per_run']:.5f} "
            f"| {arm['cache_share']:.3f} |"
        )
    lines.append('')
    for arm_name in sorted(set(ratios) - {'noise_floor'}):
        metrics = ratios[arm_name]
        pairs = next(iter(metrics.values()), {}).get('pairs', 0)
        lines.append(f'Paired {arm_name} vs {baseline} (same case and repeat, n={pairs}):')
        for key in METRICS:
            if key in metrics:
                entry = metrics[key]
                lines.append(
                    f"- {key} ratio {entry['ratio']:.3f}, 95% CI [{entry['ci_low']:.3f}, {entry['ci_high']:.3f}]"
                )
        lines.append('')
    if 'noise_floor' in ratios:
        entry = ratios['noise_floor']['cost']
        lines.append(
            f"Noise floor: baseline repeat 1 vs repeat 0 cost ratio {entry['ratio']:.3f}, "
            f"CI [{entry['ci_low']:.3f}, {entry['ci_high']:.3f}] (n={entry['pairs']})."
        )
        lines.append('')
    lines += [
        'Cost split (volume vs cache share at the baseline cache share):',
        '',
        '| Arm | Prompt | Cached share | Cost/run | At baseline cache share |',
        '|---|---:|---:|---:|---:|',
    ]
    for arm in split:
        lines.append(
            f"| {arm['arm']} | {arm['prompt_tokens']:.0f} | {arm['cached_share']:.3f} "
            f"| ${arm['cost_per_run']:.5f} | ${arm['cost_at_baseline_cache_share']:.5f} |"
        )
    lines.append('')
    if gates:
        lines.append('## Gates')
        lines.append('')
        for gate in gates:
            lines.append(f"- {gate['verdict']}: {gate['gate']} — {gate['detail']}")
        lines.append('')
    return '\n'.join(lines)


def cost_from_tokens(row: Mapping[str, Any], prices: tuple[float, float, float]) -> float:
    """Per-run cost recomputed from the row's token counts at the given card."""
    price_in, price_cached, price_out = prices
    prompt = row.get('prompt_tokens') or 0
    cached = min(prompt, row.get('cached_tokens') or 0)
    output = row.get('completion_tokens') or 0
    return ((prompt - cached) * price_in + cached * price_cached + output * price_out) / 1e6


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('results', help='results JSONL (outside the repository)')
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--max-cost-per-run', type=float)
    parser.add_argument('--no-worse', default='', help='comma-separated metrics, e.g. rejections,cost')
    parser.add_argument('--seed', type=int, default=BOOTSTRAP_SEED)
    parser.add_argument('--bootstrap', type=int, default=BOOTSTRAP_ITERATIONS)
    parser.add_argument(
        '--prices',
        default=','.join(str(price) for price in PRICES),
        help='input,cached,output USD per million tokens; match the card the bench ran on',
    )
    parser.add_argument('--out', help='write the markdown report here')
    args = parser.parse_args(argv)
    prices = tuple(float(part) for part in str(args.prices).split(','))
    if len(prices) != 3 or any(price < 0 for price in prices):
        raise SystemExit('--prices needs three nonnegative numbers: input,cached,output')
    rows = load_rows(args.results)
    if tuple(prices) != PRICES:
        # One card for everything: the override reprices every stored row so the
        # per-arm table, paired ratios, gates and the split cannot disagree.
        rows = [{**row, 'cost': cost_from_tokens(row, tuple(prices))} for row in rows]
    arms = [arm for arm in per_arm(rows)]
    if args.baseline not in {arm['arm'] for arm in arms}:
        raise SystemExit(f'baseline {args.baseline} not in results')
    ratios = paired_ratios(rows, args.baseline, seed=args.seed, iterations=args.bootstrap)
    split = cost_split(rows, args.baseline, prices)
    no_worse = [m.strip() for m in args.no_worse.split(',') if m.strip()]
    gates = evaluate_gates(arms, ratios, max_cost_per_run=args.max_cost_per_run, no_worse=no_worse)
    markdown = render_markdown(rows, args.baseline, arms, ratios, split, gates)
    if args.out:
        Path(args.out).write_text(markdown + '\n')
    print(markdown)
    return 1 if any(gate['verdict'] == 'FAIL' for gate in gates) else 0


if __name__ == '__main__':
    sys.exit(main())
