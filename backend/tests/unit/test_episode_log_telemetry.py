"""Drain deadlines and migration drift must reach the deployed collector."""

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.usefixtures('isolated_episode_capture')


BACKEND = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('profile', ['cloud_run_gmp_sync.yaml', 'cloud_run_gmp_sidecar.yaml'])
def test_episode_log_observability_survives_collector_filters(profile):
    endpoint = yaml.safe_load((BACKEND / 'deploy' / profile).read_text())['spec']['endpoints'][0]
    rules = endpoint['metricRelabeling']
    names = {
        'omi_episode_view_drift_total',
        'omi_episode_view_compare_skipped_total',
        'omi_episode_drain_total',
        'omi_episode_drain_sweep_observed_at_seconds',
        'omi_episode_drain_deadline_total',
        *{
            f'omi_episode_drain_{family}_{suffix}'
            for family in ('seconds', 'dwell_seconds')
            for suffix in ('bucket', 'count', 'sum')
        },
    }
    alerts = yaml.safe_load((BACKEND / 'charts/monitoring/episode-log/alerts.yaml').read_text())
    for group in alerts['spec']['groups']:
        for alert in group['rules']:
            names.update(re.findall(r'\bomi_episode_\w+', alert['expr']))
    for name in sorted(names):
        for rule in rules:
            if rule['sourceLabels'][0] != '__name__':
                continue
            matches = re.fullmatch(rule['regex'].split(';')[0], name) is not None
            assert not (rule['action'] == 'keep' and not matches), (profile, name)
            assert not (rule['action'] == 'drop' and matches), (profile, name)
