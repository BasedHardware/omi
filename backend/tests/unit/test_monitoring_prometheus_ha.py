"""Keep query warm-up routing separate from both replicas' self-scrapes."""

import copy
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.verify_prometheus_replica_readiness import PROD_STATEFULSET, validate_readiness

MONITORING = Path(__file__).resolve().parents[2] / 'charts/monitoring'
VALUES = MONITORING / 'kube-prometheus-stack/prod_omi_monitoring_values.yaml'
RELEASE = 'prod-omi-kube-prometheus-stack'
QUERY_SERVICE = 'prod-omi-kube-prometheus-s-prometheus'


def test_source_separates_pinned_queries_from_unpinned_self_monitoring():
    values = yaml.safe_load(VALUES.read_text())
    assert values['prometheus']['service']['enabled'] is False
    extras = values['extraManifests']
    query = extras['prometheusWarmupService']
    monitoring = extras['prometheusSelfMonitorService']
    assert 'self-monitor: "false"' in query
    assert 'statefulset.kubernetes.io/pod-name: prometheus-prod-omi-kube-prometheus-s-prometheus-0' in query
    assert 'self-monitor: "true"' in monitoring
    assert 'statefulset.kubernetes.io/pod-name' not in monitoring
    assert 'operator.prometheus.io/name:' in monitoring
    assert 'port: 9090' in monitoring and 'port: 8080' in monitoring
    assert values['prometheus']['prometheusSpec']['replicas'] == 2
    assert 'both temporary Services' in VALUES.read_text()


@pytest.fixture(scope='module')
def rendered():
    chart_env = os.environ.get('KUBE_PROMETHEUS_STACK_CHART')
    if not chart_env:
        pytest.skip('set KUBE_PROMETHEUS_STACK_CHART to a locally downloaded pinned75.15.1 chart for Helm verification')
    helm = shutil.which('helm')
    if not helm:
        pytest.skip('Helm is not installed')
    chart = Path(chart_env)
    assert yaml.safe_load((chart / 'Chart.yaml').read_text())['version'] == '75.15.1'
    command = [
        helm,
        'template',
        RELEASE,
        str(chart),
        '--namespace',
        'prod-omi-monitoring',
        '--kube-version',
        'v1.35.8-gke.1380001',
        '--api-versions',
        'discovery.k8s.io/v1/EndpointSlice',
        '--skip-crds',
        '--no-hooks',
        '--values',
        str(VALUES),
    ]
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    return [obj for obj in yaml.safe_load_all(output) if obj]


def _matches(selector, labels):
    return all(labels.get(key) == value for key, value in selector.items())


def test_rendered_service_monitor_discovers_both_replicas_and_both_ports_once(rendered):
    monitors = [obj for obj in rendered if obj['kind'] == 'ServiceMonitor' and obj['metadata']['name'] == QUERY_SERVICE]
    assert len(monitors) == 1
    monitor = monitors[0]
    selected = [
        obj
        for obj in rendered
        if obj['kind'] == 'Service'
        and _matches(monitor['spec']['selector']['matchLabels'], obj['metadata'].get('labels', {}))
    ]
    assert [obj['metadata']['name'] for obj in selected] == [QUERY_SERVICE + '-selfmonitor']
    service = selected[0]
    selector = service['spec']['selector']
    assert selector == {
        'app.kubernetes.io/name': 'prometheus',
        'operator.prometheus.io/name': QUERY_SERVICE,
    }
    pods = [
        {
            **selector,
            'statefulset.kubernetes.io/pod-name': f'prometheus-{QUERY_SERVICE}-{ordinal}',
        }
        for ordinal in (0, 1)
    ]
    assert sum(_matches(selector, labels) for labels in pods) == 2
    assert {endpoint['port'] for endpoint in monitor['spec']['endpoints']} == {'http-web', 'reloader-web'}
    assert {port['name']: port['port'] for port in service['spec']['ports']} == {'http-web': 9090, 'reloader-web': 8080}
    assert service['spec']['publishNotReadyAddresses'] is False


def test_rendered_query_service_remains_pinned_and_recording_rules_stay_enabled(rendered):
    query = next(obj for obj in rendered if obj['kind'] == 'Service' and obj['metadata']['name'] == QUERY_SERVICE)
    assert query['metadata']['labels']['self-monitor'] == 'false'
    assert query['spec']['selector']['statefulset.kubernetes.io/pod-name'] == f'prometheus-{QUERY_SERVICE}-0'
    rules = [
        rule
        for obj in rendered
        if obj['kind'] == 'PrometheusRule'
        for group in obj['spec']['groups']
        for rule in group['rules']
    ]
    assert len(rules) == 81 and all('record' in rule and 'alert' not in rule for rule in rules)


def _readiness_objects():
    statefulset = {
        'kind': 'StatefulSet',
        'metadata': {'name': PROD_STATEFULSET, 'namespace': 'prod-omi-monitoring', 'uid': 'test-sts', 'generation': 7},
        'spec': {'replicas': 2, 'volumeClaimTemplates': [{'metadata': {'name': 'data'}}]},
        'status': {
            'observedGeneration': 7,
            'replicas': 2,
            'currentReplicas': 2,
            'updatedReplicas': 2,
            'readyReplicas': 2,
            'currentRevision': 'test-revision',
            'updateRevision': 'test-revision',
        },
    }
    pods, pvcs = {'items': []}, {'items': []}
    for ordinal in (0, 1):
        pod_name = f'{PROD_STATEFULSET}-{ordinal}'
        claim_name = f'data-{pod_name}'
        pods['items'].append(
            {
                'metadata': {
                    'name': pod_name,
                    'namespace': 'prod-omi-monitoring',
                    'ownerReferences': [{'kind': 'StatefulSet', 'uid': 'test-sts', 'controller': True}],
                },
                'spec': {
                    'nodeName': f'node-{ordinal}',
                    'volumes': [{'persistentVolumeClaim': {'claimName': claim_name}}],
                },
                'status': {'phase': 'Running', 'conditions': [{'type': 'Ready', 'status': 'True'}]},
            }
        )
        pvcs['items'].append(
            {
                'metadata': {'name': claim_name, 'namespace': 'prod-omi-monitoring'},
                'spec': {
                    'volumeName': f'pv-{ordinal}',
                    'storageClassName': 'standard-rwo',
                    'accessModes': ['ReadWriteOnce'],
                    'resources': {'requests': {'storage': '100Gi'}},
                },
                'status': {'phase': 'Bound', 'capacity': {'storage': '100Gi'}},
            }
        )
    return statefulset, pods, pvcs


def test_ready_owned_replicas_require_distinct_bound_data_volumes():
    objects = _readiness_objects()
    assert validate_readiness(*objects) == []
    # Retained claims need not have Pod ownerReferences: the mounted ordinal
    # claim names and separate Bound PVs establish the actual attachment.
    assert all('ownerReferences' not in pvc['metadata'] for pvc in objects[2]['items'])


@pytest.mark.parametrize(
    'object_index,path,value,expected',
    [
        (0, ('status', 'observedGeneration'), 6, 'generation not observed'),
        (0, ('spec', 'replicas'), 1, 'desired replicas'),
        (0, ('status', 'updatedReplicas'), 1, 'replica counts'),
        (0, ('status', 'readyReplicas'), 1, 'replica counts'),
        (0, ('status', 'currentRevision'), 'old', 'rollout revision'),
        (1, ('items', 1, 'metadata', 'ownerReferences', 0, 'uid'), 'unrelated', 'StatefulSet-owned'),
        (1, ('items', 1, 'status', 'conditions', 0, 'status'), 'False', 'not Running/Ready'),
        (1, ('items', 1, 'metadata', 'deletionTimestamp'), '2026-10-15T00:00:00Z', 'terminating'),
        (1, ('items', 1, 'spec', 'nodeName'), 'node-0', 'distinct nodes'),
        (1, ('items', 1, 'spec', 'volumes'), [], 'not mounted'),
        (2, ('items', 1, 'status', 'phase'), 'Pending', 'unbound'),
        (2, ('items', 1, 'spec', 'volumeName'), 'pv-0', 'distinct persistent volumes'),
        (2, ('items', 1, 'spec', 'storageClassName'), 'different-class', 'standard-rwo'),
        (2, ('items', 1, 'spec', 'resources', 'requests', 'storage'), '99Gi', 'below 100Gi'),
        (2, ('items', 1, 'status', 'capacity', 'storage'), 'not-a-quantity', 'invalid storage'),
    ],
)
def test_incomplete_reconciliation_fails_closed(object_index, path, value, expected):
    objects = copy.deepcopy(_readiness_objects())
    target = objects[object_index]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    findings = validate_readiness(*objects)
    assert any(expected in finding for finding in findings)
    assert all('unrelated' not in finding and 'not-a-quantity' not in finding for finding in findings)


def test_retired_alertmanager_has_no_resources_endpoints_or_grafana_datasource(rendered):
    assert not any(obj['kind'] == 'Alertmanager' for obj in rendered)
    alertmanager_name = 'prod-omi-kube-prometheus-s-alertmanager'
    retired = {'Service', 'ServiceAccount', 'ServiceMonitor', 'StatefulSet'}
    assert not any(obj['kind'] in retired and obj['metadata']['name'] == alertmanager_name for obj in rendered)
    assert not any(
        obj['kind'] == 'StatefulSet' and obj['metadata']['name'] == 'alertmanager-' + alertmanager_name
        for obj in rendered
    )
    prometheus = next(obj for obj in rendered if obj['kind'] == 'Prometheus')
    assert not prometheus['spec'].get('alerting', {}).get('alertmanagers')
    assert prometheus['spec']['persistentVolumeClaimRetentionPolicy'] == {
        'whenDeleted': 'Retain',
        'whenScaled': 'Retain',
    }
    claim = prometheus['spec']['storage']['volumeClaimTemplate']['spec']
    assert claim['storageClassName'] == 'standard-rwo'
    assert claim['resources']['requests']['storage'] == '100Gi'
    datasources = next(
        yaml.safe_load(obj['data']['datasource.yaml'])
        for obj in rendered
        if obj['kind'] == 'ConfigMap' and 'datasource.yaml' in obj.get('data', {})
    )
    assert not any(source.get('uid') == 'alertmanager' for source in datasources['datasources'])
    assert not datasources.get('deleteDatasources')
    assert (
        next(source for source in datasources['datasources'] if source.get('uid') == 'prometheus')['isDefault'] is True
    )
    assert not datasources.get('prune')
