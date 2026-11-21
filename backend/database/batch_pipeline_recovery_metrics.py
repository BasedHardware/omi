"""Required recovery collectors shared by database hooks and caller utilities.

No caller utility, store, optional driver or client construction belongs here.
Collectors are created once in the default registry and can also be exported
through a worker-owned private registry.
"""

from prometheus_client import Counter, Gauge, Histogram

RECOVERY_DISCOVERY_TOTAL = Counter(
    'omi_jobstore_recovery_discovery_total',
    'Caller entries, attempts and candidate work; not billed reads.',
    ['namespace', 'caller', 'event', 'source', 'reason'],
)
PRIMARY_SCAN_SUCCESS_TIMESTAMP = Gauge(
    'omi_jobstore_index_primary_scan_success_timestamp_seconds',
    'Unix completion time of the last successful bounded primary due query; not backlog coverage.',
    ['namespace', 'query'],
)
CALLER_GAP_SECONDS = Histogram(
    'omi_jobstore_recovery_caller_gap_seconds',
    'Monotonic gap between actual per-process caller entries.',
    ['namespace', 'caller'],
    buckets=(1, 5, 15, 30, 60, 120, 300, 900),
)
CUTOFF_AGE_SECONDS = Histogram(
    'omi_jobstore_recovery_cutoff_age_seconds',
    'Wall-time age of the recovery cutoff at leased discovery after migration.',
    ['namespace', 'caller'],
    buckets=(0.01, 0.2, 1, 5, 15, 60, 120, 300, 900),
)
PRIMARY_QUERY_SECONDS = Histogram(
    'omi_jobstore_recovery_primary_query_seconds',
    'Actual primary discovery duration including failures.',
    ['namespace', 'caller'],
    buckets=(0.01, 0.05, 0.2, 1, 5, 15, 60),
)
RECOVERY_COLLECTORS = (
    RECOVERY_DISCOVERY_TOTAL,
    PRIMARY_SCAN_SUCCESS_TIMESTAMP,
    CALLER_GAP_SECONDS,
    CUTOFF_AGE_SECONDS,
    PRIMARY_QUERY_SECONDS,
)
