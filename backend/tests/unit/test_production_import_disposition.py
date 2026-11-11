"""Keep the approved day-1 import routing explicit without weakening debt thresholds."""

import json
from pathlib import Path

import pytest

MON = Path(__file__).resolve().parents[2] / 'charts/monitoring'
SPLIT = {r['uid']: r for p in (MON / 'alerts').glob('*.json') for r in json.loads(p.read_text())}
COMBINED = {r['uid']: r for r in json.loads((MON / 'alert-rules.json').read_text())}
PAUSED = {
    'omi-pipeline-held-row-age': ('$A > 21600', '10m', '21600s'),
    'omi-batch-unit-unpublished-2h': ('($A > 7200 && $B < 1200) || ($C > 7200 && $F < 120)', '5m', '7200s'),
    'omi-record-pending-dwell': (7200, '10m', '7200s'),
    'omi-enrichment-fresh-dwell': (3600, '10m', '3600s'),
    'omi-pipeline-projection-drain-stall': ('($A > 0.5 || $B < 10) && $C > 0', '15m', '10 rows/s'),
}


@pytest.mark.parametrize('uid', PAUSED)
def test_known_backlog_pages_are_paused_with_unchanged_thresholds_and_recovery_criteria(uid):
    rule = SPLIT[uid]
    assert COMBINED[uid] == rule
    assert rule['isPaused'] is True
    assert rule['labels']['tier'] == 'page' and rule['labels']['audience'] == 'human'
    threshold, pending, recovery = PAUSED[uid]
    if isinstance(threshold, str):
        actual = next(n['model']['expression'] for n in rule['data'] if n['refId'] == 'D')
    else:
        actual = rule['data'][2]['model']['conditions'][0]['evaluator']['params'][0]
    assert actual == threshold
    assert rule['for'] == pending
    criteria = rule['annotations']['unpause_criteria']
    for text in ('24h', 'production', 'fresh', 'approve a separate unpause', recovery):
        assert text.lower() in criteria.lower()
    runbook = (MON / 'batch-projection/pipeline-alerts.md').read_text()
    assert uid in runbook and criteria in runbook
    assert 'unpause_criteria' in rule['annotations']['safe_next_action']


def test_queue_blind_budget_covers_worker_cadence_without_changing_other_arms():
    rule = SPLIT['omi-batch-queue-safety-blind']
    assert rule == COMBINED[rule['uid']]
    selector = '{namespace="prod-omi-backend"}'
    assert rule['data'][0]['model']['expr'] == (
        f'((max(time() - omi_batch_pipeline_metrics_refreshed_at_seconds{selector}) >= bool 900) or vector(1))'
        f' + (count(count by (priority) (omi_batch_pipeline_oldest_age_seconds{selector} != omi_batch_pipeline_oldest_age_seconds{selector})) or vector(0))'
        f' + (count(count by (priority) (omi_batch_pipeline_retry_age_seconds{selector} != omi_batch_pipeline_retry_age_seconds{selector})) or vector(0))'
    )
    assert rule['for'] == '5m' and not rule['isPaused']
    assert rule['labels']['tier'] == 'page'
    assert '900s' in rule['annotations']['threshold']
    assert '514s' in rule['annotations']['verification']
    assert 'fifteen minutes' in rule['annotations']['summary']


def test_byok_remains_active_at_three_days_but_cannot_page():
    uid = 'omi-finalization-byok-dwell-page'
    rule = SPLIT[uid]
    assert rule == COMBINED[uid] and not rule['isPaused']
    assert rule['data'][2]['model']['conditions'][0]['evaluator'] == {'params': [259200], 'type': 'gt'}
    assert rule['for'] == '1h'
    assert rule['labels']['alert_identity'] == uid
    assert {key: rule['labels'][key] for key in ('tier', 'audience', 'severity')} == {
        'tier': 'agent',
        'audience': 'agent',
        'severity': 'warning',
    }
    route = rule['notification_settings']
    assert route['receiver'] == 'Omi - Services Alerting (Telegram)'
    assert route['mute_time_intervals'] == ['omi-tier-silent']
    assert (route['group_wait'], route['group_interval'], route['repeat_interval']) == ('5m', '1h', '24h')
    assert uid in (MON / 'lifecycle-alarms.md').read_text()
