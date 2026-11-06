"""Offline Prometheus evaluation of the committed pair-alert queries.

PROMTOOL_BIN opts into the real engine without downloading or starting a server
inside a test. The always-on rule contract separately pins the reviewed query.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


def _observations(new_count, new_leg='jobs'):
    snapshots = [('a', 'backend', 'jobs', 0, 26, 1)]
    if new_count is not None:
        snapshots.append(('b', 'listen', new_leg, 900, new_count, 0))
    result = []
    for instance, service, leg, observed, count, blind in snapshots:
        labels = f'instance="{instance}",service_name="{service}",leg="{leg}"'
        for metric, value, kind in (
            ('omi_finalization_pair_new_mismatch', count, True),
            ('omi_finalization_pair_mismatch', count, True),
            ('omi_finalization_pair_observed_at_seconds', observed, False),
            ('omi_finalization_pair_scan_truncated', blind, False),
        ):
            series_labels = labels + (',kind="conv_processing_job_terminal"' if kind else '')
            values = ['_'] * (observed // 60) + [str(value)] * (41 - observed // 60)
            result.append({'series': f'{metric}{{{series_labels}}}', 'values': ' '.join(values)})
    return result


def test_committed_pair_queries_follow_the_newest_leader_snapshot(tmp_path):
    executable = os.environ.get('PROMTOOL_BIN') or shutil.which('promtool')
    if not executable:
        pytest.skip('set PROMTOOL_BIN to run the offline Prometheus semantic regression')
    assert Path(executable).is_file(), 'PROMTOOL_BIN must identify an existing executable'
    monitoring = Path(__file__).resolve().parents[2] / 'charts/monitoring'
    rules = {rule['uid']: rule for rule in json.loads((monitoring / 'alerts/resilience.json').read_text())}
    page = rules['omi-finalization-pair-drift']
    queries = {
        uid: rules[uid]['data'][0]['model']['expr']
        for uid in (
            'omi-finalization-pair-drift',
            'omi-finalization-pair-stock',
            'omi-finalization-pair-drift-blind',
        )
    }
    threshold = page['data'][2]['model']['conditions'][0]['evaluator']['params'][0]
    alert = {'alert': 'PairDrift', 'expr': f"({queries[page['uid']]}) > {threshold}", 'for': page['for']}
    (tmp_path / 'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'pair', 'rules': [alert]}]}))

    def case(name, observations, values, *, firing=False, when='30m'):
        return {
            'name': name,
            'interval': '1m',
            'input_series': observations,
            'promql_expr_test': [
                {
                    'expr': queries[uid],
                    'eval_time': when,
                    'exp_samples': [] if value is None else [{'labels': '{}', 'value': value}],
                }
                for uid, value in zip(queries, values)
            ],
            'alert_rule_test': [
                {
                    'eval_time': when,
                    'alertname': 'PairDrift',
                    'exp_alerts': [{'exp_labels': {}, 'exp_annotations': {}}] if firing else [],
                }
            ],
        }

    tests = [
        case('new leader clear supersedes old bad replica', _observations(0), (0, 0, 0)),
        case('ongoing drift survives a leader change', _observations(30), (30, 30, 0), firing=True),
        case('another scan leg cannot clear jobs drift', _observations(0, 'queued'), (26, 26, 1), firing=True),
        case('expired source cannot page', _observations(None), (None, 26, 1), when='36m'),
        case('absent observer stays blind', [], (None, None, 1)),
    ]
    spec = {'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': tests}
    (tmp_path / 'test.yaml').write_text(yaml.safe_dump(spec))
    result = subprocess.run(
        [executable, 'test', 'rules', 'test.yaml'], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
