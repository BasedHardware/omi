"""Keep the Core Features recording rules installable and cheap to read."""

from pathlib import Path

import yaml

RULES = Path(__file__).resolve().parents[2] / 'charts/monitoring/core-features/recording-rules.yaml'


def _document():
    return yaml.safe_load(RULES.read_text())


def test_prometheus_operator_selects_the_rule():
    metadata = _document()['metadata']
    assert metadata['namespace'] == 'prod-omi-monitoring'
    assert metadata['labels'] == {'release': 'prod-omi-kube-prometheus-stack'}


def test_rules_only_record_and_drop_instance_labels():
    (group,) = _document()['spec']['groups']
    # Tiles multiply sum_over_time by 60, so this interval is part of their arithmetic.
    assert group['interval'] == '1m'
    assert group['rules']
    for rule in group['rules']:
        assert 'alert' not in rule
        assert rule['record'].endswith(':rate5m')
        assert rule['expr'].startswith('sum by (')
        assert '[5m]))' in rule['expr']
