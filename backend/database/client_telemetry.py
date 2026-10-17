"""Durable client telemetry: owner+event dedup and daily aggregates.

Accepted counters live in Firestore day documents updated in the same
transaction as the dedup claim. Process-local Prometheus counters are not
this store. Document access is by id so retention filtering does not depend
on a collection scan.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from typing import Any

from google.cloud import firestore  # type: ignore[import]  # google-cloud-firestore ships no py.typed

from config.client_telemetry import (
    SCHEMA_VERSION,
    TelemetryContractError,
    aggregate_visible,
    day_shard_id,
    iso_z,
    observation_shard_id,
    plan_batch,
    project_query,
    validate_batch,
    window_days,
)
from database._client import get_firestore_client

logger = logging.getLogger(__name__)

RATE = "client_telemetry_rate"
DEDUP = "client_telemetry_dedup"
OBSERVATIONS = "client_telemetry_observations"
ATTEMPTS = "client_telemetry_attempts"
DAYS = "client_telemetry_days"
DAY_SHARDS = "client_telemetry_day_shards"
ROSTER = "client_telemetry_channel_roster"
_MAX_DAY_BYTES = 900_000


class RetryableTransaction(Exception):
    """The memory transaction fixture asks the caller to rerun the callback."""


def doc_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def dedup_document_id(owner: str, event_id: str) -> str:
    return doc_id(owner, event_id)


def recent_owner_ids(*, limit: int = 256) -> set[str]:
    """Owner hashes with recent ingest activity, from the rate-limiter collection.

    Best-effort roster hint source: the rate doc per owner carries the owner's
    hashed id (doc_id(owner)) but not the raw id, so the roster is keyed by the
    same hash. Enrollment stores the document under that hash as well.
    """
    client = get_firestore_client()
    owners: set[str] = set()
    for snapshot in client.collection(RATE).stream():
        owners.add(getattr(snapshot, "id", ""))
        if len(owners) >= limit:
            break
    return owners


def ref(client: Any, collection: str, document_id: str) -> Any:
    return client.collection(collection).document(document_id)


def _read(transaction: Any, client: Any, collection: str, document_id: str) -> dict[str, Any] | None:
    snapshot = ref(client, collection, document_id).get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else None


def _read_direct(client: Any, collection: str, document_id: str) -> dict[str, Any] | None:
    snapshot = ref(client, collection, document_id).get()
    if not getattr(snapshot, "exists", False):
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else None


def run_telemetry_transaction(client: Any, callback: Any) -> Any:
    if getattr(client, "manual_telemetry_transaction", False):
        for _attempt in range(32):
            transaction = client.transaction()
            try:
                result = callback(transaction)
            except Exception:
                transaction.discard()
                raise
            try:
                transaction.commit()
            except RetryableTransaction:
                continue
            return result
        raise TelemetryContractError(503, "telemetry_unavailable", "durable transaction failed")
    if type(client).__name__ == "StrictFirestore":
        return callback(client.transaction())
    return firestore.transactional(callback)(client.transaction())


def accept_batch(
    owner: str,
    payload: Any,
    *,
    firestore_client: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and durably accept one batch for the authenticated owner."""
    if not owner.strip():
        raise TelemetryContractError(401, "telemetry_unauthorized", "authenticated owner is required")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise TelemetryContractError(422, "telemetry_invalid", "clock must be timezone-aware")
    batch_id, observations = validate_batch(payload, moment)
    client = firestore_client if firestore_client is not None else get_firestore_client()

    def callback(transaction: Any) -> dict[str, Any]:
        return _accept(transaction, client, owner, observations, moment)

    try:
        result = run_telemetry_transaction(client, callback)
    except TelemetryContractError:
        raise
    except Exception as exc:
        logger.warning("client telemetry accept failed owner=%s", owner)
        raise TelemetryContractError(503, "telemetry_unavailable", "durable store is unavailable") from exc
    result["batch_id"] = batch_id
    result["schema_version"] = SCHEMA_VERSION
    return result


def _accept(
    transaction: Any,
    client: Any,
    owner: str,
    observations: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    rate = _read(transaction, client, RATE, doc_id(owner))
    dedup = {}
    for observation in observations:
        event_id = observation["event_id"]
        dedup[event_id] = _read(transaction, client, DEDUP, dedup_document_id(owner, event_id))
    dedup = {key: value for key, value in dedup.items() if value is not None}
    attempts: dict[str, dict[str, Any]] = {}
    for observation in observations:
        if observation["family"] != "upload":
            continue
        attempt_id = observation["attributes"]["attempt_id"]
        loaded = _read(transaction, client, ATTEMPTS, doc_id(owner, attempt_id))
        if loaded is not None:
            attempts[attempt_id] = loaded
    day_ids = {observation["day"] for observation in observations}
    for attempt in attempts.values():
        accepted_day = attempt.get("accepted_day")
        if isinstance(accepted_day, str):
            day_ids.add(accepted_day)
    shard_ids: set[str] = set()
    for observation in observations:
        shard_ids.add(observation_shard_id(owner, observation))
    for attempt in attempts.values():
        accepted_day = attempt.get("accepted_day")
        accepted_key = attempt.get("accepted_series_key")
        if isinstance(accepted_day, str) and isinstance(accepted_key, str):
            shard_ids.add(day_shard_id(accepted_day, owner, accepted_key))
    days = {}
    for day in sorted(day_ids):
        if not aggregate_visible(day, now):
            raise TelemetryContractError(422, "telemetry_invalid", "occurred_at is outside aggregate retention")
        loaded_day = _read(transaction, client, DAYS, day)
        if loaded_day is not None:
            days[day] = loaded_day
    shards = {}
    for shard_id in sorted(shard_ids):
        day = shard_id.split("#", 1)[0]
        if not aggregate_visible(day, now):
            continue
        loaded_shard = _read(transaction, client, DAY_SHARDS, shard_id)
        if loaded_shard is not None:
            shards[shard_id] = loaded_shard
    plan = plan_batch(
        owner,
        observations,
        now,
        rate,
        dedup,
        attempts,
        days,
        shards,
    )
    _write_plan(transaction, client, owner, plan, days, shards)
    return plan


def _write_plan(
    transaction: Any,
    client: Any,
    owner: str,
    plan: dict[str, Any],
    previous_days: dict[str, dict[str, Any]],
    previous_shards: dict[str, dict[str, Any]] | None = None,
) -> None:
    if plan.get("status") == 200:
        for day, document in plan["days"].items():
            if previous_days.get(day) == document:
                continue
            if len(repr(document).encode("utf-8")) > _MAX_DAY_BYTES:
                raise TelemetryContractError(503, "telemetry_unavailable", "daily aggregate document is full")
        for shard_id, document in plan.get("shards", {}).items():
            if previous_shards and previous_shards.get(shard_id) == document:
                continue
            if len(repr(document).encode("utf-8")) > _MAX_DAY_BYTES:
                raise TelemetryContractError(
                    503, "telemetry_unavailable", "daily shard document is full; widen DAY_SHARD_COUNT"
                )
    transaction.set(ref(client, RATE, doc_id(owner)), plan["rate"])
    if plan.get("status") != 200:
        return
    for event_id, document in plan["dedup"].items():
        transaction.set(ref(client, DEDUP, dedup_document_id(owner, event_id)), document)
        transaction.set(ref(client, OBSERVATIONS, dedup_document_id(owner, event_id)), plan["observations"][event_id])
    for attempt_id, document in plan["attempts"].items():
        transaction.set(ref(client, ATTEMPTS, doc_id(owner, attempt_id)), document)
    for day, document in plan["days"].items():
        if previous_days.get(day) == document:
            continue
        transaction.set(ref(client, DAYS, day), document)
    for shard_id, document in plan.get("shards", {}).items():
        if previous_shards and previous_shards.get(shard_id) == document:
            continue
        transaction.set(ref(client, DAY_SHARDS, shard_id), document)


def merge_day_shards(day: str, shards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Additively fold shard documents into a day-shaped document.

    A voice observation's shard is chosen per operation id, so the same voice
    key legitimately appears in several shards — every counter, duration and
    voice row must SUM across shards (take-first would silently drop counts
    and break owner-isolation totals).
    """
    merged: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "day": day,
        "series": {},
        "voice": {},
    }
    for shard_id in sorted(shards):
        shard = shards[shard_id]
        if shard.get("day") != day:
            continue
        for key, series in shard.get("series", {}).items():
            target = merged["series"].get(key)
            if target is None:
                merged["series"][key] = deepcopy(series)
                continue
            for counter, amount in series.get("counters", {}).items():
                target["counters"][counter] = target["counters"].get(counter, 0) + amount
            for name, hist in series.get("durations", {}).items():
                existing = target["durations"].get(name)
                if existing is None:
                    target["durations"][name] = deepcopy(hist)
                    continue
                existing["count"] += hist.get("count", 0)
                existing["sum_ms"] += hist.get("sum_ms", 0)
                buckets = hist.get("buckets", [])
                for index, amount in enumerate(buckets):
                    if index < len(existing["buckets"]) and isinstance(existing["buckets"][index], int):
                        existing["buckets"][index] += amount
        for key, row in shard.get("voice", {}).items():
            target = merged["voice"].get(key)
            if target is None:
                merged["voice"][key] = deepcopy(row)
                continue
            target["count"] += row.get("count", 0)
            target["duration_ms"] += row.get("duration_ms", 0)
            target["latency_count"] += row.get("latency_count", 0)
    return merged


def load_day_merged(client: Any, day: str) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Load a day summary plus its shard documents.

    Returns (summary, shards_by_id). A legacy day (no manifest) yields shards
    from the summary itself so old documents keep querying unchanged.
    """
    summary = _read_direct(client, DAYS, day)
    if summary is None:
        return None, {}
    shards: dict[str, dict[str, Any]] = {}
    manifest = summary.get("shards")
    if isinstance(manifest, dict) and manifest:
        for shard_id in manifest:
            loaded = _read_direct(client, DAY_SHARDS, shard_id)
            if loaded is not None:
                shards[shard_id] = loaded
    else:
        shards[day] = summary
    return summary, shards


def merge_day_for_query(summary: dict[str, Any], shards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summary fields + shard series/voice, shaped exactly like a legacy day doc."""
    day = summary["day"]
    merged = dict(summary)
    shard_map = shards.get(day)
    if shard_map is not None:
        # legacy layout: the "shard" IS the day document; nothing to merge
        return merged
    combined = merge_day_shards(day, shards)
    merged["series"] = combined["series"]
    merged["voice"] = combined["voice"]
    return merged


def seal_day(day: str, *, firestore_client: Any = None, now: datetime | None = None) -> dict[str, Any]:
    """Record a rollup health receipt. A recent event alone does not seal a day."""
    moment = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else get_firestore_client()

    def callback(transaction: Any) -> dict[str, Any]:
        current = _read(transaction, client, DAYS, day) or {
            "schema_version": SCHEMA_VERSION,
            "day": day,
            "rollup_sealed": False,
            "sealed_at": None,
            "accepted_observations": 0,
            "accepted_batches": 0,
            "last_accepted_at": None,
            "series": {},
            "voice": {},
        }
        current["rollup_sealed"] = True
        current["sealed_at"] = iso_z(moment)
        transaction.set(ref(client, DAYS, day), current)
        return current

    return run_telemetry_transaction(client, callback)


def query_aggregates(
    *,
    days: int,
    channel: str,
    firestore_client: Any = None,
    now: datetime | None = None,
    channel_by_actor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Read durable daily aggregates. Store errors become telemetry_unavailable."""
    moment = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        selected = window_days(moment, days)
        loaded: dict[str, dict[str, Any] | None] = {}
        for day in selected:
            if not aggregate_visible(day, moment):
                loaded[day] = None
                continue
            summary, shards = load_day_merged(client, day)
            if summary is None:
                loaded[day] = None
                continue
            loaded[day] = merge_day_for_query(summary, shards)
        projected = project_query(loaded, moment, days, channel, channel_by_actor)
    except TelemetryContractError:
        raise
    except Exception as exc:
        logger.warning("client telemetry query failed")
        raise TelemetryContractError(503, "telemetry_unavailable", "aggregate store is unavailable") from exc
    projected.pop("stale", None)
    return projected


def query_is_stale(
    *,
    days: int,
    channel: str,
    firestore_client: Any = None,
    now: datetime | None = None,
    channel_by_actor: dict[str, str] | None = None,
) -> tuple[dict[str, Any], bool]:
    moment = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        selected = window_days(moment, days)
        loaded: dict[str, dict[str, Any] | None] = {}
        for day in selected:
            summary, shards = load_day_merged(client, day)
            if summary is None or not aggregate_visible(day, moment):
                loaded[day] = None
                continue
            loaded[day] = merge_day_for_query(summary, shards)
        projected = project_query(loaded, moment, days, channel, channel_by_actor)
    except TelemetryContractError:
        raise
    except Exception as exc:
        logger.warning("client telemetry query failed")
        raise TelemetryContractError(503, "telemetry_unavailable", "aggregate store is unavailable") from exc
    stale = bool(projected.pop("stale", False))
    return projected, stale


def purge_expired_aggregates(*, firestore_client: Any = None, now: datetime | None = None) -> list[str]:
    """Delete day documents older than the 90-day aggregate retention.

    Query filtering already hides them. Dedup rows expire logically after 48
    hours even if the document is still physically present.
    """
    moment = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    removed: list[str] = []
    today = moment.astimezone(timezone.utc).date()
    for age in range(91, 200):
        day = (today - timedelta(days=age)).isoformat()
        for collection in (DAYS, DAY_SHARDS):
            for prefix in (day, f"{day}#"):
                if collection == DAY_SHARDS and not prefix.endswith("#"):
                    continue
                document_ref = ref(client, collection, prefix)
                snapshot = document_ref.get()
                if not getattr(snapshot, "exists", False):
                    continue
                delete = getattr(document_ref, "delete", None)
                if delete is None:
                    raise TelemetryContractError(503, "telemetry_unavailable", "store cannot delete expired aggregates")
                delete()
                if collection == DAYS:
                    removed.append(day)
    return removed


def observation_visible(document: dict[str, Any], now: datetime) -> bool:
    expires_at = document.get("expires_at")
    if not isinstance(expires_at, str):
        return False
    text = expires_at[:-1] + "+00:00" if expires_at.endswith("Z") else expires_at
    try:
        expiry = datetime.fromisoformat(text)
    except ValueError:
        return False
    if expiry.tzinfo is None:
        return False
    return expiry.astimezone(timezone.utc) > now
