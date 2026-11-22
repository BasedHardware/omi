"""Check the projection finish guard counters at the Cloud Run GMP scrape.

The guard ratio uses both producer counters. The GMP keep and drop rules
must admit them even while the in-cluster exporter rollback is in effect.
"""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[2]
MONITORING = BACKEND / 'charts/monitoring'
ALERTS = MONITORING / 'batch-projection' / 'alerts.yaml'
ALERT_NAME = 'OmiBatchProjectionFinishReadsPerCompletion'


def guard_metric_names(source=None):
    """Read the two counter registrations without importing the producer."""
    if source is None:
        source = (BACKEND / 'utils/batch_pipeline/metrics.py').read_text()
    tree = ast.parse(source)
    names = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in {
            'PROJECTION_FINISH_READS',
            'PROJECTION_FINISH_COMPLETED',
        }:
            continue
        name = ast.literal_eval(node.value.args[0])
        assert isinstance(name, str) and name.startswith('omi_')
        names.append(name)
    assert names, 'projection finish counter registrations not found'
    return names


def keep_rule():
    config = yaml.safe_load((BACKEND / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    rules = config['spec']['endpoints'][0]['metricRelabeling']
    keep = next(rule for rule in rules if rule['action'] == 'keep')
    assert keep['sourceLabels'] == ['__name__']
    return rules, keep


def test_guard_names_are_the_two_finish_counters():
    assert set(guard_metric_names()) == {
        'omi_batch_projection_finish_reads_total',
        'omi_batch_projection_finish_completed_total',
    }


def test_guard_counters_survive_cloud_run_gmp():
    rules, keep = keep_rule()
    for name in guard_metric_names():
        assert re.fullmatch(keep['regex'], name), f'Cloud Run drops {name}'
        labels = {'__name__': name}
        for rule in rules:
            if rule['action'] == 'drop':
                value = ';'.join(labels.get(label, '') for label in rule['sourceLabels'])
                assert not re.fullmatch(rule['regex'], value), f'Cloud Run drops {name}'


def test_alert_ratio_consumes_both_guard_counters():
    rules = yaml.safe_load(ALERTS.read_text(encoding='utf-8'))
    alerts = {rule['alert']: rule for group in rules['spec']['groups'] for rule in group['rules']}
    expression = ' '.join(alerts[ALERT_NAME]['expr'].split())
    for name in guard_metric_names():
        assert name in expression, f'{ALERT_NAME} does not read {name}'
    assert '> 1200' in expression


def test_guard_counters_are_declared_in_the_metric_inventory():
    inventory = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())
    declared = set(inventory['declared_metrics'])
    for name in guard_metric_names():
        assert name in declared, f'{name} is not declared in the metric inventory'


@pytest.mark.parametrize(
    'source',
    [
        'backend/utils/batch_pipeline/metrics.py',
        'backend/deploy/cloud_run_gmp_sync.yaml',
        'backend/charts/monitoring/prometheus-stackdriver-exporter/prod_sync_omi_cloud_run_metrics_exporter.yaml',
    ],
)
def test_regression_surfaces_select_this_guard(tmp_path, source):
    changed = tmp_path / 'changed.txt'
    changed.write_text(source + '\n')
    result = subprocess.run(
        [sys.executable, str(BACKEND / 'scripts/select_backend_unit_tests.py'), '--changed-files', str(changed)],
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
        # Cold CI checkouts can slow selector discovery. Three calls get 225s of the 300s file budget.
        timeout=75,
    )
    assert 'tests/unit/test_projection_finish_guard_metrics_are_scraped.py' in result.stdout.splitlines()
