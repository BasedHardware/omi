"""Evaluate exported recovery/lifecycle alerts against counter fixtures.

The supported query grammar covers sum/increase ratios and lifecycle gaps with
a one-hour carry-in. Grafana math and elapsed pending time use the repository
backtest engine. Counter fixtures are monotonic; Prometheus extrapolation and
reset handling are out of scope. Unsupported expressions fail closed.
"""

import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
MONITORING = BACKEND / 'charts' / 'monitoring'
_spec = importlib.util.spec_from_file_location('alert_backtest', BACKEND / 'scripts/alert_backtest.py')
backtest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backtest)
ALERT_RULES_BY_EXPORT = {
    export: {rule['uid']: rule for rule in json.loads((MONITORING / export).read_text())}
    for export in ('alerts/live-stt.json', 'alert-rules.json')
}


def _sum_increase(expression, series):
    match = re.fullmatch(r'sum\(increase\((\w+)(?:\{([^{}]+)\})?\[(?:10|15|30)m\]\)\)', expression)
    assert match, f'Unsupported counter query: {expression}'
    metric, selector = match.groups()
    labels = {}
    for matcher in selector.split(',') if selector else []:
        parsed = re.fullmatch(r'(\w+)="([^"]*)"', matcher.strip())
        assert parsed, f'Unsupported label matcher: {matcher}'
        labels[parsed[1]] = parsed[2]
    return sum(
        samples[-1] - samples[0]
        for name, sample_labels, samples in series
        if name == metric and all(sample_labels.get(key) == value for key, value in labels.items())
    )


def _evaluate(rule, series):
    models = {item['refId']: item['model'] for item in rule['data']}
    accepted = _sum_increase(models['A']['expr'], series)
    numerator, separator, denominator = models['B']['expr'].partition(' / clamp_min(')
    assert separator and denominator.endswith(', 1)'), 'Unsupported ratio query'
    ratio = _sum_increase(numerator, series) / max(_sum_increase(denominator[:-4], series), 1)
    threshold = re.fullmatch(r'\$A >= (\d+) && \$B > ([\d.]+)', models['C']['expression'])
    assert threshold, 'Unsupported Grafana threshold'
    return accepted, ratio, accepted >= int(threshold[1]) and ratio > float(threshold[2])


def _series(metric, track, increase, *, pod='one', job='backend-listen-metrics', labels=None):
    # Nonzero starts prove this evaluates counter increases, not raw totals.
    sample_labels = {'listen_track': track, 'job': job, 'pod': pod}
    if labels:
        sample_labels.update(labels)
    return metric, sample_labels, [100 + increase * i / 10 for i in range(11)]


@pytest.mark.parametrize('export', ['alerts/live-stt.json', 'alert-rules.json'])
@pytest.mark.parametrize(
    'canary_transcribed,canary_failures,stable_transcribed,stable_failures,expected_transcribed,expected_ratio,fires',
    [
        # 2026-09-28..10-12 measured p90 17.8%; batch 1 pages above 25%.
        (100, 30, 10000, 0, 10100, 30 / 10100, False),  # Stable traffic contributes to denominator.
        (100, 30, 0, 0, 100, 0.30, True),
        (0, 0, 100, 30, 100, 0.30, True),  # Stable traffic contributes to numerator.
        (10, 0, 10, 0, 20, 0, False),  # Both cohorts count toward the volume floor.
        (10, 6, 10, 0, 20, 0.30, True),
        (100, 25, 0, 0, 100, 0.25, False),  # Threshold is strictly greater than 25%.
        (100, 2, 0, 0, 100, 0.02, False),  # The former 1% threshold paged on normal traffic.
        (10, 6, 0, 0, 10, 0.60, False),  # High ratio below the volume floor stays healthy.
        (0, 0, 0, 0, 0, 0, False),
    ],
)
def test_recovery_alert_evaluates_all_listen_traffic(
    export,
    canary_transcribed,
    canary_failures,
    stable_transcribed,
    stable_failures,
    expected_transcribed,
    expected_ratio,
    fires,
):
    rule = ALERT_RULES_BY_EXPORT[export]['omi-stt-terminal-after-text']
    transcribed_metric = 'omi_live_session_transcript_outcome_total'
    accepted_metric = 'omi_listen_accepted_total'
    failure_metric = 'omi_live_session_terminal_after_text_total'
    series = [
        _series(transcribed_metric, 'canary', canary_transcribed / 2, labels={'outcome': 'transcribed'}),
        _series(transcribed_metric, 'canary', canary_transcribed / 2, pod='two', labels={'outcome': 'transcribed'}),
        _series(failure_metric, 'canary', canary_failures),
        _series(transcribed_metric, 'stable', stable_transcribed, labels={'outcome': 'transcribed'}),
        _series(failure_metric, 'stable', stable_failures),
        # Admitted sessions and too-short sessions are not the ratio cohort: a
        # flood of either must not satisfy the floor or dilute the failure ratio.
        _series(accepted_metric, 'canary', 10000),
        _series(transcribed_metric, 'canary', 10000, labels={'outcome': 'too_short'}),
        _series(transcribed_metric, 'canary', 10000, job='other-job', labels={'outcome': 'transcribed'}),
        _series(failure_metric, 'canary', 1000, job='other-job'),
    ]
    transcribed, ratio, actual_fires = _evaluate(rule, series)
    assert transcribed == expected_transcribed
    assert math.isclose(ratio, expected_ratio, rel_tol=1e-12, abs_tol=1e-12)
    assert actual_fires is fires


@pytest.mark.parametrize('export', ['alerts/live-stt.json', 'alert-rules.json'])
def test_recovery_alert_no_series_stays_below_floor(export):
    rule = ALERT_RULES_BY_EXPORT[export]['omi-stt-terminal-after-text']
    # Grafana noDataState=OK is the deployed empty-vector policy.
    assert rule['noDataState'] == 'OK'
    assert _evaluate(rule, []) == (0, 0, False)


@pytest.mark.parametrize('export', ['alerts/live-stt.json', 'alert-rules.json'])
@pytest.mark.parametrize(
    'opened,settled,transport_open,fires',
    [
        (29, 24, 4, False),  # Run 5b is an omission warning, not duplicate settlement.
        (10, 10, 2, False),  # Settled while transport remains open is legitimate.
        (10, 8, 0, False),  # Released transport with pending settlement needs investigation.
        (0, 0, 0, False),
        (10, 11, 0, True),  # Exactly-once settlement invariant really is violated.
    ],
)
def test_lifecycle_alert_uses_settlement_invariant(export, opened, settled, transport_open, fires):
    rule = ALERT_RULES_BY_EXPORT[export]['omi-stt-leg-lifecycle-gap']
    models = {item['refId']: item['model'] for item in rule['data']}
    # Evaluate the exported expression, rejecting unsupported query changes.
    query = models['B']['expr']
    assert query == (
        'omi_stt_managed_legs_settled_total{job="backend-listen-metrics"}'
        ' - omi_stt_managed_legs_opened_total{job="backend-listen-metrics"}'
    )
    assert models['C']['expression'] == '$A >= 0 && $B > 0'
    assert (opened >= 0 and settled - opened > 0) is fires
    assert rule['for'] == '2m'
    assert rule['isPaused'] is False
    assert 'direct instrumentation' in rule['annotations']['evaluated_good']


# Evaluate the exported omission queries and Grafana expression/pending chain.
# Each fixture key represents one process/target; no fleet pooling is allowed.
def _lifecycle_gap(expression, counters):
    selector = '{job="backend-listen-metrics"}'
    names = ('opened_total', 'settled_total', 'open')
    query = ' - '.join('omi_stt_managed_legs_' + name + selector for name in names)
    assert expression == query, f'Unsupported lifecycle query: {expression}'
    return counters[0] - counters[1] - counters[2]


def _omission_frame(rule, current, carry_in):
    models = {item['refId']: item['model'] for item in rule['data']}
    gap_query = models['A']['expr']
    # Removing offsets is safe only after asserting the complete supported grammar.
    historical_query = models['B']['expr']
    historical_gap, separator, zero = historical_query.removeprefix('clamp_min((').partition(') or (0 * ')
    assert separator and historical_query.startswith('clamp_min((')
    assert historical_gap.count(' offset 1h') == 3
    assert zero == 'omi_stt_managed_legs_opened_total{job="backend-listen-metrics"}), 0)'
    historical_gap = historical_gap.replace(' offset 1h', '')
    frames = {'A': {}, 'B': {}}
    for key, counters in current.items():
        frames['A'][key] = [_lifecycle_gap(gap_query, counters)]
        frames['B'][key] = [max(_lifecycle_gap(historical_gap, carry_in[key]), 0) if key in carry_in else 0]
    return backtest.evaluate(rule, frames)


@pytest.mark.parametrize('export', ['alerts/live-stt.json', 'alert-rules.json'])
@pytest.mark.parametrize(
    'counters,baseline,duration,fires',
    [
        ((29, 24, 4), (0, 0, 0), 900, True),  # Run 5b: new +1 sustained for 15m.
        ((29, 24, 4), None, 900, True),  # New pod: no historical series, zero baseline.
        ((29, 24, 4), (0, 0, 0), 885, False),  # 59 samples span <15m; still pending.
        ((29, 24, 4), (20, 15, 4), 1200, False),  # Unchanged +1 control carry-in.
        ((29, 24, 4), (20, 20, 1), 900, True),  # Negative carry-in cannot mask new +1.
        ((100, 10, 90), (0, 0, 0), 1200, False),  # Many normal in-flight legs.
        ((10, 10, 2), (0, 0, 0), 1200, False),  # Legitimate settled-but-open legs.
        ((0, 0, 0), (0, 0, 0), 1200, False),
    ],
)
def test_omission_alert_requires_new_positive_gap_for_15_minutes(export, counters, baseline, duration, fires):
    rule = ALERT_RULES_BY_EXPORT[export]['omi-stt-leg-settlement-omission']
    key = (('pod', 'canary'), ('target', 'modulate'))
    carry_in = {} if baseline is None else {key: baseline}
    samples = [(t, _omission_frame(rule, {key: counters}, carry_in)) for t in range(0, duration + 1, 15)]
    result = backtest.episodes(rule, samples, 0, duration, 15)
    assert bool(result['episodes']) is fires
    if fires:
        assert result['total_duration_seconds'] == duration - 900 + 15
    assert rule['for'] == '15m'
    assert rule['noDataState'] == 'OK'
    assert rule['isPaused'] is False


@pytest.mark.parametrize('export', ['alerts/live-stt.json', 'alert-rules.json'])
@pytest.mark.parametrize('interruption', ['recovered', 'missing'])
def test_omission_alert_transient_and_missing_samples_reset_pending(export, interruption):
    rule = ALERT_RULES_BY_EXPORT[export]['omi-stt-leg-settlement-omission']
    key = (('pod', 'canary'), ('target', 'modulate'))
    samples = []
    for t in range(0, 1801, 15):
        current = {key: (29, 24, 4)}
        if t == 885:
            current = {} if interruption == 'missing' else {key: (29, 25, 4)}
        samples.append((t, _omission_frame(rule, current, {})))
    # Two <15m runs separated by one good/missing evaluation cannot be combined.
    result = backtest.episodes(rule, samples, 0, 1800, 15)
    assert result['episodes'] == 1  # Only the second full 15m interval fires at 1800.
    assert result['total_duration_seconds'] == 15
    assert backtest.episodes(rule, samples[:-1], 0, 1785, 15)['episodes'] == 0


@pytest.mark.parametrize('export', ['alerts/live-stt.json', 'alert-rules.json'])
def test_omission_alert_keeps_canary_debt_separate_from_control_and_negative_gap(export):
    rule = ALERT_RULES_BY_EXPORT[export]['omi-stt-leg-settlement-omission']
    keys = [(('pod', pod), ('target', 'modulate')) for pod in ('canary', 'control', 'settled-open')]
    frame = _omission_frame(
        rule,
        dict(zip(keys, [(29, 24, 4), (20, 15, 4), (10, 10, 1)])),
        {keys[1]: (10, 5, 4)},
    )
    assert frame == {keys[0]: 1, keys[1]: 0, keys[2]: 0}


def test_runbook_exhaustion_ratio_aggregates_mismatched_label_sets():
    doc = (BACKEND / 'docs/runbooks/live-stt-routing.md').read_text()
    expression = re.search(r'\| Exhausted chains \| `([^`]+)`', doc)[1]
    numerator, denominator = expression.split(' / ')
    series = [
        _series('omi_stt_chain_exhausted_total', 'canary', 3, labels={'demand_cohort': 'all'}),
        _series('omi_listen_accepted_total', 'canary', 10, labels={'transcription_source': 'device'}),
        _series('omi_listen_accepted_total', 'canary', 20, labels={'client_platform': 'ios'}),
    ]
    assert _sum_increase(numerator, series) / _sum_increase(denominator, series) == 0.1
