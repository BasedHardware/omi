"""GMP's app-namespace token must follow the application's Secret Manager source."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def _render_backend_secrets(stage, tmp_path, remote_key=None, include_metrics=True):
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')
    chart = ROOT / 'backend/charts/backend-secrets'
    values = yaml.safe_load((chart / f'{stage}_omi_backend_secrets_values.yaml').read_text())
    metrics_source = next(
        item for item in values['externalSecret']['secretKeys'] if item['secretKey'] == 'METRICS_SECRET'
    )
    assert metrics_source['remoteKey'] == 'METRICS_SECRET'
    if remote_key is not None:
        metrics_source['remoteKey'] = remote_key
    if not include_metrics:
        values['externalSecret']['secretKeys'].remove(metrics_source)
    values_file = tmp_path / 'values.yaml'
    values_file.write_text(yaml.safe_dump(values))
    result = subprocess.run(
        [
            helm,
            'template',
            f'{stage}-omi-backend-secrets',
            str(chart),
            '--namespace',
            f'{stage}-omi-backend',
            '-f',
            str(values_file),
            '--set',
            'gke.projectID=synthetic-project,gke.clusterLocation=synthetic-region,gke.clusterName=synthetic-cluster',
            '--set-string',
            'gsa.name=synthetic-eso@synthetic-project.iam.gserviceaccount.com',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    resources = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    return resources, values


@pytest.mark.parametrize('stage', ['dev', 'prod'])
@pytest.mark.parametrize('remote_key', [None, 'synthetic-rotated-metrics-source'])
def test_metrics_scrape_token_render(stage, remote_key, tmp_path):
    resources, values = _render_backend_secrets(stage, tmp_path, remote_key)
    externals = [doc for doc in resources if doc['kind'] == 'ExternalSecret']
    assert len(externals) == 2
    app = next(doc for doc in externals if doc['metadata']['name'] == values['externalSecret']['name'])
    scrape = next(doc for doc in externals if doc['metadata']['name'] == 'metrics-scrape-token-store')
    store = next(doc for doc in resources if doc['kind'] == 'SecretStore')
    assert scrape['apiVersion'] == app['apiVersion'] == 'external-secrets.io/v1beta1'
    assert scrape['metadata']['namespace'] == f'{stage}-omi-backend'
    assert scrape['spec']['refreshInterval'] == app['spec']['refreshInterval'] == '1h'
    assert (
        scrape['spec']['secretStoreRef']
        == app['spec']['secretStoreRef']
        == {
            'kind': 'SecretStore',
            'name': store['metadata']['name'],
        }
    )
    assert scrape['spec']['target'] == {'name': 'metrics-scrape-token', 'creationPolicy': 'Owner'}
    app_token = next(item for item in app['spec']['data'] if item['secretKey'] == 'METRICS_SECRET')
    assert scrape['spec']['data'] == [{'secretKey': 'token', 'remoteRef': app_token['remoteRef']}]
    assert app_token['remoteRef']['key'] == (remote_key or 'METRICS_SECRET')
    assert not any(doc['kind'] == 'Secret' for doc in resources)


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_metrics_scrape_token_absent_without_metrics_secret(stage, tmp_path):
    resources, values = _render_backend_secrets(stage, tmp_path, include_metrics=False)
    externals = [doc for doc in resources if doc['kind'] == 'ExternalSecret']
    assert len(externals) == 1
    assert externals[0]['metadata']['name'] == values['externalSecret']['name']
    assert not any(doc['metadata']['name'] == 'metrics-scrape-token-store' for doc in externals)


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_metrics_scrape_secret_cross_chart_contract(stage, tmp_path):
    resources, _ = _render_backend_secrets(stage, tmp_path)
    scrape = next(
        doc
        for doc in resources
        if doc['kind'] == 'ExternalSecret' and doc['metadata']['name'] == 'metrics-scrape-token-store'
    )
    target_name = scrape['spec']['target']['name']
    for chart, suffix in [('pusher', 'pusher'), ('backend-listen', 'backend_listen')]:
        chart_dir = ROOT / 'backend/charts' / chart
        result = subprocess.run(
            [
                shutil.which('helm'),
                'template',
                f'{stage}-omi-{chart}',
                str(chart_dir),
                '--namespace',
                f'{stage}-omi-backend',
                '-f',
                str(chart_dir / f'{stage}_omi_{suffix}_values.yaml'),
                '--set-string',
                'image.tag=synthetic',
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        serving = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
        monitors = [doc for doc in serving if doc['kind'] == 'PodMonitoring']
        roles = [doc for doc in serving if doc['kind'] == 'Role']
        assert len(monitors) == len(roles) == 1
        for monitor in monitors:
            for endpoint in monitor['spec']['endpoints']:
                assert endpoint['authorization']['credentials']['secret']['name'] == target_name
        for role in roles:
            for rule in role['rules']:
                assert rule['resourceNames'] == [target_name]
