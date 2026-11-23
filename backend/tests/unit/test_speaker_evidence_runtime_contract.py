"""SCA-3684. Exercise the deployment inputs used to stop L2 observation."""

from pathlib import Path
import subprocess

import pytest
import yaml

from scripts import render_backend_runtime_env as renderer

BACKEND = Path(__file__).resolve().parents[2]
MODE = 'SPEAKER_EVIDENCE_MODE'
SERVICES = {'backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration', 'backend-projection-pump'}
JOB_READERS = {'x-connector-sync-job'}  # External memory capture may enter required source admission.
OTHER_JOBS = {'notifications-job', 'frame-request-retention-job', 'day3-reengagement-email-job'}


def test_cloud_run_reader_inventory(monkeypatch):
    prod = renderer._load_yaml(renderer.DEFAULT_MANIFEST)['environments']['prod']['cloud_run']
    assert set(prod['services']) == SERVICES
    assert set(prod['jobs']) == JOB_READERS | OTHER_JOBS
    for name in sorted(SERVICES | JOB_READERS):
        section = prod['services'][name] if name in SERVICES else prod['jobs'][name]
        for binding in section['env'].values():
            if 'env_var' in binding:
                monkeypatch.setenv(binding['env_var'], 'render-input')
        rendered = renderer._parse_deploy_cloud_run_env_vars(renderer._render_env_vars(section['env']))
        assert [value for key, value in rendered if key == MODE] == ['off'], name
        assert MODE not in section.get('secrets', {}), name
        assert MODE not in section.get('forbidden_env', []), name


@pytest.mark.parametrize(
    'chart,release',
    [
        ('backend-listen', 'prod-omi-backend-listen'),
        ('backend-listen', 'listen-parakeet'),
        ('backend-listen', 'listen-soniox'),
        ('backend-listen', 'listen-dg-canary'),
        ('backend-listen', 'listen-velma-canary'),
        ('pusher', 'prod-omi-pusher'),
        ('sync-backfill-worker', 'sync-backfill-worker'),
    ],
)
def test_helm_reader_pod_env(chart, release):
    path = BACKEND / 'charts' / chart
    if chart == 'sync-backfill-worker':
        # Its isolated utils.sync.worker_job child inherits this container env.
        options = [
            '--set-string',
            'image.repository=example/worker,image.digest=sha256:' + '0' * 64,
            '--set-string',
            'runtimeSecret=test,serviceAccount.gcpEmail=test@example.com',
            '--set-string',
            'worker.apiUrl=https://test.run.app,worker.audience=https://test.run.app',
        ]
    else:
        values = path / (
            'prod_omi_backend_listen_values.yaml' if chart == 'backend-listen' else 'prod_omi_pusher_values.yaml'
        )
        options = ['-f', str(values), '--set-string', 'image.tag=test']
        if chart == 'backend-listen':
            options.extend(['--set-string', 'serviceAccount.name=prod-omi-backend-listen'])
    result = subprocess.run(
        ['helm', 'template', release, str(path), '--namespace', 'prod-omi-backend', *options],
        check=True,
        capture_output=True,
        text=True,
    )
    (deployment,) = (doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    name = 'worker' if chart == 'sync-backfill-worker' else chart
    container = next(item for item in deployment['spec']['template']['spec']['containers'] if item['name'] == name)
    assert [entry for entry in container['env'] if entry['name'] == MODE] == [{'name': MODE, 'value': 'off'}]
