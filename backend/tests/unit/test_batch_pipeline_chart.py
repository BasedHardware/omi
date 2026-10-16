"""Offline Helm contract: no deployment, dedicated pool and scoped queue age."""

from pathlib import Path
import os
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
        'gcpServiceAccount=synthetic-worker@example.invalid',
        '--set',
        'nodeSelector.env=dev',
        '--set',
        'stage=dev',
        '--set',
        'namespace=batch_pipeline_dev',
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
    assert values['autoscaling']['enabled'] is False
    assert values['podMonitoring']['enabled'] is True
    assert values['worker']['batchSize'] == 8
    assert values['resources']['requests']['memory'] == '12Gi'
    assert values['resources']['limits']['memory'] == '14Gi'
    result = render()
    assert result.returncode == 0 and list(yaml.safe_load_all(result.stdout)) == []


def test_enabled_chart_pins_gpu_pool_image_and_age_autoscaling():
    result = render(*enabled_arguments(), '--set', 'autoscaling.enabled=true')
    assert result.returncode == 0, result.stderr
    manifests = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    pod = manifests['Deployment']['spec']['template']['spec']
    assert pod['nodeSelector'] == {
        'cloud.google.com/gke-nodepool': 'batch-pipeline-pool',
        'service': 'batch-pipeline',
        'env': 'dev',
    }
    assert {(item['key'], item['operator'], item['value'], item['effect']) for item in pod['tolerations']} == {
        ('omi.ai/batch-pipeline', 'Equal', 'true', 'NoSchedule'),
        ('nvidia.com/gpu', 'Equal', 'present', 'NoSchedule'),
    }
    assert manifests['ServiceAccount']['metadata']['annotations'] == {
        'iam.gke.io/gcp-service-account': 'synthetic-worker@example.invalid'
    }
    container = pod['containers'][0]
    assert '@sha256:' in container['image']
    assert container['resources']['limits']['nvidia.com/gpu'] == '1'
    env = {v['name']: v.get('value') for v in container['env']}
    assert env['BATCH_PIPELINE_MODEL_BATCH_SIZE'] == '8'
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
    result = render(*enabled_arguments(), '--set', 'autoscaling.enabled=true', '--set', 'autoscaling.minReplicas=0')
    assert result.returncode != 0 and 'independent sampler' in result.stderr


def test_enabled_release_scrapes_but_waits_for_live_series_before_autoscaling():
    result = render(*enabled_arguments())
    assert result.returncode == 0, result.stderr
    manifests = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    assert 'HorizontalPodAutoscaler' not in manifests
    assert manifests['Deployment']['spec']['replicas'] == 1
    monitor = manifests['PodMonitoring']['spec']
    assert monitor['selector']['matchLabels']['app.kubernetes.io/instance'] == 'synthetic-worker'
    assert monitor['endpoints'] == [{'port': 'http', 'path': '/metrics', 'interval': '15s'}]
    env = {v['name']: v for v in manifests['Deployment']['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_WORKER_RELEASE']['value'] == 'synthetic-worker'
    assert env['POD_NAMESPACE']['valueFrom']['fieldRef']['fieldPath'] == 'metadata.namespace'
    assert render(*enabled_arguments(), '--set', 'replicaCount=0').returncode != 0


@pytest.mark.parametrize(
    'environment,stage,namespace,project,bucket,gsa,secret',
    [
        (
            'dev',
            'dev',
            'batch_pipeline_dev',
            'based-hardware',
            'based-hardware-dev-batch-pipeline-staging',
            'batch-pipeline-worker@based-hardware-dev.iam.gserviceaccount.com',
            'dev-omi-backend-secrets',
        ),
        (
            'prod',
            'prod',
            'batch_pipeline_prod',
            'based-hardware',
            'based-hardware-batch-pipeline-staging',
            'batch-pipeline-worker@based-hardware.iam.gserviceaccount.com',
            'prod-omi-backend-secrets',
        ),
    ],
)
def test_environment_values_render_worker_identity_and_gpu_pool(
    environment, stage, namespace, project, bucket, gsa, secret
):
    values = CHART / f'{environment}_omi_batch-pipeline-worker_values.yaml'
    result = render('-f', str(values), '--set-string', 'image.digest=sha256:' + 'b' * 64)
    assert result.returncode == 0, result.stderr
    manifests = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    account = manifests['ServiceAccount']['metadata']
    assert account['name'] == 'batch-pipeline-worker'
    assert account['annotations']['iam.gke.io/gcp-service-account'] == gsa

    deployment = manifests['Deployment']
    assert deployment['spec']['progressDeadlineSeconds'] == 1800
    pod = deployment['spec']['template']['spec']
    assert deployment['spec']['replicas'] == 1
    assert pod['serviceAccountName'] == 'batch-pipeline-worker'
    assert pod['nodeSelector'] == {
        'cloud.google.com/gke-nodepool': 'batch-pipeline-pool',
        'service': 'batch-pipeline',
        'env': stage,
    }
    assert {(item['key'], item['operator'], item['value'], item['effect']) for item in pod['tolerations']} == {
        ('omi.ai/batch-pipeline', 'Equal', 'true', 'NoSchedule'),
        ('nvidia.com/gpu', 'Equal', 'present', 'NoSchedule'),
    }
    container = pod['containers'][0]
    project_env = {item['name']: item for item in container['env']}
    assert project_env['OMI_FIRESTORE_DATA_PLANE_PROJECT']['value'] == project
    assert project_env['OMI_ENV_STAGE']['value'] == stage
    assert project_env['BATCH_PIPELINE_NAMESPACE']['value'] == namespace
    assert project_env['BUCKET_BATCH_PIPELINE']['value'] == bucket
    defaults = yaml.safe_load((CHART / 'values.yaml').read_text())
    environment_values = yaml.safe_load(values.read_text())
    batch_size = environment_values.get('worker', {}).get('batchSize', defaults['worker']['batchSize'])
    assert batch_size == 8
    assert project_env['BATCH_PIPELINE_MODEL_BATCH_SIZE']['value'] == str(batch_size)
    assert container['resources']['requests']['memory'] == '12Gi'
    assert container['resources']['limits']['memory'] == '14Gi'
    assert container['resources']['requests']['cpu'] == '4'
    assert container['resources']['limits']['cpu'] == '8'
    assert container['resources']['requests']['nvidia.com/gpu'] == '1'
    assert container['resources']['limits']['nvidia.com/gpu'] == '1'
    for name in ('ENCRYPTION_SECRET', 'HUGGINGFACE_TOKEN'):
        assert project_env[name]['valueFrom']['secretKeyRef']['name'] == secret
    project_id = 'based-hardware-dev' if environment == 'dev' else 'based-hardware'
    assert container['image'] == f"gcr.io/{project_id}/batch-pipeline-worker@sha256:{'b' * 64}"
    assert 'HorizontalPodAutoscaler' not in manifests


@pytest.mark.parametrize('service,timeout', [('batch-pipeline-worker', '1800s'), ('diarizer', '600s')])
@pytest.mark.parametrize('rollout_exit', [0, 1])
def test_rollout_wait_covers_worker_startup_and_still_fails_on_timeout(tmp_path, service, timeout, rollout_exit):
    workflow = yaml.safe_load((CHART.parents[2] / '.github/workflows/gcp_diarizer.yml').read_text())
    step = next(step for step in workflow['jobs']['deploy']['steps'] if step.get('name') == 'Verify rollout')
    receipt = tmp_path / 'kubectl-arguments'
    kubectl = tmp_path / 'kubectl'
    kubectl.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$RECEIPT"\nexit "$ROLLOUT_EXIT"\n')
    kubectl.chmod(0o755)
    reporter = tmp_path / 'python3'
    reporter.write_text('#!/bin/sh\nexit 0\n')
    reporter.chmod(0o755)
    result = subprocess.run(
        ['bash', '-e', '-c', step['run']],
        env={
            **os.environ,
            'PATH': f'{tmp_path}:{os.environ["PATH"]}',
            'SERVICE': service,
            'DEPLOY_NAMESPACE': 'synthetic',
            'DEPLOY_ENV': 'dev',
            'TARGET_RELEASE': f'synthetic-{service}',
            'RECEIPT': str(receipt),
            'ROLLOUT_EXIT': str(rollout_exit),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == rollout_exit, result.stderr
    assert receipt.read_text().splitlines() == [
        '-n',
        'synthetic',
        'rollout',
        'status',
        f'deploy/synthetic-{service}',
        f'--timeout={timeout}',
    ]


def test_production_worker_refuses_missing_or_mismatched_policy_binding():
    values = CHART / 'prod_omi_batch-pipeline-worker_values.yaml'
    args = ['-f', str(values), '--set-string', 'image.digest=sha256:' + 'c' * 64]
    for override in ['worker.apiUrl=', 'worker.apiUrl=http://insecure.invalid', 'worker.audience=wrong']:
        result = render(*args, '--set-string', override)
        assert result.returncode != 0 and 'matching OIDC audience' in result.stderr


def test_production_worker_policy_binding_matches_accepted_identity():
    values = CHART / 'prod_omi_batch-pipeline-worker_values.yaml'
    config = yaml.safe_load(values.read_text())
    assert config['image']['digest'] == ''  # Workflow supplies the built prod digest.
    result = render('-f', str(values), '--set-string', 'image.digest=sha256:' + 'c' * 64)
    assert result.returncode == 0, result.stderr
    docs = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    env = {e['name']: e.get('value') for e in docs['Deployment']['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_WORKER_ENABLED'] == 'true'
    assert env['BATCH_PIPELINE_ENABLED'] == 'false'
    assert env['BATCH_PIPELINE_API_URL'] == config['worker']['apiUrl'] == config['worker']['audience']
    assert env['BATCH_PIPELINE_WORKER_AUDIENCE'] == config['worker']['audience']
    assert 'HorizontalPodAutoscaler' not in docs
