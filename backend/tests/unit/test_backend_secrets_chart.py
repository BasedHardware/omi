"""GMP's app-namespace token must follow the application's Secret Manager source."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('stage', ['dev', 'prod'])
@pytest.mark.parametrize('remote_key', [None, 'synthetic-rotated-metrics-source'])
def test_metrics_scrape_token_render(stage, remote_key, tmp_path):
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
