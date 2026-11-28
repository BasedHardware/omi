"""The Soniox daily-hours page replaces Soniox's batch daily cap (David 2026-11-27), so it is pinned here."""

import json
from pathlib import Path

import pytest

from scripts.alert_backtest import math_expression
from utils.batch_pipeline import vendor_route_contracts as c
from utils.batch_pipeline import vendor_route_metrics as m

MONITORING = Path(__file__).resolve().parents[2] / 'charts' / 'monitoring'
UID = 'omi-batch-soniox-daily-hours'


def _rule(path):
    return next(rule for rule in json.loads(path.read_text()) if rule['uid'] == UID)


@pytest.fixture(scope='module')
def rule():
    return _rule(MONITORING / 'alerts' / 'backend-sync.json')


def test_the_page_reads_24h_of_batch_soniox_audio_hours(rule):
    query = next(node for node in rule['data'] if node['refId'] == 'A')
    expr = query['model']['expr']
    assert query['datasourceUid'] == 'gmp-cloud-run'
    assert c.METRIC_ATTEMPT_AUDIO in expr and 'provider="soniox"' in expr
    assert '[24h]' in expr and '/ 3600' in expr
    assert 'backend-sync|backend-sync-backfill|backend-integration' in expr


def test_the_emitted_counter_is_the_one_the_page_reads():
    assert m.ATTEMPT_AUDIO._name + '_total' == c.METRIC_ATTEMPT_AUDIO


@pytest.mark.parametrize('hours, fires', [(1499.0, False), (1500.0, False), (1500.5, True), (4000.0, True)])
def test_it_fires_above_1500_audio_hours(rule, hours, fires):
    threshold = next(node for node in rule['data'] if node['refId'] == 'C')['model']['expression']
    assert bool(math_expression(threshold, {'A': hours})) is fires


def test_it_pages_a_human_and_is_in_the_fail_closed_live_gate(rule):
    assert rule['for'] == '5m' and not rule['isPaused']
    assert rule['labels']['tier'] == 'page' and rule['labels']['audience'] == 'human'
    assert rule['notification_settings']['receiver']
    assert UID in json.loads((MONITORING / 'live-alert-gate.json').read_text())['uids']


def test_the_combined_export_matches_the_split_source(rule):
    assert _rule(MONITORING / 'alert-rules.json') == rule


def test_the_prod_table_it_replaces_a_cap_for_has_no_soniox_cap():
    table = json.loads(
        (MONITORING.parent.parent / 'deploy' / 'batch-pipeline' / 'vendor_route_table.prod.json').read_text()
    )
    assert table['routes']['soniox']['daily_audio_hours_cap'] is None
