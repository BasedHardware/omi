"""Atomic, content-free cross-device budget reservations for JIT proactivity."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database._client import data_plane_db as default_db_client
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.memory_apply_store import transactional
from database.memory_collections import MemoryCollections
from database.read_boundary import parse_payload_strict, parse_snapshot_strict
from models.jit_proactivity import (
    JIT_AMBIGUOUS_NANO_TRIAGES_PER_DAY,
    JIT_FULL_TURNS_PER_CANDIDATE,
    JIT_PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY,
    JIT_TOTAL_FULL_TURNS_PER_DAY,
    JIT_TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY,
    JITProactivityEventReceipt,
    JITProactivityOperation,
)
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItem
from utils.memory.jit_trigger_snapshot import is_authoritative_trigger_for_paid_work


class JITProactivityReservationError(RuntimeError):
    pass


def _budget_day_for_timezone(at: datetime, timezone_name: str) -> str:
    if at.tzinfo is None or at.utcoffset() is None:
        raise JITProactivityReservationError("JIT reservation time is timezone-naive")
    normalized = timezone_name.strip()
    if not normalized:
        raise JITProactivityReservationError("JIT user timezone is unavailable")
    try:
        user_timezone = ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise JITProactivityReservationError("JIT user timezone is invalid") from exc
    return at.astimezone(user_timezone).date().isoformat()


def _next_local_midnight(at: datetime, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    local = at.astimezone(zone)
    next_date = local.date() + timedelta(days=1)
    return datetime.combine(next_date, time.min, tzinfo=zone).astimezone(timezone.utc)


def _timezone_from_user_snapshot(snapshot: Any) -> str:
    payload = _snapshot_payload(snapshot)
    timezone_name = payload.get("time_zone")
    if not isinstance(timezone_name, str):
        raise JITProactivityReservationError("JIT user timezone is unavailable")
    normalized = timezone_name.strip()
    _budget_day_for_timezone(datetime.now(timezone.utc), normalized)
    return normalized


def _snapshot_payload(snapshot: Any) -> dict[str, Any]:
    payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
    if not isinstance(payload, dict):
        raise JITProactivityReservationError("required JIT authority document is unavailable")
    return payload


@transactional
def _reserve_transaction(
    transaction: Any,
    db_client: Any,
    proposed: JITProactivityEventReceipt,
) -> tuple[JITProactivityEventReceipt, bool]:
    uid = proposed.uid
    collections = MemoryCollections(uid=uid)
    user_snapshot = db_client.document(f"users/{uid}").get(transaction=transaction)
    authoritative_timezone = _timezone_from_user_snapshot(user_snapshot)
    if authoritative_timezone != proposed.budget_timezone:
        raise JITProactivityReservationError("JIT user timezone authority changed")
    deletion_ref = db_client.document(f"account_deletions/{uid}")
    deletion_snapshot = deletion_ref.get(transaction=transaction)
    deletion_payload = deletion_snapshot.to_dict() if getattr(deletion_snapshot, "exists", False) else {}
    deletion_status = normalize_account_deletion_status(
        marker_exists=bool(getattr(deletion_snapshot, "exists", False)),
        raw_status=deletion_payload.get("wipe_status") if isinstance(deletion_payload, dict) else None,
    )
    if account_deletion_blocks_access(deletion_status):
        raise JITProactivityReservationError("JIT reservation blocked by account deletion")

    control_snapshot = db_client.document(collections.memory_apply_control_state).get(transaction=transaction)
    control = parse_snapshot_strict(MemoryControlState, control_snapshot, payload_from_snapshot=_snapshot_payload)
    if control.uid != uid or control.account_generation != proposed.account_generation:
        raise JITProactivityReservationError("JIT reservation generation is stale")

    event_ref = db_client.document(f"{collections.jit_proactivity_events}/{proposed.event_id}")
    event_snapshot = event_ref.get(transaction=transaction)

    parent: JITProactivityEventReceipt | None = None
    if proposed.parent_event_id is not None:
        parent_snapshot = db_client.document(f"{collections.jit_proactivity_events}/{proposed.parent_event_id}").get(
            transaction=transaction
        )
        parent = parse_snapshot_strict(
            JITProactivityEventReceipt,
            parent_snapshot,
            payload_from_snapshot=_snapshot_payload,
        )
        if (
            parent.uid != uid
            or parent.account_generation != proposed.account_generation
            or parent.operation not in {"planned_notification", "ambient_notification"}
            or parent.candidate_id != proposed.candidate_id
            or parent.device_id != proposed.device_id
            or parent.budget_day != proposed.budget_day
            or parent.budget_timezone != proposed.budget_timezone
            or parent.trigger_memory_id != proposed.trigger_memory_id
            or parent.trigger_revision != proposed.trigger_revision
            or parent.event_id == proposed.event_id
            or parent.feedback_id is not None
        ):
            raise JITProactivityReservationError("JIT full-turn admission authority is stale")

    if proposed.trigger_memory_id is not None:
        trigger_snapshot = db_client.document(f"{collections.memory_items}/{proposed.trigger_memory_id}").get(
            transaction=transaction
        )
        trigger = parse_snapshot_strict(MemoryItem, trigger_snapshot, payload_from_snapshot=_snapshot_payload)
        if (
            trigger.uid != uid
            or trigger.account_generation != proposed.account_generation
            or trigger.item_revision != proposed.trigger_revision
            or not is_authoritative_trigger_for_paid_work(trigger, proposed.created_at)
        ):
            raise JITProactivityReservationError("JIT trigger authority is stale")

    if getattr(event_snapshot, "exists", False):
        existing = parse_snapshot_strict(
            JITProactivityEventReceipt,
            event_snapshot,
            payload_from_snapshot=_snapshot_payload,
        )
        if existing.request_hash != proposed.request_hash:
            raise JITProactivityReservationError("JIT event id was reused with a different payload")
        return existing, False

    budget_control_ref = db_client.document(f"{collections.user_root}/jit_proactivity_budget_control/current")
    budget_control_snapshot = budget_control_ref.get(transaction=transaction)
    if getattr(budget_control_snapshot, "exists", False):
        budget_control = _snapshot_payload(budget_control_snapshot)
        if (
            budget_control.get("schema_version") != "jit_proactivity_budget_control.v1"
            or budget_control.get("uid") != uid
            or budget_control.get("account_generation") != proposed.account_generation
            or not isinstance(budget_control.get("budget_timezone"), str)
            or not isinstance(budget_control.get("budget_day"), str)
            or not isinstance(budget_control.get("window_ends_at"), datetime)
        ):
            raise JITProactivityReservationError("JIT budget timezone authority is malformed")
        window_ends_at = budget_control["window_ends_at"]
        if window_ends_at.tzinfo is None or window_ends_at.utcoffset() is None:
            raise JITProactivityReservationError("JIT budget timezone authority is malformed")
        if proposed.created_at < window_ends_at and (
            budget_control["budget_timezone"] != proposed.budget_timezone
            or budget_control["budget_day"] != proposed.budget_day
        ):
            raise JITProactivityReservationError("JIT timezone change would split an active budget window")
    budget_control_write = {
        "schema_version": "jit_proactivity_budget_control.v1",
        "uid": uid,
        "account_generation": proposed.account_generation,
        "budget_timezone": proposed.budget_timezone,
        "budget_day": proposed.budget_day,
        "window_ends_at": _next_local_midnight(proposed.created_at, proposed.budget_timezone),
        "updated_at": proposed.created_at,
    }

    day_ref = db_client.document(f"{collections.jit_proactivity_daily_budgets}/{proposed.budget_day}")
    day_snapshot = day_ref.get(transaction=transaction)
    budget: dict[str, Any]
    if getattr(day_snapshot, "exists", False):
        budget = _snapshot_payload(day_snapshot)
        prior_generation = budget.get("account_generation")
        if type(prior_generation) is not int or prior_generation > proposed.account_generation:
            raise JITProactivityReservationError("JIT daily budget authority is malformed")
        if prior_generation < proposed.account_generation:
            budget = {}
        elif (
            budget.get("schema_version") != "jit_proactivity_daily_budget.v1"
            or budget.get("uid") != uid
            or budget.get("budget_day") != proposed.budget_day
            or budget.get("budget_timezone") != proposed.budget_timezone
        ):
            raise JITProactivityReservationError("JIT daily budget authority is malformed")
    else:
        budget = {}

    if not budget:
        budget = {
            "schema_version": "jit_proactivity_daily_budget.v1",
            "uid": uid,
            "account_generation": proposed.account_generation,
            "budget_day": proposed.budget_day,
            "budget_timezone": proposed.budget_timezone,
            "total_notifications": 0,
            "nano_triages": 0,
            "full_turns": 0,
            "planned_by_trigger": {},
        }

    operation = proposed.operation
    if operation in {"planned_notification", "ambient_notification"}:
        total = budget.get("total_notifications")
        if type(total) is not int or total < 0:
            raise JITProactivityReservationError("JIT notification budget is malformed")
        if total >= JIT_TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY:
            raise JITProactivityReservationError("JIT notification budget exhausted")
        budget["total_notifications"] = total + 1
        if operation == "planned_notification":
            counts = budget.get("planned_by_trigger")
            if not isinstance(counts, dict):
                raise JITProactivityReservationError("JIT per-trigger budget is malformed")
            assert proposed.trigger_memory_id is not None
            if proposed.trigger_memory_id not in counts and len(counts) >= 500:
                raise JITProactivityReservationError("JIT per-trigger budget is malformed")
            used = counts.get(proposed.trigger_memory_id, 0)
            if type(used) is not int or used < 0:
                raise JITProactivityReservationError("JIT per-trigger budget is malformed")
            if used >= JIT_PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY:
                raise JITProactivityReservationError("JIT per-trigger budget exhausted")
            budget["planned_by_trigger"] = {**counts, proposed.trigger_memory_id: used + 1}
    elif operation == "nano_triage":
        used = budget.get("nano_triages")
        if type(used) is not int or used < 0:
            raise JITProactivityReservationError("JIT nano-triage budget is malformed")
        if used >= JIT_AMBIGUOUS_NANO_TRIAGES_PER_DAY:
            raise JITProactivityReservationError("JIT nano-triage budget exhausted")
        budget["nano_triages"] = used + 1
    elif operation == "full_turn":
        if parent is None:  # pragma: no cover - the typed receipt owns this invariant.
            raise JITProactivityReservationError("JIT full-turn admission authority is unavailable")
        full_turns = budget.get("full_turns", 0)
        if type(full_turns) is not int or full_turns < 0:
            raise JITProactivityReservationError("JIT full-turn daily budget is malformed")
        if full_turns >= JIT_TOTAL_FULL_TURNS_PER_DAY:
            raise JITProactivityReservationError("JIT full-turn daily budget exhausted")
        candidate_ref = db_client.document(f"{collections.jit_proactivity_candidate_turns}/{proposed.candidate_id}")
        candidate_snapshot = candidate_ref.get(transaction=transaction)
        if getattr(candidate_snapshot, "exists", False):
            candidate_payload = _snapshot_payload(candidate_snapshot)
            prior_generation = candidate_payload.get("account_generation")
            if type(prior_generation) is not int or prior_generation > proposed.account_generation:
                raise JITProactivityReservationError("JIT candidate full-turn authority is malformed")
            if prior_generation == proposed.account_generation:
                raise JITProactivityReservationError("JIT candidate full-turn budget exhausted")
        budget["full_turns"] = full_turns + JIT_FULL_TURNS_PER_CANDIDATE
        transaction.set(
            candidate_ref,
            {
                "schema_version": "jit_proactivity_candidate_turn.v1",
                "uid": uid,
                "account_generation": proposed.account_generation,
                "candidate_id": proposed.candidate_id,
                "event_id": proposed.event_id,
                "parent_event_id": proposed.parent_event_id,
                "budget_day": proposed.budget_day,
                "created_at": proposed.created_at,
            },
        )
    else:  # pragma: no cover - typed model owns this boundary.
        raise JITProactivityReservationError("unsupported JIT reservation operation")

    budget["updated_at"] = proposed.created_at
    transaction.set(budget_control_ref, budget_control_write)
    transaction.set(day_ref, budget)
    transaction.set(event_ref, proposed.model_dump(mode="python"))
    return proposed, True


def reserve_jit_proactivity_event(
    uid: str,
    *,
    event_id: str,
    candidate_id: str,
    operation: JITProactivityOperation,
    account_generation: int,
    device_id: str,
    trigger_memory_id: str | None = None,
    trigger_revision: int | None = None,
    parent_event_id: str | None = None,
    now: datetime | None = None,
    db_client: Any = None,
) -> tuple[JITProactivityEventReceipt, bool]:
    client = db_client if db_client is not None else default_db_client
    created_at = now or datetime.now(timezone.utc)
    normalized_timezone = _timezone_from_user_snapshot(client.document(f"users/{uid}").get())
    budget_day = _budget_day_for_timezone(created_at, normalized_timezone)
    canonical_request = {
        "schema_version": "jit_proactivity_event.v1",
        "uid": uid.strip(),
        "event_id": event_id.strip(),
        "candidate_id": candidate_id.strip(),
        "operation": operation,
        "account_generation": account_generation,
        "trigger_memory_id": trigger_memory_id.strip() if trigger_memory_id is not None else None,
        "trigger_revision": trigger_revision,
        "parent_event_id": parent_event_id.strip() if parent_event_id is not None else None,
        "device_id": device_id.strip(),
        "budget_day": budget_day,
        "budget_timezone": normalized_timezone,
    }
    request_hash = hashlib.sha256(
        json.dumps(canonical_request, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    proposed = parse_payload_strict(
        JITProactivityEventReceipt,
        {
            **canonical_request,
            "created_at": created_at,
            "request_hash": request_hash,
        },
        document_path="<request>/jit_proactivity_event",
    )
    transaction = client.transaction()
    return _reserve_transaction(transaction, client, proposed)


__all__ = ["JITProactivityReservationError", "reserve_jit_proactivity_event"]
