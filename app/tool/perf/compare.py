#!/usr/bin/env python3
"""Compare complete device receipts; accepting a baseline is an explicit action."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median


def compare(before, after):
    virtual = before.get('qualified_virtual_baseline') is True
    if before.get('accepted_baseline') is not True and not virtual:
        raise ValueError('reference is not an accepted three-run profile baseline')
    for key in ('dataset', 'frame_policy', 'build_mode', 'timeline_enabled', 'pacing', 'runs'):
        if before.get(key) != after.get(key):
            raise ValueError(f'incomparable {key}')
    if after.get('timeline_enabled') is not False:
        raise ValueError('timeline diagnostics cannot be compared as frame acceptance')
    for key in ('device_id', 'device_os_version', 'platform', 'flutter_revision', 'harness_sha256'):
        if not before.get('identity', {}).get(key) or before['identity'][key] != after.get('identity', {}).get(key):
            raise ValueError(f'incomparable or missing {key}; qualify a new baseline')
    if virtual:
        if after.get('virtual_qualification') is not True:
            raise ValueError('virtual and physical evidence cannot be compared')
        if any(not value['identity'].get('virtual_runtime', {}).get('host') for value in (before, after)):
            raise ValueError('virtual comparison requires host identity; qualify a new baseline')
        for key in ('virtual_runtime', 'launch_protocol'):
            if not before['identity'].get(key) or before['identity'][key] != after['identity'].get(key):
                raise ValueError(f'incomparable virtual {key}')
    elif after.get('virtual_qualification') is True:
        raise ValueError('physical and virtual evidence cannot be compared')
    result = {'before': before['identity'], 'after': after['identity'],
              'current_variance_pass': after.get('variance_pass'), 'scenarios': {}}
    for name, old in before['scenarios'].items():
        new = after['scenarios'][name]
        values = {}
        for metric in ('build_p90_us', 'raster_p90_us', 'total_p90_us'):
            left, right = median(old[metric]), median(new[metric])
            values[metric] = {'before': left, 'after': right,
                              'change_percent': (right / left - 1) * 100 if left else None}
        for metric in ('frames_over_16ms', 'frames_over_100ms'):
            values[metric] = {'before': sum(old[metric]), 'after': sum(new[metric])}
        values['worst_total_us'] = {'before': max(old['worst_total_us']), 'after': max(new['worst_total_us'])}
        result['scenarios'][name] = values
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--accept-baseline', action='store_true')
    args = parser.parse_args()
    summary = json.loads((args.directory / 'summary.json').read_text())
    pointer = args.artifact_root / 'last-accepted-baseline.json'
    baseline = args.baseline
    if baseline is None and pointer.is_file():
        baseline = Path(json.loads(pointer.read_text())['directory'])
    if baseline and summary.get('timeline_enabled') is not True:
        try:
            result = compare(json.loads((baseline / 'summary.json').read_text()), summary)
        except ValueError as error:
            if not args.accept_baseline or summary.get('accepted_baseline') is not True:
                raise
            print(f'Explicitly qualifying a new reference; old batch is incomparable: {error}')
        else:
            result['before_directory'] = str(baseline)
            result['after_directory'] = str(args.directory)
            (args.directory / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
            print(f'Compared against {baseline}')
            for name, metrics in result['scenarios'].items():
                print(name, 'total p90', metrics['total_p90_us'], '>100ms', metrics['frames_over_100ms'])
    elif baseline is None:
        print('No accepted reference yet; use --accept-baseline after reviewing the first qualifying batch.')
    if args.accept_baseline:
        if summary.get('accepted_baseline') is not True:
            raise ValueError('refusing to accept failed variance, incomplete, debug or timeline evidence')
        args.artifact_root.mkdir(parents=True, exist_ok=True)
        if pointer.is_file():
            history = args.artifact_root / 'baseline-history'
            history.mkdir(exist_ok=True)
            (history / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ.json')).write_text(pointer.read_text())
        temporary = pointer.with_suffix('.pending')
        temporary.write_text(json.dumps({'directory': str(args.directory.resolve()),
                             'accepted_at_utc': datetime.now(timezone.utc).isoformat(),
                             'identity': summary['identity']}, indent=2) + '\n')
        temporary.replace(pointer)
        print(f'Accepted baseline pointer: {pointer}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(f'invalid baseline comparison: {error}')
