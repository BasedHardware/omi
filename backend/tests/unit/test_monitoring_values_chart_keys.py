"""kube-prometheus-stack ignores unknown top-level keys silently.

#21455 put the operator's resource requests under a top-level ``operator:`` key;
the chart reads ``prometheusOperator``, so prod kept running the operator
BestEffort and its liveness-probe restarts continued.
"""

from pathlib import Path

import yaml

VALUES = Path(__file__).resolve().parents[2] / 'charts/monitoring/kube-prometheus-stack/prod_omi_monitoring_values.yaml'

# Top-level keys kube-prometheus-stack 75.x actually reads that this file uses.
KNOWN_TOP_LEVEL = {
    'alertmanager',
    'crds',
    'defaultRules',
    'extraManifests',
    'fullnameOverride',
    'global',
    'grafana',
    'kube-state-metrics',
    'kubeApiServer',
    'kubeControllerManager',
    'kubeDns',
    'kubeEtcd',
    'kubeProxy',
    'kubeScheduler',
    'kubeStateMetrics',
    'kubelet',
    'nameOverride',
    'nodeExporter',
    'prometheus',
    'prometheus-node-exporter',
    'prometheusOperator',
    'coreDns',
    'cleanPrometheusOperatorObjectNames',
    'commonLabels',
    'additionalPrometheusRulesMap',
    'windowsMonitoring',
    'thanosRuler',
}


def _values():
    return yaml.safe_load(VALUES.read_text())


def test_top_level_keys_are_chart_keys():
    unknown = set(_values()) - KNOWN_TOP_LEVEL
    assert not unknown, f'kube-prometheus-stack silently ignores {sorted(unknown)}'


def test_operator_has_cpu_and_memory_requests():
    requests = _values()['prometheusOperator']['resources']['requests']
    assert requests.get('cpu') and requests.get('memory')
