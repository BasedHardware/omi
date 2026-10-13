"""Bounded counters of drift findings, counted once per comparison run."""

from prometheus_client import Counter

from utils.billing_reconciliation import DRIFT_CATEGORIES, DriftReport

DRIFT = Counter(
    'omi_billing_reconciliation_drift_total',
    'Subscription drift observations (repeated runs can observe the same row).',
    ['category'],
)
RUNS = Counter('omi_billing_reconciliation_runs_total', 'Completed billing comparison runs.')
for category in DRIFT_CATEGORIES:
    DRIFT.labels(category=category)


def record_report(report: DriftReport) -> None:
    RUNS.inc()
    for category in DRIFT_CATEGORIES:
        DRIFT.labels(category=category).inc(report.counts.get(category, 0))
