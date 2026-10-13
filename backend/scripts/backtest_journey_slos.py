#!/usr/bin/env python3
"""Read-only, bounded production SLO receipt; run under gcp-agent-env ro-prod.

Uses only explicit-context kubectl get --raw. No provisioning or log payloads.
"""

import argparse
import json
import math
import re
import subprocess
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

MONITORING = Path(__file__).resolve().parents[1] / 'charts/monitoring'
CONTEXT = 'gke_based-hardware_us-central1_prod-omi-gke'
API = '/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/'
# Bad and valid selectors for the alert SLIs. WINDOW is replaced per range.
SLIS = {
    'live': (
        'sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome="no_transcript"}[WINDOW]))',
        'sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[WINDOW]))',
        'omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}',
    ),
    'chat': (
        'sum(increase(omi_journey_terminal_total{job="cloud-run-application-metrics",journey="chat_response",outcome=~"failure|stale"}[WINDOW]))',
        'sum(increase(omi_journey_accepted_total{job="cloud-run-application-metrics",journey="chat_response"}[WINDOW]))',
        'omi_journey_accepted_total{job="cloud-run-application-metrics",journey="chat_response"}',
    ),
    'pusher': (
        'sum(increase(omi_journey_terminal_total{job="pusher-metrics",journey="pusher_session",outcome=~"failure|cancelled"}[WINDOW]))',
        'sum(increase(omi_journey_terminal_total{job="pusher-metrics",journey="pusher_session"}[WINDOW]))',
        'omi_journey_terminal_total{job="pusher-metrics",journey="pusher_session"}',
    ),
}
OBJECTIVES = {'live': 0.921, 'chat': 0.994, 'pusher': 0.989}


def query(expression, **params):
    endpoint = 'query_range' if 'start' in params else 'query'
    url = API + endpoint + '?' + urllib.parse.urlencode(dict(query=expression, **params))
    last_error = None
    for attempt in range(4):
        try:
            payload = subprocess.check_output(
                ['kubectl', '--context', CONTEXT, 'get', '--raw', url], stderr=subprocess.STDOUT
            )
            break
        except subprocess.CalledProcessError as error:
            last_error = error
            time.sleep(15)
    else:
        detail = (last_error.output or b'').decode('utf-8', 'replace').split('query=', 1)[0][:240]
        raise RuntimeError(f'Prometheus request failed after retries: {detail}') from last_error
    result = json.loads(payload)
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


def synthetic_expression(rule, rate, outage_minutes=10, ending='cancelled'):
    """Substitute aggregate event counts into the exact rule expression.

    Ten minutes of the steady rate are the outage. ``cancelled`` turns those
    minutes into bad terminals (failure|cancelled for pusher). ``no_terminal``
    leaves them in flight, so they never enter a terminal ratio. Chat counts
    only failure|stale, so either ending contributes zero bad chat events.
    """

    def replace(match):
        metric, labels, window = match.groups()
        minutes = int(window[:-1]) * {'m': 1, 'h': 60, 'd': 1440}[window[-1]]
        total = rate * minutes
        outage = rate * min(minutes, outage_minutes)
        if 'outcome=~"failure|cancelled"' in labels:
            value = outage if ending == 'cancelled' else 0
        elif 'outcome=~"failure|stale"' in labels:
            value = 0
        elif metric == 'omi_journey_accepted_total':
            value = total
        elif 'outcome="no_transcript"' in labels:
            value = outage
        elif 'outcome="success"' in labels or 'outcome="transcribed"' in labels:
            value = total - outage
        elif ending == 'no_terminal' and metric == 'omi_journey_terminal_total':
            value = total - outage
        else:
            value = total
        return f'vector({value:.12g})'

    return re.sub(r'sum\(increase\((\w+)\{([^}]+)\}\[(\d+[mhd])\]\)\)', replace, rule['data'][0]['model']['expr'])


def _shares(bad_template, valid_template, start, end, step, window):
    bad_rows = _aligned(query(bad_template.replace('WINDOW', window), start=start, end=end, step=step))
    valid_rows = _aligned(query(valid_template.replace('WINDOW', window), start=start, end=end, step=step))
    rows = []
    for (timestamp, bad), (other, valid) in zip(bad_rows, valid_rows):
        if timestamp != other or not valid:
            raise RuntimeError('bad and valid windows did not align')
        rows.append(dict(end_utc=utc(timestamp), bad_events=bad, valid_events=valid, share=bad / valid))
    return rows


def _aligned(result):
    totals = {}
    for series in result:
        for timestamp, value in series['values']:
            totals[int(timestamp)] = totals.get(int(timestamp), 0.0) + float(value)
    return sorted(totals.items())


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
                'Pusher bad share counts terminal failure and cancelled only. In-flight sessions are outside that ratio.',
                'Chat bad share counts failure and stale terminals. Accepted work with no such terminal is not a miss.',
                'No Grafana pending history, notification policy or causal incident proof was read.',
            ],
            baselines={},
            rules={},
        )
        for journey, (bad_template, valid_template, presence_selector) in SLIS.items():
            bad_query = bad_template.replace('WINDOW', '10d')
            valid_query = valid_template.replace('WINDOW', '10d')
            bad = float(query(bad_query, time=end)[0]['value'][1])
            valid = float(query(valid_query, time=end)[0]['value'][1])
            presence = query(f'sum({presence_selector})', start=start, end=end, step=3600)
            daily = _shares(bad_template, valid_template, end - 9 * 86400, end, 86400, '1d')
            rolling = _shares(bad_template, valid_template, end - 7 * 86400, end, 3600, '3d')
            worst = max(rolling, key=lambda row: row['share'])
            evidence['baselines'][journey] = dict(
                bad_query=bad_query,
                valid_query=valid_query,
                good_query=f'({valid_query}) - ({bad_query})',
                bad_events=bad,
                good_events=valid - bad,
                valid_events=valid,
                success_fraction=(valid - bad) / valid,
                bad_share=bad / valid,
                objective=OBJECTIVES[journey],
                worst_3d=worst,
                worst_3d_error_budget_fraction=worst['share'] / (1 - OBJECTIVES[journey]),
                daily=daily,
                hourly_presence_samples=len(presence[0]['values']),
            )
            print(journey, (valid - bad) / valid, 'worst3d', worst['share'], flush=True)
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
        target = float(rule['annotations']['slo_target'])
        if not math.isclose(target, OBJECTIVES[journey]):
            raise SystemExit(f'{journey} objective {target} != {OBJECTIVES[journey]}')
        rate = evidence['baselines'][journey]['valid_events'] / 14400
        for ending in ('cancelled', 'no_terminal'):
            expr = synthetic_expression(rule, rate, ending=ending)
            value = float(query(expr, time=end)[0]['value'][1])
            # In-flight pusher work and every chat success gap stay at 0.
            # A pusher cancelled burst is bad terminal share and can page.
            if journey == 'chat' or ending == 'no_terminal':
                assert value == 0, (journey, ending, value)
            else:
                assert value > 0, (journey, ending, value)
            evidence['synthetic_cases'][f'{journey}_{ending}_10m'] = dict(
                uid=rule['uid'],
                events_per_minute=rate,
                outage_minutes=10,
                ending=ending,
                expression=expr,
                value=value,
            )
    rule = next(r for r in rules if r['uid'] == 'omi-slo-live-signal-dead')
    expr = vanished_expression(rule)
    value = float(query(expr, time=end)[0]['value'][1])
    assert value > 0
    evidence['synthetic_cases']['live_both_families_vanished'] = dict(uid=rule['uid'], expression=expr, value=value)
    receipt_path.write_text(json.dumps(evidence, indent=2) + '\n')
    print('receipt written', receipt_path, flush=True)


if __name__ == '__main__':
    main()
