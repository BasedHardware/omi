"""Prevent SLO budget, paired-window, sparse-series and export drift."""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

import pytest

MONITORING = Path(__file__).resolve().parents[2] / 'charts/monitoring'
SCOPES = {
    'live': ('omi_live_session_transcript_outcome_total', 'job="backend-listen-metrics"', 0.921),
    'chat': ('omi_journey_accepted_total', 'job="cloud-run-application-metrics",journey="chat_response"', 0.994),
    'pusher': ('omi_journey_terminal_total', 'job="pusher-metrics",journey="pusher_session"', 0.989),
}
PAIRS = {
    'critical': [('1h', '5m', 14.4), ('6h', '30m', 6)],
    'warning': [('24h', '2h', 3), ('3d', '6h', 1)],
}
# Receipt bound for chat critical pages. Raise it only when an interval is a real failure burst.
CHAT_CRITICAL_INTERVAL_BOUND = 0


# A burn multiplier whose share exceeds 100% can never fire; cap it at half of eligible work.
BURN_SHARE_CAP = 0.5


def _burn_share(target, multiplier):
    return min((1 - target) * multiplier, BURN_SHARE_CAP)


def _seconds(duration):
    return int(duration[:-1]) * {'s': 1, 'm': 60, 'h': 3600}[duration[-1]]


def _volume_floor(classic, threshold):
    """Smallest count at or above the classic floor where one miss stays under the burn share."""
    minimum = classic
    while not 1 / minimum < threshold:
        minimum += 1
    return minimum


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
    chat_page = journey == 'chat' and severity == 'critical'
    # Two burn arms plus the empty-series zero. Pusher has no accepted zero-completion arm.
    assert expr.count(' > 0) or (') == 2
    assert float(rule['annotations']['slo_target']) == target
    assert f'| {journey} | {target:.1%} |' in (MONITORING / 'SLOS.md').read_text()
    thresholds = re.findall(r'> bool ([0-9.]+)', expr)
    if chat_page:
        # Long windows only, counted on explicit failure|stale terminals.
        # Accepted minus success invents misses when Cloud Run series churn.
        assert len(thresholds) == 2
        assert all(
            math.isclose(float(value), (1 - target) * multiplier, rel_tol=1e-10)
            for value, multiplier in zip(thresholds, (14.4, 6))
        )
        assert '[5m]' not in expr and '[30m]' not in expr and '[10m]' not in expr
        assert ' - ' not in expr
        assert 'outcome=~"failure|stale"' in expr
        assert 'cancelled' not in expr
        assert 'outcome="success"' not in expr
        checked = [('1h', 20, 4, 14.4), ('6h', 40, 7, 6)]
    else:
        assert len(thresholds) == 4
        checked = []
        for index, (long, short, multiplier) in enumerate(PAIRS[severity]):
            assert all(
                math.isclose(float(v), _burn_share(target, multiplier), rel_tol=1e-10)
                for v in thresholds[index * 2 : index * 2 + 2]
            )
            if severity == 'critical':
                burn = _burn_share(target, multiplier)
                long_min = _volume_floor(20, burn)
                short_min = _volume_floor(5, burn)
            else:
                long_min, short_min = 20, 5
            checked.extend([(long, long_min, None, multiplier), (short, short_min, None, multiplier)])
    for window, minimum, bad_minimum, multiplier in checked:
        if chat_page:
            assert math.isclose((1 - target) * multiplier, float(thresholds[0] if window == '1h' else thresholds[1]))
        labels = scope + ',outcome=~"transcribed|no_transcript"' if journey == 'live' else scope
        valid = f'sum(increase({metric}{{{labels}}}[{window}]))'
        assert f'({valid} >= bool {minimum})' in expr
        if journey == 'live':
            assert f'outcome="no_transcript"}}[{window}]' in expr
            assert 'too_short' not in expr
        elif journey == 'chat':
            bad = (
                f'(sum(increase(omi_journey_terminal_total{{{scope},outcome=~"failure|stale"}}[{window}]))'
                f' or (clamp_min({valid}, 1) * 0))'
            )
            denom = f'clamp_min({valid}, 1)'
            assert f'({bad} / {denom}) > bool ' in expr
            if bad_minimum is not None:
                assert f'({bad} >= bool {bad_minimum})' in expr
        else:
            assert 'omi_journey_accepted_total' not in expr
            assert ' - ' not in expr
            bad = f'(sum(increase({metric}{{{scope},outcome=~"failure|cancelled"}}[{window}]))' f' or ({valid} * 0))'
            assert f'({bad} / {valid}) > bool ' in expr
            assert 'outcome="success"' not in expr
    if chat_page:
        assert '[10m]' not in expr
        assert rule['for'] == '5m'
        scope_text = rule['annotations']['scope']
        assert 'omi-journey-chat-success-critical' in scope_text
        assert 'omi-journey-chat-fail' in scope_text
        assert 'alerts/resilience.json' in scope_text
    else:
        if journey == 'chat':
            assert ' - ' not in expr
            assert 'outcome=~"failure|stale"' in expr
            assert 'cancelled' not in expr
            assert 'outcome="success"' not in expr
        # Burn-rate pairs already debounce; the pending duration is the house floor for ratio rules.
        assert rule['for'] == {'critical': '2m', 'warning': '15m'}[severity]
    assert rule['keep_firing_for'] == '0s'
    assert rule['noDataState'] == 'NoData'  # absent SLI must never resolve healthy
    assert rule['execErrState'] == 'KeepLast'  # datasource canary owns query-path outages
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
    # The accepted counter is sparse until traffic, so its absence after a restart is not a vanished family.
    assert 'absent(omi_live_stt_accepted_total' not in expr
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
        # Replays record the pending they ran with; longer live pending only suppresses pages.
        assert _seconds(proof['for']) <= _seconds(rule['for'])
        assert 0 < proof['evaluated_samples'] <= evidence['expected_samples']
        assert len(proof['post_warmup_firing_intervals']) <= len(proof['sampled_firing_intervals'])
    for journey, (_, _, target) in SCOPES.items():
        baseline = evidence['baselines'][journey]
        assert baseline['valid_events'] > 20
        assert baseline['good_events'] / baseline['valid_events'] >= target
        assert baseline['hourly_presence_samples'] >= 240


@pytest.mark.parametrize('journey', SCOPES)
@pytest.mark.parametrize('severity', PAIRS)
def test_each_minimum_event_gate_fits_measured_baseline_volume(journey, severity, rule_exports):
    evidence = json.loads((MONITORING / 'slo-backtest.prod.json').read_text())
    rate = evidence['baselines'][journey]['valid_events'] / (10 * 24 * 60)
    expr = rule_exports['split'][f'omi-slo-{journey}-{severity}'][0]['data'][0]['model']['expr']
    gates = re.findall(r'\[(\d+)([mhd])\]\)\) >= bool (\d+)', expr)
    if journey == 'chat' and severity == 'critical':
        expected_gates = 2  # 1h and 6h accepted floors; total outage stays on the live chat rules
    else:
        expected_gates = 4
    assert len(gates) == expected_gates
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
    assert case['expression'] == backtest.synthetic_expression(rule, rate, ending=ending)
    # Chat counts failure|stale only, so a success gap does not page.
    # Pusher counts terminal failure|cancelled. A cancelled burst can page; in-flight work cannot.
    # Value is Prometheus's result for the substituted expression.
    if journey == 'chat' or ending == 'no_terminal':
        assert case['value'] == 0
    else:
        assert case['value'] > 0
    assert case['outage_minutes'] == 10
    assert math.isclose(case['events_per_minute'], rate)


@pytest.mark.parametrize('severity', PAIRS)
def test_pusher_sli_counts_terminal_failures_not_accepted_work(severity, rule_exports):
    rule = rule_exports['split'][f'omi-slo-pusher-{severity}'][0]
    expr = rule['data'][0]['model']['expr']
    assert 'omi_journey_accepted_total' not in expr
    assert ' - ' not in expr
    assert 'outcome=~"failure|cancelled"' in expr
    assert '[10m]' not in expr
    scope = rule['annotations']['scope']
    assert 'in-flight' in scope
    assert 'omi-journey-pusher-success-critical' in scope
    assert 'omi-journey-pusher-fail' in scope
    assert '1000' in scope and '1001' in scope and '1011' in scope


def _annotation_windows(text):
    return set(re.findall(r'(?<![\d.])(\d+[mhd])\b', text))


@pytest.mark.parametrize('journey', SCOPES)
@pytest.mark.parametrize('severity', PAIRS)
def test_threshold_and_scope_name_exactly_the_expression_windows(journey, severity, rule_exports):
    rule = rule_exports['split'][f'omi-slo-{journey}-{severity}'][0]
    expr = rule['data'][0]['model']['expr']
    expr_windows = set(re.findall(r'\[(\d+[mhd])\]', expr))
    for field in ('threshold', 'scope'):
        assert _annotation_windows(rule['annotations'][field]) == expr_windows
        has_zero_completion = '[10m]' in expr and '< bool 1' in expr
        assert ('10m' in rule['annotations'][field]) is has_zero_completion
    assert 'chat fast short window' not in rule['annotations']['scope']


@pytest.mark.parametrize('journey', SCOPES)
def test_one_miss_at_each_critical_volume_gate_stays_under_the_burn_threshold(journey, rule_exports):
    expr = rule_exports['split'][f'omi-slo-{journey}-critical'][0]['data'][0]['model']['expr']
    saw_burn_arm = False
    for arm in expr.split(' > 0) or ('):
        thresholds = [float(value) for value in re.findall(r'(?<!=)> bool ([0-9.]+)', arm)]
        if not thresholds:
            continue
        saw_burn_arm = True
        assert len(set(thresholds)) == 1
        threshold = thresholds[0]
        gates = [int(count) for _, _, count in re.findall(r'\[(\d+)([mhd])\]\)\) >= bool (\d+)', arm)]
        assert gates
        for minimum in gates:
            assert 1 / minimum < threshold
    assert saw_burn_arm


def test_chat_critical_burn_arms_ignore_three_isolated_misses(rule_exports):
    expr = rule_exports['split']['omi-slo-chat-critical'][0]['data'][0]['model']['expr']
    assert 'outcome=~"failure|stale"' in expr
    assert ' - ' not in expr
    assert '>= bool 4' in expr
    assert '>= bool 7' in expr


def test_chat_critical_uses_explicit_failures_and_five_minute_pending(rule_exports):
    rule = rule_exports['split']['omi-slo-chat-critical'][0]
    expr = rule['data'][0]['model']['expr']
    assert rule['for'] == '5m'
    assert 'outcome=~"failure|stale"' in expr
    assert ' - ' not in expr
    assert '[10m]' not in expr
    assert 'omi-journey-chat-success-critical' in rule['annotations']['scope']
    assert 'omi-journey-chat-fail' in rule['annotations']['scope']


def test_chat_critical_receipt_intervals_stay_within_bound():
    evidence = json.loads((MONITORING / 'slo-backtest.prod.json').read_text())
    proof = evidence['rules']['omi-slo-chat-critical']
    assert proof['for'] == '5m'
    assert len(proof['sampled_firing_intervals']) <= CHAT_CRITICAL_INTERVAL_BOUND
    assert len(proof['post_warmup_firing_intervals']) <= CHAT_CRITICAL_INTERVAL_BOUND


def test_page_replay_stays_within_the_baseline_page_budget():
    evidence = json.loads((MONITORING / 'slo-backtest.prod.json').read_text())
    replay = evidence['page_replay']
    rules = {r['uid']: r for r in json.loads((MONITORING / 'alerts' / 'journey-slos.json').read_text())}
    assert replay['end_unix'] == evidence['end_unix']
    assert set(replay['expressions']) == set(replay['rules'])
    for uid, expr in replay['expressions'].items():
        assert expr == rules[uid]['data'][0]['model']['expr'], uid
    assert replay['step_seconds'] <= 900
    assert replay['days'] >= 10
    for uid in ('omi-slo-live-critical', 'omi-slo-chat-critical', 'omi-slo-pusher-critical'):
        proof = replay['rules'][uid]
        assert proof['failed_days'] == 0
        assert proof['would_page'] == 0
        assert proof['pages'] == []
    for uid in ('omi-slo-chat-warning', 'omi-slo-live-warning', 'omi-slo-pusher-warning'):
        proof = replay['rules'][uid]
        assert proof['failed_days'] == 0
        assert proof['would_page'] <= 1
        assert len(proof['pages']) == proof['would_page']
        assert proof['explanation']
    assert replay['rules']['omi-slo-chat-critical']['for'] == '5m'


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


def test_every_burn_threshold_is_reachable(rule_exports):
    checked = 0
    for uid, (rule, _) in rule_exports['split'].items():
        if uid == 'omi-slo-live-signal-dead':
            continue  # volume gates compare counts, not shares
        for value in re.findall(r'> bool ([0-9.]+)', rule['data'][0]['model']['expr']):
            assert 0 < float(value) < 1, uid
            checked += 1
    assert checked == 22
