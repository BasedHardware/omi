"""Listen/pusher GMP discovery must match the serving pods and authenticated metrics route."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('chart,values_suffix', [('backend-listen', 'backend_listen'), ('pusher', 'pusher')])
@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_serving_podmonitoring_render(chart, values_suffix, stage):
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')
    chart_dir = ROOT / 'backend/charts' / chart
    command = [
        helm,
        'template',
        'synthetic-release',
        str(chart_dir),
        '--namespace',
        f'{stage}-omi-backend',
        '-f',
        str(chart_dir / f'{stage}_omi_{values_suffix}_values.yaml'),
        '--set-string',
        'image.tag=synthetic',
        '--set-string',
        'fullnameOverride=synthetic-serving',
        '--set-string',
        'nameOverride=synthetic-name',
    ]

    def render(*extra):
        result = subprocess.run(command + list(extra), check=True, capture_output=True, text=True, timeout=30)
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    default = render()
    monitors = [doc for doc in default if doc['kind'] == 'PodMonitoring']
    assert len(monitors) == 1
    monitor = monitors[0]
    assert monitor['apiVersion'] == 'monitoring.googleapis.com/v1'
    assert monitor['metadata']['name'] == 'synthetic-serving'
    deployment = next(doc for doc in default if doc['kind'] == 'Deployment')
    service = next(doc for doc in default if doc['kind'] == 'Service')
    selector = monitor['spec']['selector']['matchLabels']
    assert selector == deployment['spec']['selector']['matchLabels'] == service['spec']['selector']
    assert selector.items() <= deployment['spec']['template']['metadata']['labels'].items()
    port = deployment['spec']['template']['spec']['containers'][0]['ports'][0]
    assert port['name'] == service['spec']['ports'][0]['targetPort'] == 'http'
    assert port['containerPort'] == service['spec']['ports'][0]['port'] == 8080
    assert monitor['spec']['endpoints'] == [
        {
            'port': port['name'],
            'path': '/metrics',
            'interval': '15s',
            'authorization': {
                'type': 'Bearer',
                'credentials': {'secret': {'name': 'metrics-scrape-token', 'key': 'token'}},
            },
        }
    ]
    roles = [doc for doc in default if doc['kind'] == 'Role']
    bindings = [doc for doc in default if doc['kind'] == 'RoleBinding']
    assert len(roles) == len(bindings) == 1
    role, binding = roles[0], bindings[0]
    for resource in (role, binding):
        assert resource['apiVersion'] == 'rbac.authorization.k8s.io/v1'
        assert resource['metadata']['name'] == 'synthetic-serving-metrics-scrape'
        assert resource['metadata']['namespace'] == f'{stage}-omi-backend'
    assert role['rules'] == [
        {
            'apiGroups': [''],
            'resources': ['secrets'],
            'resourceNames': [monitor['spec']['endpoints'][0]['authorization']['credentials']['secret']['name']],
            'verbs': ['get', 'list', 'watch'],
        }
    ]
    assert binding['roleRef'] == {
        'apiGroup': 'rbac.authorization.k8s.io',
        'kind': 'Role',
        'name': role['metadata']['name'],
    }
    assert binding['subjects'] == [{'kind': 'ServiceAccount', 'name': 'collector', 'namespace': 'gmp-system'}]
    assert not any(doc['kind'] == 'Secret' for doc in default)
    assert render('--set', 'podMonitoring.enabled=true') == default
    assert render('--set', 'podMonitoring.enabled=false') == [
        doc for doc in default if doc['kind'] not in {'PodMonitoring', 'Role', 'RoleBinding'}
    ]
    overridden = next(
        doc for doc in render('--set-string', 'podMonitoring.interval=30s') if doc['kind'] == 'PodMonitoring'
    )
    assert overridden['spec']['endpoints'][0]['interval'] == '30s'
