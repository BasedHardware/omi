# LIFECYCLE: permanent
"""Read-only hard-three observer using the existing paged metadata collector.

No marker, manifest pin, worker/image pin, controller epoch, or prod write.
Run in a NEW process after lead acceptance; never patch a live observer.
The output is aggregate evidence, not authorization to change production.
"""

import argparse
import datetime as dt
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import batch_quality_gate as batch_guard


def collect(sampler_path, since, percent, marker_free_root):
    sys.path.insert(0, str(sampler_path.resolve().parent))
    spec = importlib.util.spec_from_file_location('hard3_paged_collector', sampler_path)
    sampler = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = sampler
    spec.loader.exec_module(sampler)
    # paged_sample.ROOT is used after import only for the optional t2-window
    # read. A fresh task-owned directory has no such file. Module dependencies
    # were loaded from their original paths; no sealed/live bytes are changed.
    # Reject any manual marker in this directory instead of reading it.
    if (marker_free_root / 't2-window.json').exists():
        raise ValueError('manual_marker_not_supported')
    sampler.ROOT = marker_free_root
    return sampler.sample(since, percent)


def write_record(out, record):
    out.mkdir(parents=True, exist_ok=True)
    temporary = out / 'watch-latest.tmp'
    temporary.write_text(json.dumps(record, sort_keys=True) + '\n')
    temporary.replace(out / 'watch-latest.json')
    with (out / 'watch-samples.jsonl').open('a') as stream:
        stream.write(json.dumps(record, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--sampler', type=Path, required=True, help='installed read-only paged_sample.py collector')
    parser.add_argument('--since', required=True, help='real observation start, UTC ISO; not an arming permit')
    parser.add_argument('--percent', type=int, required=True, choices=range(101))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GCP_AGENT_TIER') != 'ro-prod':
        parser.error('ro-prod required')
    since = batch_guard.epoch(args.since)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    if not 0 <= since <= now:
        parser.error('observation start must be real and not future')
    args.out.mkdir(parents=True, exist_ok=True)
    marker_free_root = args.out / 'collector-without-markers'
    marker_free_root.mkdir(exist_ok=True)
    try:
        sample = collect(args.sampler, args.since, args.percent, marker_free_root)
        at = dt.datetime.now(dt.timezone.utc).isoformat()
        record = batch_guard.observer_record(sample, at)
        # All historical sampled units remain in hard-three scope. No marker
        # can exclude custody or turn missing evidence into zero.
        record['observation_since'] = args.since
        record['collector_scope'] = 'all_admitted_in_observation_window'
        # Identity is provenance and alerting only, never a seal or a re-arm.
        record['collector_sha256'] = hashlib.sha256(args.sampler.read_bytes()).hexdigest()
        record['serving_fingerprint'] = hashlib.sha256(
            json.dumps(
                [
                    (r.get('service'), r.get('revision'), r.get('image'), r.get('traffic'))
                    for r in sample.get('serving', [])
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if any(str(row.get('percent')) != str(args.percent) for row in sample.get('serving', [])):
            record['alerts'].append('serving_percent_drift')
        try:
            prior = json.loads((args.out / 'watch-latest.json').read_text())
        except (OSError, ValueError):
            prior = {}
        record = batch_guard.observed_clock(record, prior)
        for key, alert in (
            ('collector_sha256', 'observer_source_changed'),
            ('serving_fingerprint', 'serving_revision_changed_requalify'),
        ):
            if prior.get(key) and prior[key] != record[key]:
                record['alerts'].append(alert)
    except Exception as error:
        record = dict(
            at=dt.datetime.now(dt.timezone.utc).isoformat(),
            verdict='BLIND',
            reasons=['sample_unavailable'],
            alerts=[],
            hard3=dict(T1='UNKNOWN', T2='UNKNOWN', T4='UNKNOWN'),
            read_error_class=type(error).__name__,
            policy=batch_guard.POLICY,
            observation_since=args.since,
        )
    write_record(args.out, record)
    print(json.dumps(record, sort_keys=True))
    return 0 if record['verdict'] == 'CLEAN' and set(record['hard3'].values()) == {'CLEAN'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
