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


def test_parakeet_deploy_workflow_selects_environment_owned_values_file():
    workflow = (ROOT / '.github' / 'workflows' / 'gcp_parakeet.yml').read_text(encoding='utf-8')

    assert './backend/charts/${{ env.SERVICE }}/${{ vars.ENV }}_omi_${{ env.SERVICE }}_values.yaml' in workflow


@pytest.mark.parametrize('dockerfile_name', ['Dockerfile', 'Dockerfile.nim'])
def test_parakeet_pod_runs_one_uvicorn_process_for_its_gpu(dockerfile_name):
    dockerfile = (ROOT / 'backend' / 'parakeet' / dockerfile_name).read_text(encoding='utf-8')

    command = next(line for line in dockerfile.splitlines() if line.startswith('CMD ["uvicorn"'))
    assert '--workers' not in command
