"""Pin the day-1 backlog page dispositions: unpaused, page tier, at most one page a day."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

MON = Path(__file__).resolve().parents[2] / 'charts/monitoring'
SPLIT = {r['uid']: r for p in (MON / 'alerts').glob('*.json') for r in json.loads(p.read_text())}
COMBINED = {r['uid']: r for r in json.loads((MON / 'alert-rules.json').read_text())}
# SCA-2116 retired the 2026-11-08 import pause. Each rule keeps its threshold and
# stays page tier; the repeat cap keeps a standing breach to one page a day.
ACTIVE = {
    'omi-pipeline-held-row-age': ('$A > 21600', '10m', '21600s'),
    'omi-batch-unit-unpublished-2h': ('($A > 7200 && $B < 1200) || ($C > 7200 && $F < 120)', '5m', '7200s'),
    'omi-record-pending-dwell': (7200, '10m', '7200s'),
    'omi-enrichment-fresh-dwell': (3600, '10m', '3600s'),
    'omi-pipeline-projection-drain-stall': ('($A > 0.5 || $B < 10) && $C > 0', '15m', '10 rows/s'),
}
REPEAT_SECONDS = {'30s': 30, '1m': 60, '5m': 300, '1h': 3600, '4h': 14400, '12h': 43200, '24h': 86400}


@pytest.mark.parametrize('uid', ACTIVE)
def test_known_backlog_pages_are_active_with_unchanged_thresholds_and_owned_disposition(uid):
    rule = SPLIT[uid]
    assert COMBINED[uid] == rule
    assert rule['isPaused'] is False
    assert rule['labels']['tier'] == 'page' and rule['labels']['audience'] == 'human'
    assert rule['labels']['owner']
    threshold, pending, recovery = ACTIVE[uid]
    if isinstance(threshold, str):
        actual = next(n['model']['expression'] for n in rule['data'] if n['refId'] == 'D')
    else:
        actual = rule['data'][2]['model']['conditions'][0]['evaluator']['params'][0]
    assert actual == threshold
    assert rule['for'] == pending
    # A standing breach on current data must not page more than twice a day.
    assert REPEAT_SECONDS[rule['notification_settings']['repeat_interval']] >= 43200
    disposition = rule['annotations']['page_disposition']
    assert 'SCA-2116' in disposition and '2026-11-14' in disposition
    review = rule['annotations']['page_review_by']
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', review)
    assert date.fromisoformat(review) > date(2026, 11, 14)
    runbook = (MON / 'batch-projection/pipeline-alerts.md').read_text()
    assert uid in runbook and disposition in runbook


def test_no_page_tier_rule_lands_paused():
    """S5.2: a paused page rule is a blind spot with no owner and no deadline."""
    for name, rules in (('split', SPLIT), ('combined', COMBINED)):
        paused = sorted(
            uid for uid, rule in rules.items() if rule.get('labels', {}).get('tier') == 'page' and rule.get('isPaused')
        )
        assert paused == [], f'{name} export pauses page-tier rules: {paused}'


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
