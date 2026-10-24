"""Low-cardinality audio custody signals shared by listen and pusher."""

import time

from prometheus_client import Counter, Gauge

CUSTODY_COMMITS = Counter('omi_audio_custody_commits_total', 'Immutable media and manifest receipts committed')
CUSTODY_FAILURES = Counter(
    'omi_audio_custody_failures_total', 'Audio custody failures; producer remains unacknowledged', ['stage']
)
WOULD_DROP = Counter('omi_audio_custody_would_drop_total', 'Prevented pre-durability audio drops', ['stage'])
BACKPRESSURE = Counter('omi_audio_custody_backpressure_total', 'Producer waits for custody capacity', ['stage'])
LAST_RISK = Gauge(
    'omi_audio_custody_last_risk_timestamp_seconds', 'Latest custody refusal/failure, including before first scrape'
)


def record_would_drop(stage: str) -> None:
    WOULD_DROP.labels(stage=stage).inc()
    LAST_RISK.set(time.time())


def record_failure(stage: str) -> None:
    CUSTODY_FAILURES.labels(stage=stage).inc()
    LAST_RISK.set(time.time())


# A first refusal must have a scraped zero baseline; dynamically creating a
# child at 1 would hide the first event from increase(...[5m]). Labels are a
# bounded contract, never account/session identifiers.
for _stage in ('commit', 'raw_commit', 'projection'):
    CUSTODY_FAILURES.labels(stage=_stage).inc(0)
for _stage in (
    'pusher_queue',
    'pusher_budget',
    'pusher_pending',
    'pending_refs',
    'listen_budget',
    'raw_pack',
    'raw_capacity',
    'raw_timeout',
):
    WOULD_DROP.labels(stage=_stage).inc(0)
    BACKPRESSURE.labels(stage=_stage).inc(0)
