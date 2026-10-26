"""Fail-closed experiment routing, guard state and zero-margin acceptance."""

import json
from pathlib import Path
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

from config import parakeet_canary as routing
from scripts import parakeet_shape_watch as watcher
from scripts import qualify_parakeet_shape as qualify


@pytest.fixture
def lease(tmp_path, monkeypatch):
    path = tmp_path / 'route.json'
    monkeypatch.setenv('PARAKEET_SHAPE_CANARY_FILE', str(path))
    monkeypatch.setattr(routing.time, 'time', lambda: 1000)
    monkeypatch.setattr(routing.secrets, 'randbelow', lambda _: 0)

    def write(**changes):
        value = {'percent': 5, 'expires': 1200, 'identity': 'a' * 64, 'url': routing.CANDIDATE}
        value.update(changes)
        path.write_text(json.dumps(value))

    write()
    return write


def test_route_affinity_and_kill_does_not_reenter(lease):
    route = routing.ShapeRoute()
    assert route.resolve() == routing.CANDIDATE
    assert route.resolve() == routing.CANDIDATE
    lease(percent=0)
    assert route.resolve() is None
    lease()
    assert route.resolve() is None
    assert route.arm == 'canary'  # intent-to-treat survives rollback


@pytest.mark.parametrize(
    'changes',
    [
        {'expires': 999},
        {'expires': 1400},
        {'percent': -1},
        {'percent': 6},
        {'percent': float('nan')},
        {'url': 'https://api.omi.me'},
        {'identity': 'uid'},
        {'expires': '1200'},
    ],
)
def test_invalid_config_routes_baseline(lease, changes):
    lease(**changes)
    assert routing.ShapeRoute().resolve() is None


def test_identity_change_drains_old_session(lease):
    route = routing.ShapeRoute()
    route.resolve()
    lease(identity='b' * 64)
    assert route.resolve() is None
    assert routing.ShapeRoute().resolve() == routing.CANDIDATE


def test_control_cannot_be_promoted_mid_session(lease):
    lease(percent=0)
    route = routing.ShapeRoute()
    assert route.resolve() is None
    lease(percent=5)
    assert route.resolve() is None


def test_replacement_threads_cannot_see_half_initialized_assignment(lease, monkeypatch):
    entered, release, second_finished = threading.Event(), threading.Event(), threading.Event()

    def draw(_):
        entered.set()
        assert release.wait(5)
        return 0

    monkeypatch.setattr(routing.secrets, 'randbelow', draw)
    route = routing.ShapeRoute()

    def second():
        result = route.resolve()
        second_finished.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(route.resolve)
        assert entered.wait(5)
        another = pool.submit(second)
        try:
            assert not second_finished.wait(0.05)
        finally:
            release.set()
        assert first.result() == another.result() == routing.CANDIDATE


def test_fraction_not_replica_fraction(lease, monkeypatch):
    monkeypatch.setattr(routing.secrets, 'randbelow', lambda _: 50_000)
    assert routing.ShapeRoute().resolve() is None
    monkeypatch.setattr(routing.secrets, 'randbelow', lambda _: 49_999)
    assert routing.ShapeRoute().resolve() == routing.CANDIDATE


def healthy():
    values = {k: 0.0 for k in watcher.queries()}
    values.update(gpu_count=1, gpu_nonzero=5, gpu_samples=60, ready=1, listeners_up=1, listener_coverage=1)
    for arm in ('control', 'canary'):
        values.update(
            {f'{arm}_first_count': 100, f'{arm}_first_p95': 10, f'{arm}_post_count': 100, f'{arm}_post_p95': 1}
        )
    return values


def test_watcher_full_window_and_sample_floor():
    values = healthy()
    assert watcher.evaluate(values, 899)[0] == 'WARMUP'
    assert watcher.evaluate(values, 900)[0] == 'ARMED'
    values['canary_first_count'] = 8
    assert watcher.evaluate(values, 900)[0] == 'HOLD'


@pytest.mark.parametrize(
    'key,value,state',
    [
        ('gpu_stale', 61, 'HOLD'),
        ('canary_first_count', None, 'HOLD'),
        ('listener_coverage', 0.5, 'HOLD'),
        ('canary_bad', 1, 'ABORT'),
        ('queue', 0.75, 'ABORT'),
        ('restarts', 1, 'ABORT'),
        ('ready', 0, 'ABORT'),
        ('canary_first_p95', 30, 'ABORT'),
        ('canary_post_p95', 3, 'ABORT'),
        ('gpu_count', 2, 'ABORT'),
        ('gpu_nonzero', 0, 'HOLD'),
        ('gpu_samples', 50, 'HOLD'),
        ('gpu_oom', 1, 'ABORT'),
        ('gpu_fatal', 1, 'ABORT'),
        ('gpu_error_stale', 61, 'HOLD'),
        ('gpu_fatal', None, 'HOLD'),
    ],
)
def test_guard_bad_signal(key, value, state):
    values = healthy()
    values[key] = value
    assert watcher.evaluate(values, 901)[0] == state


@pytest.mark.parametrize(
    'key', ['canary_bad', 'canary_first_p95', 'canary_post_p95', 'throttle', 'gpu_oom', 'gpu_fatal']
)
def test_previous_revision_history_cannot_trip_during_warmup(key):
    values = healthy()
    values[key] = 100
    assert watcher.evaluate(values, 899)[0] == 'WARMUP'
    assert watcher.evaluate(values, 900)[0] == 'ABORT'


def test_current_queue_pressure_trips_even_in_warmup():
    values = healthy()
    values['queue'] = 0.75
    assert watcher.evaluate(values, 1)[0] == 'ABORT'


def test_operator_kill_cannot_be_overwritten(monkeypatch):
    monkeypatch.setenv('KUBECONFIG', '/tmp/fresh-test-config')
    cluster = watcher.Cluster('explicit-test-context')
    stored = {'data': {'route.json': '{"percent":0}'}}

    def call(*args, payload=None):
        if args[0] == 'get':
            return {'data': dict(stored['data'])}
        stored['data'] = dict(payload['data'])
        return {}

    monkeypatch.setattr(cluster, 'call', call)
    assert cluster.route('a' * 64, 5)
    stored['data'] = {'route.json': '{"percent":0}'}
    assert not cluster.route('a' * 64, 5)
    assert json.loads(stored['data']['route.json'])['percent'] == 0


def test_listener_rollout_resets_identity_and_mixed_images_block(monkeypatch):
    monkeypatch.setenv('KUBECONFIG', '/tmp/fresh-test-config')
    cluster = watcher.Cluster('explicit-test-context')
    container = {'resources': {'limits': {'memory': '12Gi'}}}
    candidate = {
        'metadata': {'uid': 'candidate'},
        'spec': {'nodeName': 'candidate-node', 'containers': [container]},
        'status': {'containerStatuses': [{'ready': True, 'restartCount': 0, 'imageID': 'parakeet-digest'}]},
    }
    control = {**candidate, 'metadata': {'uid': 'baseline'}}
    listener = {
        'spec': {
            'containers': [
                {'env': [{'name': 'PARAKEET_SHAPE_CANARY_FILE', 'value': '/var/run/parakeet-shape/route.json'}]}
            ]
        },
        'status': {'containerStatuses': [{'ready': True, 'imageID': 'listen-image-1'}]},
    }
    listeners = [listener]
    node = {
        'metadata': {
            'labels': {
                'node.kubernetes.io/instance-type': 'g2-standard-4',
                'cloud.google.com/gke-nodepool': 'parakeet-g24-canary',
            }
        },
        'status': {'allocatable': {'nvidia.com/gpu': '1'}},
        'spec': {'taints': [{'key': 'omi.ai/parakeet-shape-canary', 'value': 'g24', 'effect': 'NoSchedule'}]},
    }

    def call(*args, payload=None):
        if args[1] == 'node':
            return node
        selector = args[3]
        return {
            'items': (
                listeners
                if selector.endswith('backend-listen')
                else [candidate if selector.endswith('g24') else control]
            )
        }

    monkeypatch.setattr(cluster, 'call', call)
    before = cluster.identity('routing-revision')
    listener['status']['containerStatuses'][0]['imageID'] = 'listen-image-2'
    assert cluster.identity('routing-revision') != before
    listeners.append({**listener, 'status': {'containerStatuses': [{'ready': True, 'imageID': 'listen-image-1'}]}})
    with pytest.raises(ValueError, match='listener_rollout_incomplete'):
        cluster.identity('routing-revision')


def test_harness_rejects_stale_or_changed_watcher(tmp_path):
    status_file = tmp_path / 'status.json'
    status = {'state': 'ARMED', 'observed_at': qualify.time.time(), 'age': 900, 'identity': 'a'}
    status_file.write_text(json.dumps(status))
    qualify.require_watcher(status_file, 'a')
    status_file.write_text(json.dumps({**status, 'age': 899}))
    with pytest.raises(ValueError):
        qualify.require_watcher(status_file, 'a')
    status_file.write_text(json.dumps({**status, 'observed_at': 0}))
    with pytest.raises(ValueError):
        qualify.require_watcher(status_file, 'a')
    status_file.write_text(json.dumps(status))
    with pytest.raises(ValueError):
        qualify.require_watcher(status_file, 'b')


def test_uncertainty_is_hold_not_parity():
    assert qualify.compare([1] * 8, [1] * 8)['state'] == 'HOLD'
    assert qualify.compare([2] * 500, [1] * 500)['state'] == 'PASS'
    assert qualify.compare([1] * 500, [2] * 500)['state'] == 'ABORT'
    assert qualify.compare(list(range(500)), list(range(500)))['state'] == 'HOLD'


def test_quality_catches_tail_and_speaker_loss():
    fixture = {'reference': 'blue bird sings'}
    control = [{'text': 'blue bird sings', 'start': 1, 'end': 3, 'speaker': 'SPEAKER_0'}]
    assert qualify.quality(fixture, control, control)['pass']
    assert not qualify.quality(fixture, control, [{**control[0], 'speaker': 'SPEAKER_1'}])['pass']
    assert not qualify.quality(fixture, control, [{**control[0], 'end': 2}])['pass']
    assert not qualify.quality(fixture, control, [{**control[0], 'text': 'blue bird'}])['pass']


def test_chart_isolated_one_gpu_and_internal_service():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            'helm',
            'template',
            'prod-omi-parakeet-g24',
            str(root / 'backend/charts/parakeet'),
            '-f',
            str(root / 'backend/charts/parakeet/prod_omi_parakeet_values.yaml'),
            '-f',
            str(root / 'backend/charts/parakeet/g24_canary_values.yaml'),
            '--set',
            'image.digest=sha256:' + 'a' * 64,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    objects = [v for v in yaml.safe_load_all(result.stdout) if v]
    assert not any(v['kind'] in ('Ingress', 'HTTPRoute', 'BackendConfig', 'HorizontalPodAutoscaler') for v in objects)
    deployment = next(v for v in objects if v['kind'] == 'Deployment')
    assert deployment['spec']['replicas'] == 1
    pod = deployment['spec']['template']['spec']
    assert 'affinity' not in pod
    assert pod['nodeSelector']['cloud.google.com/gke-nodepool'] == 'parakeet-g24-canary'
    assert pod['containers'][0]['resources']['limits'] == {'cpu': 3, 'memory': '12Gi', 'nvidia.com/gpu': 1}
    assert '@sha256:' in pod['containers'][0]['image']
    service = next(v for v in objects if v['kind'] == 'Service' and v['metadata']['name'] == 'prod-omi-parakeet-g24')
    assert service['spec']['type'] == 'ClusterIP'
    assert 'annotations' not in service['metadata']


def test_listener_projection_is_opt_in_and_keeps_existing_volumes():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            'helm',
            'template',
            'prod-omi-backend-listen',
            str(root / 'backend/charts/backend-listen'),
            '-f',
            str(root / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml'),
            '--set',
            'image.tag=local-test',
            '--set',
            'parakeetShapeCanary.enabled=true',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    objects = [v for v in yaml.safe_load_all(result.stdout) if v]
    deployment = next(v for v in objects if v['kind'] == 'Deployment')
    spec = deployment['spec']['template']['spec']
    mount = next(v for v in spec['containers'][0]['volumeMounts'] if v['name'] == 'parakeet-shape-route')
    assert 'subPath' not in mount and mount['readOnly']
    route = next(v for v in objects if v['kind'] == 'ConfigMap' and v['metadata']['name'] == 'parakeet-shape-route')
    assert json.loads(route['data']['route.json'])['percent'] == 0
