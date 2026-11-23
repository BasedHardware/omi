"""Durable distinct-owner counts keyed by UTC event hour.

Membership and aggregate writes share the client-telemetry dedup transaction.
Owner hashes are used only to find membership documents and never exported.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from config.client_telemetry import DEVICE_SIGNAL_EVENTS, DEVICE_SIGNAL_FILTERS

HOUR_SHARDS = "client_telemetry_signal_hour_shards"
MEMBERSHIPS = "client_telemetry_signal_memberships"
SHARD_COUNT = 16
SIGNALS = sorted((DEVICE_SIGNAL_EVENTS - {"heartbeat"}) | DEVICE_SIGNAL_FILTERS)
HOUR = timedelta(hours=1)
BASELINE_HOURS = 167
DELIVERY_GRACE = timedelta(minutes=10)


def _bucket_start(at: datetime) -> datetime:
    return at.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _signals(attributes: dict[str, Any]) -> set[str]:
    event = attributes["event"]
    result = {event}
    if event == "local_wal_stuck":
        if attributes.get("over_age"):
            result.add("wal_backlog_age_24h")
        if attributes.get("over_count"):
            result.add("wal_backlog_over_cap")
    if event == "capture_wedge_detected":
        reason = {
            "count_cap": "wedge_count_cap",
            "disk_reserve": "wedge_disk_reserve",
            "missing": "wedge_other",
        }.get(attributes["block_reason"])
        if reason:
            result.add(reason)
    return result


def plan_hour_writes(
    transaction: Any,
    client: Any,
    owner_hash: str,
    observations: dict[str, dict[str, Any]],
) -> list[tuple[Any, dict[str, Any]]]:
    by_hour: dict[datetime, set[str]] = defaultdict(set)
    for observation in observations.values():
        family = observation["family"]
        if family not in {"device_signal", "fallback"}:
            continue
        hour = _bucket_start(datetime.fromisoformat(observation["occurred_at"]))
        signals = _signals(observation["attributes"]) if family == "device_signal" else {"fallback_triggered"}
        by_hour[hour].update(signals)

    writes: list[tuple[Any, dict[str, Any]]] = []
    buckets: dict[str, dict[str, Any]] = {}
    shard = int(owner_hash[:8], 16) % SHARD_COUNT
    for hour, signals in sorted(by_hour.items()):
        hour_id = str(int(hour.timestamp()))
        member = client.collection(MEMBERSHIPS).document(f"{owner_hash}-{hour_id}")
        existing: dict[str, Any] = member.get(transaction=transaction).to_dict() or {}
        seen: set[str] = set(existing.get("signals", ()))
        added = signals - seen
        if not added:
            continue
        day = hour.date().isoformat()
        # A batch can touch several hours of one UTC day. Reuse the planned
        # document instead of rereading and overwriting earlier increments.
        if day not in buckets:
            bucket = client.collection(HOUR_SHARDS).document(f"{day}-{shard}")
            buckets[day] = bucket.get(transaction=transaction).to_dict() or {
                "day": day,
                "expires_at": hour.replace(hour=0) + timedelta(days=9),
                "hours": {},
            }
            writes.append((bucket, buckets[day]))
        counts = buckets[day]["hours"].setdefault(hour_id, {})
        for signal in added:
            counts[signal] = counts.get(signal, 0) + 1
        writes.append((member, {"signals": sorted(seen | added), "expires_at": hour + timedelta(hours=26)}))
    return writes


def load_hour_snapshot(client: Any, now: datetime) -> tuple[datetime, int, int, dict[str, tuple[int, float]]]:
    current = _bucket_start(now - DELIVERY_GRACE) - HOUR
    first = current - BASELINE_HOURS * HOUR
    days = {str((first + offset * HOUR).date()) for offset in range(BASELINE_HOURS + 1)}
    refs = [
        client.collection(HOUR_SHARDS).document(f"{day}-{shard}")
        for day in sorted(days)
        for shard in range(SHARD_COUNT)
    ]
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for snapshot in client.get_all(refs, retry=None, timeout=5):
        if snapshot.exists:
            for hour_id, values in snapshot.to_dict()["hours"].items():
                counts[hour_id].update(values)

    latest = counts[str(int(current.timestamp()))]
    baseline = [counts[str(int((current - offset * HOUR).timestamp()))] for offset in range(1, BASELINE_HOURS + 1)]
    covered = [bucket for bucket in baseline if bucket["heartbeat"]]
    # HogQL groups hours containing the matching event. Keep that median
    # convention while tracking how many historical hours had intake coverage.
    values: dict[str, tuple[int, float]] = {}
    for signal in SIGNALS:
        positive = [bucket[signal] for bucket in covered if bucket[signal]]
        values[signal] = (latest[signal], median(positive) if positive else 0.0)
    return current, latest["heartbeat"], len(covered), values
