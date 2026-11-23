"""Service identity must reach both GMP and the in-cluster Prometheus."""

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

CHARTS = Path(__file__).resolve().parents[2] / 'charts'


@pytest.fixture
def helm():
    executable = shutil.which('helm')
    if executable is None:
        pytest.skip('helm is not installed')
    return executable


@pytest.mark.parametrize('stage', ['dev', 'prod'])
@pytest.mark.parametrize(
    'chart,suffix',
    [('backend-listen', 'backend_listen'), ('pusher', 'pusher'), ('batch-pipeline-worker', 'batch-pipeline-worker')],
)
def test_workload_service_labels_render_and_are_exported(helm, stage, chart, suffix):
    directory = CHARTS / chart
    image = (
        ['--set-string', 'image.digest=sha256:' + 'a' * 64]
        if chart == 'batch-pipeline-worker'
        else ['--set-string', 'image.tag=synthetic']
    )
    result = subprocess.run(
        [
            helm,
            'template',
            'synthetic',
            str(directory),
            '-n',
            f'{stage}-omi-backend',
            '-f',
            str(directory / f'{stage}_omi_{suffix}_values.yaml'),
            *image,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    deployments = [doc for doc in docs if doc['kind'] == 'Deployment']
    monitors = [doc for doc in docs if doc['kind'] == 'PodMonitoring']
    for deployment in deployments:
        pod = deployment['spec']['template']
        service = 'record-seal-worker' if deployment['metadata']['name'] == 'record-seal-worker' else chart
        assert pod['metadata']['labels']['service_name'] == service
        monitor = next(
            m for m in monitors if m['spec']['selector']['matchLabels'].items() <= pod['metadata']['labels'].items()
        )
        assert {'from': 'service_name', 'to': 'service_name'} in monitor['spec']['targetLabels']['fromPod']
    jobs = [doc for doc in docs if doc['kind'] == 'CronJob']
    if chart == 'batch-pipeline-worker' and stage == 'prod':
        assert {j['metadata']['name'] for j in jobs} == {'record-seal-repair', 'record-seal-sweeper'}
        for job in jobs:
            labels = job['spec']['jobTemplate']['spec']['template']['metadata']['labels']
            assert labels['service_name'] == job['metadata']['name']
        seal = next(d for d in deployments if d['metadata']['name'] == 'record-seal-worker')
        env = {entry['name']: entry.get('value') for entry in seal['spec']['template']['spec']['containers'][0]['env']}
        # This configuration intentionally serves an idle metrics endpoint.
        assert env['RECORD_SEAL_REPAIR_ENABLED'] == 'false'
    else:
        assert not jobs


def test_sync_backfill_pilot_service_label_is_exported(helm):
    result = subprocess.run(
        [
            helm,
            'template',
            'synthetic',
            str(CHARTS / 'sync-backfill-worker'),
            '--set-string',
            'image.repository=synthetic',
            '--set-string',
            'image.digest=sha256:' + 'a' * 64,
            '--set-string',
            'runtimeSecret=synthetic',
            '--set-string',
            'serviceAccount.gcpEmail=worker@synthetic.invalid',
            '--set-string',
            'worker.apiUrl=https://synthetic.run.app',
            '--set-string',
            'worker.audience=https://synthetic.run.app',
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    deployment = next(doc for doc in docs if doc['kind'] == 'Deployment')
    labels = deployment['spec']['template']['metadata']['labels']
    assert labels['service_name'] == 'sync-backfill-worker'
    monitor = next(doc for doc in docs if doc['kind'] == 'PodMonitoring')
    assert monitor['spec']['selector']['matchLabels'].items() <= labels.items()
    assert {'from': 'service_name', 'to': 'service_name'} in monitor['spec']['targetLabels']['fromPod']


@pytest.mark.parametrize('labels', [None, {}])
def test_batch_worker_accepts_empty_pod_labels(helm, tmp_path, labels):
    override = tmp_path / 'labels.yaml'
    override.write_text(yaml.safe_dump({'podLabels': labels}))
    directory = CHARTS / 'batch-pipeline-worker'
    result = subprocess.run(
        [
            helm,
            'template',
            'synthetic',
            str(directory),
            '-n',
            'prod-omi-backend',
            '-f',
            str(directory / 'prod_omi_batch-pipeline-worker_values.yaml'),
            '-f',
            str(override),
            '--set-string',
            'image.digest=sha256:' + 'a' * 64,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    deployments = [doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment']
    assert deployments
    for deployment in deployments:
        assert (
            deployment['spec']['selector']['matchLabels'].items()
            <= deployment['spec']['template']['metadata']['labels'].items()
        )


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_existing_prometheus_jobs_copy_the_same_pod_service_label(stage):
    values = yaml.safe_load(
        (CHARTS / 'monitoring/kube-prometheus-stack' / f'{stage}_omi_monitoring_values.yaml').read_text()
    )
    jobs = values['prometheus']['prometheusSpec']['additionalScrapeConfigs']
    names = {'backend-listen-metrics', 'pusher-metrics'}
    if stage == 'prod':
        names |= {'batch-pipeline-worker-metrics', 'record-seal-worker-metrics'}
    for name in names:
        job = next(job for job in jobs if job['job_name'] == name)
        assert {'source_labels': ['__meta_kubernetes_pod_label_service_name'], 'target_label': 'service_name'} in job[
            'relabel_configs'
        ]
