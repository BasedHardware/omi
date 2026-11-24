"""Listen/pusher GMP discovery must match the serving pods and authenticated metrics route."""

import csv
import json
import re
import shutil
import subprocess
from copy import deepcopy
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
    assert len(monitors) == (2 if stage == 'prod' else 1)
    monitor = next(m for m in monitors if m['metadata']['name'] == 'synthetic-serving')
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
    expected_endpoint = {
        'port': port['name'],
        'path': '/metrics',
        'interval': '15s',
        'authorization': {
            'type': 'Bearer',
            'credentials': {'secret': {'name': 'metrics-scrape-token', 'key': 'token'}},
        },
    }
    if stage == 'prod':
        fast = monitor['spec']['endpoints'][0]['metricRelabeling']
        assert len(fast) == 1
        assert fast[0]['action'] == 'keep' and fast[0]['sourceLabels'] == ['__name__']
        expected_endpoint['metricRelabeling'] = fast
        bulk = next(m for m in monitors if m['metadata']['name'] == 'synthetic-serving-bulk')
        assert bulk['spec']['selector'] == monitor['spec']['selector']
        assert bulk['spec']['targetLabels'] == monitor['spec']['targetLabels']
        bulk_endpoint = dict(expected_endpoint, interval='120s')
        bulk_endpoint['metricRelabeling'] = [dict(fast[0], action='drop')]
        assert bulk['spec']['endpoints'] == [bulk_endpoint]
        rollback_bulk = deepcopy(bulk)
        rollback_bulk['spec']['endpoints'][0]['interval'] = '60s'
        assert render('--set-string', 'podMonitoring.bulkInterval=60s') == [
            rollback_bulk if doc is bulk else doc for doc in default
        ]
        # Only PodMonitoring changes: the pod template, HPA, RBAC and service
        # must be identical to the single 15s scrape configuration.
        unsplit = render('--set-string', 'podMonitoring.bulkInterval=')
        assert [d for d in default if d['kind'] != 'PodMonitoring'] == [
            d for d in unsplit if d['kind'] != 'PodMonitoring'
        ]
        original = next(d for d in unsplit if d['kind'] == 'PodMonitoring')
        assert original['spec']['endpoints'] == [
            {k: v for k, v in expected_endpoint.items() if k != 'metricRelabeling'}
        ]
        expression = fast[0]['regex']
        # Complements are checked against the observed inventory AND future names.
        metrics = json.loads((ROOT / 'backend/charts/monitoring/metric-inventory.prod.json').read_text())
        with (ROOT / 'backend/docs/monitoring/2026-11-17-serving-metrics-consumers.csv').open() as stream:
            observed_names = {row['metric'] for row in csv.DictReader(stream)}
        names = (
            set(metrics['declared_metrics'])
            | observed_names
            | {
                'future_metric_total',
                'omi_fallback_total',
                'omi_stt_cost_routing_ignored_deaths_total',
                'omi_firestore_billed_reads_by_origin_total',
                'omi_episode_compose_seconds_bucket',
                'omi_episode_compose_seconds_sum',
                'omi_episode_compose_seconds_count',
            }
        )
        for name in names:
            assert (
                sum(
                    bool(re.fullmatch(rule['regex'], name)) == (rule['action'] == 'keep')
                    for rule in (fast[0], bulk_endpoint['metricRelabeling'][0])
                )
                == 1
            ), name
        for name in (
            'backend_listen_active_ws_connections',
            'pusher_active_ws_connections',
            'privacy_check_calls_total',
            'privacy_ttl_cache_disabled',
            'privacy_session_cycle_operations_bucket',
            'omi_firestore_billed_reads_by_caller_total',
            'omi_firestore_caller_label_overflow_total',
            'omi_batch_pipeline_completed_audio_seconds_total',
            'omi_audio_pcm_storage_total',
            'omi_audio_pcm_storage_seconds_bucket',
            'omi_audio_custody_failures_total',
            'omi_audio_raw_read_total',
            'omi_record_token_late_append_total',
            'omi_stt_cost_routing_snapshot_timestamp_seconds',
        ):
            assert re.fullmatch(expression, name), name
        # All application metrics referenced by a GMP page retain 15s resolution.
        from scripts.alert_backtest import metric_names

        rules = json.loads((ROOT / 'backend/charts/monitoring/alert-rules.json').read_text())
        for rule in rules:
            for node in rule['data']:
                if node.get('datasourceUid') != 'gmp-cloud-run':
                    continue
                for name in metric_names(node.get('model', {}).get('expr', '')):
                    if name.startswith(('omi_', 'privacy_')) and 'cluster="__run__"' not in node['model']['expr']:
                        assert re.fullmatch(expression, name), (rule['uid'], name)
        # A missing partition expression must fail rather than drop all fast metrics.
        failed = subprocess.run(
            command + ['--set-string', 'podMonitoring.fastMetrics='], capture_output=True, text=True, timeout=30
        )
        assert failed.returncode != 0
        assert 'fastMetrics is required' in failed.stderr
    assert monitor['spec']['endpoints'] == [expected_endpoint]
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
        doc
        for doc in render('--set-string', 'podMonitoring.interval=30s')
        if doc['kind'] == 'PodMonitoring' and doc['metadata']['name'] == 'synthetic-serving'
    )
    assert overridden['spec']['endpoints'][0]['interval'] == '30s'
    if chart == 'pusher':
        # The isolated prod canary borrows the shared KSA and the shared collector Role; the CI
        # deployer cannot create RBAC, so the canary must render none of its own.
        canary = render('--set', 'serviceAccount.create=false', '--set-string', 'serviceAccount.name=shared')
        assert [doc for doc in canary if doc['kind'] == 'PodMonitoring'] == monitors
        assert not any(doc['kind'] in {'Role', 'RoleBinding'} for doc in canary)
