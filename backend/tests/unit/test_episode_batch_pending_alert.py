"""Read-observed batch dwell has a staged, bounded info alert."""

import json
from pathlib import Path


def test_home_pending_dwell_alert_is_info_and_observation_scoped():
    catalog = Path(__file__).resolve().parents[2] / 'charts/monitoring/pending/episode-batch-pending.json'
    (rule,) = json.loads(catalog.read_text(encoding='utf-8'))
    assert rule['uid'] == 'omi-episode-batch-pending-overdue'
    assert rule['labels']['severity'] == 'info'
    assert rule['labels']['tier'] == 'agent'
    assert rule['data'][0]['model']['expr'] == 'sum(increase(omi_episode_batch_pending_overdue_reads_total[15m]))'
    assert rule['noDataState'] == 'OK'
    assert 'not unique members' in rule['annotations']['scope']
