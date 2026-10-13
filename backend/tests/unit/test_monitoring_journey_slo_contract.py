"""Prevent SLO budget, paired-window, sparse-series and export drift."""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

import pytest

MONITORING = Path(__file__).resolve().parents[2] / 'charts/monitoring'
SCOPES = {
    'live': ('omi_live_session_transcript_outcome_total', 'job="backend-listen-metrics"', 0.95),
    'chat': ('omi_journey_accepted_total', 'job="cloud-run-application-metrics",journey="chat_response"', 0.995),
    'pusher': ('omi_journey_accepted_total', 'job="pusher-metrics",journey="pusher_session"', 0.955),
}
PAIRS = {
    'critical': [('1h', '5m', 14.4), ('6h', '30m', 6)],
    'warning': [('24h', '2h', 3), ('3d', '6h', 1)],
}


@lru_cache
def _raw_rules(path):
    """Retain raw UID blocks: semantic equality alone permits export reformatting."""
    text = path.read_text()
    decoder = json.JSONDecoder()
    index = text.index('[') + 1
    result = {}
    while True:
        while text[index] in ' \n,':
            index += 1
        if text[index] == ']':
            break
        rule, end = decoder.raw_decode(text, index)
        result[rule['uid']] = (rule, text[index:end])
        index = end
    return result


@pytest.fixture(scope='module')
def rule_exports():
    # Parse the large combined export once as shared test setup.
    return {
        'split': _raw_rules(MONITORING / 'alerts/journey-slos.json'),
        'combined': _raw_rules(MONITORING / 'alert-rules.json'),
    }


@pytest.mark.parametrize('journey', SCOPES)
@pytest.mark.parametrize('severity', PAIRS)
def test_slo_rules_use_exact_budget_and_two_independent_window_pairs(journey, severity, rule_exports):
    rules = rule_exports['split']
    uid = f'omi-slo-{journey}-{severity}'
    rule, raw = rules[uid]
    metric, scope, target = SCOPES[journey]
    expr = rule['data'][0]['model']['expr']
    assert expr.count(' > 0) or (') == (4 if journey == 'pusher' and severity == 'critical' else 2)
    assert float(rule['annotations']['slo_target']) == target
    thresholds = re.findall(r'> bool ([0-9.]+)', expr)
    assert len(thresholds) == 4
    for index, (long, short, multiplier) in enumerate(PAIRS[severity]):
        assert all(
            math.isclose(float(v), (1 - target) * multiplier, rel_tol=1e-10)
            for v in thresholds[index * 2 : index * 2 + 2]
        )
        for window, minimum in [(long, 20), (short, 2 if journey == 'chat' and short == '5m' else 5)]:
            labels = scope + ',outcome=~"transcribed|no_transcript"' if journey == 'live' else scope
            valid = f'sum(increase({metric}{{{labels}}}[{window}]))'
            assert f'({valid} >= bool {minimum})' in expr
            if journey == 'live':
                assert f'outcome="no_transcript"}}[{window}]' in expr
                assert 'too_short' not in expr
            else:
                good = f'sum(increase(omi_journey_terminal_total{{{scope},outcome="success"}}[{window}]))'
                assert f'clamp_min({valid} - ({good} or ({valid} * 0)), 0)' in expr
                assert 'success|failure' not in expr
    assert rule['data'][1]['model']['expression'] == '$A > 0'
    assert rule['data'][2]['model']['expression'] == 'C'
    assert rule['condition'] == 'D'
    assert rule['for'] == rule['keep_firing_for'] == '0s'
    assert rule['noDataState'] == 'NoData'  # absent SLI must never resolve healthy
    assert rule['execErrState'] == 'Error'
    assert rule['labels']['severity'] == severity
    assert rule['labels']['alert_identity'] == uid
    assert rule['notification_settings']['receiver'] == 'Omi - Services Alerting (Telegram)'
    assert not rule['isPaused']
    combined = rule_exports['combined']
    assert combined[uid] == (rule, raw)


def test_slo_scope_and_documentation_do_not_claim_uningested_sync(rule_exports):
    rules = rule_exports['split']
    assert set(rules) == {f'omi-slo-{journey}-{severity}' for journey in SCOPES for severity in PAIRS} | {
        'omi-slo-live-signal-dead'
    }
    doc = (MONITORING / 'SLOS.md').read_text()
    for journey, (_, _, target) in SCOPES.items():
        assert f'| {journey} | {target:.1%} |' in doc
    assert 'Sync/upload: withheld' in doc


def test_live_slo_liveness_detects_vanished_families_even_without_demand(rule_exports):
    rule, raw = rule_exports['split']['omi-slo-live-signal-dead']
    expr = rule['data'][0]['model']['expr']
    assert 'absent(omi_live_session_transcript_outcome_total{job="backend-listen-metrics"})' in expr
    assert 'absent(omi_live_stt_accepted_total{job="backend-listen-metrics"})' in expr
    assert expr.count('or vector(0)') == 5
    assert 'outcome=' not in expr  # quiet sessions still prove emission
    assert 'journey="live_transcription"' in expr  # retained client-boundary coverage
    assert '< bool 1' in expr
    assert rule['noDataState'] == 'NoData'
    assert rule['for'] == '5m'
    assert rule['labels']['severity'] == 'warning'
    assert rule_exports['combined'][rule['uid']] == (rule, raw)


def test_backtest_evidence_matches_every_rule_and_achievable_declared_targets(rule_exports):
    rules = rule_exports['split']
    evidence = json.loads((MONITORING / 'slo-backtest.prod.json').read_text())
    assert evidence['identity_tier'] == 'ro-prod'
    assert evidence['step_seconds'] == 300
    assert set(evidence['rules']) == set(rules)
    for uid, (rule, _) in rules.items():
        proof = evidence['rules'][uid]
        assert proof['expression'] == rule['data'][0]['model']['expr']
        assert proof['for'] == rule['for']
        assert 0 < proof['evaluated_samples'] <= evidence['expected_samples']
        assert len(proof['post_warmup_firing_intervals']) <= len(proof['sampled_firing_intervals'])
    for journey, (_, _, target) in SCOPES.items():
        baseline = evidence['baselines'][journey]
        assert baseline['valid_events'] > 20
        assert baseline['good_events'] / baseline['valid_events'] >= target
        assert baseline['hourly_presence_samples'] == 241


@pytest.mark.parametrize('journey', SCOPES)
@pytest.mark.parametrize('severity', PAIRS)
def test_each_minimum_event_gate_fits_measured_baseline_volume(journey, severity, rule_exports):
    evidence = json.loads((MONITORING / 'slo-backtest.prod.json').read_text())
    rate = evidence['baselines'][journey]['valid_events'] / (10 * 24 * 60)
    expr = rule_exports['split'][f'omi-slo-{journey}-{severity}'][0]['data'][0]['model']['expr']
    gates = re.findall(r'\[(\d+)([mhd])\]\)\) >= bool (\d+)', expr)
    assert len(gates) == (5 if journey == 'pusher' and severity == 'critical' else 4)
    for count, unit, minimum in gates:
        expected = rate * int(count) * {'m': 1, 'h': 60, 'd': 1440}[unit]
        assert int(minimum) <= expected, (journey, count, unit, minimum, expected)


@pytest.mark.parametrize('journey', ['chat', 'pusher'])
@pytest.mark.parametrize('ending', ['cancelled', 'no_terminal'])
def test_ten_minute_total_outage_pages_at_measured_volume(journey, ending, rule_exports):
    import importlib.util

    script = MONITORING.parents[1] / 'scripts/backtest_journey_slos.py'
    spec = importlib.util.spec_from_file_location('slo_backtest', script)
    backtest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backtest)
    evidence = json.loads((MONITORING / 'slo-backtest.prod.json').read_text())
    case = evidence['synthetic_cases'][f'{journey}_{ending}_10m']
    rule = rule_exports['split'][case['uid']][0]
    rate = evidence['baselines'][journey]['valid_events'] / 14400
    assert case['expression'] == backtest.synthetic_expression(rule, rate)
    assert case['value'] > 0  # exact expression executed by Prometheus, not hand-computed burn
    assert case['outage_minutes'] == 10
    assert math.isclose(case['accepted_per_minute'], rate)


def test_pusher_no_completion_arm_is_independent_of_long_window_success(rule_exports):
    expr = rule_exports['split']['omi-slo-pusher-critical'][0]['data'][0]['model']['expr']
    assert 'omi_journey_accepted_total{job="pusher-metrics",journey="pusher_session"}[10m])) >= bool 20' in expr
    assert 'outcome="success"}[10m])) or vector(0)) < bool 1' in expr


def test_vanished_live_families_fire_exact_liveness_expression(rule_exports):
    import importlib.util

    script = MONITORING.parents[1] / 'scripts/backtest_journey_slos.py'
    spec = importlib.util.spec_from_file_location('slo_backtest', script)
    backtest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backtest)
    evidence = json.loads((MONITORING / 'slo-backtest.prod.json').read_text())
    case = evidence['synthetic_cases']['live_both_families_vanished']
    rule = rule_exports['split'][case['uid']][0]
    assert case['expression'] == backtest.vanished_expression(rule)
    assert case['value'] > 0
