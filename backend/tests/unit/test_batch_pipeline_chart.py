"""Offline Helm contract: no deployment, dedicated pool and scoped queue age."""

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / 'charts' / 'batch-pipeline-worker'


def render(*arguments):
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('Helm unavailable; render check runs on the packaging host')
    return subprocess.run(
        [helm, 'template', 'synthetic-worker', str(CHART), '--namespace', 'synthetic', *arguments],
        capture_output=True,
        text=True,
    )


def enabled_arguments():
    return [
        '--set',
        'enabled=true',
        '--set',
        'image.repository=synthetic/worker',
        '--set',
        'image.digest=sha256:' + 'a' * 64,
        '--set',
        'serviceAccountName=synthetic-worker',
        '--set',
        'bucket=synthetic-batch',
        '--set',
        'secretName=synthetic-secret',
        '--set',
        'dataPlaneProject=demo-synthetic',
    ]


def test_default_chart_has_no_resources_or_admission():
    values = yaml.safe_load((CHART / 'values.yaml').read_text())
    assert values['enabled'] is False and values['autoscaling']['minReplicas'] == 1
    result = render()
    assert result.returncode == 0 and list(yaml.safe_load_all(result.stdout)) == []


def test_enabled_chart_pins_gpu_pool_image_and_age_autoscaling():
    result = render(*enabled_arguments())
    assert result.returncode == 0, result.stderr
    manifests = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    pod = manifests['Deployment']['spec']['template']['spec']
    assert pod['nodeSelector']['cloud.google.com/gke-nodepool'] == 'diarizer-batch-pool'
    container = pod['containers'][0]
    assert '@sha256:' in container['image']
    assert container['resources']['limits']['nvidia.com/gpu'] == '1'
    env = {v['name']: v.get('value') for v in container['env']}
    assert env['BATCH_PIPELINE_ENABLED'] == 'false' and env['BATCH_PIPELINE_PERCENT'] == '0'
    assert env['BATCH_PIPELINE_POOL_KIND'] == 'dedicated_batch'
    assert env['BATCH_PIPELINE_SHARED_LIVE_ENABLED'] == 'false'
    hpa = manifests['HorizontalPodAutoscaler']['spec']
    assert hpa['minReplicas'] == 1 and hpa['behavior']['scaleDown']['stabilizationWindowSeconds'] == 300
    assert {m['external']['metric']['selector']['matchLabels']['priority'] for m in hpa['metrics']} == {
        'fresh',
        'recent',
        'deep',
    }
    assert all(
        m['external']['metric']['selector']['matchLabels']['worker_release'] == 'synthetic-worker'
        for m in hpa['metrics']
    )


def test_enabled_chart_refuses_unpinned_image_and_unsampled_scale_to_zero():
    assert render('--set', 'enabled=true').returncode != 0
    result = render(*enabled_arguments(), '--set', 'autoscaling.minReplicas=0')
    assert result.returncode != 0 and 'independent sampler' in result.stderr


def test_joint_image_contains_runtime_first_party_import_closure():
    # This image has no deployment workflow by design. Exercise the existing
    # closure guard directly until a lead-authorized publication workflow exists.
    from dataclasses import replace
    from scripts.runtime_image_contracts import load_contracts, source_closure_errors

    base = next(image for image in load_contracts() if image.name == 'backend')
    contract = replace(
        base,
        name='batch-pipeline-worker',
        dockerfile=CHART.parents[1] / 'diarizer' / 'Dockerfile.batch-pipeline',
        deployment_workflows=(),
        entrypoints=('diarizer.batch_pipeline_runtime',),
    )
    assert source_closure_errors(contract) == []
