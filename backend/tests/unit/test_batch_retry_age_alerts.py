"""Offline contract for the batch retry-age and capture retry-cap alert rules."""

import importlib.util
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MONITORING = BACKEND / 'charts/monitoring'
spec = importlib.util.spec_from_file_location('retry_alert_backtest', BACKEND / 'scripts/alert_backtest.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

SOURCE = {r['uid']: r for r in json.loads((MONITORING / 'alerts/batch-queue-safety.json').read_text())}
COMBINED = {r['uid']: r for r in json.loads((MONITORING / 'alert-rules.json').read_text())}
INVENTORY = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())

RETRY_AGE = 'omi-batch-retry-age-over-24h'
RETRY_CAP = 'omi-capture-retry-cap-shadow-7d'
NEW = {
    RETRY_AGE: (
        'max(omi_batch_pipeline_retry_age_seconds{namespace="prod-omi-backend"})',
        '$A > 86400',
        '10m',
    ),
    RETRY_CAP: (
        'sum(increase(omi_capture_retry_cap_total{outcome="would_quarantine"}[7d]))',
        '$A > 0',
        '1h',
    ),
}


def _query(rule):
    return next(d['model']['expr'] for d in rule['data'] if d['datasourceUid'] == 'prometheus')


def _expression(rule):
    return next(d['model']['expression'] for d in rule['data'] if d['refId'] == 'D')


def test_both_rules_are_in_the_split_source_and_the_combined_export():
    for uid in NEW:
        assert uid in SOURCE, uid
        assert COMBINED[uid] == SOURCE[uid], uid


def test_expressions_and_thresholds_are_exactly_as_scoped():
    for uid, (expr, expression, pending) in NEW.items():
        rule = SOURCE[uid]
        assert _query(rule) == expr, uid
        assert _expression(rule) == expression, uid
        assert rule['for'] == pending, uid


def test_retry_cap_counter_is_declared_so_the_alert_lint_admits_it():
    assert 'omi_capture_retry_cap_total' in INVENTORY['declared_metrics']


def test_both_rules_pass_the_repo_alert_lint():
    for uid in NEW:
        assert b.lint_rule(SOURCE[uid], INVENTORY) == [], uid


def test_both_rules_stay_agent_tier_warnings_and_do_not_page_a_human():
    for uid in NEW:
        labels = SOURCE[uid]['labels']
        assert labels['tier'] == 'agent', uid
        assert labels['audience'] == 'agent', uid
        assert labels['severity'] == 'warning', uid
        assert SOURCE[uid]['notification_settings']['mute_time_intervals'] == ['omi-tier-silent'], uid
        assert labels['alert_identity'] == uid, uid


def test_both_rules_name_an_existing_runbook_and_authorize_no_runtime_change():
    for uid in NEW:
        annotations = SOURCE[uid]['annotations']
        assert (BACKEND.parent / annotations['runbook']).is_file(), uid
        assert 'authorizes no runtime change' in annotations['safe_next_action'], uid
