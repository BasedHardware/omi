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
        (100, 2, 10000, 0, 10100, 2 / 10100, False),  # Stable traffic contributes to denominator.
        (100, 2, 0, 0, 100, 0.02, True),
        (0, 0, 100, 2, 100, 0.02, True),  # Stable traffic contributes to numerator.
        (10, 0, 10, 0, 20, 0, False),  # Both cohorts count toward the volume floor.
        (10, 1, 10, 0, 20, 0.05, True),
        (100, 1, 0, 0, 100, 0.01, False),  # Threshold is strictly greater than 1%.
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
