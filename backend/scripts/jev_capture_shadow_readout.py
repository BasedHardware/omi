#!/usr/bin/env python3
"""Read-only EXP-003 readout from Cloud Logging JSONL exports.

Accepts raw `textPayload` lines, Cloud Logging JSON objects, or the emitted
record objects. No Firestore reads, credentials, or backend imports required.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _record(line: str) -> dict | None:
    try:
        obj = json.loads(line)
    except (TypeError, ValueError):
        obj = None
    if isinstance(obj, dict):
        if obj.get('event'):
            return obj
        payload = obj.get('jsonPayload')
        if isinstance(payload, dict) and payload.get('event'):
            return payload
        line = obj.get('textPayload') or (payload.get('message') if isinstance(payload, dict) else '') or ''
    if isinstance(line, str):
        for marker in ('jev_capture_shadow_outcome ', 'jev_capture_shadow '):
            if marker in line:
                try:
                    return json.loads(line.split(marker, 1)[1])
                except (TypeError, ValueError):
                    return None
    return None


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[math.ceil(fraction * len(ordered)) - 1], 4)


def _upper_false_rate(errors: int, total: int) -> float | None:
    """Exact one-sided 95% binomial upper bound by inversion."""
    if not total:
        return None
    if errors == total:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        cdf = sum(math.comb(total, i) * mid**i * (1 - mid) ** (total - i) for i in range(errors + 1))
        if cdf > 0.05:
            lo = mid
        else:
            hi = mid
    return round(hi, 6)


def _score_buckets(rows: list[dict]) -> dict[str, int]:
    edges = (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.675, 0.725, 0.8, 0.9, 1)
    counts: Counter[str] = Counter()
    for row in rows:
        score = row['p']
        for low, high in zip(edges[:-1], edges[1:]):
            if low <= score < high or high == 1 and score == 1:
                counts[f'{low:g}-{high:g}'] += 1
                break
    return dict(sorted(counts.items()))


def readout(records: list[dict], labels: dict[str, bool] | None = None) -> dict:
    attempts = [row for row in records if row.get('event') == 'jev_capture_shadow']
    decisions = [row for row in attempts if isinstance(row.get('p'), (int, float))]
    outcomes = [row for row in records if row.get('event') == 'jev_capture_shadow_outcome']
    by_decision = defaultdict(list)
    for row in decisions:
        by_decision[row['decision']].append(row)
    counts = Counter((row['decision'], row['category']) for row in attempts)
    attempt_outcomes = Counter((row['decision'], row.get('outcome', 'success')) for row in attempts)
    daily_attempts = Counter(row['timestamp'][:10] for row in attempts if row.get('timestamp'))
    matrix = Counter()
    proxies = Counter()
    for row in decisions:
        if row['decision'] != 'same_scene':
            continue
        rule, jev = row['rule_fold'], row['would_decide']
        matrix[
            (
                row['category'],
                'both_fold' if rule and jev else 'rule_only' if rule else 'jev_only' if jev else 'neither',
            )
        ] += 1
        pair = {row['first_id'], row['second_id']}
        for outcome in outcomes:
            if row['uid'] == outcome['uid'] and pair <= set(outcome['conversation_ids']):
                if outcome['action'] == 'separate' and outcome.get('separated_id') not in pair:
                    continue
                proxies[(outcome['action'], 'would_fold' if jev else 'would_keep')] += 1
    view: dict[str, Any] = {
        'volumes': {f'{d}:{c}': n for (d, c), n in sorted(counts.items())},
        'attempt_outcomes': {f'{d}:{o}': n for (d, o), n in sorted(attempt_outcomes.items())},
        'agreement': {f'{c}:{a}': n for (c, a), n in sorted(matrix.items())},
        'scores': {
            d: {'p50': _quantile([r['p'] for r in rows], 0.5), 'p95': _quantile([r['p'] for r in rows], 0.95)}
            for d, rows in by_decision.items()
        },
        'score_histogram': {d: _score_buckets(rows) for d, rows in by_decision.items()},
        'latency_seconds': {
            d: {
                'p50': _quantile([r['latency_seconds'] for r in rows], 0.5),
                'p95': _quantile([r['latency_seconds'] for r in rows], 0.95),
            }
            for d, rows in by_decision.items()
        },
        'estimated_vendor_cost_usd': round(len(attempts) * 0.00011, 4),
        'daily_estimated_vendor_cost_usd': {
            day: round(count * 0.00011, 4) for day, count in sorted(daily_attempts.items())
        },
        'cost_note': 'Upper estimate from admitted calls and the 2026-09-27 pilot; compare gateway accounting for billed cost.',
        'unavailable_rate': (
            round(sum(row.get('outcome', 'success') != 'success' for row in attempts) / len(attempts), 4)
            if attempts
            else None
        ),
        'p95_end_to_end_seconds': _quantile([row['latency_seconds'] for row in attempts], 0.95),
        'outcome_proxies': {f'{a}:{b}': n for (a, b), n in sorted(proxies.items())},
        'labels': {},
        'verdict': 'pending_prospective_labels',
    }
    if labels:
        same = [r for r in by_decision['same_scene'] if r['id'] in labels]
        proposed = [r for r in same if r['would_decide']]
        false = sum(not labels[r['id']] for r in proposed)
        actual_same = [r for r in same if labels[r['id']]]
        missed = sum(not r['would_decide'] for r in actual_same)
        bound = _upper_false_rate(false, len(proposed))
        view['labels'] = {
            'same_scene_labeled': len(same),
            'proposed_folds_labeled': len(proposed),
            'false_folds': false,
            'false_fold_upper95': bound,
            'missed_true_joins': missed,
            'missed_fold_rate': round(missed / len(actual_same), 4) if actual_same else None,
            'shipped_missed_fold_rate': (
                round(sum(not r['rule_fold'] for r in actual_same) / len(actual_same), 4) if actual_same else None
            ),
        }
        summary = [r for r in by_decision['resummary'] if r['id'] in labels]
        proposed_summary = [r for r in summary if r['would_decide']]
        actual_material = [r for r in summary if labels[r['id']]]
        view['labels']['resummary_labeled'] = len(summary)
        view['labels']['resummary_precision'] = (
            round(sum(labels[r['id']] for r in proposed_summary) / len(proposed_summary), 4)
            if proposed_summary
            else None
        )
        view['labels']['resummary_missed_material'] = sum(not r['would_decide'] for r in actual_material)
        criteria = {
            'false_fold_upper_below_1pct': bound is not None and bound < 0.01,
            'at_least_30_true_joins': len(actual_same) >= 30,
            'missed_fold_improves_on_rule': bool(actual_same) and missed < sum(not r['rule_fold'] for r in actual_same),
            'at_least_50_resummary_labels': len(summary) >= 50,
            'resummary_precision_at_least_90pct': (view['labels']['resummary_precision'] or 0) >= 0.9,
            'p95_within_2_5s': view['p95_end_to_end_seconds'] is not None and view['p95_end_to_end_seconds'] <= 2.5,
            'unavailable_under_5pct': view['unavailable_rate'] is not None and view['unavailable_rate'] < 0.05,
            'estimated_daily_cost_under_2usd': bool(daily_attempts)
            and all(count * 0.00011 < 2 for count in daily_attempts.values()),
        }
        view['criteria'] = criteria
        if all(criteria.values()):
            view['verdict'] = 'candidate_pending_David_summary_quality_and_privacy_review'
        elif false:
            view['verdict'] = 'no_go_false_folds'
    return view


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+', type=Path, help='Cloud Logging JSONL exports')
    parser.add_argument('--labels', type=Path, help='JSONL rows with shadow record id and boolean truth')
    parser.add_argument('--allowlist', default='', help='Comma-separated UIDs to export for prospective review')
    parser.add_argument('--export', type=Path, help='Write identifier-only review rows for the allowlist')
    args = parser.parse_args()
    records = [record for path in args.logs for line in path.read_text().splitlines() if (record := _record(line))]
    labels = None
    if args.labels:
        labels = {}
        for line in args.labels.read_text().splitlines():
            row = json.loads(line)
            if not isinstance(row.get('truth'), bool):
                raise ValueError('labels require a boolean truth field')
            labels[row['id']] = row['truth']
    if args.export:
        allowed = set(args.allowlist.split(',')) - {''}
        with args.export.open('w') as handle:
            for row in records:
                if row.get('event') == 'jev_capture_shadow' and row.get('uid') in allowed:
                    handle.write(json.dumps(row, separators=(',', ':'), sort_keys=True) + '\n')
    print(json.dumps(readout(records, labels), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
