"""Rendered deploy contracts for Parakeet live-stream capacity ownership."""

from __future__ import annotations

import json
import math
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


def _render(environment: str, release: str, *, is_upgrade: bool = False) -> list[dict]:
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')

    command = [
        helm,
        'template',
        release,
        str(CHART),
        '-f',
        str(CHART / f'{environment}_omi_parakeet_values.yaml'),
        '-f',
        str(CHART / f'{environment}_omi_parakeet_stream_values.yaml'),
        '--set-string',
        'image.digest=sha256:' + 'a' * 64,
        '--set-string',
        'image.tag=',
    ]
    if is_upgrade:
        command.append('--is-upgrade')
    rendered = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [document for document in yaml.safe_load_all(rendered) if isinstance(document, dict)]


def _document(documents: list[dict], kind: str) -> dict:
    return next(document for document in documents if document.get('kind') == kind)


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_parakeet_values_own_explicit_stream_capacity_and_allocation(environment):
    values = _values(environment)
    env = _literal_env(values)

    assert env['PARAKEET_STREAM_CAPACITY'] == '25'
    assert env['PARAKEET_STREAM_ALLOCATION_PERCENT'] == '100'
    assert env['PARAKEET_CUDA_GRAPHS'] == 'false'
    assert int(values['autoscaling']['requestsPerPod']) < int(env['PARAKEET_STREAM_CAPACITY'])


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
        'failureThreshold': 60,
        'periodSeconds': 10,
    }


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
    container = deployment['spec']['template']['spec']['containers'][0]
    assert container['readinessProbe']['httpGet']['path'] == '/health'
    assert container['readinessProbe']['failureThreshold'] == 1
    assert container['livenessProbe']['httpGet']['path'] == '/health'
    assert container['livenessProbe']['failureThreshold'] == 3


@pytest.mark.parametrize(
    ('environment', 'peak', 'expected_min', 'expected_pdb'),
    [('dev', 10, 2, 2), ('prod', 600, 40, 39)],
)
def test_stream_overlay_sizes_warm_floor_from_peak_reserve_and_failure(
    environment: str, peak: int, expected_min: int, expected_pdb: int
):
    values = yaml.safe_load((CHART / f'{environment}_omi_parakeet_stream_values.yaml').read_text(encoding='utf-8'))
    assert isinstance(values, dict)
    plan = values['capacityPlan']
    autoscaling = values['autoscaling']

    target = int(autoscaling['streamDemandPerPod'])
    calculated_min = max(
        2,
        math.ceil(peak * (1 + int(plan['headroomPercent']) / 100) / target) + int(plan['failureReplicas']),
    )
    assert plan['peakConcurrentStreams'] == peak
    assert calculated_min == expected_min
    assert autoscaling['minReplicas'] == calculated_min
    assert values['podDisruptionBudget']['minAvailable'] == expected_pdb
    assert autoscaling['maxReplicas'] >= autoscaling['minReplicas']


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_rendered_stream_release_owns_mode_models_and_internal_service(environment: str):
    documents = _render(environment, f'{environment}-omi-parakeet-stream')
    deployment = _document(documents, 'Deployment')
    container = deployment['spec']['template']['spec']['containers'][0]
    env = {entry['name']: entry.get('value') for entry in container['env']}

    assert env['PARAKEET_SERVICE_MODE'] == 'stream'
    assert 'PARAKEET_MODEL' not in env
    assert env['PARAKEET_STREAM_MODEL'] == 'nvidia/parakeet-tdt-0.6b-v3'
    model_env = {name: value for name, value in env.items() if name in {'PARAKEET_MODEL', 'PARAKEET_STREAM_MODEL'}}
    assert model_env == {'PARAKEET_STREAM_MODEL': 'nvidia/parakeet-tdt-0.6b-v3'}
    assert env['PARAKEET_STREAM_CAPACITY'] == '25'
    assert env['PARAKEET_STREAM_ALLOCATION_PERCENT'] == '100'
    expected_repository = (
        'gcr.io/based-hardware-dev/parakeet' if environment == 'dev' else 'gcr.io/based-hardware/parakeet'
    )
    assert container['image'] == f'{expected_repository}@sha256:{"a" * 64}'
    assert container['readinessProbe']['httpGet']['path'] == '/health'
    assert container['readinessProbe']['failureThreshold'] == 1
    assert container['resources']['requests']['nvidia.com/gpu'] == 1
    assert deployment['spec']['strategy']['rollingUpdate'] == {'maxUnavailable': 0, 'maxSurge': 1}

    service = next(
        document
        for document in documents
        if document.get('kind') == 'Service' and not document['metadata']['name'].endswith('-metrics')
    )
    assert service['metadata']['name'] == f'{environment}-omi-parakeet-stream'
    assert service['spec']['type'] == 'LoadBalancer'
    assert service['spec']['ports'] == [
        {'port': 8080, 'targetPort': 8080, 'protocol': 'TCP', 'name': 'http'},
    ]
    assert service['metadata']['annotations']['networking.gke.io/load-balancer-type'] == 'Internal'
    assert 'cloud.google.com/neg' not in service['metadata']['annotations']
    backend_config_name = json.loads(service['metadata']['annotations']['cloud.google.com/backend-config'])['default']
    assert backend_config_name == f'{environment}-omi-parakeet-stream-backend-config'
    assert 'loadBalancerIP' not in service['spec']
    assert not any(document.get('kind') == 'Ingress' for document in documents)

    backend_config = _document(documents, 'BackendConfig')
    assert backend_config['metadata']['name'] == backend_config_name
    assert backend_config['spec']['connectionDraining']['drainingTimeoutSec'] == 35
    assert backend_config['spec']['healthCheck']['port'] == 8080


@pytest.mark.parametrize(('environment', 'expected_min'), [('dev', 2), ('prod', 40)])
def test_rendered_stream_release_has_failure_reserve_hpa_and_drain_contract(environment: str, expected_min: int):
    documents = _render(environment, f'{environment}-omi-parakeet-stream')
    deployment = _document(documents, 'Deployment')
    pod_spec = deployment['spec']['template']['spec']
    hpa = _document(documents, 'HorizontalPodAutoscaler')
    pdb = _document(documents, 'PodDisruptionBudget')

    assert hpa['spec']['minReplicas'] == expected_min
    assert hpa['spec']['maxReplicas'] == (4 if environment == 'dev' else 60)
    metrics = {
        metric['pods']['metric']['name']: metric['pods']['target']['averageValue']
        for metric in hpa['spec']['metrics']
        if metric['type'] == 'Pods'
    }
    assert metrics['parakeet_active_streams'] == '20'
    assert metrics['parakeet_stream_demand'] == '20'
    assert 'parakeet_gpu_utilization' not in metrics
    assert pdb['spec']['minAvailable'] == (2 if environment == 'dev' else 39)
    assert 'maxUnavailable' not in pdb['spec']

    anti_affinity = pod_spec['affinity']['podAntiAffinity']['requiredDuringSchedulingIgnoredDuringExecution']
    assert any(
        item['topologyKey'] == 'kubernetes.io/hostname'
        and item['labelSelector']['matchLabels'] == {'app.kubernetes.io/name': 'parakeet'}
        for item in anti_affinity
    )
    assert pod_spec['nodeSelector']['cloud.google.com/gke-accelerator'] == 'nvidia-l4'
    assert pod_spec['nodeSelector']['service'] == 'parakeet-stream'
    assert pod_spec['terminationGracePeriodSeconds'] == 105
    container = pod_spec['containers'][0]
    assert container['startupProbe']['failureThreshold'] * container['startupProbe']['periodSeconds'] >= 900
    assert pod_spec['terminationGracePeriodSeconds'] >= 5 + 30 + 30 + 30 + 5 + 5
    lifecycle_command = pod_spec['containers'][0]['lifecycle']['preStop']['exec']['command'][-1]
    assert 'POST http://127.0.0.1:8080/__internal/drain' in lifecycle_command
    assert 'sleep 30' in lifecycle_command


@pytest.mark.parametrize(('environment', 'expected_min'), [('dev', 2), ('prod', 40)])
def test_stream_install_seeds_hpa_warm_floor_but_upgrade_defers_to_hpa(environment: str, expected_min: int):
    installed = _document(_render(environment, f'{environment}-omi-parakeet-stream'), 'Deployment')
    upgraded = _document(_render(environment, f'{environment}-omi-parakeet-stream', is_upgrade=True), 'Deployment')

    assert installed['spec']['replicas'] == expected_min
    assert 'replicas' not in upgraded['spec']


def test_batch_values_render_as_a_distinct_batch_owner_without_stream_model():
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
    documents = [document for document in yaml.safe_load_all(rendered) if isinstance(document, dict)]
    deployment = _document(documents, 'Deployment')
    env = {
        entry['name']: entry.get('value') for entry in deployment['spec']['template']['spec']['containers'][0]['env']
    }
    assert env['PARAKEET_SERVICE_MODE'] == 'batch'
    assert env['PARAKEET_MODEL'] == 'nvidia/parakeet-tdt-0.6b-v3'
    assert 'PARAKEET_STREAM_MODEL' not in env
    assert (
        env
        and deployment['spec']['template']['spec']['containers'][0]['image'] == 'gcr.io/based-hardware/parakeet:abc1234'
    )
    assert any(document.get('kind') == 'Ingress' for document in documents)


def test_stream_release_rejects_a_mutable_tag_without_an_image_digest():
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')
    completed = subprocess.run(
        [
            helm,
            'template',
            'prod-omi-parakeet-stream',
            str(CHART),
            '-f',
            str(CHART / 'prod_omi_parakeet_values.yaml'),
            '-f',
            str(CHART / 'prod_omi_parakeet_stream_values.yaml'),
            '--set-string',
            'image.tag=abc1234',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert 'image.digest is required for this release' in completed.stderr


def test_parakeet_deploy_workflow_selects_environment_owned_values_file():
    workflow = (ROOT / '.github' / 'workflows' / 'gcp_parakeet.yml').read_text(encoding='utf-8')

    assert './backend/charts/${{ env.SERVICE }}/${{ vars.ENV }}_omi_${{ env.SERVICE }}_values.yaml' in workflow


@pytest.mark.parametrize('dockerfile_name', ['Dockerfile', 'Dockerfile.nim'])
def test_parakeet_pod_runs_one_uvicorn_process_for_its_gpu(dockerfile_name):
    dockerfile = (ROOT / 'backend' / 'parakeet' / dockerfile_name).read_text(encoding='utf-8')

    command = next(line for line in dockerfile.splitlines() if line.startswith('CMD ["uvicorn"'))
    assert '--workers' not in command
