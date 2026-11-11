"""Guard the measured cost cuts against new dashboard/rule/HPA consumers."""

import re
from pathlib import Path

import pytest
import yaml

from scripts.monitoring_metric_usage import consumer_files, referenced_metrics, usage_map

REPO = Path(__file__).resolve().parents[3]
VALUES = REPO / 'backend/charts/monitoring/kube-prometheus-stack/prod_omi_monitoring_values.yaml'
SIZE_PATTERN = 'kubernetes_feature_enabled|rest_client_(request|response)_size_bytes_(bucket|sum|count)'
PROBE_PATTERN = 'prober_probe_duration_seconds_(bucket|sum|count)'
DROPPED = {'kubernetes_feature_enabled'} | {
    f'{family}_{suffix}'
    for family in ('rest_client_request_size_bytes', 'rest_client_response_size_bytes', 'prober_probe_duration_seconds')
    for suffix in ('bucket', 'sum', 'count')
}


def test_no_committed_consumer_references_cost_drops():
    usage = usage_map(DROPPED, consumer_files())
    assert not {metric: paths for metric, paths in usage.items() if paths}


def test_cost_drop_policy_is_scoped_and_preserves_chart_default():
    monitor = yaml.safe_load(VALUES.read_text())['kubelet']['serviceMonitor']
    default, sizes = monitor['metricRelabelings']
    assert default == {
        'action': 'drop',
        'sourceLabels': ['__name__', 'le'],
        'regex': r'(csi_operations|storage_operation_duration)_seconds_bucket;(0.25|2.5|15|25|120|600)(\.0)?',
    }
    assert sizes == {'action': 'drop', 'sourceLabels': ['__name__'], 'regex': SIZE_PATTERN}
    assert monitor['probesMetricRelabelings'] == [
        {'action': 'drop', 'sourceLabels': ['__name__'], 'regex': PROBE_PATTERN}
    ]
    assert all(re.fullmatch(f'{SIZE_PATTERN}|{PROBE_PATTERN}', name) for name in DROPPED)
    for signal in (
        'prober_probe_total',
        'kubelet_runtime_operations_duration_seconds_bucket',
        'rest_client_requests_total',
    ):
        assert not re.fullmatch(f'{SIZE_PATTERN}|{PROBE_PATTERN}', signal)


@pytest.mark.parametrize(
    'query',
    [
        'rate(prober_probe_duration_seconds_count[5m])',
        '{__name__=~"prober_probe_duration_seconds_.*"}',
        '{__name__="prober_probe_duration_seconds_count"}',
    ],
)
def test_detects_direct_and_metric_name_selector_consumers(query):
    assert 'prober_probe_duration_seconds_count' in referenced_metrics(query, DROPPED)


def test_metric_names_are_matched_as_whole_identifiers():
    assert not referenced_metrics('my_prober_probe_duration_seconds_count_backup', DROPPED)
