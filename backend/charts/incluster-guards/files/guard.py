"""One bounded in-cluster safety reading. Stdlib only; no cloud identity or payload IO."""

import concurrent.futures
import copy
import datetime as dt
import hashlib
import json
import math
import logging
import os
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from omi_logging import configure_logging

configure_logging('incluster-guards', default_format='json')

LATENCY = {
    'type': 'External',
    'external': {'metric': {'name': 'parakeet_request_latency_p99'}, 'target': {'type': 'Value', 'value': '3'}},
}
WINDOW = 900
BLIND_LIMIT = 3
REFUSAL_GATE_VERSION = 'same-hour-of-week-12-pod-v2'
REFUSAL_ABSOLUTE_CEILING = 0.02
FIRST_P95_FLOOR = 30
FIRST_P95_BASELINE_FACTOR = 1.2
FIRST_P95_MIN_SLOW_TEXTS = 4
FIRST_P95_BASELINE_MIN_COUNT = 20
FAST_SCALE_UP = {
    'stabilizationWindowSeconds': 0,
    'selectPolicy': 'Max',
    'policies': [{'type': 'Pods', 'value': 4, 'periodSeconds': 15}],
}


def refusal_baseline_queries(namespace):
    """The same rolling UTC hour a week ago; never learn from the trial itself."""

    def inc(outcome):
        return (
            'sum(increase(omi_stt_window_admissions_total'
            '{job="backend-listen-metrics",outcome' + outcome + '}[1h] offset 7d))'
        )

    accepted = inc('="accepted"')
    refused = inc('=~"overflow|batch_pressure"')
    total = f'({accepted}) + ({refused} or ({accepted} * 0))'
    name = namespace.removesuffix('-backend') + '-parakeet'
    ready = 'kube_deployment_status_replicas_available{namespace="' + namespace + '",deployment="' + name + '"}'
    admissions = 'omi_stt_window_admissions_total{job="backend-listen-metrics",outcome="accepted"}'
    targets = 'up{job="backend-listen-metrics"}'
    listeners = (
        'kube_deployment_status_replicas_available{namespace="'
        + namespace
        + '",deployment=~"'
        + namespace.removesuffix('-backend')
        + '-backend-listen(-.*)?"}'
    )
    # Count against the independent deployment inventory so a target missing from
    # both up and admissions cannot disappear from the completeness check.
    coverage = (
        f'(min({targets}) == bool 1) * (count({targets}) == bool sum({listeners}))'
        f' * ((count({targets} unless on(job,instance) {admissions}) or vector(0)) == bool 0)'
        f' * ((count({admissions} unless on(job,instance) {targets}) or vector(0)) == bool 0)'
    )

    def stale(metric):
        # A one-minute subquery checks freshness throughout the historical hour.
        # Fill absent points so gaps cannot silently qualify as a 12-pod baseline.
        return f'max_over_time((max(time() - timestamp({metric})) or vector(1000000000))[1h:1m] offset 7d)'

    return {
        'refusal_baseline_fraction': f'({refused} or ({accepted} * 0)) / ({total})',
        'refusal_baseline_count': total,
        'refusal_baseline_ready_min': f'min(min_over_time({ready}[1h] offset 7d))',
        'refusal_baseline_ready_max': f'max(max_over_time({ready}[1h] offset 7d))',
        'refusal_baseline_ready_stale': stale(ready),
        'refusal_baseline_admission_stale': stale(admissions),
        'refusal_baseline_coverage': f'min_over_time((({coverage}) or vector(0))[1h:1m] offset 7d)',
        'refusal_baseline_target_stale': stale(targets),
        'refusal_baseline_listener_stale': stale(listeners),
    }


def refusal_limit(values):
    """The same-hour-of-week relative limit, or None when that baseline is unqualified.

    None is not a limit: evaluate substitutes REFUSAL_ABSOLUTE_CEILING rather
    than blinding, so a coverage series younger than the 7d offset cannot roll
    the floor back on blindness alone (2026-10-24 16:05Z, blind_runs=4).
    """
    if not all(finite(values.get(k)) for k in refusal_baseline_queries('unused')):
        return None
    if not 0 <= values['refusal_baseline_fraction'] <= 1 or values['refusal_baseline_count'] < 20:
        return None
    if values['refusal_baseline_ready_min'] != 12 or values['refusal_baseline_ready_max'] != 12:
        return None
    if values['refusal_baseline_coverage'] != 1:
        return None
    if any(
        not 0 <= values[k] <= 120
        for k in (
            'refusal_baseline_ready_stale',
            'refusal_baseline_admission_stale',
            'refusal_baseline_target_stale',
            'refusal_baseline_listener_stale',
        )
    ):
        return None
    return max(REFUSAL_ABSOLUTE_CEILING, values['refusal_baseline_fraction'] * 1.25 + 0.005)


def first_p95_limit(values):
    """The 30s floor, or 1.2x the same rolling UTC hour a week ago when that baseline is qualified.

    The weekly baseline is used only when its own hour carried at least 20 first
    texts; a sparse historical hour (one 60s observation prices its p95 near 59s)
    would otherwise lift the threshold to ~71s and mask a live regression. An
    unavailable or unqualified baseline is the documented fallback (floor plus
    the slow-text gate in evaluate), never blindness: a missing weekly series
    must not itself roll the floor back.
    """
    baseline = values.get('first_p95_baseline')
    if (
        finite(baseline)
        and finite(values.get('first_count_baseline'))
        and values['first_count_baseline'] >= (FIRST_P95_BASELINE_MIN_COUNT)
    ):
        return max(FIRST_P95_FLOOR, FIRST_P95_BASELINE_FACTOR * baseline)
    return FIRST_P95_FLOOR


def queries(namespace):
    # Ported from P77 guard_fast.py, including its job and exported_endpoint selectors.
    sel = '{job="backend-listen-metrics"}'

    def inc(metric, labels=sel):
        return f'sum(increase({metric}{labels}[15m]))'

    accepted = inc('omi_stt_window_admissions_total', '{job="backend-listen-metrics",outcome="accepted"}')
    refused = inc(
        'omi_stt_window_admissions_total', '{job="backend-listen-metrics",outcome=~"overflow|batch_pressure"}'
    )
    gpu = '{namespace="' + namespace + '",container="parakeet"}'
    v2 = '{namespace="' + namespace + '",exported_endpoint="v2_transcribe"}'
    return {
        **refusal_baseline_queries(namespace),
        'first_p95': f'histogram_quantile(0.95,sum by(le)(rate(omi_stt_window_first_text_seconds_bucket{sel}[15m])))',
        # Same rolling UTC hour a week ago: a 15-minute window carries only ~40
        # first texts, so two slow sessions alone can push its p95 past 60s.
        'first_p95_baseline': (
            'histogram_quantile(0.95,sum by(le)(rate(omi_stt_window_first_text_seconds_bucket' f'{sel}[1h] offset 7d)))'
        ),
        'first_count_baseline': f'sum(increase(omi_stt_window_first_text_seconds_count{sel}[1h] offset 7d))',
        'first_count': inc('omi_stt_window_first_text_seconds_count'),
        'first_over30': inc('omi_stt_window_first_text_seconds_count')
        + ' - '
        + inc('omi_stt_window_first_text_seconds_bucket', '{job="backend-listen-metrics",le="30.0"}'),
        'post_p95': f'histogram_quantile(0.95,sum by(le)(rate(omi_stt_window_post_seconds_bucket{sel}[15m])))',
        'v2_p95': f'histogram_quantile(0.95,sum by(le)(rate(parakeet_request_duration_seconds_bucket{v2}[15m])))',
        'refusal_fraction': f'({refused} or ({accepted} * 0)) / (({accepted}) + ({refused} or ({accepted} * 0)))',
        'admission_count': f'({accepted}) + ({refused} or ({accepted} * 0))',
        'dcgm_nonzero': f'max(max_over_time(DCGM_FI_DEV_GPU_UTIL{gpu}[15m]))',
        'first_stale': f'max(time()-timestamp(omi_stt_window_first_text_seconds_count{sel}))',
        'post_stale': f'max(time()-timestamp(omi_stt_window_post_seconds_count{sel}))',
        'admission_stale': 'max(time()-timestamp(omi_stt_window_admissions_total{job="backend-listen-metrics",outcome="accepted"}))',
        'dcgm_stale': f'max(time()-timestamp(DCGM_FI_DEV_GPU_UTIL{gpu}))',
        'v2_stale': f'max(time()-timestamp(parakeet_request_duration_seconds_count{v2}))',
        'no_text_deadline': inc(
            'omi_stt_window_session_outcome_total',
            '{job="backend-listen-metrics",outcome="no_text",reason="first_text_deadline"}',
        ),
    }


def workload_only(spec):
    return spec.get('minReplicas') in (5, 8) and not any(
        m.get('external', {}).get('metric', {}).get('name') == 'parakeet_request_latency_p99'
        for m in spec.get('metrics', [])
    )


def build_rollback(old):
    """Exact step_fast.build(old, 12, rollback=True) patch and drift assertions."""
    assert old['maxReplicas'] == 12, 'Unexpected cap'
    metrics = old['metrics']
    names = [m.get('pods', m.get('external', {})).get('metric', {}).get('name') for m in metrics]
    assert set(names) <= {
        'parakeet_active_requests_total',
        'parakeet_gpu_utilization',
        'parakeet_request_latency_p99',
    }, 'Unexpected metrics'
    assert len(names) == len(set(names)) and set(names) >= {
        'parakeet_active_requests_total',
        'parakeet_gpu_utilization',
    }, 'Missing/duplicate metric'
    assert next(
        m for m in metrics if m.get('pods', {}).get('metric', {}).get('name') == 'parakeet_active_requests_total'
    )['pods']['target'] == {'type': 'AverageValue', 'averageValue': '2'}, 'Requests drift'
    assert next(
        m for m in metrics if m.get('external', {}).get('metric', {}).get('name') == 'parakeet_gpu_utilization'
    )['external']['target'] == {'type': 'Value', 'value': '35'}, 'GPU drift'
    # Kubernetes defaults selectPolicy=Max on stored objects; Helm may omit it.
    up = {'selectPolicy': 'Max', **old['behavior']['scaleUp']}
    legacy_up = {
        'stabilizationWindowSeconds': 0,
        'selectPolicy': 'Max',
        'policies': [{'type': 'Pods', 'value': 1, 'periodSeconds': 60}],
    }
    assert up in (legacy_up, FAST_SCALE_UP), 'Scale-up drift'
    assert old['behavior']['scaleDown']['stabilizationWindowSeconds'] == 900, 'Down drift'
    restored = [
        m for m in metrics if m.get('external', {}).get('metric', {}).get('name') != 'parakeet_request_latency_p99'
    ]
    restored.append(copy.deepcopy(LATENCY))
    return [
        {'op': 'test', 'path': '/spec', 'value': copy.deepcopy(old)},
        {'op': 'replace', 'path': '/spec/minReplicas', 'value': 12},
        {'op': 'replace', 'path': '/spec/metrics', 'value': restored},
    ]


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def evaluate(values):
    counts_known = all(finite(values.get(k)) for k in ('first_count', 'admission_count'))
    low = counts_known and (values['first_count'] < 20 or values['admission_count'] < 20)
    stale_keys = ('first_stale', 'post_stale', 'admission_stale', 'dcgm_stale', 'v2_stale')
    fresh = all(finite(values.get(k)) and 0 <= values[k] <= 120 for k in stale_keys)
    # Prometheus returns NaN for idle histogram/ratio arithmetic. Fresh low counts
    # distinguish that expected lack of samples from a missing series/query error
    # (None). It remains LOW_SAMPLE, never CLEAN, without rolling back quiet hours.
    idle_nan = {'first_p95', 'post_p95', 'v2_p95', 'refusal_fraction'} if low and fresh else set()
    # The weekly first_p95 evidence (quantile + its sample count) is optional
    # (retention, metric age, sparse hour): its absence selects the fallback
    # threshold instead of blinding the whole reading. The weekly refusal
    # baseline is optional the same way: missing or unqualified selects the
    # absolute refusal ceiling below, never blindness.
    optional_weekly = ('first_p95_baseline', 'first_count_baseline', *refusal_baseline_queries('unused'))
    blind = [
        f'missing_or_nonfinite_{k}'
        for k in queries('unused')
        if k not in optional_weekly
        and not finite(values.get(k))
        and not (k in idle_nan and isinstance(values.get(k), float) and math.isnan(values[k]))
    ]
    blind += [k for k in stale_keys if finite(values.get(k)) and (values[k] > 120 or values[k] < 0)]
    if finite(values.get('dcgm_nonzero')) and values['dcgm_nonzero'] <= 0 and not low:
        blind.append('dcgm_no_real_nonzero_value')
    trips = []
    refusal_threshold = refusal_limit(values)
    refusal_mode = 'relative'
    if refusal_threshold is None:
        # An unqualified weekly baseline (coverage series younger than its 7d
        # offset, sparse hour, missing series) left this guard BLIND on every
        # run and rolled floor 8 back with zero refusals. Fail closed on the
        # absolute ceiling instead; missing or stale CURRENT refusal data
        # still blinds via the keys above.
        refusal_threshold = REFUSAL_ABSOLUTE_CEILING
        refusal_mode = 'absolute_fallback'
    if not low:
        trips += [k for k, limit in [('post_p95', 3), ('v2_p95', 3)] if finite(values.get(k)) and values[k] >= limit]
        # A 15-minute p95 over ~35-45 first texts is small-sample noise: one or
        # two slow sessions drove floor-10 rollbacks at 04:08Z/06:19Z while the
        # floor-10 fleet beat floor 12. Trip only with several slow texts AND a
        # p95 worse than both the floor and the same UTC hour a week ago.
        if (
            finite(values.get('first_p95'))
            and finite(values.get('first_over30'))
            and values['first_over30'] >= FIRST_P95_MIN_SLOW_TEXTS
            and values['first_p95'] >= first_p95_limit(values)
        ):
            trips.append('first_p95')
        if (
            refusal_threshold is not None
            and finite(values.get('refusal_fraction'))
            and values['refusal_fraction'] >= refusal_threshold
        ):
            trips.append('refusal_fraction')
    trips += [
        k
        for k, limit in [('first_over30', 12), ('no_text_deadline', 36)]
        if finite(values.get(k)) and values[k] > limit
    ]
    return {
        'trips': trips,
        'blind': blind,
        'low_sample': low,
        'refusal_threshold': refusal_threshold,
        'refusal_mode': refusal_mode,
        'first_p95_threshold': first_p95_limit(values),
    }


def scheduling_failures(events, name, now):
    failed = []
    for event in events:
        obj = event.get('involvedObject', {})
        if event.get('reason') != 'FailedScheduling' or not obj.get('name', '').startswith(name + '-'):
            continue
        if obj.get('kind') != 'Pod':
            continue
        timestamp = (
            event.get('series', {}).get('lastObservedTime')
            or event.get('lastTimestamp')
            or event.get('eventTime')
            or event.get('metadata', {}).get('creationTimestamp')
        )
        if not timestamp:
            raise ValueError('scheduling_event_timestamp_missing')
        if dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp() >= now - WINDOW:
            failed.append('FailedScheduling_in_15m')
    return failed


def advance(state, identity, now, blind):
    """Persist the observed state's clock and consecutive blind count across Jobs."""
    if state.get('identity') != identity:
        state = {'identity': identity, 'since': now, 'blind': 0}
    return {
        'identity': identity,
        'since': state['since'],
        'blind': state.get('blind', 0) + 1 if blind else 0,
        'last_read': now,
    }


def decide(hpa, deployment, events, values, state, now):
    reading = evaluate(values)
    if not workload_only(hpa['spec']):
        return 'NOOP', {}, reading
    # HPA configuration/generation and image changes invalidate the lookback.
    # Deployment generation also changes on ordinary HPA replica writes; using
    # it here would keep a scaling or unschedulable workload in perpetual warmup.
    identity = hashlib.sha256(
        json.dumps(
            [
                REFUSAL_GATE_VERSION,
                hpa['spec'],
                hpa['metadata'].get('generation'),
                [c['image'] for c in deployment['spec']['template']['spec']['containers']],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    reading['trips'] += scheduling_failures(events, hpa['metadata']['name'], now)
    if not any(
        c['type'] == 'ScalingActive' and c['status'] == 'True' for c in hpa.get('status', {}).get('conditions', [])
    ):
        reading['trips'].append('HPA_not_ScalingActive')
    desired = hpa.get('status', {}).get('desiredReplicas')
    if desired is None:
        reading['blind'].append('desired_replicas_missing')
    elif deployment.get('status', {}).get('readyReplicas', 0) < desired:
        reading['trips'].append('ready_shortfall')
    state = advance(state, identity, now, bool(reading['blind']))
    if now - state['since'] < WINDOW:
        verdict = 'WARMUP'
    elif reading['trips'] or state['blind'] >= BLIND_LIMIT:
        verdict = 'TRIP'
    elif reading['blind']:
        verdict = 'BLIND'
    else:
        verdict = 'LOW_SAMPLE' if reading['low_sample'] else 'CLEAN'
    return verdict, state, reading


def batch_queries(namespace):
    sel = '{namespace="' + namespace + '"}'
    return {
        'oldest_age': f'max(omi_batch_pipeline_oldest_age_seconds{sel})',
        'retry_age': f'max(omi_batch_pipeline_retry_age_seconds{sel})',
        'freshness': f'max(time() - omi_batch_pipeline_metrics_refreshed_at_seconds{sel})',
        'scrape_age': f'max(time() - timestamp(omi_batch_pipeline_metrics_refreshed_at_seconds{sel}))',
    }


def evaluate_batch(values):
    # No invented projection/custody/speech metrics: worker queue age is a proxy only.
    unknown = ['new_projection_obligations_unavailable', 'audio_custody_unavailable', 'proven_speech_loss_unavailable']
    blind = any(not finite(values.get(k)) for k in batch_queries('unused'))
    blind = blind or values.get('freshness', 0) > 120 or values.get('scrape_age', 0) > 120
    trips = [] if blind else (['uncommitted_job_age_over_30m'] if values['oldest_age'] > 1800 else [])
    return {
        'verdict': 'TRIP' if trips else 'BLIND' if blind else 'PARTIAL',
        'trips': trips,
        'unknown': unknown,
        'metrics_blind': blind,
    }


class Client:
    def __init__(self, prometheus, namespace, name, state_name):
        self.prometheus = prometheus
        self.base = (
            'https://' + os.environ['KUBERNETES_SERVICE_HOST'] + ':' + os.environ.get('KUBERNETES_SERVICE_PORT', '443')
        )
        self.namespace, self.name, self.state_name = namespace, name, state_name
        self.sa = Path('/var/run/secrets/kubernetes.io/serviceaccount')
        self.context = ssl.create_default_context(cafile=str(self.sa / 'ca.crt'))

    def kube(self, path, patch=None):
        headers = {'Authorization': 'Bearer ' + (self.sa / 'token').read_text().strip()}
        if patch is not None:
            headers['Content-Type'] = 'application/json-patch+json'
        req = urllib.request.Request(
            self.base + path,
            data=None if patch is None else json.dumps(patch).encode(),
            headers=headers,
            method='GET' if patch is None else 'PATCH',
        )
        with urllib.request.urlopen(req, context=self.context, timeout=10) as response:
            return json.load(response)

    def path(self, resource):
        prefix = (
            '/apis/autoscaling/v2' if resource == 'hpa' else '/apis/apps/v1' if resource == 'deployment' else '/api/v1'
        )
        suffix = {
            'hpa': 'horizontalpodautoscalers/' + self.name,
            'deployment': 'deployments/' + self.name,
            'state': 'configmaps/' + self.state_name,
            'events': 'events',
        }[resource]
        return prefix + '/namespaces/' + self.namespace + '/' + suffix

    def sample(self, expressions):
        def one(item):
            key, expr = item
            try:
                url = self.prometheus + '/api/v1/query?' + urllib.parse.urlencode({'query': expr})
                with urllib.request.urlopen(url, timeout=10) as response:
                    data = json.load(response)
                if data['status'] != 'success' or data.get('warnings'):
                    raise ValueError('query_incomplete')
                rows = data['data']['result']
                if len(rows) != 1:
                    return key, None
                stamp, value = rows[0]['value']
                return key, float(value) if abs(time.time() - float(stamp)) <= 120 else None
            except Exception:
                return key, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            return dict(pool.map(one, expressions.items()))


def log(event, **fields):
    # Metrics/booleans only; never workload env, event messages or HTTP response bodies.
    def safe(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {k: safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [safe(v) for v in value]
        return value

    severity = logging.ERROR if fields.get('verdict') in {'TRIP', 'BLIND'} or event.endswith('error') else logging.INFO
    logging.getLogger('incluster-guards').log(
        severity, json.dumps(safe({'event': event, **fields}), allow_nan=False, sort_keys=True)
    )


def run(client, dry_run, now=None):
    now = time.time() if now is None else now
    cm = client.kube(client.path('state'))
    state = json.loads(cm.get('data', {}).get('state', '{}'))
    # Batch evaluation is independent of a missing dev HPA or Parakeet data failure.
    batch_values = client.sample(batch_queries(client.namespace))
    batch = evaluate_batch(batch_values)
    log('batch_safety', **batch, values=batch_values, cloud_run_rollback='disabled')
    hpa = None
    values = {}
    try:
        hpa = client.kube(client.path('hpa'))
        values = client.sample(queries(client.namespace))
        if workload_only(hpa['spec']):
            deployment = client.kube(client.path('deployment'))
            events = client.kube(client.path('events'))['items']
            verdict, state, reading = decide(hpa, deployment, events, values, state, now)
        else:
            verdict, state, reading = 'NOOP', {}, evaluate(values)
    except Exception as exc:
        # No exact observed spec => no rollback; failed Job still alerts.
        log('parakeet_read_error', error=type(exc).__name__)
        verdict, reading = 'BLIND', {'trips': [], 'blind': ['kubernetes_read_unavailable']}
    log(
        'parakeet_guard',
        verdict=verdict,
        reading=reading,
        values=values,
        floor=hpa['spec'].get('minReplicas') if hpa else None,
        blind_runs=state.get('blind', 0),
        dry_run=dry_run,
    )
    # Record evidence before attempting rollback; optimistic concurrency protects the persisted counter.
    data = {
        'state': json.dumps(state, sort_keys=True),
        'parakeet-verdict': verdict,
        'batch-verdict': batch['verdict'],
        'last-observed-at': str(now),
        'batch-trips': ','.join(batch['trips']),
    }
    client.kube(
        client.path('state'),
        [
            {'op': 'test', 'path': '/metadata/resourceVersion', 'value': cm['metadata']['resourceVersion']},
            {'op': 'add', 'path': '/data', 'value': data},
            {
                'op': 'add',
                'path': '/metadata/annotations',
                'value': {
                    'omi.me/batch-safety-verdict': batch['verdict'],
                    'omi.me/parakeet-guard-verdict': verdict,
                },
            },
        ],
    )
    if verdict == 'TRIP':
        patch = build_rollback(hpa['spec'])  # Drift refuses loudly, including in dry-run.
        if not dry_run:
            client.kube(client.path('hpa'), patch)
        log('parakeet_rollback', result='dry_run' if dry_run else 'applied')
    return 1 if verdict in {'TRIP', 'BLIND'} or batch['verdict'] in {'TRIP', 'BLIND'} else 0


def main():
    if sys.argv[1:] == ['--batch']:
        from batch_guard import main as batch_main

        return batch_main()
    client = Client(
        os.environ['PROMETHEUS_URL'], os.environ['NAMESPACE'], os.environ['HPA_NAME'], os.environ['STATE_NAME']
    )
    try:
        return run(client, os.environ.get('DRY_RUN', 'false').lower() == 'true')
    except Exception as exc:
        log(
            'guard_error', error=type(exc).__name__, drift=str(exc) if isinstance(exc, AssertionError) else None
        )  # Avoid leaking HTTP bodies or workload objects.
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
