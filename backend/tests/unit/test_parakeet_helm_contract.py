"""Rendered deploy contracts for Parakeet live-stream capacity ownership."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / 'backend' / 'charts' / 'parakeet'


def _values(environment: str) -> dict:
    path = CHART / f'{environment}_omi_parakeet_values.yaml'
    loaded = yaml.safe_load(path.read_text(encoding='utf-8'))
    assert isinstance(loaded, dict)
    return loaded


def _literal_env(values: dict) -> dict[str, str]:
    return {
        str(entry['name']): str(entry['value'])
        for entry in values.get('env', [])
        if isinstance(entry, dict) and 'name' in entry and 'value' in entry
    }


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_parakeet_values_own_explicit_stream_capacity_and_allocation(environment):
    values = _values(environment)
    env = _literal_env(values)

    assert env['PARAKEET_STREAM_CAPACITY'] == '25'
    assert env['PARAKEET_STREAM_ALLOCATION_PERCENT'] == '100'
    assert env['PARAKEET_CUDA_GRAPHS'] == 'false'
    assert int(values['autoscaling']['requestsPerPod']) < int(env['PARAKEET_STREAM_CAPACITY'])


def test_prod_parakeet_autoscaling_and_zone_spread_contract():
    values = _values('prod')

    assert values['autoscaling']['minReplicas'] == 3
    assert values['autoscaling']['maxReplicas'] == 7
    assert values['topologySpreadConstraints'] == [
        {
            'maxSkew': 1,
            'topologyKey': 'topology.kubernetes.io/zone',
            'whenUnsatisfiable': 'ScheduleAnyway',
        }
    ]


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_parakeet_probes_remove_and_recycle_fatal_gpu_workers(environment):
    values = _values(environment)

    assert values['readinessProbe'] == {
        'httpGet': {'path': '/health', 'port': 8080},
        'failureThreshold': 1,
        'periodSeconds': 10,
    }
    assert values['livenessProbe'] == {
        'httpGet': {'path': '/health', 'port': 8080},
        'failureThreshold': 3,
        'periodSeconds': 10,
    }
    assert values['startupProbe'] == {
        'httpGet': {'path': '/health', 'port': 8080},
        'failureThreshold': 180 if environment == 'dev' else 60,
        'periodSeconds': 10,
    }
    assert values.get('progressDeadlineSeconds') == (2100 if environment == 'dev' else None)


def test_rendered_prod_deployment_contains_stream_admission_settings():
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')

    rendered = subprocess.run(
        [
            helm,
            'template',
            'prod-omi-parakeet',
            str(CHART),
            '-f',
            str(CHART / 'prod_omi_parakeet_values.yaml'),
            '--set-string',
            'image.tag=abc1234',
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert 'name: PARAKEET_STREAM_CAPACITY\n              value: "25"' in rendered
    assert 'name: PARAKEET_STREAM_ALLOCATION_PERCENT\n              value: "100"' in rendered
    deployment = next(document for document in yaml.safe_load_all(rendered) if document.get('kind') == 'Deployment')
    hpa = next(
        document for document in yaml.safe_load_all(rendered) if document.get('kind') == 'HorizontalPodAutoscaler'
    )
    assert hpa['spec']['minReplicas'] == 3
    assert hpa['spec']['maxReplicas'] == 7
    metrics = hpa['spec']['metrics']
    request_metric = next(metric['pods'] for metric in metrics if metric['type'] == 'Pods')
    gpu_metric = next(metric['external'] for metric in metrics if metric['type'] == 'External')
    assert request_metric['metric']['name'] == 'parakeet_active_requests_total'
    assert request_metric['target'] == {'type': 'AverageValue', 'averageValue': '3'}
    assert gpu_metric['metric']['name'] == 'parakeet_gpu_utilization'
    assert gpu_metric['target'] == {'type': 'Value', 'value': '45'}
    assert hpa['spec']['behavior']['scaleUp']['policies'] == [{'type': 'Pods', 'value': 1, 'periodSeconds': 60}]
    assert 'progressDeadlineSeconds' not in deployment['spec']
    container = deployment['spec']['template']['spec']['containers'][0]
    assert container['readinessProbe']['httpGet']['path'] == '/health'
    assert container['readinessProbe']['failureThreshold'] == 1
    assert container['livenessProbe']['httpGet']['path'] == '/health'
    assert container['livenessProbe']['failureThreshold'] == 3
    assert deployment['spec']['template']['spec']['topologySpreadConstraints'] == [
        {
            'maxSkew': 1,
            'topologyKey': 'topology.kubernetes.io/zone',
            'whenUnsatisfiable': 'ScheduleAnyway',
            'labelSelector': {'matchLabels': deployment['spec']['selector']['matchLabels']},
        }
    ]


def test_rendered_dev_deployment_allows_cold_model_startup():
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')

    rendered = subprocess.run(
        [
            helm,
            'template',
            'dev-omi-parakeet',
            str(CHART),
            '-f',
            str(CHART / 'dev_omi_parakeet_values.yaml'),
            '--set-string',
            'image.tag=abc1234',
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    deployment = next(document for document in yaml.safe_load_all(rendered) if document.get('kind') == 'Deployment')
    assert deployment['spec']['progressDeadlineSeconds'] == 2100
    container = deployment['spec']['template']['spec']['containers'][0]
    assert container['startupProbe']['failureThreshold'] == 180


def test_parakeet_deploy_workflow_selects_environment_owned_values_file():
    workflow = (ROOT / '.github' / 'workflows' / 'gcp_parakeet.yml').read_text(encoding='utf-8')

    assert './backend/charts/${{ env.SERVICE }}/${{ vars.ENV }}_omi_${{ env.SERVICE }}_values.yaml' in workflow


@pytest.mark.parametrize('dockerfile_name', ['Dockerfile', 'Dockerfile.nim'])
def test_parakeet_pod_runs_one_uvicorn_process_for_its_gpu(dockerfile_name):
    dockerfile = (ROOT / 'backend' / 'parakeet' / dockerfile_name).read_text(encoding='utf-8')

    command = next(line for line in dockerfile.splitlines() if line.startswith('CMD ["uvicorn"'))
    assert '--workers' not in command


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_headless_batch_pressure_service_selects_each_ready_gpu_pod(environment):
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')
    rendered = subprocess.run(
        [
            helm,
            'template',
            f'{environment}-omi-parakeet',
            str(CHART),
            '-f',
            str(CHART / f'{environment}_omi_parakeet_values.yaml'),
            '--set-string',
            'image.tag=abc1234',
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    services = {
        document['metadata']['name']: document
        for document in yaml.safe_load_all(rendered)
        if document and document.get('kind') == 'Service'
    }
    name = f'{environment}-omi-parakeet'
    assert services[f'{name}-headless']['spec']['clusterIP'] == 'None'
    assert services[f'{name}-headless']['spec']['selector'] == services[name]['spec']['selector']
    assert services[f'{name}-headless']['spec']['ports'][0]['port'] == 8080


def test_prod_mixed_load_headroom_is_consistent_across_runtime_and_helm():
    listen = yaml.safe_load((ROOT / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml').read_text())
    env = _literal_env(listen)
    overlay = yaml.safe_load((ROOT / 'backend/deploy/runtime_env/prod.overlay.yaml').read_text())
    runtime = overlay['overlay']['gke']['backend-listen']['env']
    expected = {
        'PARAKEET_WINDOW_MAX_SESSIONS': '16',
        'PARAKEET_BATCH_PRESSURE_MIN_REPLICAS': '3',
        'PARAKEET_BATCH_PRESSURE_MAX_LIVE_PENDING_PER_REPLICA': '8',
        'PARAKEET_BATCH_PRESSURE_MAX_LIVE_OLDEST_SECONDS': '1.5',
    }
    for name, value in expected.items():
        assert env[name] == runtime[name]['value'] == value
    hpa = _values('prod')['autoscaling']
    assert hpa['requestsPerPod'] == 3
    assert hpa['targetGPUUtilization'] == 45
    assert hpa['requestsPerPod'] < int(env['PARAKEET_BATCH_PRESSURE_MAX_LIVE_PENDING_PER_REPLICA'])
    assert float(env['PARAKEET_BATCH_PRESSURE_MAX_LIVE_OLDEST_SECONDS']) < float(
        env['PARAKEET_WINDOW_POST_TIMEOUT_SECONDS']
    )
    assert hpa['minReplicas'] == int(env['PARAKEET_BATCH_PRESSURE_MIN_REPLICAS'])
