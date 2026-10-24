"""Hermetic safety decisions and the real single-run write path, with explicit API fakes."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
import subprocess
import sys
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / 'backend/charts/incluster-guards'
FIXTURES = Path(__file__).parent / 'fixtures/incluster_guards'
spec = importlib.util.spec_from_file_location('incluster_guard', CHART / 'files/guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def values():
    result = dict.fromkeys(guard.queries('prod-omi-backend'), 0.0)
    result.update(
        first_p95=20,
        first_over30=4,
        post_p95=0.5,
        v2_p95=1,
        first_count=30,
        admission_count=100,
        dcgm_nonzero=1,
        refusal_baseline_count=100,
        refusal_baseline_ready_min=12,
        refusal_baseline_ready_max=12,
        refusal_baseline_coverage=1,
    )
    return result


def objects():
    old = json.loads((FIXTURES / 'hpa_spec.json').read_text())
    old['minReplicas'] = 5
    old['metrics'] = [
        m
        for m in old['metrics']
        if m.get('external', {}).get('metric', {}).get('name') != 'parakeet_request_latency_p99'
    ]
    return (
        {
            'metadata': {'name': 'prod-omi-parakeet', 'generation': 2},
            'spec': old,
            'status': {'desiredReplicas': 5, 'conditions': [{'type': 'ScalingActive', 'status': 'True'}]},
        },
        {
            'metadata': {'generation': 1},
            'spec': {'template': {'spec': {'containers': [{'image': 'frozen:sha'}]}}},
            'status': {'readyReplicas': 5},
        },
    )


@pytest.mark.parametrize(
    'key,limit,inclusive',
    [
        ('first_p95', 30, True),
        ('post_p95', 3, True),
        ('v2_p95', 3, True),
        ('refusal_fraction', 0.02, True),
        ('first_over30', 12, False),
        ('no_text_deadline', 36, False),
    ],
)
@pytest.mark.parametrize('delta', [-0.00001, 0, 0.00001])
def test_threshold_boundaries(key, limit, inclusive, delta):
    v = values()
    v[key] = limit + delta
    assert (key in guard.evaluate(v)['trips']) == (delta >= 0 if inclusive else delta > 0)


@pytest.mark.parametrize('baseline', [0, 0.01, 0.02, 0.063])
@pytest.mark.parametrize('delta', [-1e-8, 0, 1e-8])
def test_relative_refusal_boundary(baseline, delta):
    threshold = max(0.02, baseline * 1.25 + 0.005)
    v = dict(values(), refusal_baseline_fraction=baseline, refusal_fraction=threshold + delta)
    reading = guard.evaluate(v)
    assert not reading['blind']
    assert reading['refusal_threshold'] == threshold
    assert reading['refusal_mode'] == 'relative'
    assert ('refusal_fraction' in reading['trips']) == (delta >= 0)


def test_peak_baseline_does_not_trip_at_peak_or_old_absolute_boundary():
    for current in (0.0203, 0.063):
        reading = guard.evaluate(dict(values(), refusal_baseline_fraction=0.063, refusal_fraction=current))
        assert not reading['trips'] and not reading['blind']
        assert reading['refusal_threshold'] == pytest.approx(0.08375)


def test_first_p95_baseline_query_reads_same_metric_same_hour_last_week():
    expressions = guard.queries('unused')
    assert 'histogram_quantile(0.95' in expressions['first_p95_baseline']
    assert 'omi_stt_window_first_text_seconds_bucket' in expressions['first_p95_baseline']
    assert '[1h] offset 7d' in expressions['first_p95_baseline']
    assert expressions['first_count_baseline'] == (
        'sum(increase(omi_stt_window_first_text_seconds_count{job="backend-listen-metrics"}[1h] offset 7d))'
    )


@pytest.mark.parametrize('baseline,limit', [(0, 30), (20, 30), (25, 30), (35, 42), (100, 120)])
@pytest.mark.parametrize('delta', [-1e-8, 0, 1e-8])
def test_first_p95_is_relative_to_weekly_same_hour_baseline(baseline, limit, delta):
    v = dict(values(), first_p95_baseline=baseline, first_count_baseline=100, first_p95=limit + delta)
    reading = guard.evaluate(v)
    assert not reading['blind']
    assert reading['first_p95_threshold'] == pytest.approx(limit)
    assert ('first_p95' in reading['trips']) == (delta >= 0)


def test_sparse_weekly_baseline_falls_back_to_floor():
    # One 60s text last week prices the historical p95 near 59.25s; unqualified,
    # the 1.2x threshold (~71.1s) would mask this week's real regression at 45s.
    v = dict(values(), first_p95=45, first_over30=4, first_p95_baseline=59.25, first_count_baseline=1)
    reading = guard.evaluate(v)
    assert reading['first_p95_threshold'] == 30
    assert reading['trips'] == ['first_p95']
    assert 'first_p95' not in guard.evaluate(dict(v, first_count_baseline=20))['trips']
    assert guard.evaluate(dict(v, first_count_baseline=None))['first_p95_threshold'] == 30


@pytest.mark.parametrize('baseline', [None, float('nan'), float('inf')])
def test_first_p95_baseline_unavailable_falls_back_to_floor_not_p95_alone(baseline):
    v = dict(values(), first_p95=30)
    if baseline is None:
        del v['first_p95_baseline']
    else:
        v['first_p95_baseline'] = baseline
    reading = guard.evaluate(v)
    assert not reading['blind'] and reading['first_p95_threshold'] == 30
    assert reading['trips'] == ['first_p95']
    assert 'first_p95' not in guard.evaluate(dict(v, first_over30=3.99))['trips']


def test_one_or_two_slow_sessions_never_trip_first_p95():
    # 04:08Z/06:19Z shape: 1-2 slow sessions in a ~40-text window push p95 past
    # 60s while floor 10 beat floor 12 fleet-wide (p95 14.3s vs 17.5s, 6h cohort).
    v = dict(values(), first_p95=60, first_over30=3)
    assert guard.evaluate(v)['trips'] == []
    assert guard.evaluate(dict(v, first_p95_baseline=100))['trips'] == []
    assert 'first_p95' in guard.evaluate(dict(v, first_over30=4))['trips']


def test_first_p95_needs_twenty_first_texts():
    v = dict(values(), first_count=19.99, first_p95=60, first_over30=10)
    reading = guard.evaluate(v)
    assert reading['low_sample'] and reading['trips'] == []


@pytest.mark.parametrize(
    'key,bad',
    [
        ('refusal_baseline_fraction', -0.01),
        ('refusal_baseline_fraction', 1.01),
        ('refusal_baseline_count', 19.99),
        ('refusal_baseline_ready_min', 11),
        ('refusal_baseline_ready_max', 13),
        ('refusal_baseline_ready_stale', 120.01),
        ('refusal_baseline_admission_stale', 120.01),
        ('refusal_baseline_ready_stale', -1),
        ('refusal_baseline_coverage', 0),
        ('refusal_baseline_target_stale', 121),
        ('refusal_baseline_listener_stale', 121),
    ],
)
def test_unqualified_baseline_uses_absolute_ceiling_and_retains_other_trips(key, bad):
    v = dict(values(), **{key: bad}, first_p95=30)
    reading = guard.evaluate(v)
    assert not reading['blind']
    assert reading['refusal_threshold'] == guard.REFUSAL_ABSOLUTE_CEILING
    assert reading['refusal_mode'] == 'absolute_fallback'
    assert 'first_p95' in reading['trips'] and 'refusal_fraction' not in reading['trips']
    # Fail-closed on the ceiling: a live 5% refusal still trips.
    tripped = guard.evaluate(dict(v, refusal_fraction=0.05))
    assert 'refusal_fraction' in tripped['trips'] and not tripped['blind']


def test_unqualified_baseline_alone_never_accumulates_blind_runs():
    # 2026-10-24 16:05Z shape: refusal_baseline_coverage 0 (series younger than
    # its 7d offset) with refusal_fraction 0 used to read BLIND on every run
    # and roll floor 8 back at blind_runs=4; the absolute fallback keeps CLEAN.
    hpa, dep = objects()
    v = dict(values(), refusal_baseline_coverage=0, refusal_fraction=0.0)
    _, state, _ = guard.decide(hpa, dep, [], v, {}, 0)
    for now in (900, 1200, 1500):
        verdict, state, reading = guard.decide(hpa, dep, [], v, state, now)
        assert verdict == 'CLEAN' and state['blind'] == 0
        assert reading['refusal_mode'] == 'absolute_fallback'


def test_missing_baseline_series_falls_back_to_absolute_ceiling():
    v = values()
    del v['refusal_baseline_fraction']
    reading = guard.evaluate(v)
    assert not reading['blind']
    assert reading['refusal_mode'] == 'absolute_fallback'
    assert reading['refusal_threshold'] == guard.REFUSAL_ABSOLUTE_CEILING


def test_current_refusal_data_missing_or_stale_stays_blind_under_fallback():
    base = dict(values(), refusal_baseline_coverage=0)
    assert 'missing_or_nonfinite_refusal_fraction' in guard.evaluate(dict(base, refusal_fraction=None))['blind']
    assert 'admission_stale' in guard.evaluate(dict(base, admission_stale=121))['blind']


def test_baseline_queries_use_weekly_history_and_qualified_deployment_only():
    expressions = guard.refusal_baseline_queries('prod-omi-backend')
    assert all('offset 7d' in query for query in expressions.values())
    assert 'deployment="prod-omi-parakeet"' in expressions['refusal_baseline_ready_min']
    assert 'namespace="prod-omi-backend"' in expressions['refusal_baseline_ready_min']
    assert all('vector(1000000000)' in expressions[k] for k in expressions if k.endswith('_stale'))
    assert all('[1h:1m]' in expressions[k] for k in expressions if k.endswith('_stale'))
    coverage = expressions['refusal_baseline_coverage']
    assert 'up{job="backend-listen-metrics"}' in coverage
    assert 'unless on(job,instance)' in coverage
    assert 'count(' in coverage and 'sum(kube_deployment_status_replicas_available' in coverage


def test_partial_history_does_not_raise_threshold_above_real_baseline():
    # The review's incomplete-target example: 8% on partial coverage must not
    # widen the gate to ~10.5%; the fallback ceiling stays 2% and a 5% live
    # refusal still trips, harder than the full 3% baseline would.
    row = dict(values(), refusal_baseline_fraction=0.08, refusal_fraction=0.05, refusal_baseline_coverage=0)
    reading = guard.evaluate(row)
    assert reading['refusal_mode'] == 'absolute_fallback'
    assert reading['refusal_threshold'] == guard.REFUSAL_ABSOLUTE_CEILING
    assert reading['trips'] == ['refusal_fraction']
    complete = dict(row, refusal_baseline_fraction=0.03, refusal_baseline_coverage=1)
    assert guard.evaluate(complete)['trips'] == ['refusal_fraction']


def test_guard_upgrade_restarts_full_lookback(monkeypatch):
    hpa, dep = objects()
    monkeypatch.setattr(guard, 'REFUSAL_GATE_VERSION', 'old-absolute-refusal')
    _, old_state, _ = guard.decide(hpa, dep, [], values(), {}, 0)
    monkeypatch.setattr(guard, 'REFUSAL_GATE_VERSION', 'same-hour-of-week-12-pod-v2')
    assert guard.decide(hpa, dep, [], values(), old_state, 900)[0] == 'WARMUP'


# Weekly refusal-baseline keys are exempt like first_p95_baseline: an unqualified
# baseline selects the absolute refusal ceiling (fail-closed), never blindness.
@pytest.mark.parametrize(
    'key',
    [
        k
        for k in guard.queries('unused')
        if k not in ('first_p95_baseline', 'first_count_baseline') and k not in guard.refusal_baseline_queries('unused')
    ],
)
@pytest.mark.parametrize('bad', [None, float('nan'), float('inf'), -float('inf')])
def test_missing_nonfinite_never_clean(key, bad):
    v = values()
    if bad is None:
        del v[key]
    else:
        v[key] = bad
    assert guard.evaluate(v)['blind']


@pytest.mark.parametrize('key', ['first_stale', 'post_stale', 'admission_stale', 'dcgm_stale', 'v2_stale'])
@pytest.mark.parametrize('age', [119.99, 120, 120.01])
def test_staleness(key, age):
    assert bool(guard.evaluate(dict(values(), **{key: age}))['blind']) == (age > 120)


@pytest.mark.parametrize('count', [0, 19.99, 20])
def test_low_sample_does_not_trip(count):
    v = dict(values(), first_count=count, admission_count=count, first_p95=100, refusal_fraction=0.9)
    assert guard.evaluate(v)['low_sample'] == (count < 20)
    assert bool(guard.evaluate(v)['trips']) == (count >= 20)


def test_reference_rollback_exact_and_atomic():
    old = json.loads((FIXTURES / 'hpa_spec.json').read_text())
    # Frozen output of P77 step_fast.build(spec,12,True), not our implementation.
    expected = json.loads((FIXTURES / 'rollback_patch.json').read_text())
    assert guard.build_rollback(old) == expected
    before = deepcopy(old)
    patch = guard.build_rollback(old)
    patch[0]['value']['maxReplicas'] = 999
    assert old == before


def test_proposed_scale_up_can_rollback_actual_rendered_production_hpa():
    chart = ROOT / 'backend/charts/parakeet'
    output = subprocess.check_output(
        [
            'helm',
            'template',
            'prod-omi-parakeet',
            str(chart),
            '-f',
            str(chart / 'prod_omi_parakeet_values.yaml'),
            '--set',
            'image.tag=test',
        ],
        text=True,
    )
    old = next(obj['spec'] for obj in yaml.safe_load_all(output) if obj and obj['kind'] == 'HorizontalPodAutoscaler')
    assert old['behavior']['scaleUp'] == guard.FAST_SCALE_UP
    patch = guard.build_rollback(old)
    assert patch[0] == {'op': 'test', 'path': '/spec', 'value': old}
    assert patch[1] == {'op': 'replace', 'path': '/spec/minReplicas', 'value': 12}
    assert patch[2]['value'][-1] == guard.LATENCY


@pytest.mark.parametrize('key,bad', [('stabilizationWindowSeconds', 60), ('selectPolicy', 'Min')])
def test_proposed_scale_up_drift_refuses(key, bad):
    old = objects()[0]['spec']
    old['behavior']['scaleUp'] = deepcopy(guard.FAST_SCALE_UP)
    old['behavior']['scaleUp'][key] = bad
    with pytest.raises(AssertionError, match='Scale-up drift'):
        guard.build_rollback(old)


@pytest.mark.parametrize('drift', ['cap', 'extra', 'duplicate', 'missing', 'requests', 'gpu', 'up', 'down'])
def test_drift_refuses(drift):
    old = objects()[0]['spec']
    if drift == 'cap':
        old['maxReplicas'] = 13
    if drift == 'extra':
        old['metrics'].append({'type': 'Resource', 'resource': {'name': 'cpu'}})
    if drift == 'duplicate':
        old['metrics'].append(deepcopy(old['metrics'][0]))
    if drift == 'missing':
        old['metrics'] = old['metrics'][:1]
    if drift == 'requests':
        old['metrics'][0]['pods']['target']['averageValue'] = '3'
    if drift == 'gpu':
        old['metrics'][1]['external']['target']['value'] = '36'
    if drift == 'up':
        old['behavior']['scaleUp']['policies'][0]['value'] = 2
    if drift == 'down':
        old['behavior']['scaleDown']['stabilizationWindowSeconds'] = 899
    with pytest.raises((AssertionError, KeyError)):
        guard.build_rollback(old)


@pytest.mark.parametrize('floor', [3, 5, 8, 12])
@pytest.mark.parametrize('latency', [False, True])
def test_state_gating(floor, latency):
    hpa, _ = objects()
    hpa['spec']['minReplicas'] = floor
    if latency:
        hpa['spec']['metrics'].append(guard.LATENCY)
    assert guard.workload_only(hpa['spec']) == (floor in (5, 8) and not latency)


def test_arm_full_window_and_reset_on_spec_image_generation_changes():
    hpa, dep = objects()
    verdict, state, _ = guard.decide(hpa, dep, [], values(), {}, 1000)
    assert verdict == 'WARMUP'
    assert guard.decide(hpa, dep, [], values(), state, 1899)[0] == 'WARMUP'
    assert guard.decide(hpa, dep, [], values(), state, 1900)[0] == 'CLEAN'
    changed_hpa, changed_dep = deepcopy(hpa), deepcopy(dep)
    changed_hpa['spec']['minReplicas'] = 8
    assert guard.decide(changed_hpa, dep, [], values(), state, 1900)[0] == 'WARMUP'
    changed_dep['spec']['template']['spec']['containers'][0]['image'] = 'another:sha'
    assert guard.decide(hpa, changed_dep, [], values(), state, 1900)[0] == 'WARMUP'
    changed_hpa = deepcopy(hpa)
    changed_hpa['metadata']['generation'] += 1
    assert guard.decide(changed_hpa, dep, [], values(), state, 1900)[0] == 'WARMUP'


def test_three_blind_runs_and_clean_reset_and_warmup():
    hpa, dep = objects()
    _, state, _ = guard.decide(hpa, dep, [], values(), {}, 0)
    for now, verdict in [(900, 'BLIND'), (1200, 'BLIND'), (1500, 'TRIP')]:
        actual, state, _ = guard.decide(hpa, dep, [], {}, state, now)
        assert actual == verdict
    actual, state, _ = guard.decide(hpa, dep, [], values(), state, 1800)
    assert actual == 'CLEAN' and state['blind'] == 0
    assert guard.decide(hpa, dep, [], {}, {}, 0)[0] == 'WARMUP'
    del hpa['status']['desiredReplicas']
    for now in (2100, 2400, 2700):
        actual, state, _ = guard.decide(hpa, dep, [], values(), state, now)
    assert actual == 'TRIP' and state['blind'] == 3


def test_ready_and_scheduling():
    hpa, dep = objects()
    _, state, _ = guard.decide(hpa, dep, [], values(), {}, 0)
    dep['status']['readyReplicas'] = 4
    assert guard.decide(hpa, dep, [], values(), state, 900)[0] == 'TRIP'
    dep['status']['readyReplicas'] = 5
    event = {
        'reason': 'FailedScheduling',
        'involvedObject': {'kind': 'Pod', 'name': 'prod-omi-parakeet-x'},
        'lastTimestamp': '1970-01-01T00:15:00Z',
    }
    assert guard.decide(hpa, dep, [event], values(), state, 900)[0] == 'TRIP'
    assert not guard.scheduling_failures([event], 'other', 900)
    assert not guard.scheduling_failures([event], 'prod-omi-parakeet', 1801)


@pytest.mark.parametrize('age', [1799, 1800, 1801])
def test_batch_stuck_proxy_and_missing_projection_is_explicit(age):
    reading = guard.evaluate_batch({'oldest_age': age, 'retry_age': 0, 'freshness': 0, 'scrape_age': 0})
    assert reading['verdict'] == ('TRIP' if age > 1800 else 'PARTIAL')
    assert 'new_projection_obligations_unavailable' in reading['unknown']
    assert guard.evaluate_batch({})['verdict'] == 'BLIND'
    assert (
        guard.evaluate_batch({'oldest_age': 9999, 'retry_age': 0, 'freshness': 121, 'scrape_age': 0})['verdict']
        == 'BLIND'
    )


class FakeClient:
    namespace = 'prod-omi-backend'

    def __init__(self):
        self.hpa, self.dep = objects()
        self.state = {}
        self.patches = []
        self.signals = values()

    def path(self, name):
        return name

    def sample(self, expr):
        return (
            self.signals if 'first_p95' in expr else {'oldest_age': 0, 'retry_age': 0, 'freshness': 0, 'scrape_age': 0}
        )

    def kube(self, path, patch=None):
        if patch is not None:
            self.patches.append((path, patch))
            if path == 'state':
                self.state = json.loads(patch[1]['value']['state'])
            return {}
        return {
            'hpa': self.hpa,
            'deployment': self.dep,
            'events': {'items': []},
            'state': {'metadata': {'resourceVersion': '7'}, 'data': {'state': json.dumps(self.state)}},
        }[path]


@pytest.mark.parametrize('dry_run', [False, True])
def test_run_writes_only_reference_rollback_or_dry_run(dry_run, caplog):
    client = FakeClient()
    assert guard.run(client, dry_run, 0) == 0
    assert '"refusal_mode": "relative"' in caplog.text
    client.signals['first_p95'] = 30
    assert guard.run(client, dry_run, 900) == 1
    hpa_writes = [patch for path, patch in client.patches if path == 'hpa']
    assert hpa_writes == ([] if dry_run else [guard.build_rollback(client.hpa['spec'])])
    assert 'parakeet_rollback' in caplog.text
    client.hpa['spec']['minReplicas'] = 12
    client.patches = []
    assert guard.run(client, dry_run, 1200) == 0
    assert all(path == 'state' for path, _ in client.patches)


def render(environment='prod', *extra):
    output = subprocess.check_output(
        [
            'helm',
            'template',
            f'{environment}-omi-incluster-guards',
            str(CHART),
            '--namespace',
            f'{environment}-omi-backend',
            '-f',
            str(CHART / f'{environment}_omi_incluster_guards_values.yaml'),
            *extra,
        ],
        text=True,
    )
    return {
        obj['kind']: obj
        for obj in yaml.safe_load_all(output)
        if obj
        and (
            obj['kind'] == 'PodMonitor'
            or obj['metadata']['name']
            not in {f'{environment}-omi-incluster-guards-batch', f'{environment}-omi-incluster-guards-batch-state'}
        )
    }


def render_docs(environment='prod', *extra, overlay=True):
    command = [
        'helm',
        'template',
        f'{environment}-omi-incluster-guards',
        str(CHART),
        '--namespace',
        f'{environment}-omi-backend',
    ]
    if overlay:
        command += ['-f', str(CHART / f'{environment}_omi_incluster_guards_values.yaml')]
    return [obj for obj in yaml.safe_load_all(subprocess.check_output([*command, *extra], text=True)) if obj]


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_helm_rbac_and_cpu_placement(environment):
    objs = render(environment)
    assert set(objs) == {'ServiceAccount', 'Role', 'RoleBinding', 'ConfigMap', 'CronJob', 'PodMonitor'}
    assert objs['PodMonitor']['spec']['selector']['matchLabels'] == {'app.kubernetes.io/name': 'batch-pipeline-worker'}
    parakeet_values = yaml.safe_load(
        (ROOT / f'backend/charts/parakeet/{environment}_omi_parakeet_values.yaml').read_text()
    )
    assert (
        objs['PodMonitor']['metadata']['labels']['release']
        == parakeet_values['metrics']['serviceMonitor']['labels']['release']
    )
    assert not objs['ServiceAccount']['metadata'].get('annotations')
    assert objs['Role']['rules'] == [
        {
            'apiGroups': ['autoscaling'],
            'resources': ['horizontalpodautoscalers'],
            'resourceNames': [f'{environment}-omi-parakeet'],
            'verbs': ['get', 'patch'],
        },
        {
            'apiGroups': ['apps'],
            'resources': ['deployments'],
            'resourceNames': [f'{environment}-omi-parakeet'],
            'verbs': ['get'],
        },
        {'apiGroups': [''], 'resources': ['events'], 'verbs': ['list']},
        {
            'apiGroups': [''],
            'resources': ['configmaps'],
            'resourceNames': [f'{environment}-omi-incluster-guards-state'],
            'verbs': ['get', 'patch'],
        },
    ]
    cron = objs['CronJob']['spec']
    assert cron['schedule'] == '*/5 * * * *' and cron['concurrencyPolicy'] == 'Forbid'
    job = cron['jobTemplate']['spec']
    assert job['activeDeadlineSeconds'] == 240 and job['backoffLimit'] == 0
    pod = job['template']['spec']
    assert pod['tolerations'] == []
    assert {'key': 'cloud.google.com/gke-accelerator', 'operator': 'DoesNotExist'} in pod['affinity']['nodeAffinity'][
        'requiredDuringSchedulingIgnoredDuringExecution'
    ]['nodeSelectorTerms'][0]['matchExpressions']
    container = pod['containers'][0]
    assert '@sha256:' in container['image']
    env = {item['name']: item['value'] for item in container['env']}
    assert env['DRY_RUN'] == ('true' if environment == 'dev' else 'false')
    adapter = yaml.safe_load(
        (ROOT / f'backend/charts/monitoring/prometheus-adapter/{environment}_omi_prometheus_adapter.yaml').read_text()
    )
    expected_url = (
        adapter['prometheus']['url'].replace('{{ .Release.Namespace }}', f'{environment}-omi-monitoring') + ':9090'
    )
    assert env['PROMETHEUS_URL'] == expected_url
    assert not render(environment, '--set', 'enabled=false')


def test_cloud_run_gate_refuses_unapproved_identity_or_namespace():
    with pytest.raises(subprocess.CalledProcessError):
        render('prod', '--set', 'batch.enabled=true', '--set', 'batch.gcpServiceAccount=wrong@example.com')
    with pytest.raises(subprocess.CalledProcessError):
        render('dev', '--set', 'batch.cloudRunRollbackEnabled=true')


BATCH_GUARD_OBJECTS = frozenset(
    {
        ('ServiceAccount', 'prod-omi-incluster-guards-batch'),
        ('ConfigMap', 'prod-omi-incluster-guards-batch-state'),
        ('Role', 'prod-omi-incluster-guards-batch'),
        ('RoleBinding', 'prod-omi-incluster-guards-batch'),
        ('CronJob', 'prod-omi-incluster-guards-batch'),
    }
)


def test_prod_overlay_defers_batch_guard_objects_until_deployer_rbac_and_producer_exist():
    # Deploy run 40126547763: the prod deployer's name-scoped RBAC refuses to
    # create the -batch objects, so the prod overlay keeps batch.enabled=false
    # until that access change is approved (David) and g2's producer exists.
    rendered = {(doc['kind'], doc['metadata']['name']) for doc in render_docs('prod')}
    assert not rendered & BATCH_GUARD_OBJECTS
    assert ('PodMonitor', 'prod-omi-incluster-guards-batch') in rendered  # Predates the batch guard; stays live.
    assert ('CronJob', 'prod-omi-incluster-guards') in rendered
    # The default toggle stays on: re-enabling in prod needs only this flip.
    reenabled = {(doc['kind'], doc['metadata']['name']) for doc in render_docs('prod', '--set', 'batch.enabled=true')}
    assert BATCH_GUARD_OBJECTS <= reenabled
    # Default values alone render no batch objects, exactly as before the toggle.
    assert (
        not {(doc['kind'], doc['metadata']['name']) for doc in render_docs('prod', overlay=False)} & BATCH_GUARD_OBJECTS
    )


def test_run_persists_three_blind_observations_and_trips():
    client = FakeClient()
    guard.run(client, False, 0)
    client.signals = {}
    for now in (900, 1200):
        assert guard.run(client, False, now) == 1
        assert not any(path == 'hpa' for path, _ in client.patches)
    assert guard.run(client, False, 1500) == 1
    assert len([path for path, _ in client.patches if path == 'hpa']) == 1
    assert client.state['blind'] == 3


def test_drift_is_a_failed_run_without_hpa_patch():
    client = FakeClient()
    client.hpa['spec']['maxReplicas'] = 13
    guard.run(client, False, 0)
    client.signals['first_p95'] = 31
    with pytest.raises(AssertionError, match='Unexpected cap'):
        guard.run(client, False, 900)
    assert not any(path == 'hpa' for path, _ in client.patches)


@pytest.mark.parametrize(
    'data',
    [
        {'status': 'success', 'data': {'result': []}},
        {'status': 'success', 'warnings': ['partial'], 'data': {'result': [{'value': [1000, '1']}]}},
        {'status': 'success', 'data': {'result': [{'value': [1000, 'NaN']}]}},
        {'status': 'success', 'data': {'result': [{'value': [879, '1']}]}},
        {'status': 'success', 'data': {'result': [{'value': [1000, '1']}, {'value': [1000, '2']}]}},
        {'status': 'error'},
    ],
)
def test_query_rejects_missing_partial_stale_nonfinite_and_multiseries(monkeypatch, data):
    import io
    import math

    client = object.__new__(guard.Client)
    client.prometheus = 'http://prometheus.invalid:9090'
    monkeypatch.setattr(guard.urllib.request, 'urlopen', lambda *args, **kwargs: io.BytesIO(json.dumps(data).encode()))
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    value = client.sample({'signal': 'vector(1)'})['signal']
    assert value is None or not math.isfinite(value)


def test_query_uses_direct_prometheus_without_bearer_token(monkeypatch):
    import io

    client = object.__new__(guard.Client)
    client.prometheus = 'http://prometheus.invalid:9090'
    calls = []

    def opened(url, **kwargs):
        calls.append((url, kwargs))
        return io.BytesIO(b'{"status":"success","data":{"result":[{"value":[1000,"2"]}]}}')

    monkeypatch.setattr(guard.urllib.request, 'urlopen', opened)
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    assert client.sample({'signal': 'vector(2)'}) == {'signal': 2.0}
    assert calls == [('http://prometheus.invalid:9090/api/v1/query?query=vector%282%29', {'timeout': 10})]


@pytest.mark.parametrize(
    'path', ['backend/charts/incluster-guards/files/guard.py', 'backend/charts/incluster-guards/files/batch_guard.py']
)
def test_guard_chart_selects_its_behavioral_suite_on_future_changes(path):
    selector_spec = importlib.util.spec_from_file_location(
        'unit_selector_guards', ROOT / 'backend/scripts/select_backend_unit_tests.py'
    )
    selector = importlib.util.module_from_spec(selector_spec)
    selector_spec.loader.exec_module(selector)
    selected, _ = selector.tests_for_changed_paths(
        [path], ['tests/unit/test_incluster_guards.py', 'tests/unit/test_unrelated.py']
    )
    assert selected == ['tests/unit/test_incluster_guards.py']


def test_fresh_quiet_nan_arithmetic_is_low_sample_not_three_blind_trips():
    hpa, dep = objects()
    v = dict(values(), first_count=0, admission_count=0, dcgm_nonzero=0)
    for key in ('first_p95', 'post_p95', 'v2_p95', 'refusal_fraction', 'first_p95_baseline'):
        v[key] = float('nan')
    state = {}
    for now in (0, 300, 600, 900, 1200, 1500):
        verdict, state, _ = guard.decide(hpa, dep, [], v, state, now)
        assert verdict == ('WARMUP' if now < 900 else 'LOW_SAMPLE')
        assert state['blind'] == 0
    v['first_p95'] = None  # Missing/failed query remains blindness, even on a quiet night.
    assert guard.evaluate(v)['blind']
    v['first_p95'] = float('nan')
    v['first_stale'] = 121
    assert guard.evaluate(v)['blind']


def test_render_packages_exact_entrypoint_and_shared_logging_module():
    output = subprocess.check_output(
        [
            'helm',
            'template',
            'prod-omi-incluster-guards',
            str(CHART),
            '--namespace',
            'prod-omi-backend',
        ],
        text=True,
    )
    objs = [obj for obj in yaml.safe_load_all(output) if obj]
    script = next(obj for obj in objs if obj['metadata']['name'].endswith('-script'))
    assert script['data']['guard.py'] == (CHART / 'files/guard.py').read_text()
    assert script['data']['batch_guard.py'] == (CHART / 'files/batch_guard.py').read_text()
    assert script['data']['omi_logging.py'] == (ROOT / 'backend/omi_logging.py').read_text()


def test_non_workload_state_is_noop_even_when_deployment_reader_is_unavailable():
    client = FakeClient()
    client.hpa['spec']['minReplicas'] = 12
    original = client.kube

    def limited(path, patch=None):
        assert path not in {'deployment', 'events'}
        return original(path, patch)

    client.kube = limited
    assert guard.run(client, False, 1000) == 0
    assert not any(path == 'hpa' for path, _ in client.patches)


def test_autoscaling_does_not_restart_window_or_hide_ready_shortfall():
    hpa, dep = objects()
    _, state, _ = guard.decide(hpa, dep, [], values(), {}, 0)
    dep['metadata']['generation'] += 1
    dep['spec']['replicas'] = 8
    hpa['status']['desiredReplicas'] = 8
    verdict, state, _ = guard.decide(hpa, dep, [], values(), state, 300)
    assert verdict == 'WARMUP' and state['since'] == 0
    verdict, state, reading = guard.decide(hpa, dep, [], values(), state, 900)
    assert verdict == 'TRIP' and 'ready_shortfall' in reading['trips']


# Batch admission rollback shares this chart's registered behavioral suite.
batch: Any = None


@pytest.fixture(scope='module', autouse=True)
def batch_runtime_module():
    spec = importlib.util.spec_from_file_location('batch_guard', CHART / 'files/batch_guard.py')
    module = importlib.util.module_from_spec(spec)
    with pytest.MonkeyPatch.context() as imports:
        imports.setitem(sys.modules, 'guard', guard)
        spec.loader.exec_module(module)
    with pytest.MonkeyPatch.context() as state:
        state.setattr(sys.modules[__name__], 'batch', module)
        yield


def template():
    return {
        'serviceAccount': 'backend-runtime@example.invalid',
        'timeout': '300s',
        'containers': [
            {
                'image': 'image@sha256:' + 'a' * 64,
                'resources': {'limits': {'memory': '2Gi'}},
                'env': [
                    {'name': batch.KEY, 'value': '5'},
                    {'name': 'KEEP', 'value': 'x,y'},
                    {'name': 'SECRET', 'valueSource': {'secretKeyRef': {'secret': 'ref', 'version': '1'}}},
                ],
            }
        ],
    }


class Cloud:
    def __init__(self):
        self.services, self.revisions, self.writes = {}, {}, []
        self.fail = None
        for key in batch.SERVICES:
            name = batch.ROOT + key
            rev = name + '/revisions/' + key + '-old'
            self.services[name] = {
                'name': name,
                'generation': '1',
                'observedGeneration': '1',
                'etag': '1',
                'terminalCondition': {'state': 'CONDITION_SUCCEEDED'},
                'reconciling': False,
                'template': template(),
                'latestCreatedRevision': rev,
                'latestReadyRevision': rev,
                'trafficStatuses': [{'revision': rev, 'percent': 100}],
            }
            self.revisions[rev] = dict(template(), name=rev, reconciling=False)

    def get(self, path):
        return deepcopy((self.revisions if '/revisions/' in path else self.services)[path])

    def patch(self, service, body, mask):
        if self.fail == service['name']:
            raise ValueError('fake_service_failure')
        old = self.services[service['name']]
        assert old['etag'] == service['etag']
        self.writes.append((service['name'], deepcopy(body), mask))
        if 'template' in body:
            new = deepcopy(body['template'])
            rev = service['name'] + '/revisions/' + new['revision']
            self.revisions[rev] = dict(new, name=rev, reconciling=False)
            old.update(template=new, latestCreatedRevision=rev, latestReadyRevision=rev)
        old['trafficStatuses'] = deepcopy(body['traffic'])
        for target in old['trafficStatuses']:
            if '/' not in target['revision']:
                target['revision'] = old['name'] + '/revisions/' + target['revision']
        old['etag'] = str(int(old['etag']) + 1)
        return {'name': 'operation-not-polled'}


class Kube:
    def __init__(self):
        self.cm = {'metadata': {'resourceVersion': '1'}, 'data': {'state': '{}'}}

    def path(self, resource):
        assert resource == 'state'
        return resource

    def kube(self, path, body=None):
        assert path == 'state'
        if body:
            assert body[0]['value'] == self.cm['metadata']['resourceVersion']
            self.cm['data'] = deepcopy(body[1]['value'])
            self.cm['metadata']['resourceVersion'] = str(int(self.cm['metadata']['resourceVersion']) + 1)
        return deepcopy(self.cm)

    @property
    def state(self):
        return json.loads(self.cm['data']['state'])


def sample(identity='id', since=0, now=1800):
    return {
        'schema_version': 1,
        'identity': identity,
        'since': since,
        'arm_since': since,
        'observed_at': now,
        'read_completed_at': now,
        'custody': {'missing': 0, 'unknown': 0},
        **dict.fromkeys(
            [
                'proven_terminal_loss_speech_seconds',
                'proven_failed_held_speech_seconds',
                'since_t0_projection_obligations_over_15m',
                'since_t0_stuck_jobs_over_30m',
                'terminal_unrecovered_speech_unknown_units',
                'since_t0_failed_held_unknown_duration',
                'terminal_unrecovered_speech_vad_fallback_units',
                'since_t0_failed_held_vad_fallback_units',
            ],
            0,
        ),
    }


def test_env_update_preserves_every_other_field_including_secret_refs():
    old = template()['containers']
    old.append({'name': 'metrics', 'image': 'metrics@sha256:frozen', 'env': [{'name': 'UNCHANGED', 'value': 'yes'}]})
    new = batch.containers_at_zero(old)
    assert batch.percent(old) == 5 and batch.percent(new) == 0
    new[0]['env'][0]['value'] = '5'
    assert new == old


def test_proto_default_false_fields_are_optional():
    cloud = Cloud()
    for service in cloud.services.values():
        service.pop('reconciling')
    for revision in cloud.revisions.values():
        revision.pop('reconciling')
    assert len(batch.snapshot(cloud)) == 4


def test_template_tag_resolves_to_frozen_serving_digest(tmp_path, monkeypatch):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    for service in cloud.services.values():
        service['template']['containers'][0]['image'] = 'image:mutable'
    batch.run(kube, cloud, path, now=100)
    data = sample(kube.state['identity'], since=100, now=1900)
    data['custody']['missing'] = 1
    path.write_text(json.dumps(data))
    assert batch.run(kube, cloud, path, now=1900) == 1
    for _, body, mask in cloud.writes:
        if mask != 'traffic':
            assert body['template']['containers'][0]['image'] == 'image@sha256:' + 'a' * 64


def test_cloud_uses_gke_metadata_token_and_etag_mask(monkeypatch):
    import io

    calls = []

    def opened(request, **kwargs):
        calls.append(request)
        if request.full_url.endswith('/token'):
            return io.BytesIO(b'{"access_token":"fake-gke-token"}')
        return io.BytesIO(b'{"name":"operation"}')

    monkeypatch.setattr(batch.urllib.request, 'urlopen', opened)
    batch.Cloud().patch({'name': batch.ROOT + 'backend', 'etag': 'expected'}, {'traffic': []}, 'traffic')
    assert calls[0].full_url.endswith('/default/token')
    assert calls[0].get_header('Metadata-flavor') == 'Google'
    assert calls[1].get_header('Authorization') == 'Bearer fake-gke-token'
    assert calls[1].full_url.endswith('/services/backend?updateMask=traffic')
    assert json.loads(calls[1].data)['etag'] == 'expected'


def test_registered_logging_entrypoint_dispatches_batch(monkeypatch):
    from types import SimpleNamespace

    called = []

    def batch_main():
        called.append(True)
        return 17

    monkeypatch.setattr(sys, 'argv', ['guard.py', '--batch'])
    with patch.dict(sys.modules, {'batch_guard': SimpleNamespace(main=batch_main)}):
        assert guard.main() == 17
    assert called == [True]


@pytest.mark.parametrize(
    'bad',
    [
        [],
        [{'name': 'BATCH_PIPELINE_PERCENT', 'value': '101'}],
        [{'name': 'BATCH_PIPELINE_PERCENT', 'valueSource': {'secretKeyRef': {}}}],
        [{'name': 'BATCH_PIPELINE_PERCENT', 'value': '5'}] * 2,
    ],
)
def test_invalid_percent_refuses(bad):
    containers = template()['containers']
    containers[0]['env'] = bad
    with pytest.raises(ValueError):
        batch.containers_at_zero(containers)


@pytest.mark.parametrize(
    'field',
    [
        'proven_terminal_loss_speech_seconds',
        'proven_failed_held_speech_seconds',
        'since_t0_projection_obligations_over_15m',
        'since_t0_stuck_jobs_over_30m',
        'custody',
    ],
)
def test_p90_three_trip_classes_only_after_full_new_window(field):
    data = sample()
    if field == 'custody':
        data['custody']['missing'] = 1
    else:
        data[field] = 1
    assert batch.decision(data, 'id', 0, 1799)[0] == 'BLIND'  # Future sample rejected.
    data['observed_at'] = data['read_completed_at'] = 1799
    assert batch.decision(data, 'id', 0, 1799)[0] == 'WARMUP'
    assert batch.decision(data, 'id', 0, 1800)[0] == 'TRIP'


@pytest.mark.parametrize('bad', [None, float('nan'), -1, True])
def test_unknown_never_clean_or_trip(bad):
    data = sample()
    data['proven_terminal_loss_speech_seconds'] = bad
    assert batch.decision(data, 'id', 0, 1800)[0] == 'BLIND'
    data['custody']['missing'] = 1
    assert batch.decision(data, 'id', 0, 1800)[0] == 'TRIP'


def test_fallback_unknown_stale_mismatch_and_quality_watch():
    data = sample()
    assert batch.decision(data, 'id', 0, 1800)[0] == 'CLEAN'
    data['watches'] = {'quality_p95': 9999, 'first_summary_status': 'UNAVAILABLE'}
    assert batch.decision(data, 'id', 0, 1800)[0] == 'CLEAN'
    assert batch.decision(data, 'id', 0, 2401)[0] == 'BLIND'
    assert batch.decision(data, 'other', 0, 1800)[0] == 'BLIND'
    assert batch.decision(data, 'id', 1, 1800)[0] == 'BLIND'
    data['since_t0_failed_held_vad_fallback_units'] = 1
    assert batch.decision(data, 'id', 0, 1800)[0] == 'BLIND'


def test_first_write_scope_precedes_all_serving_arming_and_cannot_move():
    data = sample(since=600, now=2399)
    data['since'] = 100  # Obligations during partial apply remain in scope.
    data['custody']['missing'] = 1
    assert batch.decision(data, 'id', 600, 2399, 100)[0] == 'WARMUP'
    assert batch.decision(data, 'id', 600, 2400, 100)[0] == 'TRIP'
    data['since'] = 101
    assert batch.decision(data, 'id', 600, 2400, 100)[0] == 'BLIND'
    data['since'] = 601
    assert batch.decision(data, 'id', 600, 2400)[0] == 'BLIND'


@pytest.mark.parametrize('drift', ['split', 'tag', 'template', 'latest', 'reconciling'])
def test_snapshot_refuses_split_tag_unserved_or_reconciling(drift):
    cloud = Cloud()
    service = cloud.services[batch.ROOT + 'backend']
    if drift == 'split':
        service['trafficStatuses'] *= 2
    if drift == 'tag':
        service['trafficStatuses'][0]['tag'] = 'canary'
    if drift == 'template':
        service['template']['containers'][0]['env'][1]['value'] = 'unserved'
    if drift == 'latest':
        service['latestCreatedRevision'] = 'unserved'
    if drift == 'reconciling':
        service['reconciling'] = True
    with pytest.raises(ValueError):
        batch.snapshot(cloud)
    assert not cloud.writes


def no_sleep(_):
    pass


def prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(batch.time, 'sleep', no_sleep)
    # Defaults capture time.sleep at definition; inject it at the worker boundary.
    original = batch.rollback_one
    monkeypatch.setattr(batch, 'rollback_one', lambda *args: original(*args, sleep=no_sleep))
    cloud, kube = Cloud(), Kube()
    path = tmp_path / 'snapshot.json'
    assert batch.run(kube, cloud, path, now=0) == 1  # Missing input, never clean.
    data = sample(kube.state['identity'])
    data['custody']['missing'] = 1
    path.write_text(json.dumps(data))
    return cloud, kube, path


@pytest.mark.parametrize('observed', [900, 2400])
@pytest.mark.parametrize('invalid', ['missing', 'unknown', 'fallback'])
def test_incomplete_snapshot_cannot_pin_epoch_or_block_later_proven_trip(tmp_path, monkeypatch, observed, invalid):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    # Initialize a new all-serving clock, with no trusted safety snapshot yet.
    kube.cm['data']['state'] = '{}'
    path.unlink()
    assert batch.run(kube, cloud, path, now=600) == 1
    data = sample(kube.state['identity'], since=600, now=observed)
    data['since'] = 200  # Incorrect but in-range epoch from an incomplete producer read.
    if invalid == 'missing':
        data.pop('proven_terminal_loss_speech_seconds')
    elif invalid == 'unknown':
        data['custody']['unknown'] = None
    else:
        data['since_t0_failed_held_vad_fallback_units'] = 1
    path.write_text(json.dumps(data))
    assert batch.run(kube, cloud, path, now=observed) == 1
    assert kube.cm['data']['verdict'] == 'BLIND'
    assert 'first_write_since' not in kube.state and not cloud.writes

    now = max(2400, observed + 1)
    data = sample(kube.state['identity'], since=600, now=now)
    data['since'] = 100  # Complete read establishes the actual first-write epoch.
    data['custody']['missing'] = 1
    path.write_text(json.dumps(data))
    assert batch.run(kube, cloud, path, now=now) == 1
    assert kube.state['first_write_since'] == 100
    assert kube.cm['data']['verdict'] == 'ROLLED_BACK'
    assert len(cloud.writes) == 8


@pytest.mark.parametrize('dry', [True, False])
def test_real_run_preserves_env_pins_old_traffic_promotes_and_reads_back(tmp_path, monkeypatch, dry):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    assert batch.run(kube, cloud, path, dry_run=dry, now=1800) == 1
    if dry:
        assert not cloud.writes and not kube.state.get('pending')
        return
    assert len(cloud.writes) == 8
    for service_id in batch.SERVICES:
        writes = [w for w in cloud.writes if w[0] == batch.ROOT + service_id]
        assert writes[0][1]['traffic'][0]['revision'].endswith(service_id + '-old')
        assert writes[0][2] == 'template.containers,template.revision,traffic'
        new = deepcopy(writes[0][1]['template'])
        new.pop('revision')
        new['containers'][0]['env'][0]['value'] = '5'
        assert new == template()
        assert writes[1][2] == 'traffic'
    assert {s['percent'] for s in batch.snapshot(cloud).values()} == {0}
    assert not kube.state.get('pending') and kube.cm['data']['verdict'] == 'ROLLED_BACK'


def test_partial_failure_retries_remaining_after_signal_disappears(tmp_path, monkeypatch):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    cloud.fail = batch.ROOT + 'backend-sync'
    assert batch.run(kube, cloud, path, now=1800) == 2
    assert kube.state['pending'] and kube.cm['data']['verdict'] == 'ROLLBACK_FAILED'
    assert len(cloud.writes) == 6
    path.unlink()
    cloud.fail = None
    assert batch.run(kube, cloud, path, now=2100) == 1
    assert len(cloud.writes) == 8
    assert not kube.state.get('pending')


def test_candidate_created_before_interruption_is_promoted_without_recreation(tmp_path, monkeypatch):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    original = batch.rollback_one

    def interrupted(cloud, key, pin, deadline):
        if key == 'backend':
            real = cloud.patch

            def stop(service, body, mask):
                if mask == 'traffic':
                    raise ValueError('simulated_interruption_before_promotion')
                return real(service, body, mask)

            with patch.object(cloud, 'patch', side_effect=stop):
                return original(cloud, key, pin, deadline)
        raise ValueError('other_services_interrupted')

    monkeypatch.setattr(batch, 'rollback_one', interrupted)
    assert batch.run(kube, cloud, path, now=1800) == 2
    assert len(cloud.writes) == 1
    monkeypatch.setattr(batch, 'rollback_one', original)
    assert batch.run(kube, cloud, path, now=2100) == 1
    assert len(cloud.writes) == 8


def test_identity_change_resets_window(tmp_path, monkeypatch):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    # A new revision with identical env still restarts arming; cannot reuse old snapshots.
    service = cloud.services[batch.ROOT + 'backend']
    old_name = service['latestReadyRevision']
    new_name = old_name + '-new'
    cloud.revisions[new_name] = dict(cloud.revisions[old_name], name=new_name)
    service.update(
        latestReadyRevision=new_name,
        latestCreatedRevision=new_name,
        trafficStatuses=[{'revision': new_name, 'percent': 100}],
    )
    assert batch.run(kube, cloud, path, now=1800) == 1
    assert kube.state['since'] == 1800 and not cloud.writes


def test_helm_dedicated_identity_state_only_rbac_and_cpu_placement():
    docs = render_docs('prod', '--set', 'batch.enabled=true')
    resources = {d['kind']: d for d in docs if d and d['metadata']['name'] == 'prod-omi-incluster-guards-batch'}
    assert resources['ServiceAccount']['metadata']['annotations'] == {
        'iam.gke.io/gcp-service-account': 'omi-batch-rollback-guard@based-hardware.iam.gserviceaccount.com'
    }
    assert resources['Role']['rules'] == [
        {
            'apiGroups': [''],
            'resources': ['configmaps'],
            'resourceNames': ['prod-omi-incluster-guards-batch-state'],
            'verbs': ['get', 'patch'],
        }
    ]
    job = resources['CronJob']['spec']['jobTemplate']['spec']
    assert job['backoffLimit'] == 0 and job['activeDeadlineSeconds'] == 840
    pod = job['template']['spec']
    assert pod['serviceAccountName'] == 'prod-omi-incluster-guards-batch'
    assert pod['nodeSelector'] == {'iam.gke.io/gke-metadata-server-enabled': 'true'}
    assert pod['tolerations'] == [] and pod['affinity']
    assert pod['volumes'][1]['configMap']['optional'] is True
    assert pod['containers'][0]['command'] == ['python3', '/guard/guard.py', '--batch']
    assert all(d['kind'] not in {'ClusterRole', 'ClusterRoleBinding', 'Secret'} for d in docs)
