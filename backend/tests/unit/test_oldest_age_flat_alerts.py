"""Offline N5 contract: sampler flatness and held-content snapshot freshness."""

import importlib.util
import json
from pathlib import Path

import pytest

from utils.batch_pipeline import vendor_route_contracts, vendor_route_metrics

BACKEND = Path(__file__).resolve().parents[2]
MONITORING = BACKEND / 'charts/monitoring'
spec = importlib.util.spec_from_file_location('oldest_age_alert_backtest', BACKEND / 'scripts/alert_backtest.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
SOURCE = {
    r['uid']: r
    for name in ('pipeline-drain', 'resilience')
    for r in json.loads((MONITORING / 'alerts' / f'{name}.json').read_text())
}
COMBINED = {r['uid']: r for r in json.loads((MONITORING / 'alert-rules.json').read_text())}
INVENTORY = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())
FLAT = 'omi-oldest-age-gauge-flat-1h'
STALE = 'omi-held-content-snapshot-stale'
AGES = (
    'omi_batch_projection_obligation_oldest_age_seconds',
    'omi_batch_pipeline_vendor_held_oldest_age_seconds',
    'omi_summary_debt_oldest_age_seconds',
    'omi_demand_processing_queue_age_seconds',
)
FLAT_EXPR = (
    ' + '.join(
        f'(count({m} > 0 and (max_over_time({m}[1h]) - min_over_time({m}[1h]) == 0)) or vector(0))' for m in AGES
    )
    + ' + ((time() - max(omi_summary_debt_sample_timestamp_seconds) > bool 3600) or vector(1))'
)


@pytest.mark.parametrize('uid', [FLAT, STALE])
def test_rules_match_split_and_combined_exports_and_pass_lint(uid):
    assert SOURCE[uid] == COMBINED[uid]
    assert b.lint_rule(SOURCE[uid], INVENTORY) == []


def test_queries_and_pending_windows_match_the_n5_scope():
    for uid, query, threshold, no_data in (
        (FLAT, FLAT_EXPR, '$A > 0', 'OK'),
        (STALE, 'time() - max(omi_held_content_fleet_snapshot_timestamp_seconds)', '$A > 3600', 'Alerting'),
    ):
        rule = SOURCE[uid]
        assert next(d['model']['expr'] for d in rule['data'] if d['refId'] == 'A') == query
        assert next(d['model']['expression'] for d in rule['data'] if d['refId'] == 'D') == threshold
        assert rule['for'] == '10m'
        assert rule['noDataState'] == no_data
        assert not rule['isPaused']
    assert SOURCE[FLAT]['ruleGroup'] == 'Pipeline drain guards'
    assert SOURCE[STALE]['ruleGroup'] == 'Resilience'


@pytest.mark.parametrize('uid', [FLAT, STALE])
def test_rules_are_agent_tier_warnings_with_required_route_and_annotations(uid):
    rule = SOURCE[uid]
    assert len(uid) < 40
    assert rule['folderUID'] == 'betdycdziadc0e'
    for key, value in {
        'alert_identity': uid,
        'component': 'batch-pipeline',
        'owner': 'omi-pipeline',
        'tier': 'agent',
        'audience': 'agent',
        'severity': 'warning',
        'impact': 'infrastructure',
    }.items():
        assert rule['labels'][key] == value
    assert rule['notification_settings']['receiver'] == 'Omi - Services Alerting (Telegram)'
    assert rule['notification_settings']['mute_time_intervals'] == ['omi-tier-silent']
    annotations = rule['annotations']
    for key in ('summary', 'user_impact', 'scope', 'verification', 'safe_next_action'):
        assert annotations[key]
    runbook = BACKEND.parent / annotations['runbook']
    assert uid in runbook.read_text()
    assert 'authorizes no runtime changes' in annotations['safe_next_action']


def test_all_referenced_metrics_are_declared():
    assert set(
        AGES
        + (
            'omi_summary_debt_sample_timestamp_seconds',
            'omi_held_content_fleet_snapshot_timestamp_seconds',
        )
    ) <= set(INVENTORY['declared_metrics'])


def test_flat_rule_names_the_absence_companions_and_limits_recovery_authority():
    annotations = SOURCE[FLAT]['annotations']
    assert 'omi_batch_projection_obligation_observed_at_seconds' in annotations['verification']
    assert 'omi_batch_pipeline_metrics_refreshed_at_seconds' in annotations['verification']
    assert 'beyond a pod restart' in annotations['safe_next_action']


def test_existing_held_age_page_and_threshold_are_preserved():
    held = SOURCE['omi-pipeline-held-row-age']
    assert held['labels']['tier'] == 'page'
    assert held['labels']['audience'] == 'human'
    assert next(d['model']['expression'] for d in held['data'] if d['refId'] == 'D') == '$A > 21600'


def test_vendor_held_collector_literal_matches_the_frozen_contract():
    assert vendor_route_metrics.HELD_OLDEST_AGE._name == vendor_route_contracts.METRIC_HELD_OLDEST_AGE
