"""Offline integration test for connected Helm redaction and CAS planning."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
from threading import Thread
from urllib.parse import urlsplit

import pytest
import yaml

from scripts import worker_primary_cas as carrier

CHART = Path(__file__).resolve().parents[2] / 'charts' / 'batch-pipeline-worker'
SYNTHETIC_UID = 'syntheticAccountIdForThisTest01'
DIGEST = 'sha256:' + 'a' * 64


@pytest.fixture
def cluster(tmp_path):
    live = {}
    for i, (name, container) in enumerate(carrier.TARGETS.items(), 1):
        live[name] = {
            'apiVersion': 'apps/v1',
            'kind': 'Deployment',
            'metadata': {
                'name': name,
                'namespace': carrier.NAMESPACE,
                'uid': f'deployment-{i}',
                'resourceVersion': '1',
                'labels': {'app.kubernetes.io/managed-by': 'Helm'},
                'annotations': {
                    'meta.helm.sh/release-name': carrier.PRIMARY,
                    'meta.helm.sh/release-namespace': carrier.NAMESPACE,
                },
            },
            'spec': {
                'replicas': i,
                'template': {
                    'spec': {
                        'containers': [
                            {
                                'name': container,
                                'image': 'example.invalid/worker@sha256:' + str(i) * 64,
                                'env': [
                                    {'name': carrier.ALLOWLIST, 'value': SYNTHETIC_UID},
                                    {'name': carrier.DEPTH, 'value': '3'},
                                ],
                            }
                        ]
                    }
                },
            },
        }

    # Helm 4 maps every rendered object using discovery, including objects
    # outside --show-only. Only Deployment lookups return live objects here.
    resources = {
        'v1': {'configmaps': 'ConfigMap', 'serviceaccounts': 'ServiceAccount'},
        'apps/v1': {'deployments': 'Deployment'},
        'autoscaling/v2': {'horizontalpodautoscalers': 'HorizontalPodAutoscaler'},
        'batch/v1': {'cronjobs': 'CronJob'},
        'monitoring.googleapis.com/v1': {'podmonitorings': 'PodMonitoring'},
        'rbac.authorization.k8s.io/v1': {'roles': 'Role', 'rolebindings': 'RoleBinding'},
    }
    discovery = {
        '/version': {'gitVersion': 'v1.32.0', 'major': '1', 'minor': '32'},
        '/api': {'kind': 'APIVersions', 'versions': ['v1']},
        '/apis': {'kind': 'APIGroupList', 'groups': []},
    }
    for group_version, kinds in resources.items():
        if '/' in group_version:
            group, version = group_version.split('/')
            preferred = {'groupVersion': group_version, 'version': version}
            discovery['/apis']['groups'].append({'name': group, 'versions': [preferred], 'preferredVersion': preferred})
            path = f'/apis/{group_version}'
        else:
            path = f'/api/{group_version}'
        discovery[path] = {
            'kind': 'APIResourceList',
            'groupVersion': group_version,
            'resources': [
                {'name': plural, 'kind': kind, 'namespaced': True, 'verbs': ['get']} for plural, kind in kinds.items()
            ],
        }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            response = live.get(path.rsplit('/', 1)[-1]) if '/deployments/' in path else discovery.get(path)
            self.send_response(200 if response else 404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response or {'kind': 'Status', 'reason': 'NotFound', 'code': 404}).encode())

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            kubeconfig = tmp_path / 'kubeconfig.yaml'
            kubeconfig.write_text(
                yaml.safe_dump(
                    {
                        'apiVersion': 'v1',
                        'kind': 'Config',
                        'current-context': 'fixture',
                        'clusters': [
                            {'name': 'fixture', 'cluster': {'server': f'http://127.0.0.1:{server.server_port}'}}
                        ],
                        'contexts': [{'name': 'fixture', 'context': {'cluster': 'fixture', 'user': 'fixture'}}],
                        'users': [{'name': 'fixture', 'user': {}}],
                    }
                )
            )
            yield kubeconfig, live
        finally:
            server.shutdown()
            thread.join()


def render(kubeconfig, *args):
    helm = shutil.which('helm')
    if not helm:
        pytest.skip('Helm is required for a connected render')
    return subprocess.run(
        [
            helm,
            'template',
            carrier.PRIMARY,
            str(CHART),
            '--namespace',
            carrier.NAMESPACE,
            '-f',
            str(CHART / 'prod_omi_batch-pipeline-worker_values.yaml'),
            '--set-string',
            f'image.digest={DIGEST}',
            '--dry-run=server',
            # The loopback fixture provides discovery and live objects only.
            '--disable-openapi-validation',
            '--kubeconfig',
            str(kubeconfig),
            *args,
        ],
        text=True,
        capture_output=True,
        timeout=20,
    )


def test_connected_render_and_carrier_preview_never_print_live_allowlist(cluster, capsys):
    kubeconfig, live = cluster
    normal = render(kubeconfig)
    assert normal.returncode == 0, normal.stderr
    assert SYNTHETIC_UID not in normal.stdout + normal.stderr
    workers = [
        doc
        for doc in yaml.safe_load_all(normal.stdout)
        if doc and doc['kind'] == 'Deployment' and doc['metadata']['name'].startswith(carrier.PRIMARY)
    ]
    assert len(workers) == 2
    for doc in workers:
        assert doc['metadata']['annotations']['omi.ai/worker-allowlist-binding-kind'] == 'literal'
        assert all(entry['name'] != carrier.ALLOWLIST for entry in carrier.target_container(doc)[1]['env'])

    upgrade = render(kubeconfig, '--is-upgrade')
    assert upgrade.returncode != 0
    assert 'use the primary-only patch' in upgrade.stderr
    assert SYNTHETIC_UID not in upgrade.stdout + upgrade.stderr

    literal = render(kubeconfig, '--set-string', f'worker.uidAllowlist.value={SYNTHETIC_UID}')
    assert literal.returncode != 0
    assert 'use an allowlist Secret reference' in literal.stderr
    assert SYNTHETIC_UID not in literal.stdout + literal.stderr

    preview_flags = ('--set', 'rollout.primaryOnlyPreview=true', '--show-only', 'templates/primary-only-preview.yaml')
    preview = render(kubeconfig, *preview_flags)
    assert preview.returncode == 0, preview.stderr
    assert SYNTHETIC_UID not in preview.stdout + preview.stderr
    summary = carrier.preview(yaml.safe_load(preview.stdout))
    assert summary[carrier.PRIMARY]['allowlist'] == {'name': carrier.ALLOWLIST, 'kind': 'literal'}
    patch, expected = carrier.plan(live, summary)
    assert SYNTHETIC_UID not in json.dumps(patch)
    assert [item['path'] for item in patch if item['op'] == 'replace'] == [
        '/spec/template/spec/containers/0/image',
        '/spec/template/spec/containers/0/env/1/value',
    ]
    assert patch[:2] == [
        {'op': 'test', 'path': '/metadata/uid', 'value': 'deployment-1'},
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': '1'},
    ]
    assert all(expected[name] == live[name] for name in carrier.TARGETS if name != carrier.PRIMARY)
    assert carrier.compare(live, expected, expected)
    output = capsys.readouterr().out
    assert output.count('literal) equal=true') == 3
    assert SYNTHETIC_UID not in output

    observed = deepcopy(expected)
    carrier.target_container(observed[carrier.PRIMARY])[1]['env'][0]['value'] = 'differentSyntheticAccountId'
    assert not carrier.compare(live, expected, observed)
    output = capsys.readouterr().out
    assert 'literal) equal=false' in output
    assert SYNTHETIC_UID not in output and 'differentSyntheticAccountId' not in output

    live.update(expected)
    rollback = render(kubeconfig, *preview_flags, '--set', 'worker.pipelineDepth=3')
    assert rollback.returncode == 0, rollback.stderr
    assert SYNTHETIC_UID not in rollback.stdout + rollback.stderr
    patch, _ = carrier.plan(live, carrier.preview(yaml.safe_load(rollback.stdout)))
    assert [item['path'] for item in patch if item['op'] == 'replace'] == [
        '/spec/template/spec/containers/0/env/1/value',
    ]
