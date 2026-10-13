#!/usr/bin/env python3
"""Read-only, bounded production SLO receipt; run under gcp-agent-env ro-prod.

Uses only explicit-context kubectl get --raw. No provisioning or log payloads.
"""

import argparse
import json
import re
import subprocess
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

MONITORING = Path(__file__).resolve().parents[1] / 'charts/monitoring'
CONTEXT = 'gke_based-hardware_us-central1_prod-omi-gke'
API = '/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/'
SCOPES = {
    'live': ('omi_live_session_transcript_outcome_total', 'job="backend-listen-metrics"', 'transcribed'),
    'chat': ('omi_journey_terminal_total', 'job="cloud-run-application-metrics",journey="chat_response"', 'success'),
    'pusher': ('omi_journey_terminal_total', 'job="pusher-metrics",journey="pusher_session"', 'success'),
}


def query(expression, **params):
    endpoint = 'query_range' if 'start' in params else 'query'
    url = API + endpoint + '?' + urllib.parse.urlencode(dict(query=expression, **params))
    result = json.loads(subprocess.check_output(['kubectl', '--context', CONTEXT, 'get', '--raw', url]))
    if result['status'] != 'success' or result.get('warnings'):
        raise RuntimeError('Prometheus query failed or returned warnings')
    return result['data']['result']


def utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def pending_seconds(duration):
    match = re.fullmatch(r'(\d+)([smh])', duration)
    if match is None:
        raise ValueError(duration)
    count, unit = match.groups()
    return int(count) * {'s': 1, 'm': 60, 'h': 3600}[unit]


def intervals(samples, pending=0, cutoff=0):
    result = []
    start = last = None
    for timestamp, value in sorted(samples.items()):
        if timestamp < cutoff:
            continue
        if value > 0:
            if last is None or timestamp - last > 300:
                start = timestamp
            if timestamp - start >= pending:
                if result and last == timestamp - 300 and result[-1]['last_true_sample'] == utc(last):
                    result[-1]['last_true_sample'] = utc(timestamp)
                else:
                    result.append({'start': utc(timestamp), 'last_true_sample': utc(timestamp)})
            last = timestamp
        else:
            start = last = None
    return result


def synthetic_expression(rule, rate, outage_minutes=10):
    """Substitute aggregate event counts into the exact deployed expression.

    A steady baseline is followed by ten minutes of accepted work with zero
    successes. Cancellation and never-terminal scenarios share those counts.
    """

    def replace(match):
        metric, labels, window = match.groups()
        minutes = int(window[:-1]) * {'m': 1, 'h': 60, 'd': 1440}[window[-1]]
        accepted = rate * minutes
        failed = rate * min(minutes, outage_minutes)
        if metric == 'omi_journey_accepted_total':
            value = accepted
        elif 'outcome="success"' in labels or 'outcome="transcribed"' in labels:
            value = accepted - failed
        elif 'outcome="no_transcript"' in labels:
            value = failed
        else:
            value = accepted
        return f'vector({value:.12g})'

    return re.sub(r'sum\(increase\((\w+)\{([^}]+)\}\[(\d+[mhd])\]\)\)', replace, rule['data'][0]['model']['expr'])


def vanished_expression(rule):
    """Both metric families absent, while the scrape endpoint can remain up."""
    expr = re.sub(r'absent\([^)]*\)', 'vector(1)', rule['data'][0]['model']['expr'])
    return re.sub(r'sum\(increase\([^)]*\)\)', 'vector(0)', expr)


def main():
    # Pin a single endpoint so every rule and baseline uses the same ten days.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end-unix', type=int, help='Pin a receipt endpoint for a reproducible retry')
    parser.add_argument('--only', action='append', default=[], help='Refresh these UIDs inside the existing receipt')
    args = parser.parse_args()
    receipt_path = MONITORING / 'slo-backtest.prod.json'
    only = set(args.only)
    if only:
        evidence = json.loads(receipt_path.read_text())
        end = args.end_unix or evidence['end_unix']
        if end != evidence['end_unix']:
            raise SystemExit('pinned end does not match the receipt')
        start = end - 864000
    else:
        end = args.end_unix or int(time.time() // 300 * 300)
        start = end - 864000
        evidence = dict(
            measurement_start_utc=utc(start),
            measurement_end_utc=utc(end),
            end_unix=end,
            context=CONTEXT,
            identity_tier='ro-prod',
            api=API + 'query_range',
            step_seconds=300,
            chunk_seconds=86400,
            expected_samples=2881,
            limitations=[
                'Five-minute sampled conditions can miss shorter intervals; these are not delivered notifications.',
                'Oldest retained samples lack full windows; conservative post-warmup intervals reported separately.',
                'Accepted and successful terminals can straddle window boundaries; unmatched accepted work is conservatively bad.',
                'No Grafana pending history, notification policy or causal incident proof was read.',
            ],
            baselines={},
            rules={},
        )
        for journey, (metric, scope, outcome) in SCOPES.items():
            good = f'sum(increase({metric}{{{scope},outcome="{outcome}"}}[10d]))'
            valid_selector = (
                f'{metric}{{{scope},outcome=~"transcribed|no_transcript"}}'
                if journey == 'live'
                else f'omi_journey_accepted_total{{{scope}}}'
            )
            valid = f'sum(increase({valid_selector}[10d]))'
            g = float(query(good, time=end)[0]['value'][1])
            v = float(query(valid, time=end)[0]['value'][1])
            presence = query(f'sum({valid_selector})', start=start, end=end, step=3600)
            evidence['baselines'][journey] = dict(
                good_query=good,
                valid_query=valid,
                good_events=g,
                valid_events=v,
                success_fraction=g / v,
                hourly_presence_samples=len(presence[0]['values']),
            )
            print(journey, g / v, flush=True)
    rules = json.loads((MONITORING / 'alerts/journey-slos.json').read_text())
    selected = [rule['uid'] for rule in rules]
    unknown = only - set(selected)
    if unknown:
        raise SystemExit(f'unknown rule uid: {sorted(unknown)}')
    for rule in rules:
        if only and rule['uid'] not in only:
            continue
        expr = rule['data'][0]['model']['expr']
        samples = {}
        for chunk in range(start, end, 86400):
            result = query(expr, start=chunk, end=min(chunk + 86400, end), step=300)
            for series in result:
                for t, value in series['values']:
                    samples[int(t)] = float(value)
        warmup = 259200 if rule['uid'].endswith('warning') else 21600
        pending = pending_seconds(rule['for'])
        if rule['uid'].endswith('signal-dead'):
            warmup = 3600
        evidence['rules'][rule['uid']] = dict(
            expression=expr,
            **{'for': rule['for']},
            evaluated_samples=len(samples),
            true_condition_samples=sum(v > 0 for v in samples.values()),
            sampled_firing_intervals=intervals(samples, pending),
            post_warmup_firing_intervals=intervals(samples, pending, start + warmup),
            full_window_results_from_utc=utc(start + warmup),
        )
        print(rule['uid'], evidence['rules'][rule['uid']]['true_condition_samples'], flush=True)
        receipt_path.write_text(json.dumps(evidence, indent=2) + '\n')
    evidence['synthetic_cases'] = {}
    for journey in ('chat', 'pusher'):
        rule = next(r for r in rules if r['uid'] == f'omi-slo-{journey}-critical')
        rate = evidence['baselines'][journey]['valid_events'] / 14400
        expr = synthetic_expression(rule, rate)
        value = float(query(expr, time=end)[0]['value'][1])
        assert value > 0, (journey, value)
        for ending in ('cancelled', 'no_terminal'):
            evidence['synthetic_cases'][f'{journey}_{ending}_10m'] = dict(
                uid=rule['uid'],
                accepted_per_minute=rate,
                outage_minutes=10,
                expression=expr,
                value=value,
            )
    rule = next(r for r in rules if r['uid'] == 'omi-slo-live-signal-dead')
    expr = vanished_expression(rule)
    value = float(query(expr, time=end)[0]['value'][1])
    assert value > 0
    evidence['synthetic_cases']['live_both_families_vanished'] = dict(uid=rule['uid'], expression=expr, value=value)
    receipt_path.write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    main()
