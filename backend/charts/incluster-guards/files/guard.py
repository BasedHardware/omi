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
ROLLBACK_REPLICAS = 12
FIRST_P95_FLOOR = 30
FIRST_P95_BASELINE_FACTOR = 1.2
FIRST_P95_MIN_SLOW_TEXTS = 5
FIRST_P95_BASELINE_MIN_COUNT = 20
FIRST_P95_MIN_COUNT = 100
FIRST_P95_BASELINE_COUNT_SHARE = 0.5
# The weekly baseline counts one hour; the live sample counts WINDOW seconds.
WINDOW_SHARE_OF_BASELINE = WINDOW / 3600
# live_metrics.py buckets end at (2, 5, 10, 15, 20, 25, 30, 45, 60): a quantile
# that lands beyond the last finite bucket is reported as exactly this
# boundary, not measured.
FIRST_P95_TOP_BUCKET = 60.0
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


def first_p95_sample_floor(values):
    """max(100, half the weekly same-hour rate); 100 when that baseline is unavailable.

    first_count_baseline counts a whole hour; first_count counts the live
    15-minute window. Convert the baseline to its per-window equivalent
    (x 15/60) before halving, or the floor would always demand roughly twice
    the historical window rate and a real regression at normal volume could
    never collect a decisive sample (review r1 P1).
    """
    baseline = values.get('first_count_baseline')
    if finite(baseline):
        return max(FIRST_P95_MIN_COUNT, FIRST_P95_BASELINE_COUNT_SHARE * WINDOW_SHARE_OF_BASELINE * baseline)
    return FIRST_P95_MIN_COUNT


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
    # Every workload-only floor below the rollback cap is armed; the floor is
    # read from the HPA itself. The old (5, 8) enumeration read NOOP at the
    # 10-23 baseline floor 10 (2026-10-25 11:29Z), leaving the fleet unguarded
    # whenever the operator moved the floor off the enumerated pair.
    return spec.get('minReplicas') < ROLLBACK_REPLICAS and not any(
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
        {'op': 'replace', 'path': '/spec/minReplicas', 'value': ROLLBACK_REPLICAS},
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
    unmeasured = []
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
        # 2026-10-25 05:40Z (floor 8) and 2026-10-24 06:19Z: 26-37 first texts
        # pushed the 95th percentile into the 60s top bucket and rolled the
        # floor back on an unmeasured p95 while the fleet was healthy. Trip only
        # on a value interpolated inside the histogram (the top-bucket boundary
        # 60.0 is saturation, not a measurement), several slow texts, and a
        # 15-minute sample of at least max(100, half the weekly same-hour
        # count). A regression-shaped reading below that sample floor is
        # unmeasured evidence: BLIND alert, never rollback, never counted
        # toward the three-blind-strike rollback.
        if finite(values.get('first_p95')) and values['first_p95'] >= first_p95_limit(values):
            if (
                values['first_p95'] < FIRST_P95_TOP_BUCKET
                and finite(values.get('first_over30'))
                and values['first_over30'] >= FIRST_P95_MIN_SLOW_TEXTS
                and finite(values.get('first_count'))
                and values['first_count'] >= first_p95_sample_floor(values)
            ):
                trips.append('first_p95')
            else:
                unmeasured.append('first_p95')
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
        'unmeasured': unmeasured,
        'low_sample': low,
        'refusal_threshold': refusal_threshold,
        'refusal_mode': refusal_mode,
        'first_p95_threshold': first_p95_limit(values),
        'first_p95_sample_floor': first_p95_sample_floor(values),
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


def state_identity(hpa, deployment):
    """Arming identity: the whole HPA spec except the floor, plus serving images.

    HPA configuration and image changes invalidate the lookback, but scheduled
    floor changes do not: the floor schedule rewrites spec.minReplicas hourly,
    which also bumps the HPA generation, so both minReplicas and the generation
    counter are excluded and arming survives every scheduled change. Deployment
    generation also changes on ordinary HPA replica writes; using it here would
    keep a scaling or unschedulable workload in perpetual warmup.
    """
    spec_identity = {k: v for k, v in hpa['spec'].items() if k != 'minReplicas'}
    return hashlib.sha256(
        json.dumps(
            [
                REFUSAL_GATE_VERSION,
                spec_identity,
                [c['image'] for c in deployment['spec']['template']['spec']['containers']],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def decide(hpa, deployment, events, values, state, now):
    reading = evaluate(values)
    identity = state_identity(hpa, deployment)
    if not workload_only(hpa['spec']):
        # Keep advancing the arming clock while parked above the rollback cap
        # (or rolled back): a scheduled drop onto this spec must land on an
        # already-armed guard, never a fresh 15-minute warmup during which a
        # demand spike could not roll the floor back (review r1 P1). The floor
        # itself is excluded from the identity, so this elapsed time counts.
        # advance() rebuilds its dict, so the rolled-back clean streak must be
        # carried explicitly - same identity only; a spec change restarts it
        # (review r3 P1: without the carry the streak reset on every run and
        # the rollback could never expire).
        advanced = advance(state, identity, now, False)
        if state.get('identity') == identity and 'rollback' in state:
            advanced['rollback'] = state['rollback']
        return 'NOOP', advanced, reading
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
    elif reading['blind'] or reading['unmeasured']:
        # unmeasured (thin-sample first_p95) alerts like blind but never
        # accumulates: advance() counts only reading['blind'], so a thin
        # sample cannot reach the three-strike rollback.
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


def rolled_back(spec):
    return any(
        m.get('external', {}).get('metric', {}).get('name') == 'parakeet_request_latency_p99'
        for m in spec.get('metrics', [])
    )


def build_rollback_clear(spec):
    """The inverse rollback: restore workload-only metrics, keep the current floor.

    The floor stays at ROLLBACK_REPLICAS; the time-of-day schedule and the
    arming/usable gates own any later reduction. Drift-refuses exactly like
    build_rollback through the whole-spec test patch.
    """
    restored = [
        m
        for m in spec['metrics']
        if m.get('external', {}).get('metric', {}).get('name') != 'parakeet_request_latency_p99'
    ]
    return [
        {'op': 'test', 'path': '/spec', 'value': copy.deepcopy(spec)},
        {'op': 'replace', 'path': '/spec/metrics', 'value': restored},
    ]


def advance_rollback_state(state, is_rolled_back, reading, now):
    """Track the rolled-back clock; return True when the rollback may expire.

    A rollback expires only after one full lookback window of consecutive
    usable, clean readings while rolled back (2026-10-25 21:06Z: the 13:50Z
    rollback kept the floor schedule deferred every hour with a healthy
    fleet, and no in-band clear existed). Any trip, blind, unmeasured or
    low-sample reading restarts the clean streak.
    """
    if not is_rolled_back:
        state.pop('rollback', None)
        return False
    entry = state.get('rollback') or {}
    since = entry.get('since', now)
    clean = (
        not reading.get('trips')
        and not reading.get('blind')
        and not reading.get('unmeasured')
        and not reading.get('low_sample')
    )
    clean_since = now if clean and entry.get('clean_since') is None else (entry['clean_since'] if clean else None)
    state['rollback'] = {'since': since, 'clean_since': clean_since}
    return clean_since is not None and now - clean_since >= WINDOW and now - since >= WINDOW


def load_floor_schedule():
    """The reviewed 24-entry UTC-hour floor table, or None when not installed.

    The chart renders /guard/floors.json only when floorSchedule.enabled; its
    absence is the schedule's off switch, so development and any release that
    does not opt in never write the floor from a schedule.
    """
    try:
        rows = json.loads(open('/guard/floors.json').read())
    except (OSError, ValueError):
        return None
    if not isinstance(rows, list) or len(rows) != 24:
        return None
    if any(not isinstance(v, int) or not 1 <= v <= 12 for v in rows):
        return None
    return rows


def apply_floor_schedule(client, hpa, deployment, state, reading, schedule, now, dry_run):
    """One bounded scheduled-floor write per hourly change; never fights the guard.

    Deferred whenever the guard has rolled back (the latency metric is present):
    the reviewed schedule resumes only after an operator clears the rollback.
    A LOWER requires the guard to be armed under the current spec identity AND
    the current reading to be usable - not blind, and not carrying an
    unmeasured regression-shaped first_p95. Dropping onto a fresh warmup would
    leave a spike unable to roll back (review r1 P1); dropping while the guard
    cannot even measure would leave capacity reduced until three post-drop
    blind runs accumulate (review r2 P1). Raises apply immediately - more
    capacity is the safe direction. The whole observed /spec is JSON-patch
    tested, so a concurrent change fails this run loudly instead of
    overwriting.
    """
    spec = hpa['spec']
    hour = dt.datetime.fromtimestamp(now, dt.timezone.utc).hour
    target = schedule[hour]
    current = spec.get('minReplicas')
    if rolled_back(spec):
        log('floor_schedule', result='deferred_guard_rollback', hour=hour, target=target, floor=current)
        return
    if current == target:
        return
    if not isinstance(spec.get('maxReplicas'), int) or target > spec['maxReplicas']:
        log('floor_schedule', result='refused_target_above_cap', hour=hour, target=target, floor=current)
        return
    if dry_run:
        log('floor_schedule', result='dry_run', hour=hour, target=target, floor=current)
        return
    if target < current:
        if state.get('identity') != state_identity(hpa, deployment) or now - state.get('since', now) < WINDOW:
            log('floor_schedule', result='deferred_guard_not_armed', hour=hour, target=target, floor=current)
            return
        if reading.get('blind') or reading.get('unmeasured'):
            log('floor_schedule', result='deferred_guard_blind', hour=hour, target=target, floor=current)
            return
    client.kube(
        client.path('hpa'),
        [
            {'op': 'test', 'path': '/spec', 'value': copy.deepcopy(spec)},
            {'op': 'replace', 'path': '/spec/minReplicas', 'value': target},
        ],
    )
    log('floor_schedule', result='applied', hour=hour, target=target, floor=current)


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
    schedule = None
    try:
        hpa = client.kube(client.path('hpa'))
        values = client.sample(queries(client.namespace))
        schedule = load_floor_schedule()
        # With a schedule installed, even a parked (non-workload) HPA runs the
        # full decide pass so the arming clock advances and the scheduled change
        # is evaluated against an armed guard; without one, the historical
        # minimal NOOP path (no deployment/events reads) is preserved.
        if workload_only(hpa['spec']) or schedule is not None:
            deployment = client.kube(client.path('deployment'))
            events = client.kube(client.path('events'))['items']
            verdict, state, reading = decide(hpa, deployment, events, values, state, now)
        else:
            # Preserve the loaded state: the rolled-back clock must survive
            # parked readings, not reset on every one of them.
            verdict, reading = 'NOOP', evaluate(values)
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
    # Rollback expiry bookkeeping rides the same persisted state: a rolled-back
    # HPA that has been clean for one full lookback window clears itself, so a
    # rolled-back fleet cannot keep the floor schedule deferred forever with no
    # in-band clear path (2026-10-25 21:06Z). Any unusable reading restarts it.
    rollback_expires = False
    if hpa is not None and verdict != 'BLIND':
        rollback_expires = advance_rollback_state(state, rolled_back(hpa['spec']), reading, now)
    elif hpa is not None and state.get('rollback'):
        # An unreadable section never counts as clean: keep the clock, restart
        # the clean streak.
        state['rollback']['clean_since'] = None
    # With no HPA read at all, leave any bookkeeping; the next readable run
    # reconciles it.
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
                    **cm.get('metadata', {}).get('annotations', {}),
                    'helm.sh/resource-policy': 'keep',
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
    elif rollback_expires and hpa is not None:
        clear = build_rollback_clear(hpa['spec'])
        if not dry_run:
            client.kube(client.path('hpa'), clear)
        log('parakeet_rollback_expired', result='dry_run' if dry_run else 'applied')
    elif hpa is not None and verdict != 'BLIND' and schedule is not None:
        # Scheduled floor changes are ordinary operation, not a safety action:
        # they run after the reading (never in the same run as a rollback) and
        # apply_floor_schedule defers while a guard rollback is in force or the
        # guard is not yet armed for a lower.
        try:
            apply_floor_schedule(client, hpa, deployment, state, reading, schedule, now, dry_run)
        except Exception as exc:
            log('floor_schedule_error', error=type(exc).__name__)
            return 2
    # The batch observer is isolated evidence: its trips/unknowns never fail
    # the Job or block the Parakeet schedule (2026-10-25 21:06Z ruling); only
    # the Parakeet section owns the exit code.
    return 1 if verdict in {'TRIP', 'BLIND'} else 0


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
