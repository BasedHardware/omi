"""Held-content ramp signals. Labels are closed sets and never identify a person.

Counters are armed at import so a quiet process still exports zero. Fleet gauges
stay absent until the redrive scheduler publishes one snapshot. Read each gauge
from the replica whose snapshot timestamp is newest. Do not sum() them, and do
not max() the gauge itself: a previous replica can still export an older value.

When pending holds exist and none has a positive listed_at, oldest age is the
sentinel -1 and omi_held_content_undated_pending_count carries the count. Age 0
is an empty population, or a dated hold listed at the snapshot clock.
"""

import logging
import time

from prometheus_client import Counter, Gauge, Histogram

from utils.observability.reasons import ReasonFamily, StagingRetryOutcome, TransitionTailOutcome, reason_label

logger = logging.getLogger(__name__)

CAPTURE_KINDS = ('lost', 'byte_mismatch', 'frame_mismatch', 'ack_without_authority')
CHOICE_OUTCOMES = ('ok', 'stale_period_409', 'no_capability', 'intent_only')
RECOVERY_RESULTS = ('attempt', 'completed')
ERASURE_OUTCOMES = ('failure', 'post_delete_publication')
PUBLICATION_RETRY_OUTCOMES = ('retried_ok', 'exhausted', 'staged_unverified', 'source_orphaned')
PUBLICATION_RETRY_CAUSES = ('throttle', 'timeout', 'connection', 'other')
STAGING_RETRY_OUTCOMES = (
    StagingRetryOutcome.RETRIED_OK,
    StagingRetryOutcome.DEFERRED,
    StagingRetryOutcome.EXHAUSTED,
    StagingRetryOutcome.PERMANENT,
    StagingRetryOutcome.RETAINED,
)
STAGING_RETRY = Counter(
    'omi_held_content_staging_retry',
    'Held upload outcomes: deferred has a durable journal; retained still owns volatile PCM after both stores failed',
    ['outcome'],
)
DEFERRED_SECONDS = Counter('omi_held_content_deferred_seconds', 'Held seconds handed to encrypted staging journals')
PCM_CUSTODY_SECONDS = Gauge('omi_held_content_pcm_custody_seconds', 'Process-local pending held PCM seconds')
for _outcome in STAGING_RETRY_OUTCOMES:
    STAGING_RETRY.labels(outcome=reason_label(ReasonFamily.HELD_CONTENT, _outcome, StagingRetryOutcome))
CHOICE_METHODS = ('get', 'put')
TRANSITION_TAIL_OUTCOMES = (TransitionTailOutcome.COALESCED, TransitionTailOutcome.SEALED)
TRANSITION_TAIL = Counter(
    'omi_held_content_transition_tail',
    'Deferred tiny PCM tails joined by compatible capture or sealed without a neighbour',
    ['outcome'],
)

CAPTURE = Counter(
    'omi_held_content_capture',
    'Held capture exceptions: lost audio, byte or frame mismatch, or an acknowledgement without durable authority',
    ['kind'],
)
CHOICE = Counter('omi_held_content_choice', 'Budget-choice route outcomes', ['outcome'])
CHOICE_5XX = Counter('omi_held_content_choice_5xx', 'Budget-choice route server errors')
CHOICE_LATENCY = Histogram(
    'omi_held_content_choice_latency_seconds',
    'Budget-choice route latency so p95 can be computed',
    ['method'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
# Pending holds exist, but none has a positive listed_at. Not an age.
UNDATED_OLDEST_AGE_SENTINEL = -1.0
OLDEST_AGE = Gauge(
    'omi_held_content_oldest_age_seconds',
    'Age of the oldest dated pending hold in the redrive fleet snapshot. '
    'Publishes -1 when pending holds exist and none has a positive listed_at; never 0 in that case. '
    'Age 0 is an empty population or a hold listed at the snapshot clock. Read the replica '
    'whose omi_held_content_fleet_snapshot_timestamp_seconds is newest; do not sum() or max() this gauge',
)
PENDING_COUNT = Gauge(
    'omi_held_content_pending_count',
    'Pending held items in the redrive fleet snapshot. Read the replica whose '
    'omi_held_content_fleet_snapshot_timestamp_seconds is newest; do not sum() or max() this gauge',
)
PENDING_SECONDS = Gauge(
    'omi_held_content_pending_seconds',
    'Pending held seconds in the redrive fleet snapshot. Read the replica whose '
    'omi_held_content_fleet_snapshot_timestamp_seconds is newest; do not sum() or max() this gauge',
)
UNDATED_PENDING = Gauge(
    'omi_held_content_undated_pending_count',
    'Pending holds with no positive listed_at in the redrive fleet snapshot. '
    'Zero when every pending hold is dated, or when the population is empty. Read the replica whose '
    'omi_held_content_fleet_snapshot_timestamp_seconds is newest; do not sum() or max() this gauge',
)
RECOVERY = Counter('omi_held_content_recovery', 'Held recovery attempts and completions', ['result'])
PACING_OUTCOMES = ('granted', 'deferred', 'refused')
PACING = Counter('omi_held_recovery_pacing_intents', 'Recovery intent budget decisions', ['outcome'])
PACING_AUDIO = Counter('omi_held_recovery_pacing_audio_seconds', 'Audio tokens requested by decision', ['outcome'])
PACING_AGE = Histogram(
    'omi_held_recovery_pacing_deferred_age_seconds',
    'Age since first durable pacing deferral, sampled when a held item is deferred again; not a fleet maximum',
    buckets=(0, 60, 300, 1800, 3600, 21600, 86400, 604800, 2592000),
)
BACKLOG = Gauge(
    'omi_held_content_backlog_items',
    'Processing-backlog items in the redrive fleet snapshot. Read the replica whose '
    'omi_held_content_fleet_snapshot_timestamp_seconds is newest; do not sum() or max() this gauge',
)
FLEET_SNAPSHOT_TIMESTAMP = Gauge(
    'omi_held_content_fleet_snapshot_timestamp_seconds',
    'Unix time of the latest held-content fleet snapshot on this process. '
    'Select sibling gauges from the replica where this equals the max',
)
ERASURE = Counter('omi_held_content_erasure', 'Held erasure failures and post-delete publication', ['outcome'])
PUBLICATION_RETRY = Counter(
    'omi_held_content_publication_retry',
    'Live cap publication attempts that retried a transient failure, as a Firestore '
    'transaction restart or an immutable GCS upload retry. '
    'retried_ok completed a later upload or fresh transaction; '
    'exhausted spent the bounded budget; '
    'staged_unverified means the staging write landed and a later read failed; '
    'source_orphaned means the flush failed closed after uploading a fragment no row names. '
    'cause separates Firestore throttling (throttle) from transport timeouts (timeout) '
    'and dropped connections (connection). Labels are a closed set and never identify a person',
    ['outcome', 'cause'],
)
COHORT_SOURCE = Gauge('omi_held_content_cohort_source', 'Active held-content cohort source', ['source'])
COHORT_PERCENT = Gauge('omi_held_content_cohort_percent', 'Active held-content cohort percent; 0 denies by percent')
COHORT_REFRESH_FAILURES = Counter(
    'omi_held_content_cohort_refresh_failures',
    'Held-content cohort refresh failures',
    ['reason'],
)

for _outcome in TRANSITION_TAIL_OUTCOMES:
    TRANSITION_TAIL.labels(outcome=reason_label(ReasonFamily.HELD_CONTENT, _outcome, TransitionTailOutcome))
for _kind in CAPTURE_KINDS:
    CAPTURE.labels(kind=_kind)
for _outcome in CHOICE_OUTCOMES:
    CHOICE.labels(outcome=_outcome)
for _method in CHOICE_METHODS:
    CHOICE_LATENCY.labels(method=_method)
for _result in RECOVERY_RESULTS:
    RECOVERY.labels(result=_result)
for _outcome in PACING_OUTCOMES:
    PACING.labels(outcome=_outcome)
    PACING_AUDIO.labels(outcome=_outcome)
for _outcome in ERASURE_OUTCOMES:
    ERASURE.labels(outcome=_outcome)
for _outcome in PUBLICATION_RETRY_OUTCOMES:
    for _cause in PUBLICATION_RETRY_CAUSES:
        PUBLICATION_RETRY.labels(outcome=_outcome, cause=_cause)
for _source in ('doc', 'env', 'none'):
    COHORT_SOURCE.labels(source=_source)
for _reason in ('read', 'schedule'):
    COHORT_REFRESH_FAILURES.labels(reason=_reason)


def _inc(counter, **labels) -> None:
    try:
        counter.labels(**labels).inc() if labels else counter.inc()
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')


def record_transition_tail(outcome: str) -> None:
    if outcome in TRANSITION_TAIL_OUTCOMES:
        _inc(TRANSITION_TAIL, outcome=reason_label(ReasonFamily.HELD_CONTENT, outcome, TransitionTailOutcome))


def record_capture(kind: str) -> None:
    if kind in CAPTURE_KINDS:
        _inc(CAPTURE, kind=kind)


def record_choice(outcome: str) -> None:
    if outcome in CHOICE_OUTCOMES:
        _inc(CHOICE, outcome=outcome)


def record_choice_server_error() -> None:
    _inc(CHOICE_5XX)


def finish_choice(method: str, started: float, outcome: str | None) -> None:
    try:
        if method in CHOICE_METHODS:
            CHOICE_LATENCY.labels(method=method).observe(max(0.0, time.perf_counter() - started))
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')
    if outcome:
        record_choice(outcome)


def record_recovery(result: str) -> None:
    if result in RECOVERY_RESULTS:
        _inc(RECOVERY, result=result)


def record_pacing(outcome: str, seconds: float, deferred_age: float = 0) -> None:
    if outcome not in PACING_OUTCOMES:
        return
    try:
        PACING.labels(outcome=outcome).inc()
        PACING_AUDIO.labels(outcome=outcome).inc(seconds)
        if outcome != 'granted':
            PACING_AGE.observe(max(0, deferred_age))
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')


def record_erasure(outcome: str) -> None:
    if outcome in ERASURE_OUTCOMES:
        _inc(ERASURE, outcome=outcome)


def record_publication_retry(outcome: str, cause: str = 'other') -> None:
    if outcome in PUBLICATION_RETRY_OUTCOMES and cause in PUBLICATION_RETRY_CAUSES:
        _inc(PUBLICATION_RETRY, outcome=outcome, cause=cause)


def record_staging_retry(outcome: str) -> None:
    if outcome in STAGING_RETRY_OUTCOMES:
        _inc(STAGING_RETRY, outcome=reason_label(ReasonFamily.HELD_CONTENT, outcome, StagingRetryOutcome))


def record_deferred_seconds(seconds: float) -> None:
    try:
        DEFERRED_SECONDS.inc(seconds)
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')


def _gauge_number(value, *, whole: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return 0
    return int(value) if whole else float(value)


def publish_fleet(snapshot: dict, *, now: float | None = None) -> None:
    """Publish one scheduler snapshot.

    An empty population clears every fleet gauge, including undated pending, to 0.
    When pending holds remain and none has a positive ``listed_at``, oldest age
    is ``UNDATED_OLDEST_AGE_SENTINEL`` (-1), never 0. A dated hold listed at or
    after ``now`` is a real age of 0.
    """
    moment = time.time() if now is None else now
    body = snapshot or {}
    pending_count = _gauge_number(body.get('pending_count'), whole=True)
    pending_seconds = _gauge_number(body.get('pending_seconds'), whole=False)
    backlog = _gauge_number(body.get('backlog_items'), whole=True)
    undated = _gauge_number(body.get('undated_pending'), whole=True)
    listed = body.get('oldest_listed_at')
    if isinstance(listed, bool) or not isinstance(listed, (int, float)) or listed <= 0:
        age = UNDATED_OLDEST_AGE_SENTINEL if pending_count > 0 else 0.0
    else:
        age = max(0.0, moment - float(listed)) if pending_count > 0 else 0.0
    try:
        OLDEST_AGE.set(age)
        PENDING_COUNT.set(pending_count)
        PENDING_SECONDS.set(pending_seconds)
        UNDATED_PENDING.set(undated)
        BACKLOG.set(backlog)
        FLEET_SNAPSHOT_TIMESTAMP.set(moment)
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')
