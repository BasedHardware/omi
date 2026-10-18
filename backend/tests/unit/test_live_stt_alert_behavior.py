"""Evaluate exported recovery-alert queries against counter fixtures.

This deliberately supports only this rule's sum/increase, division, clamp_min
and Grafana threshold grammar. Counter fixtures cover exactly the 10m window
with monotonic samples; Prometheus extrapolation/reset handling is out of scope.
Unsupported expressions fail rather than silently evaluating a different query.
"""

import json
import math
import re
from pathlib import Path

import pytest

MONITORING = Path(__file__).resolve().parents[2] / 'charts' / 'monitoring'
ALERT_RULES_BY_EXPORT = {
    export: {rule['uid']: rule for rule in json.loads((MONITORING / export).read_text())}
    for export in ('alerts/live-stt.json', 'alert-rules.json')
}


def _sum_increase(expression, series):
    match = re.fullmatch(r'sum\(increase\((\w+)\{([^{}]+)\}\[10m\]\)\)', expression)
    assert match, f'Unsupported counter query: {expression}'
    metric, selector = match.groups()
    labels = {}
    for matcher in selector.split(','):
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
        (29, 24, 4, False),  # Run 5b: positive arithmetic gap is not a serving-loss oracle.
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
