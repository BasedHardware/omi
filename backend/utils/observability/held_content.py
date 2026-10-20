"""Held-content ramp signals. Labels are closed sets and never identify a person.

Counters are armed at import so a quiet process still exports zero. Gauges stay
absent until a bounded sample is published; aggregate those with max().
"""

import logging
import time

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

CAPTURE_KINDS = ('lost', 'byte_mismatch', 'frame_mismatch', 'ack_without_authority')
CHOICE_OUTCOMES = ('ok', 'stale_period_409', 'no_capability', 'intent_only')
RECOVERY_RESULTS = ('attempt', 'completed')
ERASURE_OUTCOMES = ('failure', 'post_delete_publication')
CHOICE_METHODS = ('get', 'put')

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
OLDEST_AGE = Gauge(
    'omi_held_content_oldest_age_seconds',
    'Oldest age in the latest bounded held sample; aggregate with max()',
)
PENDING_COUNT = Gauge(
    'omi_held_content_pending_count',
    'Pending held items in the latest bounded sample; aggregate with max()',
)
PENDING_SECONDS = Gauge(
    'omi_held_content_pending_seconds',
    'Pending held seconds in the latest bounded sample; aggregate with max()',
)
RECOVERY = Counter('omi_held_content_recovery', 'Held recovery attempts and completions', ['result'])
BACKLOG = Gauge(
    'omi_held_content_backlog_items',
    'Backlog items on the latest bounded choice page; aggregate with max()',
)
ERASURE = Counter('omi_held_content_erasure', 'Held erasure failures and post-delete publication', ['outcome'])
COHORT_SOURCE = Gauge('omi_held_content_cohort_source', 'Active held-content cohort source', ['source'])
COHORT_PERCENT = Gauge('omi_held_content_cohort_percent', 'Active held-content cohort percent; 0 denies by percent')
COHORT_REFRESH_FAILURES = Counter(
    'omi_held_content_cohort_refresh_failures',
    'Held-content cohort refresh failures',
    ['reason'],
)

for _kind in CAPTURE_KINDS:
    CAPTURE.labels(kind=_kind)
for _outcome in CHOICE_OUTCOMES:
    CHOICE.labels(outcome=_outcome)
for _method in CHOICE_METHODS:
    CHOICE_LATENCY.labels(method=_method)
for _result in RECOVERY_RESULTS:
    RECOVERY.labels(result=_result)
for _outcome in ERASURE_OUTCOMES:
    ERASURE.labels(outcome=_outcome)
for _source in ('doc', 'env', 'none'):
    COHORT_SOURCE.labels(source=_source)
for _reason in ('read', 'schedule'):
    COHORT_REFRESH_FAILURES.labels(reason=_reason)


def _inc(counter, **labels) -> None:
    try:
        counter.labels(**labels).inc() if labels else counter.inc()
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')


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


def record_erasure(outcome: str) -> None:
    if outcome in ERASURE_OUTCOMES:
        _inc(ERASURE, outcome=outcome)


def _age(row: dict, now: float) -> float | None:
    listed = row.get('listed_at', row.get('started_at', row.get('created_at')))
    if isinstance(listed, bool) or not isinstance(listed, (int, float)) or listed <= 0:
        return None
    return max(0.0, now - float(listed))


def publish_held_sample(rows: list, *, now: float | None = None) -> None:
    """Publish one already-loaded page. An empty page leaves the previous sample."""
    pending = []
    for row in rows:
        data = row if isinstance(row, dict) else {}
        if data.get('state') in {'held', 'staging', 'sealing', 'retained'}:
            pending.append(data)
    if not pending:
        return
    moment = time.time() if now is None else now
    ages = [age for row in pending if (age := _age(row, moment)) is not None]
    try:
        OLDEST_AGE.set(max(ages) if ages else 0.0)
        PENDING_COUNT.set(len(pending))
        PENDING_SECONDS.set(sum(max(0.0, float(row.get('seconds') or 0)) for row in pending))
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')


def publish_backlog(rows: list) -> None:
    """Sum count fields on an already-loaded choice page. Empty leaves the previous sample."""
    summaries = [row for row in rows if isinstance(row, dict)]
    if not summaries:
        return
    try:
        BACKLOG.set(sum(max(0, int(row.get('count') or 0)) for row in summaries))
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')
