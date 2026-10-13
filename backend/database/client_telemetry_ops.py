"""Operational entrypoints for the client telemetry collector.

sol blockers closed here:
- seal_day had no production caller: `seal_settled_day` is the cron-invocable,
  late-arrival-aware wrapper (refuses to seal today or a day with an in-flight
  write; idempotent re-seal refreshes the receipt after late arrivals).
- retention beyond query hiding: `purge_expired_observations` physically deletes
  dedup/observation/attempt documents whose `expires_at` has passed (the 30-day
  restricted-observation / 48-hour dedup budgets are stamped on write).
- actor/channel classification: `channel_roster` supplies the durable roster the
  router hands to `query_is_stale`; unmatched actors are excluded only once the
  roster is populated, otherwise the feed stays honestly partial.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from config.client_telemetry import STALE_AFTER, TelemetryContractError
from database import client_telemetry as store
from database.client_telemetry import (
    ATTEMPTS,
    DAYS,
    DEDUP,
    OBSERVATIONS,
    ROSTER,
    run_telemetry_transaction,
    seal_day,
)


def _telemetry_ref(client: Any, collection: str, document_id: str) -> Any:
    """Module-bound passthrough so tests patching store internals keep working."""
    return store.ref(client, collection, document_id)


def _default_client():
    # Resolve through the module so test doubles that patch
    # store.get_firestore_client are honored (import-time binding would bypass).
    return store.get_firestore_client()


logger = logging.getLogger(__name__)

PURGE_BATCH = 300


def _require_day(day: str) -> None:
    if len(day) != 10 or day[4] != "-" or day[7] != "-":
        raise TelemetryContractError(422, "telemetry_invalid", "day must be YYYY-MM-DD")


def seal_settled_day(
    day: str,
    *,
    firestore_client: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Seal a *settled* day (strictly before today, UTC).

    Late-arrival aware: a day may still receive late observations for up to the
    aggregate-retention window, so sealing is idempotent — re-running refreshes
    the receipt. Refuses today (unsettled) and refuses a day whose last accepted
    write is younger than STALE_AFTER (a batch may be in flight).
    """
    _require_day(day)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise TelemetryContractError(422, "telemetry_invalid", "clock must be timezone-aware")
    today = moment.astimezone(timezone.utc).date()
    try:
        parsed = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError as error:
        raise TelemetryContractError(422, "telemetry_invalid", "day must be YYYY-MM-DD") from error
    if parsed >= today:
        raise TelemetryContractError(422, "telemetry_invalid", "refuse to seal an unsettled day")
    client = firestore_client if firestore_client is not None else _default_client()
    current = _telemetry_read_direct(client, DAYS, day)
    if current is not None:
        last_accepted = current.get("last_accepted_at")
        if isinstance(last_accepted, str):
            text = last_accepted[:-1] + "+00:00" if last_accepted.endswith("Z") else last_accepted
            try:
                accepted_at = datetime.fromisoformat(text)
            except ValueError:
                accepted_at = None
            if accepted_at is not None and moment - accepted_at.astimezone(timezone.utc) < STALE_AFTER:
                raise TelemetryContractError(
                    409, "telemetry_conflict", "day has a recent acceptance; retry after writes settle"
                )
    return seal_day(day, firestore_client=client, now=moment)


def _telemetry_read_direct(client: Any, collection: str, document_id: str) -> dict[str, Any] | None:
    snapshot = _telemetry_ref(client, collection, document_id).get()
    if not getattr(snapshot, "exists", False):
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else None


def enroll_channel(
    owner: str,
    channel: str,
    *,
    firestore_client: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Register an actor's channel in the durable roster."""
    if not owner.strip():
        raise TelemetryContractError(401, "telemetry_unauthorized", "owner is required")
    if channel not in {"production", "beta"}:
        raise TelemetryContractError(422, "telemetry_invalid", "channel must be production or beta")
    moment = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else _default_client()
    # The roster is keyed by the raw owner id: voice aggregate rows carry
    # actor_id = owner, so enrollment and query lookup must use the same key.
    document = {"owner": owner, "channel": channel, "updated_at": moment}

    def callback(transaction: Any) -> dict[str, Any]:
        transaction.set(_telemetry_ref(client, ROSTER, owner), document)
        return document

    return run_telemetry_transaction(client, callback)


def channel_roster(
    owners: set[str],
    *,
    firestore_client: Any = None,
) -> dict[str, str] | None:
    """Read the roster subset for `owners`.

    Returns None when the roster collection is empty (deployment has not been
    seeded): the query then stays honestly `classification_partial` instead of
    pretending unknown actors were classified.
    """
    if not owners:
        return {}
    client = firestore_client if firestore_client is not None else _default_client()
    # Any roster document proves the deployment seeded the roster.
    anchor = _telemetry_read_direct(client, ROSTER, "__anchor__")
    if anchor is None:
        return None
    mapping: dict[str, str] = {}
    for owner in owners:
        document = _telemetry_read_direct(client, ROSTER, owner)
        if isinstance(document, dict) and document.get("channel") in {"production", "beta"}:
            mapping[owner] = document["channel"]
    return mapping


def purge_expired_observations(
    *,
    firestore_client: Any = None,
    now: datetime | None = None,
    batch_limit: int = PURGE_BATCH,
) -> dict[str, int]:
    """Physically delete expired dedup/observation/attempt documents.

    Contract retention is stamped on write (dedup 48h, observations 30d, owner
    joins ride the observation document). This is the durable cleanup pass the
    contract requires beyond query-time hiding. Returns per-collection counts.
    """
    moment = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else _default_client()
    removed: dict[str, int] = {}
    for collection in (DEDUP, OBSERVATIONS, ATTEMPTS):
        cutoff_expired: list[Any] = []
        for snapshot in client.collection(collection).stream():
            data = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
            expires_at = (data or {}).get("expires_at")
            if not isinstance(expires_at, str):
                continue
            text = expires_at[:-1] + "+00:00" if expires_at.endswith("Z") else expires_at
            try:
                expiry = datetime.fromisoformat(text)
            except ValueError:
                continue
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= moment:
                cutoff_expired.append(snapshot)
            if len(cutoff_expired) >= batch_limit:
                break
        deleted = 0
        for snapshot in cutoff_expired:
            reference = getattr(snapshot, "reference", None)
            if reference is not None and getattr(reference, "delete", None) is not None:
                reference.delete()
                deleted += 1
        removed[collection] = deleted
    return removed
