"""Run real PromQL backtests of the checked-in Grafana backlog warning."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import yaml

ALERT = 'RecordTokenLeaseBacklog'


def scenarios():
    def series(ages, *, releases=True):
        rows = [
            {
                'series': 'omi_record_seal_oldest_age_seconds{job="record-seal-worker",instance="idle"}',
                'values': ' '.join(['NaN'] * 121),
            }
        ]
        for index, age in enumerate(ages):
            prefix = f'_x{index * 30 - 1} ' if index else ''
            labels = f'{{job="record-seal-repair",instance="pod-{index}"}}'
            rows.extend(
                [
                    {'series': 'omi_record_seal_oldest_age_seconds' + labels, 'values': prefix + f'{age}x24 stale'},
                    {
                        'series': 'omi_record_token_lease_expired_sealed_total' + labels,
                        'values': prefix + ('0+1x24 stale' if releases else '0x24 stale'),
                    },
                ]
            )
        return rows

    def case(name, rows, firing):
        return {
            'name': name,
            'interval': '1m',
            'input_series': rows,
            'alert_rule_test': [
                {
                    'eval_time': '70m',
                    'alertname': ALERT,
                    'exp_alerts': [{'exp_labels': {}, 'exp_annotations': {}}] if firing else [],
                }
            ],
        }

    return [
        case('flat backlog survives pod gaps and idle NaN', series([86400] * 3), True),
        # A positive legacy epoch-pinned sample is indistinguishable from a
        # real stalled backlog here. Reject invalid clocks at the producer.
        case('legacy epoch-pinned sample demonstrates producer validation requirement', series([1794191453] * 3), True),
        case('corrected producer clears a legacy epoch-pinned series', series([1794191453, 0, 0]), False),
        case('all invalid enqueue clocks export zero and stay quiet', series([0] * 3), False),
        case('falling backlog across replacement pods stays quiet', series([86400, 82000, 78000]), False),
        case('no recent lease release stays quiet', series([86400] * 3, releases=False), False),
        case(
            'idle NaN is not a valid repair age',
            [
                {
                    'series': 'omi_record_seal_oldest_age_seconds{job="record-seal-worker"}',
                    'values': ' '.join(['NaN'] * 121),
                },
                {'series': 'omi_record_token_lease_expired_sealed_total', 'values': '0+1x120'},
            ],
            False,
        ),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--promtool', required=True, type=Path)
    args = parser.parse_args()
    tool = args.promtool.resolve()
    backend = Path(__file__).resolve().parents[2]
    rules = json.loads((backend / 'charts/monitoring/alerts/record-token-lease.json').read_text())
    warning = next(rule for rule in rules if rule['uid'] == 'omi-record-token-lease-backlog')
    threshold = next(node for node in warning['data'] if node['refId'] == warning['condition'])
    evaluator = threshold['model']['conditions'][0]['evaluator']
    assert evaluator['type'] == 'gt' and len(evaluator['params']) == 1
    # Grafana applies its threshold to A. Prometheus alert expressions
    # instead fire on vector presence, so reproduce that final filter too.
    expression = '(' + warning['data'][0]['model']['expr'] + f") > {evaluator['params'][0]:g}"
    with tempfile.TemporaryDirectory(prefix='record-token-lease-promql-') as directory:
        root = Path(directory)
        (root / 'rules.yml').write_text(
            yaml.safe_dump(
                {
                    'groups': [
                        {
                            'name': 'record-token-lease',
                            'interval': '1m',
                            'rules': [{'alert': ALERT, 'expr': expression, 'for': warning['for']}],
                        }
                    ]
                }
            )
        )
        tests = scenarios()
        (root / 'tests.yml').write_text(
            yaml.safe_dump(
                {
                    'rule_files': ['rules.yml'],
                    'evaluation_interval': '1m',
                    'tests': tests,
                }
            )
        )
        subprocess.run([str(tool), 'test', 'rules', 'tests.yml'], cwd=root, check=True)
    print(f'{len(tests)} PromQL scenarios passed')


if __name__ == '__main__':
    main()
