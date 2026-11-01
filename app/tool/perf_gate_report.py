#!/usr/bin/env python3
"""Summarize repeated perf runs without turning noisy host milliseconds into gates."""
import argparse
import json
import math
from pathlib import Path
import statistics

SCENARIOS = ('home_scroll', 'detail_scroll', 'memory_scroll', 'chat_tap', 'home_live_scroll', 'episode_page', 'device_page', 'tab_switch')


def summarize(cards, expected_runs):
    errors = []
    if len(cards) != expected_runs:
        errors.append(f'expected {expected_runs} scorecards, found {len(cards)}; partial/stale evidence is invalid')
    for card in cards:
        if card.get('test_failure_count') != 0:
            errors.append(f"test framework failures or missing failure evidence: {card.get('test_failure_count')}")
        if card.get('schema') != 'omi-mobile-perf/v2' or card.get('complete') is not True:
            errors.append('missing or incomplete v2 scorecard')
        if set(card.get('scenarios', {})) != set(SCENARIOS):
            errors.append('scenario coverage differs from the fixed eight-scenario contract')
    rows = []
    for name in SCENARIOS:
        scores = [c.get('scenarios', {}).get(name) for c in cards]
        if not scores or any(not isinstance(s, dict) for s in scores):
            continue
        for score in scores:
            if score.get('gate_violations') != []:
                errors.append(f"{name}: missing/present gate violations: {score.get('gate_violations')}")
        metrics = {}
        for key in scores[0]['work_counts']:
            values = [s['work_counts'][key] for s in scores]
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                errors.append(f'{name}.{key}: non-finite evidence')
                continue
            metrics[key] = {'min': min(values), 'max': max(values), 'mean': statistics.mean(values), 'stddev': statistics.pstdev(values)}
        rows.append({'scenario': name, 'work': metrics,
                     'host_p90_ms': [s['total_ms']['p90'] for s in scores],
                     'phase_shares': {phase: [s['ui_phase_shares'][phase] for s in scores] for phase in scores[0]['ui_phase_shares']}})
    return rows, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--expected-runs', type=int, required=True)
    args = parser.parse_args()
    cards = [json.loads(p.read_text()) for p in sorted(args.directory.glob('scorecard-*.json'))]
    rows, errors = summarize(cards, args.expected_runs)
    status_path = args.directory / 'run-status.json'
    if not status_path.is_file():
        errors.append('missing process exit evidence (run-status.json)')
    else:
        statuses = json.loads(status_path.read_text()).get('runs', [])
        if len(statuses) != args.expected_runs or any(type(run.get('exit_code')) is not int or run['exit_code'] != 0 for run in statuses):
            errors.append('failed or incomplete Flutter processes; measured counts alone are not admission')
    print('SCENARIO             REBUILDS min..max  LAYOUTS min..max  SEMANTICS max  HOST p90 ms (diagnostic)')
    for row in rows:
        work = row['work']
        def span(key):
            return f"{work[key]['min']}..{work[key]['max']}"
        print(f"{row['scenario']:20} {span('rebuilds'):18} {span('layouts'):17} {work['semantics_compiles']['max']:13} " + ', '.join(f'{v:.1f}' for v in row['host_p90_ms']))
    output = args.directory / 'variance.json'
    output.write_text(json.dumps({'runs': len(cards), 'scenarios': rows, 'errors': errors}, indent=2) + '\n')
    print(f'Variance evidence: {output}')
    for error in errors:
        print(f'PERF RED: {error}')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
