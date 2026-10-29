"""Redis-backed 7-day hourly baseline and alert dedupe for error classes.

Stores counts and sanitized fingerprints only - never raw log content. The
baseline hash expires after ``BASELINE_TTL_SECONDS`` of no refreshes so idle
classes drop out on their own, and buckets older than the 7-day window are
pruned by age on every write, so a long-idle class returns as new. Each
alerted class is its own string key whose 6-hour TTL *is* the dedupe window,
so one class alerting cannot extend another's suppression.
"""

from __future__ import annotations

import json
from typing import Any

from database.redis_connection import create_bounded_redis_client

BASELINE_KEY = 'errclass:baseline'
ALERTED_KEY = 'errclass:alerted'
KEEP_BUCKETS = 168  # 7 days of hourly buckets
BASELINE_TTL_SECONDS = 9 * 24 * 3600
ALERT_TTL_SECONDS = 6 * 3600


def baseline_client():
    return create_bounded_redis_client(0.25)


def record_window(
    client: Any,
    *,
    fingerprint: str,
    label: str,
    level: str,
    window_buckets: dict[int, int],
    now_epoch: int,
) -> dict:
    """Merge one class's window counts into its baseline (max, not sum).

    Overlapping 15-minute reads of the same hour re-observe entries, so a
    bucket keeps the largest count seen rather than accumulating duplicates.
    Buckets older than the 7-day window are dropped by age, so a class that
    goes silent for a week loses its history and returns as new.
    """
    raw = client.hget(BASELINE_KEY, fingerprint)
    record: dict = json.loads(raw) if raw else {'first_seen': now_epoch, 'buckets': {}}
    record['label'] = label
    record['level'] = level
    buckets = {int(k): v for k, v in record.get('buckets', {}).items()}
    age_cutoff = now_epoch // 3600 - KEEP_BUCKETS
    buckets = {bucket: count for bucket, count in buckets.items() if bucket > age_cutoff}
    for bucket, count in window_buckets.items():
        buckets[bucket] = max(int(buckets.get(bucket, 0)), count)
    ordered = sorted(buckets.items())[-KEEP_BUCKETS:]
    record['buckets'] = {str(bucket): count for bucket, count in ordered}
    client.hset(BASELINE_KEY, fingerprint, json.dumps(record, sort_keys=True))
    client.expire(BASELINE_KEY, BASELINE_TTL_SECONDS)
    return record


def _load_record(client: Any, fingerprint: str) -> dict | None:
    raw = client.hget(BASELINE_KEY, fingerprint)
    return json.loads(raw) if raw else None


def baseline_mean(
    client: Any,
    fingerprint: str,
    *,
    before_bucket: int,
    record: dict | None = None,
) -> float | None:
    """Mean hourly count over the span since the class first appeared.

    The divisor is the hour span from the earliest prior bucket to
    ``before_bucket`` (capped at the 7-day window), not the number of buckets
    with observations: a class that logged once and then went silent must trend
    toward zero, not keep the rate of its one active hour.
    """
    data = record if record is not None else _load_record(client, fingerprint)
    if data is None:
        return None
    prior = [(int(k), v) for k, v in data.get('buckets', {}).items() if int(k) < before_bucket]
    if not prior:
        return None
    total = sum(count for _, count in prior)
    span = before_bucket - min(bucket for bucket, _ in prior) + 1
    return total / min(span, KEEP_BUCKETS)


def first_seen_epoch(client: Any, fingerprint: str, record: dict | None = None) -> int | None:
    data = record if record is not None else _load_record(client, fingerprint)
    if data is None:
        return None
    value = data.get('first_seen')
    return int(value) if value is not None else None


def mark_alerted(client: Any, fingerprint: str, *, now_epoch: int) -> None:
    # One key per class: a per-key TTL cannot be extended by another class's
    # alert the way a shared hash expiry would be.
    client.set('%s:%s' % (ALERTED_KEY, fingerprint), str(now_epoch), ex=ALERT_TTL_SECONDS)


def recently_alerted(client: Any, fingerprint: str) -> bool:
    """True while the 6-hour dedupe TTL is still running for this class."""
    return bool(client.exists('%s:%s' % (ALERTED_KEY, fingerprint)))
