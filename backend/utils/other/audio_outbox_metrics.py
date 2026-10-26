"""Low-cardinality audio custody signals shared by listen and pusher."""

import time

from prometheus_client import Counter, Gauge

CUSTODY_COMMITS = Counter('omi_audio_custody_commits_total', 'Immutable media and manifest receipts committed')
CUSTODY_FAILURES = Counter(
    'omi_audio_custody_failures_total', 'Audio custody failures; producer remains unacknowledged', ['stage', 'reason']
)
WOULD_DROP = Counter('omi_audio_custody_would_drop_total', 'Prevented pre-durability audio drops', ['stage'])
BACKPRESSURE = Counter('omi_audio_custody_backpressure_total', 'Producer waits for custody capacity', ['stage'])
LAST_RISK = Gauge(
    'omi_audio_custody_last_risk_timestamp_seconds', 'Latest custody refusal/failure, including before first scrape'
)

# Failure class vocabulary: 'conflict' is a deterministic projection mismatch
# (content collision at the millisecond-keyed chunk name, or a custody read-back
# verify failure) where retrying replays the same collision; 'transient' is any
# other failure after its bounded retry budget; 'other' is the unlabeled
# default for existing call sites.
CUSTODY_FAILURE_REASONS = frozenset({'other', 'conflict', 'transient'})


def bounded_custody_failure_reason(reason: str) -> str:
    return reason if reason in CUSTODY_FAILURE_REASONS else 'other'


def record_would_drop(stage: str) -> None:
    WOULD_DROP.labels(stage=stage).inc()
    LAST_RISK.set(time.time())


def record_failure(stage: str, reason: str = 'other') -> None:
    CUSTODY_FAILURES.labels(stage=stage, reason=bounded_custody_failure_reason(reason)).inc()
    LAST_RISK.set(time.time())


# A first refusal must have a scraped zero baseline; dynamically creating a
# child at 1 would hide the first event from increase(...[5m]). Labels are a
# bounded contract, never account/session identifiers.
for _stage in ('commit', 'raw_commit', 'projection', 'window_tail'):
    CUSTODY_FAILURES.labels(stage=_stage, reason='other').inc(0)
    CUSTODY_FAILURES.labels(stage=_stage, reason='conflict').inc(0)
    CUSTODY_FAILURES.labels(stage=_stage, reason='transient').inc(0)
for _stage in (
    'pusher_queue',
    'pusher_budget',
    'pusher_pending',
    'pending_refs',
    'listen_budget',
    'raw_pack',
    'raw_capacity',
    'raw_timeout',
    'window_tail',
):
    WOULD_DROP.labels(stage=_stage).inc(0)
    BACKPRESSURE.labels(stage=_stage).inc(0)
