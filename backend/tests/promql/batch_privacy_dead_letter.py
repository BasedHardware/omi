"""Backtest the Grafana stock, inflow and freshness rules with real PromQL."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import yaml

PREFIX = 'omi_batch_pipeline_privacy_post_window_dead_letter'


def _series(suffix, values, replica='leader'):
    labels = f'{{project_id="based-hardware",instance="{replica}"}}'
    return {'series': f'{PREFIX}{suffix}{labels}', 'values': values}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--promtool', required=True, type=Path)
    tool = parser.parse_args().promtool.resolve()
    backend = Path(__file__).resolve().parents[2]
    rules = json.loads((backend / 'charts/monitoring/alerts/batch-privacy-erasure.json').read_text())
    names = ['BatchPrivacyInflow', 'BatchPrivacyStock', 'BatchPrivacyStale']
    alerts = []
    for name, rule in zip(names, rules, strict=True):
        query, condition = rule['data']
        assert condition['refId'] == rule['condition']
        assert condition['model']['type'] == 'threshold' and condition['model']['expression'] == query['refId']
        evaluator = condition['model']['conditions'][0]['evaluator']
        assert evaluator['type'] == 'gt'
        (threshold,) = evaluator['params']
        alerts.append({'alert': name, 'expr': f"({query['model']['expr']}) > {threshold:g}", 'for': rule['for']})

    def at(minute, *firing):
        return [
            {
                'eval_time': f'{minute}m',
                'alertname': name,
                'exp_alerts': [{'exp_labels': {}, 'exp_annotations': {}}] if name in firing else [],
            }
            for name in names
        ]

    rows = [
        _series('s_total', '0 1x60'),  # one dead letter at minute 1
        _series('_units', '0 1x38 0x20'),  # resolved by minute 40
        _series(
            '_observed_at_seconds',
            ' '.join(f'{minute * 60}x4' for minute in range(0, 41, 5)) + ' 2400x15',
        ),
        _series('_units', '9x60', 'old-leader'),
        _series('_observed_at_seconds', '60x60', 'old-leader'),
        _series('_observed_at_seconds', '0+60x60', 'timestamp-only'),
    ]
    tests = [
        {
            'name': 'one dead letter, then resolution and sampler failure',
            'interval': '1m',
            'input_series': rows,
            'alert_rule_test': [
                *at(10, 'BatchPrivacyInflow', 'BatchPrivacyStock'),
                *at(35, 'BatchPrivacyStock'),
                *at(40),
                *at(54),
                *at(55),
                *at(59),
                *at(60, 'BatchPrivacyStale'),
            ],
        },
        {
            'name': 'missing stock observation',
            'interval': '1m',
            'input_series': [],
            'alert_rule_test': [*at(0), *at(4), *at(5, 'BatchPrivacyStale')],
        },
        {
            'name': 'publisher replacement starts at zero, then samples within the hold',
            'interval': '1m',
            'input_series': [
                _series('_units', '0x19 stale', 'retiring'),
                _series('_observed_at_seconds', '0+60x19 stale', 'retiring'),
                _series('_units', '0x30', 'replacement'),
                _series('_observed_at_seconds', '0x21 1320x8', 'replacement'),
            ],
            'alert_rule_test': [*at(20), *at(21), *at(22), *at(25)],
        },
    ]
    with tempfile.TemporaryDirectory(prefix='batch-privacy-dead-letter-promql-') as directory:
        root = Path(directory)
        (root / 'rules.yml').write_text(yaml.safe_dump({'groups': [{'name': 'batch-privacy', 'rules': alerts}]}))
        (root / 'tests.yml').write_text(
            yaml.safe_dump({'rule_files': ['rules.yml'], 'evaluation_interval': '1m', 'tests': tests})
        )
        subprocess.run([str(tool), 'test', 'rules', 'tests.yml'], cwd=root, check=True)


if __name__ == '__main__':
    main()
