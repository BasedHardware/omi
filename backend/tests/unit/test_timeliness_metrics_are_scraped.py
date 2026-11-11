"""Every eligible timeliness leader must export its result through both filters."""

import ast
import json
from pathlib import Path
import re

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[2]


def timeliness_metric_names():
    # Read the whole registration section, including names outside timeliness_*.
    # Avoid importing the producer's database dependencies or executing any scans.
    tree = ast.parse((BACKEND / 'utils/batch_pipeline/metrics.py').read_text())
    queue = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'QueueMetrics')
    init = next(node for node in queue.body if isinstance(node, ast.FunctionDef) and node.name == '__init__')
    section = False
    names = []
    for node in init.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Attribute):
            continue
        attribute = node.targets[0].attr
        if attribute == 'timeliness_age':
            section = True
        if section and attribute == '_timeliness_due':
            break
        if section and isinstance(node.value, ast.Call):
            name = ast.literal_eval(node.value.args[0])
            assert isinstance(name, str) and name.startswith('omi_')
            names.append(name)
    assert section and names, 'QueueMetrics timeliness registration section not found'
    return names


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_timeliness_families_survive_cloud_run_and_prometheus_bridge(stage):
    config = yaml.safe_load((BACKEND / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    rules = config['spec']['endpoints'][0]['metricRelabeling']
    keep = next(rule for rule in rules if rule['action'] == 'keep')
    assert keep['sourceLabels'] == ['__name__']
    bridge = yaml.safe_load(
        (
            BACKEND
            / f'charts/monitoring/prometheus-stackdriver-exporter/{stage}_sync_omi_cloud_run_metrics_exporter.yaml'
        ).read_text()
    )['stackdriver']['metrics']
    assert '"backend-integration"' in ' '.join(bridge['filters'])
    for name in timeliness_metric_names():
        assert re.fullmatch(keep['regex'], name), f'Cloud Run drops {name}'
        # Check subsequent drop rules too: both sources use the same closed labels.
        labels = {'__name__': name}
        for rule in rules:
            if rule['action'] == 'drop':
                value = ';'.join(labels.get(label, '') for label in rule['sourceLabels'])
                assert not re.fullmatch(rule['regex'], value), f'Cloud Run drops {name}'
        assert any(
            f'prometheus.googleapis.com/{name}/'.startswith(prefix) for prefix in bridge['prefixes']
        ), f'Prometheus bridge drops {name}'


@pytest.mark.parametrize('rules_path', ['alerts/batch-timeliness.json', 'alert-rules.json'])
def test_timeliness_alerts_accept_leaders_from_both_planes(rules_path):
    rules = json.loads((BACKEND / 'charts/monitoring' / rules_path).read_text())
    expressions = [
        query['model']['expr']
        for rule in rules
        for query in rule['data']
        if 'omi_batch_timeliness_' in query['model'].get('expr', '')
    ]
    assert expressions
    for expression in expressions:
        for selector in re.findall(r'omi_batch_timeliness_\w+(?:\{[^}]*\})?', expression):
            assert not re.search(r'\b(namespace|job|cluster)\s*[!=~]', selector), selector
        assert 'max' in expression, expression
