"""Check the projection finish guard counters at the Cloud Run GMP scrape.

Both producer counters must still pass the GMP keep and drop rules during
an in-cluster exporter rollback (FC-metric-dropped-by-scrape-allowlist).
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
METRIC_PREFIX = 'omi_batch_projection_finish_'

# The ratio inputs the guard depends on. Every assertion below derives from
# this set, so a renamed or duplicated registration and an alert that stops
# reading either counter are both caught in one place.
GUARD_COUNTERS = {
    'omi_batch_projection_finish_reads_total',
    'omi_batch_projection_finish_completed_total',
}


def counter_registrations():
    """Metric names from every ``Counter('name', ...)`` call in the producer."""
    tree = ast.parse((BACKEND / 'utils/batch_pipeline/metrics.py').read_text())
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not (
            (isinstance(func, ast.Name) and func.id == 'Counter')
            or (isinstance(func, ast.Attribute) and func.attr == 'Counter')
        ):
            continue
        name = node.args[0]
        if isinstance(name, ast.Constant) and isinstance(name.value, str):
            names.append(name.value)
    return names


def alert_expression():
    rules = yaml.safe_load(ALERTS.read_text(encoding='utf-8'))
    alerts = {rule['alert']: rule for group in rules['spec']['groups'] for rule in group['rules']}
    return ' '.join(alerts[ALERT_NAME]['expr'].split())


def keep_rule():
    config = yaml.safe_load((BACKEND / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    rules = config['spec']['endpoints'][0]['metricRelabeling']
    keep = next(rule for rule in rules if rule['action'] == 'keep')
    assert keep['sourceLabels'] == ['__name__']
    return rules, keep


def test_producer_registers_each_guard_counter_once():
    names = counter_registrations()
    for name in sorted(GUARD_COUNTERS):
        assert names.count(name) == 1, f'metrics.py registers {name} {names.count(name)} times'


def test_guard_counters_survive_cloud_run_gmp():
    rules, keep = keep_rule()
    for name in sorted(GUARD_COUNTERS):
        assert re.fullmatch(keep['regex'], name), f'Cloud Run drops {name}'
        labels = {'__name__': name}
        for rule in rules:
            if rule['action'] == 'drop':
                value = ';'.join(labels.get(label, '') for label in rule['sourceLabels'])
                assert not re.fullmatch(rule['regex'], value), f'Cloud Run drops {name}'


def test_alert_ratio_consumes_both_guard_counters():
    expression = alert_expression()
    inputs = set(re.findall(METRIC_PREFIX + r'[a-z0-9_]+', expression))
    assert inputs == GUARD_COUNTERS, f'{ALERT_NAME} reads {sorted(inputs)}'
    # The bound value is the alert author's tuning, not the contract.
    assert re.search(r'>\s*\d', expression), f'{ALERT_NAME} lost its numeric bound'


def test_guard_counters_are_declared_in_the_metric_inventory():
    inventory = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())
    declared = set(inventory['declared_metrics'])
    for name in sorted(GUARD_COUNTERS):
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
