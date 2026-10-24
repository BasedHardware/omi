"""Hermetic safety decisions and the real single-run write path, with explicit API fakes."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
import subprocess

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
    assert ('refusal_fraction' in reading['trips']) == (delta >= 0)


def test_peak_baseline_does_not_trip_at_peak_or_old_absolute_boundary():
    for current in (0.0203, 0.063):
        reading = guard.evaluate(dict(values(), refusal_baseline_fraction=0.063, refusal_fraction=current))
        assert not reading['trips'] and not reading['blind']
        assert reading['refusal_threshold'] == pytest.approx(0.08375)


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
def test_unqualified_baseline_is_blind_and_retains_other_trips(key, bad):
    v = dict(values(), **{key: bad}, first_p95=30)
    reading = guard.evaluate(v)
    assert 'unqualified_refusal_baseline' in reading['blind']
    assert reading['refusal_threshold'] is None
    assert 'first_p95' in reading['trips']
    hpa, dep = objects()
    _, state, _ = guard.decide(hpa, dep, [], v, {}, 0)
    assert guard.decide(hpa, dep, [], v, state, 900)[0] == 'TRIP'


def test_missing_baseline_never_becomes_clean_or_implicit_absolute_fallback():
    hpa, dep = objects()
    v = values()
    del v['refusal_baseline_fraction']
    _, state, _ = guard.decide(hpa, dep, [], v, {}, 0)
    for now, expected in ((900, 'BLIND'), (1200, 'TRIP')):
        verdict, state, reading = guard.decide(hpa, dep, [], v, state, now)
        assert verdict == expected
        assert reading['refusal_threshold'] is None


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
    # The review's incomplete-target example: 8% instead of the full 3% baseline
    # must be BLIND even with abundant admissions, fresh remaining series and 12 GPUs.
    row = dict(values(), refusal_baseline_fraction=0.08, refusal_fraction=0.05, refusal_baseline_coverage=0)
    reading = guard.evaluate(row)
    assert reading['refusal_threshold'] is None and reading['blind']
    complete = dict(row, refusal_baseline_fraction=0.03, refusal_baseline_coverage=1)
    assert guard.evaluate(complete)['trips'] == ['refusal_fraction']


def test_guard_upgrade_restarts_full_lookback(monkeypatch):
    hpa, dep = objects()
    monkeypatch.setattr(guard, 'REFUSAL_GATE_VERSION', 'old-absolute-refusal')
    _, old_state, _ = guard.decide(hpa, dep, [], values(), {}, 0)
    monkeypatch.setattr(guard, 'REFUSAL_GATE_VERSION', 'same-hour-of-week-12-pod-v2')
    assert guard.decide(hpa, dep, [], values(), old_state, 900)[0] == 'WARMUP'


@pytest.mark.parametrize('key', list(guard.queries('unused')))
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
    return {obj['kind']: obj for obj in yaml.safe_load_all(output) if obj}


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


def test_cloud_run_gate_refuses_to_install_identity_or_writer():
    with pytest.raises(subprocess.CalledProcessError):
        render('prod', '--set', 'batch.cloudRunRollbackEnabled=true')


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


def test_guard_chart_selects_its_behavioral_suite_on_future_changes():
    selector_spec = importlib.util.spec_from_file_location(
        'unit_selector_guards', ROOT / 'backend/scripts/select_backend_unit_tests.py'
    )
    selector = importlib.util.module_from_spec(selector_spec)
    selector_spec.loader.exec_module(selector)
    path = 'backend/charts/incluster-guards/files/guard.py'
    selected, _ = selector.tests_for_changed_paths(
        [path], ['tests/unit/test_incluster_guards.py', 'tests/unit/test_unrelated.py']
    )
    assert selected == ['tests/unit/test_incluster_guards.py']


def test_fresh_quiet_nan_arithmetic_is_low_sample_not_three_blind_trips():
    hpa, dep = objects()
    v = dict(values(), first_count=0, admission_count=0, dcgm_nonzero=0)
    for key in ('first_p95', 'post_p95', 'v2_p95', 'refusal_fraction'):
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
