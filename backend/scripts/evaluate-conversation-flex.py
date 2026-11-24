#!/usr/bin/env python3
"""Evaluate blinded, paired offline results for one SCA-4247 experiment arm."""

import argparse
import json
import math
import random
from statistics import fmean

OUTLINE = 'conversation-v3-outline'
REQUIRED_TAGS = {
    OUTLINE: {'short', 'long', 'multilingual', 'late_append', 'overlap', 'open_race', 'foreground'},
    'conv-structure': {'short', 'long', 'multilingual', 'open_race', '429', 'timeout'},
    'memory-l1': {'short', 'long', 'multilingual', 'search_race', 'chat_race', '429', 'timeout'},
    'conversation-v3-summary': {'short', 'long', 'multilingual', 'open_race', '429', 'timeout'},
}


def boundary_f1(expected, actual):
    expected, actual = set(expected), set(actual)
    return 2 * len(expected & actual) / (len(expected) + len(actual)) if expected or actual else 1.0


def paired_lower_bound(differences):
    rng = random.Random(4247)
    estimates = sorted(fmean(rng.choices(differences, k=len(differences))) for _ in range(4_000))
    return estimates[100]


def percentile(values, fraction):
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def cache_usage(results):
    inputs = hits = writes = 0
    for result in results:
        usage = result['usage']
        details = usage['prompt_tokens_details']
        inputs += usage['prompt_tokens']
        hits += details['cached_tokens']
        writes += details['cache_write_tokens']
    return {'input_tokens': inputs, 'cached_tokens': hits, 'write_tokens': writes, 'hit_share': hits / inputs}


def evaluate(rows, lane):
    rows = [row for row in rows if row['lane'] == lane]
    if len(rows) < 300 or len({row['id'] for row in rows}) != len(rows):
        raise ValueError('at least 300 unique approved pairs per experiment are required')
    missing = REQUIRED_TAGS[lane] - {tag for row in rows for tag in row['tags']}
    if missing:
        raise ValueError(f'missing required strata {sorted(missing)}')

    baseline = [row['baseline'] for row in rows]
    candidate = [row['candidate'] for row in rows]
    violations = sum(
        result['critical_errors']
        + result['duplicate_publications']
        + result['missed_promotions']
        + result['due_extractions_pending']
        + int(not result['deadline_met'])
        + int(result['model'] != before['model'])
        + int(not result['schema_ok'])
        for before, result in zip(baseline, candidate)
    )

    scores = {'grounding': [int(b['grounded']) - int(a['grounded']) for a, b in zip(baseline, candidate)]}
    foreground_latency = {}
    if lane == OUTLINE:
        scores['title'] = [int(b['title_ok']) - int(a['title_ok']) for a, b in zip(baseline, candidate)]
        scores['boundary'] = [
            boundary_f1(row['expected_boundaries'], b['boundaries'])
            - boundary_f1(row['expected_boundaries'], a['boundaries'])
            for row, a, b in zip(rows, baseline, candidate)
        ]
        foreground = [row for row in rows if 'foreground' in row['tags']]
        for name, fraction in [('p95', 0.95), ('p99', 0.99)]:
            foreground_latency[name] = {
                arm: percentile([row[arm]['foreground_ms'] for row in foreground], fraction)
                for arm in ('baseline', 'candidate')
            }

    lower_bounds = {name: paired_lower_bound(values) for name, values in scores.items()}
    report = {
        'pairs': len(rows),
        'violations': violations,
        'paired_95ci_lower': lower_bounds,
        'foreground_ms': foreground_latency,
        'cache': {arm: cache_usage(results) for arm, results in [('baseline', baseline), ('candidate', candidate)]},
        'pass': not violations
        and all(value >= -0.01 for value in lower_bounds.values())
        and all(v['candidate'] <= v['baseline'] for v in foreground_latency.values()),
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lane', choices=REQUIRED_TAGS)
    parser.add_argument('pairs', type=argparse.FileType('r'), help='JSONL of approved or synthetic case receipts')
    args = parser.parse_args()
    try:
        report = evaluate([json.loads(line) for line in args.pairs if line.strip()], args.lane)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
