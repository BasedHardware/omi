"""Evaluate exported recovery-alert queries against counter fixtures.

This deliberately supports only this rule's sum/increase, division, clamp_min
and Grafana threshold grammar. Counter fixtures cover exactly the 10m window
with monotonic samples; Prometheus extrapolation/reset handling is out of scope.
Unsupported expressions fail rather than silently evaluating a different query.
"""

import json
import re
from pathlib import Path

import pytest

MONITORING = Path(__file__).resolve().parents[2] / 'charts' / 'monitoring'


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


def _series(metric, track, increase, *, pod='one', job='backend-listen-metrics'):
    # Nonzero starts prove this evaluates counter increases, not raw totals.
    return metric, {'listen_track': track, 'job': job, 'pod': pod}, [100 + increase * i / 10 for i in range(11)]


@pytest.mark.parametrize('export', ['alerts/live-stt.json', 'alert-rules.json'])
@pytest.mark.parametrize(
    'canary_accepted,canary_failures,stable_accepted,stable_failures,expected_ratio,fires',
    [
        (100, 2, 10000, 0, 0.02, True),  # Recovery-off traffic cannot dilute 2% canary failure.
        (100, 2, 0, 0, 0.02, True),
        (100, 0, 10000, 1000, 0, False),  # Other cohorts cannot inflate the numerator.
        (19, 1, 10000, 0, 1 / 19, False),  # Other cohorts cannot satisfy the volume floor.
        (20, 1, 10000, 0, 0.05, True),
        (100, 1, 10000, 1000, 0.01, False),  # Threshold is strictly greater than 1%.
        (0, 0, 10000, 1000, 0, False),
    ],
)
def test_recovery_alert_evaluates_only_canary_cohort(
    export, canary_accepted, canary_failures, stable_accepted, stable_failures, expected_ratio, fires
):
    rule = next(
        rule for rule in json.loads((MONITORING / export).read_text()) if rule['uid'] == 'omi-stt-terminal-after-text'
    )
    accepted_metric = 'omi_listen_accepted_total'
    failure_metric = 'omi_live_session_terminal_after_text_total'
    series = [
        _series(accepted_metric, 'canary', canary_accepted / 2),
        _series(accepted_metric, 'canary', canary_accepted / 2, pod='two'),
        _series(failure_metric, 'canary', canary_failures),
        _series(accepted_metric, 'stable', stable_accepted),
        _series(failure_metric, 'stable', stable_failures),
        _series(accepted_metric, 'canary', 10000, job='other-job'),
        _series(failure_metric, 'canary', 1000, job='other-job'),
    ]
    accepted, ratio, actual_fires = _evaluate(rule, series)
    assert accepted == canary_accepted
    assert ratio == pytest.approx(expected_ratio)
    assert actual_fires is fires


@pytest.mark.parametrize('export', ['alerts/live-stt.json', 'alert-rules.json'])
def test_recovery_alert_no_series_stays_below_floor(export):
    rule = next(
        rule for rule in json.loads((MONITORING / export).read_text()) if rule['uid'] == 'omi-stt-terminal-after-text'
    )
    # Grafana noDataState=OK is the deployed empty-vector policy.
    assert rule['noDataState'] == 'OK'
    assert _evaluate(rule, []) == (0, 0, False)
