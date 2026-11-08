"""Offline N5 contract: sampler flatness and held-content snapshot freshness."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

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
FLAT_EXPR = ' + '.join(
    f'(count({m} > 0 and (max_over_time({m}[1h]) - min_over_time({m}[1h]) == 0) '
    f'and (time() - min_over_time(timestamp({m})[1h:1m]) >= 3300)'
    + (
        ' and (time() - omi_summary_debt_sample_timestamp_seconds < 300)'
        if m == 'omi_summary_debt_oldest_age_seconds'
        else ''
    )
    + ') or vector(0))'
    for m in AGES
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


def test_summary_blindness_is_separate_debt_and_former_samplers_are_excluded():
    expr = SOURCE[FLAT]['data'][0]['model']['expr']
    assert 'or vector(1)' not in expr
    assert 'max(omi_summary_debt_sample_timestamp_seconds)' not in expr
    assert 'and (time() - omi_summary_debt_sample_timestamp_seconds < 300)' in expr
    runbook = (BACKEND.parent / SOURCE[FLAT]['annotations']['runbook']).read_text()
    assert 'Separate debt: summary-debt producer blindness' in runbook
    assert 'enablement-aware' in runbook
    assert 'unknown coverage' in runbook


@pytest.mark.parametrize('metric', AGES)
def test_flat_query_observation_span_and_summary_freshness_in_prometheus(metric, tmp_path):
    """Execute the committed PromQL, including the pending window, in the real engine.

    Timestamp history works for all four families without counting scrapes or
    assuming that their producer loops use the same cadence. PROMTOOL_BIN follows
    the existing optional offline semantic-test convention; query contracts above
    remain mandatory even where the tool is unavailable.
    """
    executable = os.environ.get('PROMTOOL_BIN') or shutil.which('promtool')
    if not executable:
        pytest.skip('set PROMTOOL_BIN to run the offline Prometheus semantic regression')
    rule = SOURCE[FLAT]
    expr = rule['data'][0]['model']['expr']
    alert = {'alert': 'OldestAgeFlat', 'expr': f'({expr}) > 0', 'for': rule['for']}
    (tmp_path / 'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'flat', 'rules': [alert]}]}))

    def replica(values, instance='a', sampled='0+60x70'):
        labels = f'instance="{instance}",job="backend"'
        result = [{'series': f'{metric}{{{labels}}}', 'values': values}]
        if metric == 'omi_summary_debt_oldest_age_seconds' and sampled is not None:
            result.append({'series': f'omi_summary_debt_sample_timestamp_seconds{{{labels}}}', 'values': sampled})
        return result

    def case(name, inputs, expected, *, when='60m', firing=False):
        return {
            'name': name,
            'interval': '1m',
            'input_series': inputs,
            'promql_expr_test': [
                {'expr': expr, 'eval_time': when, 'exp_samples': [{'labels': '{}', 'value': expected}]}
            ],
            'alert_rule_test': [
                {
                    'eval_time': when,
                    'alertname': 'OldestAgeFlat',
                    'exp_alerts': [{'exp_labels': {}, 'exp_annotations': {}}] if firing else [],
                }
            ],
        }

    tests = [
        case('one new positive sample cannot fire', replica('_ ' * 60 + '100'), 0),
        case('ten minutes of new constant samples cannot fire', replica('_ ' * 50 + '100+0x20'), 0),
        case('54 minutes of history is insufficient', replica('_ ' * 6 + '100+0x64'), 0),
        case('55 minute boundary starts pending only', replica('_ ' * 5 + '100+0x65'), 1),
        case('one hour flat is eligible but still pending', replica('100+0x70'), 1),
        case('one hour flat survives ten minute pending window', replica('100+0x70'), 1, when='65m', firing=True),
        case('a previously firing gauge resolves when it changes', replica('100+0x65 99+0x5'), 0, when='70m'),
        case('changing positive age is healthy', replica('100+1x70'), 0),
        case('zero is healthy empty stock', replica('0+0x70'), 0),
        case('absent optional producer is not failure', [], 0),
        case(
            'different replicas cannot combine their partial histories',
            replica('100+0x30 ' + '_ ' * 40) + replica('_ ' * 31 + '100+0x39', instance='b'),
            0,
        ),
        case(
            'sparser scrapes still establish an observed span',
            replica(' '.join('100' if minute % 2 == 0 else '_' for minute in range(71))),
            1,
            when='66m',
            firing=True,
        ),
    ]
    if metric == 'omi_summary_debt_oldest_age_seconds':
        tests.extend(
            [
                case('absent timestamp excludes summary age', replica('100+0x70', sampled=None), 0),
                case('disabled producer zero timestamp is not failure', replica('100+0x70', sampled='0+0x70'), 0),
                case('exactly 300 second old sample expires', replica('100+0x70', sampled='0+60x55 3300+0x15'), 0),
                case(
                    'healthy winning sampler does not revive retained former sampler',
                    replica('100+0x70', sampled='0+60x10 600+0x60') + replica('100+1x70', instance='b'),
                    0,
                ),
                case(
                    'fresh timestamp from another replica cannot qualify missing timestamp',
                    replica('100+0x70', sampled=None) + replica('100+1x70', instance='b'),
                    0,
                ),
            ]
        )
    spec = {'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': tests}
    (tmp_path / 'test.yaml').write_text(yaml.safe_dump(spec))
    result = subprocess.run(
        [executable, 'test', 'rules', 'test.yaml'], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
