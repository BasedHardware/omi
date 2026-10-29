"""Redis-backed 7-day hourly baseline and alert dedupe for error classes.

Stores counts and sanitized fingerprints only - never raw log content. The
baseline hash expires after ``BASELINE_TTL_SECONDS`` of no refreshes so idle
classes drop out on their own; the alerted hash entries carry a 6-hour TTL that
*is* the per-class dedupe window, so an unrefreshed entry cannot suppress a
later alert.
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
    """
    raw = client.hget(BASELINE_KEY, fingerprint)
    record: dict[str, Any] = json.loads(raw) if raw else {'first_seen': now_epoch, 'buckets': {}}
    record['label'] = label
    record['level'] = level
    buckets = {int(k): v for k, v in record.get('buckets', {}).items()}
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
    """Mean hourly count over buckets strictly before ``before_bucket``.

    The caller passes the current window's start bucket so the window being
    evaluated cannot dilute its own baseline.
    """
    data = record if record is not None else _load_record(client, fingerprint)
    if data is None:
        return None
    prior = [
        count for bucket, count in ((int(k), v) for k, v in data.get('buckets', {}).items()) if bucket < before_bucket
    ]
    if not prior:
        return None
    return sum(prior) / len(prior)


def first_seen_epoch(client: Any, fingerprint: str, record: dict | None = None) -> int | None:
    data = record if record is not None else _load_record(client, fingerprint)
    if data is None:
        return None
    value = data.get('first_seen')
    return int(value) if value is not None else None


def mark_alerted(client: Any, fingerprint: str, *, now_epoch: int) -> None:
    client.hset(ALERTED_KEY, fingerprint, str(now_epoch))
    client.expire(ALERTED_KEY, ALERT_TTL_SECONDS)


def recently_alerted(client: Any, fingerprint: str) -> bool:
    """True while the 6-hour dedupe TTL is still running for this class."""
    return client.hexists(ALERTED_KEY, fingerprint)
