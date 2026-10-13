"""Prevent SLO budget, paired-window, sparse-series and export drift."""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

import pytest

MONITORING = Path(__file__).resolve().parents[2] / 'charts/monitoring'
SCOPES = {
    'live': (
        'omi_client_journey_terminal_total',
        'job="backend-listen-metrics",journey="live_transcription"',
        'success|failure|degraded|unknown',
        'failure|degraded|unknown',
        0.99,
    ),
    'chat': (
        'omi_journey_terminal_total',
        'job="cloud-run-application-metrics",journey="chat_response"',
        'success|failure',
        'failure',
        0.995,
    ),
    'pusher': (
        'omi_journey_terminal_total',
        'job="pusher-metrics",journey="pusher_session"',
        'success|failure',
        'failure',
        0.999,
    ),
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
    metric, scope, valid_outcomes, bad_outcomes, target = SCOPES[journey]
    expr = rule['data'][0]['model']['expr']
    # Each product is AND. Filter false arms before set OR so a missing short
    # window cannot suppress the independent slow-burn arm. The last operand
    # returns healthy zero only when the observed valid denominator exists.
    operands = expr.split(' > 0) or (')
    assert len(operands) == 3
    branches = operands[:2]
    longest = '3d' if severity == 'warning' else '6h'
    assert operands[2] == (f'sum(increase({metric}{{{scope},outcome=~"{valid_outcomes}"}}[{longest}])) * 0)')
    assert ' + ' not in expr
    assert float(rule['annotations']['slo_target']) == target
    for branch, (long, short, multiplier) in zip(branches, PAIRS[severity]):
        thresholds = re.findall(r'> bool ([0-9.]+)', branch)
        assert len(thresholds) == 2
        assert all(math.isclose(float(value), (1 - target) * multiplier, rel_tol=1e-10) for value in thresholds)
        for window, minimum in [(long, 20), (short, 5)]:
            valid = f'sum(increase({metric}{{{scope},outcome=~"{valid_outcomes}"}}[{window}]))'
            bad = f'sum(increase({metric}{{{scope},outcome=~"{bad_outcomes}"}}[{window}]))'
            assert f'(({bad} or ({valid} * 0)) / {valid})' in branch
            assert f'({valid} >= bool {minimum})' in branch
        assert branch.count(' * (') == 3  # both windows and both volume gates
        assert 'cancelled' not in branch
        assert 'clamp_min' not in branch  # small denominators must not inflate success
        assert 'vector(0)' not in branch  # absent denominator is not healthy traffic
    assert rule['data'][1]['model']['expression'] == '$A > 0'
    assert rule['data'][2]['model']['expression'] == 'C'
    assert rule['condition'] == 'D'
    assert rule['for'] == rule['keep_firing_for'] == '0s'
    assert rule['noDataState'] == 'OK'  # telemetry absence is a separate ownership alert
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
    for journey, (_, _, _, _, target) in SCOPES.items():
        assert f'| {journey} | {target:.1%} |' in doc
    assert 'Sync/upload: withheld' in doc


def test_live_slo_liveness_includes_cancelled_sessions_and_independent_audio_demand(rule_exports):
    rule, raw = rule_exports['split']['omi-slo-live-signal-dead']
    expr = rule['data'][0]['model']['expr']
    assert 'journey="live_transcription"}[1h])) or vector(0)' in expr
    assert 'outcome=' not in expr  # quiet/cancelled sessions still prove emission
    assert 'omi_live_stt_accepted_total{job="backend-listen-metrics"}[1h])) > bool 20' in expr
    assert '< bool 1' in expr
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
    for journey, (_, _, _, _, target) in SCOPES.items():
        baseline = evidence['baselines'][journey]
        assert baseline['valid_events'] > 20
        assert baseline['good_events'] / baseline['valid_events'] >= target
        assert baseline['hourly_presence_samples'] == 241
