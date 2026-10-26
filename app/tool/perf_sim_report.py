#!/usr/bin/env python3
"""Validate heavy-account receipts and export timelines for Dart DevTools.

Variance = (max-min)/min: the slowest p90 must be within 15% of the fastest.
Debug simulator results are diagnostic only, even when variance is green.
"""

import argparse
from collections import Counter
import json
import math
import re
from pathlib import Path

SCENARIOS = (
    "cold_start", "scroll_conversations", "open_conversation",
    "tab_switch", "wal_sync_bg_fg",
)
METRICS = (
    "build_p50_us", "build_p90_us", "build_p99_us",
    "raster_p50_us", "raster_p90_us", "raster_p99_us",
    "total_p50_us", "total_p90_us", "total_p99_us",
    "frames_over_16ms", "frames_over_32ms", "frames_over_100ms",
    "worst_build_us", "worst_raster_us", "worst_total_us", "frame_count",
)
P90_METRICS = ("build_p90_us", "raster_p90_us", "total_p90_us")
HEAVY_DATASET = {'conversations': 2000, 'detail_segments': 120, 'wals': 6500,
                 'wal_files': 6500, 'people': 40, 'task_items': 50}


def validate(report):
    if report.get("schema") != "omi-mobile-perf-sim/v2" or report.get("complete") is not True:
        raise ValueError("incomplete or unknown heavy-profile report")
    if report.get('frame_policy') != 'framework-requested/v1':
        raise ValueError('framework-requested frame policy is required')
    idle = report.get('idle_preflight_frames')
    if type(idle) is not int or not 0 <= idle <= 3:
        raise ValueError('missing or failed idle-frame preflight')
    if (report.get('pacing') != 'fixed-real-time/v1' or report.get('foreground_before_measurement') is not True
            or report.get('native_foreground_before_measurement') is not True):
        raise ValueError('fixed pacing and foreground qualification are required')
    if not isinstance(report.get('timeline_enabled'), bool):
        raise ValueError('timeline recording mode is required')
    if report.get("storage_isolated") is not True:
        raise ValueError("fixture storage isolation is required")
    if report.get("build_mode") not in ("debug", "profile"):
        raise ValueError("unknown build mode")
    if set(report.get("scenarios", {})) != set(SCENARIOS):
        raise ValueError("missing or unexpected scenarios")
    if report.get('scenario_order') != list(SCENARIOS):
        raise ValueError('missing or unexpected scenario order')
    if report["scenarios"]["cold_start"].get("restored_from_cache") is not True:
        raise ValueError("heavy conversations were not restored")
    for scenario in SCENARIOS:
        metrics = report["scenarios"][scenario]
        for name in METRICS:
            value = metrics.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{scenario}.{name}: missing/invalid metric")
        if metrics["frame_count"] <= 0:
            raise ValueError(f"{scenario}: no engine frames")
        bounds = [metrics.get('start_vm_us'), metrics.get('end_vm_us')]
        if any(type(value) is not int for value in bounds) or not 0 < bounds[0] < bounds[1]:
            raise ValueError(f'{scenario}: missing monotonic measurement bounds')
    return report


def spread(values):
    floor = min(values)
    return (max(values) - floor) / floor if floor > 0 else (0 if max(values) == 0 else math.inf)


def summarize(directory, expected_runs):
    paths = sorted(p for p in directory.glob("receipt-*.json") if p.stem.removeprefix('receipt-').isdigit())
    if expected_runs < 1 or len(paths) != expected_runs:
        raise ValueError(f"need exactly {expected_runs} receipts; found {len(paths)}")
    reports = []
    cpu_rankings = []
    identities = []
    for path in paths:
        raw = json.loads(path.read_text())
        identity = raw.get('heavy_run')
        if not identity or not all(identity.get(key) for key in ('source_sha', 'binary_sha256', 'harness_sha256',
                                                               'device_id', 'platform', 'flutter_revision', 'device_os_version')):
            raise ValueError(f'{path.name}: missing build identity')
        if not isinstance(identity['device_os_version'], str) or not identity['device_os_version'].strip():
            raise ValueError(f'{path.name}: missing runtime device OS version')
        identities.append(identity)
        reports.append(validate(raw.get("heavy_profile", {})))
        if identity['platform'] == 'ios' and reports[-1]['build_mode'] == 'profile':
            preservation_path = directory / f'{path.stem}-preservation.json'
            if not preservation_path.is_file():
                raise ValueError(f'{path.name}: missing DEV sandbox preservation proof')
            preservation = json.loads(preservation_path.read_text())
            if preservation != {'verified': True, 'bundle_id': 'com.friend-app-with-wearable.ios12.development'}:
                raise ValueError(f'{path.name}: failed DEV sandbox preservation proof')
        capture = raw.get('heavy_timeline_capture', {})
        expected_timeline = f'{path.stem}-timeline.json'
        if reports[-1].get('timeline_enabled') is True:
            if (capture.get('enabled') is not True or capture.get('file') != expected_timeline
                    or capture.get('truncated') is not False or capture.get('events', 0) <= 0
                    or not (directory / expected_timeline).is_file()):
                raise ValueError(f'{path.name}: missing or truncated streamed timeline')
            timeline = json.loads((directory / expected_timeline).read_text())
            boundaries = {(event.get('name'), event.get('ph')) for event in timeline.get('traceEvents', [])}
            if not all((f'heavy.{scenario}', phase) in boundaries for scenario in SCENARIOS for phase in ('b', 'e')):
                raise ValueError(f'{path.name}: streamed timeline lost scenario boundaries')
        elif capture.get('enabled') is not False:
            raise ValueError(f'{path.name}: timeline mode disagrees with receipt')
        cpu = raw.get('heavy_cpu_samples')
        if cpu:
            (directory / f'{path.stem}-cpu.json').write_text(json.dumps(cpu))
            functions = cpu.get('functions', [])
            leaves = Counter(sample['stack'][0] for sample in cpu.get('samples', []) if sample.get('stack'))
            ranking = []
            for index, ticks in leaves.most_common(20):
                function = functions[index]
                ranking.append({'function': (function.get('function') or {}).get('name'),
                                'source': function.get('resolvedUrl'), 'exclusive_samples': ticks})
            cpu_rankings.append({'receipt': path.name, 'sample_count': cpu.get('sampleCount'),
                                 'top_exclusive_functions': ranking})
    first = reports[0]
    if any(identity != identities[0] for identity in identities[1:]):
        raise ValueError('receipts disagree on source/binary/harness identity')
    for report in reports[1:]:
        for key in ("dataset", "build_mode", "scenario_order", "acceptance_eligible", "timeline_enabled", "pacing"):
            if report.get(key) != first.get(key):
                raise ValueError(f"receipts disagree on {key}")
    failures = []
    print(f"heavy-account: {len(paths)} runs, {first['build_mode']}, dataset={first.get('dataset')}")
    for scenario in SCENARIOS:
        print(scenario)
        for metric in METRICS:
            values = [r["scenarios"][scenario][metric] for r in reports]
            suffix = ""
            if metric in P90_METRICS:
                relative = spread(values)
                suffix = f" spread={relative:.1%}"
                if relative > 0.15:
                    failures.append(f"{scenario}.{metric} {relative:.1%}")
            print(f"  {metric}: {values}{suffix}")
    heavy_shape = all(first.get('dataset', {}).get(key) == value for key, value in HEAVY_DATASET.items())
    if expected_runs < 3 and first.get('timeline_enabled') is not True:
        raise ValueError('baseline needs at least 3 runs; only opt-in timeline diagnostics permit fewer')
    eligible = heavy_shape and first.get('timeline_enabled') is False and all(r.get("acceptance_eligible") is True and r["build_mode"] == "profile" for r in reports)
    virtual = first.get('virtual_qualification') is True
    if any(report.get('virtual_qualification', False) != virtual for report in reports):
        raise ValueError('receipts disagree on virtual qualification')
    if virtual:
        runtime = identities[0].get('virtual_runtime', {})
        protocol = identities[0].get('launch_protocol', {})
        warmups = protocol.get('warmup_runs')
        if (runtime.get('kind') not in ('android-emulator', 'ios-simulator')
                or not runtime.get('runtime_build') or type(warmups) is not int or not 1 <= warmups <= 3
                or protocol.get('measured_runs') != expected_runs or protocol.get('outlier_policy') != 'retain-all'):
            raise ValueError('virtual qualification requires pinned runtime and retained warmup protocol')
        kind = runtime['kind']
        expected_platform, expected_mode = ('android', 'profile') if kind == 'android-emulator' else ('ios', 'debug')
        if identities[0]['platform'] != expected_platform or first['build_mode'] != expected_mode:
            raise ValueError('virtual runtime kind does not match platform/build mode')
        host = runtime.get('host', {})
        if (not isinstance(host, dict) or not re.fullmatch(r'[a-f0-9]{64}', str(host.get('node_sha256', '')))
                or not host.get('platform') or not host.get('architecture')
                or type(host.get('logical_cpus')) is not int or host['logical_cpus'] <= 0):
            raise ValueError('virtual qualification requires host identity')
        if protocol.get('host_load_policy') != 'load1-per-logical-cpu<=1/v1':
            raise ValueError('virtual qualification requires fixed host load admission')
        for prefix, count in (('warmup', warmups), ('receipt', expected_runs)):
            for index in range(1, count + 1):
                host = json.loads((directory / f'{prefix}-{index}-host-load.json').read_text())
                samples = host.get('samples', [])
                if (host.get('policy') != protocol['host_load_policy'] or host.get('passed') is not True
                        or host.get('command_exit_code') != 0 or len(samples) < 2
                        or samples[0].get('phase') != 'before' or samples[-1].get('phase') != 'after'
                        or any(type(s.get('logical_cpus')) is not int or s['logical_cpus'] <= 0
                               or not math.isfinite(s['load_1_5_15m'][0])
                               or not 0 <= s['load_1_5_15m'][0] <= s['logical_cpus'] for s in samples)):
                    raise ValueError('host overload or missing launch load evidence invalidates entire batch')
        if expected_platform == 'android' and identities[0].get('native_harness') != {
                'package': 'com.friend.ios.dev', 'firebase_auto_initializer_absent': True}:
            raise ValueError('missing native heavy APK admission')
        for index in range(1, warmups + 1):
            warmup = json.loads((directory / f'warmup-{index}.json').read_text())
            warmup_report = validate(warmup.get('heavy_profile', {}))
            if warmup.get('heavy_run') != identities[0]:
                raise ValueError('warmup differs from measured source/binary/runtime/protocol')
            for key in ('dataset', 'build_mode', 'scenario_order', 'timeline_enabled', 'pacing', 'virtual_qualification'):
                if warmup_report.get(key) != first.get(key):
                    raise ValueError(f'warmup differs from measured {key}')
        eligible = False
    summary = {
        "runs": len(paths), "build_mode": first["build_mode"],
        "identity": identities[0],
        "dataset": first['dataset'], "frame_policy": first['frame_policy'],
        "pacing": first['pacing'], "timeline_enabled": first['timeline_enabled'],
        "scenarios": {scenario: {metric: [r['scenarios'][scenario][metric] for r in reports]
                                for metric in METRICS} for scenario in SCENARIOS},
        "variance_pass": not failures, "variance_failures": failures,
        "acceptance_eligible": eligible,
        "accepted_baseline": eligible and not failures,
        "virtual_qualification": virtual,
        "qualified_virtual_baseline": (virtual and heavy_shape and not failures and expected_runs >= 3
                                       and first['build_mode'] == 'profile' and not first['timeline_enabled']),
        "heavy_dataset": heavy_shape,
        "cpu_rankings": cpu_rankings,
        "over_100ms": sum(r["scenarios"][s]["frames_over_100ms"] for r in reports for s in SCENARIOS),
    }
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("VARIANCE:", "FAIL" if failures else "PASS")
    if virtual:
        print('VIRTUAL QUALIFICATION:', 'PASS' if summary['qualified_virtual_baseline'] else 'FAIL/DIAGNOSTIC')
    print("ACCEPTANCE:", "PASS" if eligible and not failures else
          "FAIL — p90 variance" if eligible else "NOT ELIGIBLE — debug/ablation/timeline diagnostics")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-runs", type=int, default=3)
    args = parser.parse_args()
    try:
        summary = summarize(args.directory, args.expected_runs)
    except (ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"invalid benchmark: {error}\n")
    return 0 if summary["variance_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
