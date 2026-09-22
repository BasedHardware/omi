#!/usr/bin/env python3
"""Admin CLI: inspect / reset a user's monthly transcription and chat quotas.

Support-ops tool for the monthly transcription (listening) minutes quota and
the chat-question quota. Listening reads the same surface the cap enforces —
``transcription_seconds`` summed across ``users/{uid}/hourly_usage/{YYYY-MM-DD-HH}``
for the current calendar month (see ``database/user_usage.get_monthly_usage_stats``
and ``utils/subscription.get_remaining_transcription_seconds``). Chat questions
come from ``database.user_usage.get_monthly_chat_usage`` over
``users/{uid}/llm_usage/{YYYY-MM-DD}``.

Commands
--------
``show``              Lookup by --uid (or --email) and print plan / status /
                      listening minutes / chat questions for the current UTC
                      month. Metadata only — never prints transcripts, memories, or
                      messages. Fair-use is read-only (stage field or HTTP pointer).
``reset-month``       Zero ``transcription_seconds`` on every current-month
                      hourly_usage doc. DRY-RUN by default; requires ``--reason``
                      and ``--apply`` to write.
``reset-chat-month``  Zero current-UTC-month ``quota_questions`` (nested, dotted,
                      and ``plan_usage``). DRY-RUN by default; same
                      ``--reason`` / ``--apply`` / ``--operator`` / audit contract.
                      Does not delete keys, wipe telemetry, or reset fair-use.

Credentials
-----------
Uses the same loader as the backend (``database.google_credentials``): set
``GOOGLE_APPLICATION_CREDENTIALS`` to a service-account JSON file with Firestore
write on the prod project, or run ``gcloud auth application-default login`` for
ADC. ``--email`` additionally initializes firebase_admin to resolve the uid
(Auth lookup); ``--uid`` needs no Auth SDK. Never derive UID from
PostHog/Firestore email/Stripe.

Examples
--------
    # Inspect (read-only):
    GOOGLE_APPLICATION_CREDENTIALS=svc.json python -m scripts.admin.reset_transcription_usage \
        show --uid <UID>

    # Dry-run listening reset (default — writes nothing):
    python -m scripts.admin.reset_transcription_usage reset-month --uid <UID> --reason "goodwill: silent open-mic"

    # Apply listening reset:
    python -m scripts.admin.reset_transcription_usage reset-month --uid <UID> \
        --reason "goodwill: silent open-mic" --apply --operator "david@"

    # Dry-run chat-quota reset:
    python -m scripts.admin.reset_transcription_usage reset-chat-month --uid <UID> \
        --reason "goodwill: chat-quota burn"

    # Apply chat-quota reset:
    python -m scripts.admin.reset_transcription_usage reset-chat-month --uid <UID> \
        --reason "goodwill: chat-quota burn" --apply --operator "david@"

This is an ops tool, not a service: keep heavy backend imports inside the
command/I-O functions so the pure helpers stay importable without GCP and
unit-testable.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Firestore batch write limit.
_BATCH_LIMIT = 400

# How many top hourly buckets ``show`` prints.
_TOP_BUCKETS = 5

# Audit action written by ``reset-chat-month``.
_CHAT_RESET_AUDIT_ACTION = "reset-chat-quota-month"

# Fair-use write stays on the existing admin HTTP surface.
_FAIR_USE_GET_POINTER = "GET /v1/admin/fair-use/user/{uid}"
_FAIR_USE_RESET_POINTER = "POST /v1/admin/fair-use/user/{uid}/reset"


# ---------------------------------------------------------------------------
# Pure logic — no GCP, unit-testable
# ---------------------------------------------------------------------------


def month_label(now: datetime) -> str:
    """``YYYY-MM`` label for the calendar month containing ``now`` (UTC)."""
    return f"{now.year:04d}-{now.month:02d}"


@dataclass(frozen=True)
class HourlyBucket:
    """One ``hourly_usage`` doc's transcription contribution."""

    doc_id: str
    seconds: int

    @property
    def day_hour(self) -> str:
        # doc_id shape: ``YYYY-MM-DD-HH``
        return self.doc_id


@dataclass(frozen=True)
class MonthlyUsage:
    """Aggregated transcription usage for one calendar month."""

    used_seconds: int
    document_count: int
    top_buckets: tuple[HourlyBucket, ...]


def aggregate_monthly_usage(docs: Iterable[tuple[str, dict[str, Any]]], top_n: int = _TOP_BUCKETS) -> MonthlyUsage:
    """Sum ``transcription_seconds`` across hourly_usage docs.

    ``docs`` is an iterable of ``(doc_id, data_dict)`` pairs (the Firestore
    snapshot shape). Missing/zero fields count as zero, matching
    ``database/user_usage._aggregate_stats_with_count``.
    """
    total = 0
    document_count = 0
    buckets: list[HourlyBucket] = []
    for doc_id, data in docs:
        document_count += 1
        seconds = int(data.get("transcription_seconds", 0) or 0)
        total += seconds
        if seconds > 0:
            buckets.append(HourlyBucket(doc_id=doc_id, seconds=seconds))
    buckets.sort(key=lambda b: b.seconds, reverse=True)
    return MonthlyUsage(
        used_seconds=total,
        document_count=document_count,
        top_buckets=tuple(buckets[:top_n]),
    )


def seconds_to_minutes(seconds: int) -> float:
    """Seconds → minutes, rounded to one decimal (display only)."""
    return round(seconds / 60.0, 1)


@dataclass(frozen=True)
class ResetPlan:
    """What ``reset-month`` will zero, and the before/after monthly totals."""

    doc_ids: tuple[str, ...]  # docs whose transcription_seconds > 0 get zeroed
    before_total_seconds: int
    after_total_seconds: int = 0  # zeroing always lands the month at 0

    @property
    def touches(self) -> int:
        return len(self.doc_ids)


def build_reset_plan(docs: Iterable[tuple[str, dict[str, Any]]]) -> ResetPlan:
    """Build the zero-out plan for the current month.

    Only docs with ``transcription_seconds > 0`` are touched; empty buckets are
    skipped so a reset on a fresh user is a no-op write.
    """
    to_zero: list[str] = []
    before_total = 0
    for doc_id, data in docs:
        seconds = int(data.get("transcription_seconds", 0) or 0)
        if seconds > 0:
            before_total += seconds
            to_zero.append(doc_id)
    return ResetPlan(doc_ids=tuple(to_zero), before_total_seconds=before_total)


@dataclass(frozen=True)
class AuditRecord:
    """Durable audit trail for a reset op. Written to Firestore + stdout."""

    uid: str
    email: Optional[str]
    plan: str
    month: str
    reason: str
    operator: str
    applied: bool
    before_seconds: int
    after_seconds: int
    docs_touched: int
    at: str  # RFC3339 UTC

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "email": self.email,
            "plan": self.plan,
            "month": self.month,
            "reason": self.reason,
            "operator": self.operator,
            "applied": self.applied,
            "before_seconds": self.before_seconds,
            "after_seconds": self.after_seconds,
            "docs_touched": self.docs_touched,
            "at": self.at,
        }


def build_audit_record(
    *,
    uid: str,
    email: Optional[str],
    plan: str,
    month: str,
    reason: str,
    operator: str,
    applied: bool,
    before_seconds: int,
    after_seconds: int,
    docs_touched: int,
    now: Optional[datetime] = None,
) -> AuditRecord:
    now = now or datetime.now(timezone.utc)
    return AuditRecord(
        uid=uid,
        email=email,
        plan=plan,
        month=month,
        reason=reason,
        operator=operator,
        applied=applied,
        before_seconds=before_seconds,
        after_seconds=after_seconds,
        docs_touched=docs_touched,
        at=now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


@dataclass(frozen=True)
class AccountView:
    """Plan + limits the enforcement path sees (non-mutating)."""

    plan_name: str
    status: str
    listening_limit_seconds: Optional[int]
    chat_questions_limit: Optional[int]
    chat_cost_usd_limit: Optional[float]


def listening_is_throttled(limit_seconds: Optional[int], used_seconds: int) -> bool:
    """True only when a finite listening cap is exhausted. Unlimited is never throttled."""
    if limit_seconds is None:
        return False
    return used_seconds >= limit_seconds


def skip_unlimited_listening_reset(limit_seconds: Optional[int], force: bool) -> bool:
    """Do not zero minutes on unlimited plans unless the operator passed --force."""
    return limit_seconds is None and not force


_UNLIMITED_LISTENING_SKIP_MESSAGE = (
    "listening throttled: no (unlimited)\n"
    "skip reset-month: minutes used do not throttle this plan. "
    "Pass --force to goodwill-zero anyway."
)


@dataclass(frozen=True)
class ChatQuotaAuditRecord:
    """Durable audit trail for a chat-quota reset. Same sanitization as minutes."""

    uid: str
    email: Optional[str]
    plan: str
    month: str
    reason: str
    operator: str
    applied: bool
    before_questions: int
    after_questions: int
    docs_touched: int
    at: str  # RFC3339 UTC
    action: str = _CHAT_RESET_AUDIT_ACTION

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "uid": self.uid,
            "email": self.email,
            "plan": self.plan,
            "month": self.month,
            "reason": self.reason,
            "operator": self.operator,
            "applied": self.applied,
            "before_questions": self.before_questions,
            "after_questions": self.after_questions,
            "docs_touched": self.docs_touched,
            "at": self.at,
        }


def build_chat_quota_audit_record(
    *,
    uid: str,
    email: Optional[str],
    plan: str,
    month: str,
    reason: str,
    operator: str,
    applied: bool,
    before_questions: int,
    after_questions: int,
    docs_touched: int,
    now: Optional[datetime] = None,
) -> ChatQuotaAuditRecord:
    now = now or datetime.now(timezone.utc)
    return ChatQuotaAuditRecord(
        uid=uid,
        email=email,
        plan=plan,
        month=month,
        reason=reason,
        operator=operator,
        applied=applied,
        before_questions=before_questions,
        after_questions=after_questions,
        docs_touched=docs_touched,
        at=now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def llm_usage_doc_id_in_utc_month(doc_id: str, year: int, month: int) -> bool:
    """True when ``llm_usage/{YYYY-MM-DD}`` falls in the given UTC calendar month."""
    if len(doc_id) < 10 or doc_id[4] != "-" or doc_id[7] != "-":
        return False
    try:
        return int(doc_id[0:4]) == year and int(doc_id[5:7]) == month
    except ValueError:
        return False


def _has_backend_quota_questions(data: Mapping[str, Any]) -> bool:
    return any(
        (key == "backend_chat" and isinstance(value, dict) and "quota_questions" in value)
        or (key == "backend_chat.quota_questions")
        for key, value in data.items()
    )


def _has_desktop_realtime_quota_questions(data: Mapping[str, Any]) -> bool:
    return "desktop_chat_realtime.quota_questions" in data or (
        isinstance(data.get("desktop_chat_realtime"), dict) and "quota_questions" in data["desktop_chat_realtime"]
    )


def _legacy_backend_chat_call_count_would_count(data: Mapping[str, Any]) -> bool:
    """True when ``get_monthly_chat_usage`` would still count ``chat.*.call_count``."""
    if _has_backend_quota_questions(data):
        return False
    return any(
        isinstance(value, (int, float)) and key.startswith("chat.") and key.endswith(".call_count")
        for key, value in data.items()
    )


def _legacy_realtime_call_count_would_count(data: Mapping[str, Any]) -> bool:
    """True when ``get_monthly_chat_usage`` would still count realtime ``call_count``."""
    if _has_desktop_realtime_quota_questions(data):
        return False
    nested = data.get("desktop_chat_realtime")
    if isinstance(nested, dict) and int(nested.get("call_count", 0) or 0) != 0:
        return True
    dotted = data.get("desktop_chat_realtime.call_count")
    return isinstance(dotted, (int, float)) and int(dotted) != 0


def _set_nested(dest: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = dest
    for part in path[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[path[-1]] = value


def build_chat_quota_reset_update(data: Mapping[str, Any]) -> dict[str, Any]:
    """Firestore ``set(..., merge=True)`` payload that zeros this doc's chat quota.

    Sets ``quota_questions`` to 0 (never deletes the key). Does not touch
    ``call_count``, tokens, or ``cost_usd``. When legacy ``chat.*.call_count``
    would still count, introduces ``backend_chat.quota_questions = 0`` so
    telemetry stays and ``get_monthly_chat_usage`` reports 0. Same idea for
    ``desktop_chat_realtime`` fallback ``call_count``.
    """
    update: dict[str, Any] = {}

    def walk(obj: Mapping[str, Any], path: tuple[str, ...]) -> None:
        for key, value in obj.items():
            if isinstance(value, dict):
                walk(value, path + (key,))
                continue
            if key == "quota_questions":
                if int(value or 0) != 0:
                    _set_nested(update, path + (key,), 0)
            elif isinstance(key, str) and key.endswith(".quota_questions") and isinstance(value, (int, float)):
                if int(value or 0) == 0:
                    continue
                if path:
                    _set_nested(update, path + (key,), 0)
                else:
                    update[key] = 0

    walk(data, ())

    if _legacy_backend_chat_call_count_would_count(data):
        _set_nested(update, ("backend_chat", "quota_questions"), 0)

    if _legacy_realtime_call_count_would_count(data):
        nested_rt = data.get("desktop_chat_realtime")
        if isinstance(nested_rt, dict):
            _set_nested(update, ("desktop_chat_realtime", "quota_questions"), 0)
        else:
            update["desktop_chat_realtime.quota_questions"] = 0

    return update


def apply_chat_quota_reset_locally(data: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-merge a reset payload into a document copy (tests / dry-run preview)."""
    result = copy.deepcopy(dict(data))

    def merge(dest: dict[str, Any], payload: Mapping[str, Any]) -> None:
        for key, value in payload.items():
            if isinstance(value, dict):
                existing = dest.get(key)
                if isinstance(existing, dict):
                    merge(existing, value)
                else:
                    dest[key] = copy.deepcopy(dict(value))
            else:
                dest[key] = value

    merge(result, update)
    return result


def chat_questions_from_doc(data: Mapping[str, Any]) -> int:
    """Per-document question count matching ``get_monthly_chat_usage``'s inner loop.

    Used by unit tests to assert a reset payload lands questions at 0 without
    forking a second monthly aggregator. The live CLI still imports
    ``get_monthly_chat_usage`` for before/after totals.
    """
    questions = 0
    has_desktop_realtime_quota_questions = _has_desktop_realtime_quota_questions(data)
    has_backend_quota_questions = _has_backend_quota_questions(data)
    for key, value in data.items():
        if isinstance(value, dict):
            if key == "desktop_chat":
                questions += int(value.get("quota_questions", 0) or 0)
            elif key == "desktop_chat_realtime" and not has_desktop_realtime_quota_questions:
                questions += int(value.get("call_count", 0) or 0)
            elif key == "backend_chat":
                questions += int(value.get("quota_questions", 0) or 0)
            continue
        if not isinstance(value, (int, float)):
            continue
        if key.startswith("desktop_chat"):
            if key == "desktop_chat.quota_questions":
                questions += int(value)
            elif key == "desktop_chat_realtime.call_count" and not has_desktop_realtime_quota_questions:
                questions += int(value)
        elif key == "backend_chat.quota_questions":
            questions += int(value)
        elif key.startswith("chat.") and key.endswith(".call_count") and not has_backend_quota_questions:
            questions += int(value)
    return questions


@dataclass(frozen=True)
class ChatResetPlan:
    """What ``reset-chat-month`` will write, keyed by llm_usage doc id."""

    updates: tuple[tuple[str, dict[str, Any]], ...]  # (doc_id, merge payload)

    @property
    def doc_ids(self) -> tuple[str, ...]:
        return tuple(doc_id for doc_id, _payload in self.updates)

    @property
    def touches(self) -> int:
        return len(self.updates)


def build_chat_reset_plan(docs: Iterable[tuple[str, Mapping[str, Any]]]) -> ChatResetPlan:
    """Build per-doc merge payloads for the current month. Empty updates are skipped."""
    updates: list[tuple[str, dict[str, Any]]] = []
    for doc_id, data in docs:
        payload = build_chat_quota_reset_update(data)
        if payload:
            updates.append((doc_id, payload))
    return ChatResetPlan(updates=tuple(updates))


# ---------------------------------------------------------------------------
# I/O — thin wrappers over Firestore / Auth. Imports are local so the pure
# helpers above stay importable without the backend runtime.
# ---------------------------------------------------------------------------


def _firestore_client() -> Any:
    from database._client import get_firestore_client  # supported getter

    return get_firestore_client()


def fetch_monthly_hourly_docs(client: Any, uid: str, year: int, month: int) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(doc_id, data)`` for every hourly_usage doc in the given month.

    Mirrors ``database/user_usage.get_monthly_usage_stats``: filters on the
    ``year``/``month`` fields the increment path writes alongside each bucket.
    """
    from google.cloud.firestore_v1 import FieldFilter

    query = (
        client.collection("users")
        .document(uid)
        .collection("hourly_usage")
        .where(filter=FieldFilter("year", "==", year))
        .where(filter=FieldFilter("month", "==", month))
    )
    return [(doc.id, (doc.to_dict() or {})) for doc in query.stream()]


def fetch_monthly_llm_usage_docs(client: Any, uid: str, now: datetime) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(doc_id, data)`` for every ``llm_usage/{YYYY-MM-DD}`` in the UTC month.

    Reuses ``database.user_usage._current_month_llm_usage_docs`` (document-id
    range) so the CLI cannot drift from the enforcement reader.
    """
    from database.user_usage import _current_month_llm_usage_docs

    llm_usage_ref = client.collection("users").document(uid).collection("llm_usage")
    return [(doc.id, (doc.to_dict() or {})) for doc in _current_month_llm_usage_docs(llm_usage_ref, now)]


def fetch_fair_use_stage(client: Any, uid: str) -> Optional[str]:
    """Read-only ``users/{uid}/fair_use_state/current.stage`` if the doc exists."""
    ref = client.collection("users").document(uid).collection("fair_use_state").document("current")
    doc = ref.get()
    if not getattr(doc, "exists", False):
        return None
    data = doc.to_dict() or {}
    stage = data.get("stage")
    if stage is None or stage == "":
        return None
    return str(stage)


def resolve_uid(*, uid: Optional[str], email: Optional[str]) -> tuple[str, Optional[str]]:
    """Resolve a target uid from --uid (preferred) or --email (Firebase Auth)."""
    if uid:
        return uid, email
    if not email:
        raise SystemExit("error: provide --uid or --email")
    import firebase_admin
    from firebase_admin import auth as firebase_auth

    if not firebase_admin._apps:  # type: ignore[attr-defined]
        # ADC if GOOGLE_APPLICATION_CREDENTIALS unset; matches migration scripts.
        if os.getenv("SERVICE_ACCOUNT_JSON"):
            from firebase_admin import credentials

            firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ["SERVICE_ACCOUNT_JSON"])))
        else:
            firebase_admin.initialize_app()
    user = firebase_auth.get_user_by_email(email)  # raises UserNotFoundError
    return user.uid, email


def resolve_account_view(uid: str) -> AccountView:
    """Return plan / status / listening and chat limits the enforcement path sees.

    Uses ``get_user_valid_subscription(..., provision=False)`` so ``show`` and
    dry-run never create a default subscription or rewrite a legacy ``free``
    plan. Expired paid plans fall back to Basic, matching enforcement.
    """
    from database import users as users_db
    from utils.subscription import (
        get_default_basic_subscription,
        get_plan_display_name,
        get_plan_limits,
    )

    subscription = users_db.get_user_valid_subscription(uid, provision=False)
    if subscription is None:
        subscription = get_default_basic_subscription()
    plan = subscription.plan
    limits = get_plan_limits(plan)
    status = getattr(subscription.status, "value", str(subscription.status))
    listening = limits.transcription_seconds
    return AccountView(
        plan_name=get_plan_display_name(plan),
        status=status,
        listening_limit_seconds=None if listening is None else listening,
        chat_questions_limit=limits.chat_questions_per_month,
        chat_cost_usd_limit=limits.chat_cost_usd_per_month,
    )


def resolve_plan_and_limit(uid: str) -> tuple[str, Optional[int]]:
    """Return ``(plan_name, monthly_seconds_limit_or_None)``.

    Uses ``get_user_valid_subscription`` — the same effective subscription the
    enforcement path (``get_remaining_transcription_seconds``) uses. This is a
    **non-mutating** read: unlike ``get_user_subscription``, it never creates a
    default subscription or rewrites legacy ``free`` plans, so ``show`` and
    dry-run commands stay genuinely read-only.

    For a user whose paid plan has expired, this returns the Basic fallback
    rather than the stored paid plan — matching what enforcement sees.

    ``None`` limit = unlimited plan (operator/architect/unlimited/neo). The
    transcription cap only bites basic + plus, whose limits come straight from
    ``utils.subscription.get_plan_limits`` (Free still honors
    ``BASIC_TIER_MINUTES_LIMIT_PER_MONTH`` via that helper).
    """
    view = resolve_account_view(uid)
    return view.plan_name, view.listening_limit_seconds


def apply_reset(client: Any, uid: str, plan: ResetPlan) -> None:
    """Zero ``transcription_seconds`` on every doc in the reset plan (batched)."""
    if not plan.doc_ids:
        return
    hourly = client.collection("users").document(uid).collection("hourly_usage")
    for chunk_start in range(0, len(plan.doc_ids), _BATCH_LIMIT):
        batch = client.batch()
        for doc_id in plan.doc_ids[chunk_start : chunk_start + _BATCH_LIMIT]:
            batch.set(hourly.document(doc_id), {"transcription_seconds": 0}, merge=True)
        batch.commit()


def apply_chat_reset(client: Any, uid: str, plan: ChatResetPlan) -> None:
    """Merge each chat-quota reset payload onto ``llm_usage`` docs (batched)."""
    if not plan.updates:
        return
    llm = client.collection("users").document(uid).collection("llm_usage")
    for chunk_start in range(0, len(plan.updates), _BATCH_LIMIT):
        batch = client.batch()
        for doc_id, payload in plan.updates[chunk_start : chunk_start + _BATCH_LIMIT]:
            batch.set(llm.document(doc_id), payload, merge=True)
        batch.commit()


def write_audit(client: Any, record: AuditRecord | ChatQuotaAuditRecord) -> str:
    """Persist the audit record to ``admin_audit_log`` and return its doc id."""
    doc_ref = client.collection("admin_audit_log").document()
    doc_ref.set(record.to_dict())
    return doc_ref.id


def update_audit(client: Any, audit_id: str, record: AuditRecord | ChatQuotaAuditRecord) -> None:
    """Update an existing audit record after the mutation outcome is known."""
    client.collection("admin_audit_log").document(audit_id).set(record.to_dict())


# ---------------------------------------------------------------------------
# Audit payload sanitization — stdout/logs get redacted PII; the Firestore
# record retains the full fields (access-controlled).
# ---------------------------------------------------------------------------


def _sanitized_audit_payload(record: AuditRecord | ChatQuotaAuditRecord) -> dict[str, Any]:
    """Return a copy of the audit record with PII redacted for stdout/logs.

    The email and operator-provided reason may contain user-identifiable text;
    these are masked before serializing to the JSON line printed to stdout,
    which is intended for operator logs. The full record persists only in the
    access-controlled ``admin_audit_log`` Firestore collection.
    """
    try:
        from utils.log_sanitizer import sanitize_pii
    except Exception:
        # Fallback: don't crash the CLI if the sanitizer can't import.
        sanitize_pii = lambda v: str(v)  # noqa: E731

    payload = record.to_dict()
    if payload.get("email") is not None:
        payload["email"] = sanitize_pii(payload["email"])
    if payload.get("reason") is not None:
        payload["reason"] = sanitize_pii(payload["reason"])
    return payload


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def _print_usage(
    uid: str,
    email: Optional[str],
    view: AccountView,
    usage: MonthlyUsage,
    month: str,
    *,
    chat_questions: int,
    fair_use_stage: Optional[str],
) -> None:
    used = usage.used_seconds
    limit_seconds = view.listening_limit_seconds
    if limit_seconds is None:
        limit_min_s = "unlimited"
        remaining_s = "unlimited"
        pct_s = "n/a"
    else:
        limit_min_s = f"{seconds_to_minutes(limit_seconds)} min"
        remaining = max(0, limit_seconds - used)
        remaining_s = f"{seconds_to_minutes(remaining)} min ({remaining} s)"
        pct_s = f"{round(100.0 * used / limit_seconds, 1)}%" if limit_seconds else "n/a"

    chat_limit = view.chat_questions_limit
    if chat_limit is None:
        chat_limit_s = "unlimited"
        chat_remaining_s = "unlimited"
    else:
        chat_remaining = max(0, chat_limit - chat_questions)
        chat_limit_s = f"{chat_limit} questions"
        chat_remaining_s = f"{chat_remaining} questions"

    if fair_use_stage:
        fair_use_s = f"stage={fair_use_stage} (read-only; writes: {_FAIR_USE_GET_POINTER.format(uid=uid)})"
    else:
        fair_use_s = (
            f"{_FAIR_USE_GET_POINTER.format(uid=uid)} "
            f"(read-only; write remains {_FAIR_USE_RESET_POINTER.format(uid=uid)})"
        )

    print(f"uid:           {uid}")
    if email:
        print(f"email:         {email}")
    print(f"plan:          {view.plan_name}")
    print(f"status:        {view.status}")
    print(f"month:         {month} (UTC)")
    print(
        f"listening used:      {seconds_to_minutes(used)} min ({used} s) "
        f"across {usage.document_count} hourly bucket(s)"
    )
    print(f"listening limit:     {limit_min_s}")
    print(f"listening remaining: {remaining_s}")
    print(f"listening used of limit: {pct_s}")
    listening_throttled = listening_is_throttled(limit_seconds, used)
    print(f"listening throttled: {'yes' if listening_throttled else 'no'}")
    if limit_seconds is None:
        print("listening reset: skip (unlimited; not throttled). Use reset-month --force only for goodwill.")
    print(f"chat used:      {chat_questions} questions")
    print(f"chat limit:     {chat_limit_s}")
    print(f"chat remaining: {chat_remaining_s}")
    if chat_limit is None:
        print("chat included exhausted: n/a (unlimited)")
    else:
        print(f"chat included exhausted: {'yes' if chat_questions >= chat_limit else 'no'}")
    if view.chat_cost_usd_limit is not None:
        print(f"chat cost cap:  ${view.chat_cost_usd_limit:g} (architect unit; questions still shown above)")
    print(f"fair-use:       {fair_use_s}")
    if usage.top_buckets:
        print("top buckets:")
        for b in usage.top_buckets:
            share = f" ({round(100.0 * b.seconds / used, 1)}%)" if used else ""
            print(f"  {b.doc_id}: {seconds_to_minutes(b.seconds)} min ({b.seconds} s){share}")


def _monthly_chat_questions(uid: str, now: datetime, client: Any) -> int:
    from database.user_usage import get_monthly_chat_usage

    usage = get_monthly_chat_usage(uid, now=now, firestore_client=client)
    return int(usage.get("questions", 0) or 0)


def _require_operator_on_apply(args: argparse.Namespace) -> str:
    operator = (args.operator or "").strip()
    if args.apply and (not operator or operator == "unknown"):
        raise SystemExit("error: --operator is required with --apply")
    return operator or os.getenv("USER", "unknown")


def cmd_show(args: argparse.Namespace) -> int:
    uid, email = resolve_uid(uid=args.uid, email=args.email)
    client = _firestore_client()
    now = datetime.now(timezone.utc)
    view = resolve_account_view(uid)
    docs = fetch_monthly_hourly_docs(client, uid, now.year, now.month)
    usage = aggregate_monthly_usage(docs)
    chat_questions = _monthly_chat_questions(uid, now, client)
    try:
        fair_use_stage = fetch_fair_use_stage(client, uid)
    except Exception:
        fair_use_stage = None
    _print_usage(
        uid,
        email,
        view,
        usage,
        month_label(now),
        chat_questions=chat_questions,
        fair_use_stage=fair_use_stage,
    )
    return 0


def cmd_reset_month(args: argparse.Namespace) -> int:
    operator = _require_operator_on_apply(args)
    uid, email = resolve_uid(uid=args.uid, email=args.email)
    client = _firestore_client()
    now = datetime.now(timezone.utc)
    view = resolve_account_view(uid)
    plan_name = view.plan_name
    if skip_unlimited_listening_reset(view.listening_limit_seconds, bool(getattr(args, "force", False))):
        print(_UNLIMITED_LISTENING_SKIP_MESSAGE)
        return 2
    docs = fetch_monthly_hourly_docs(client, uid, now.year, now.month)
    reset_plan = build_reset_plan(docs)

    if not reset_plan.touches:
        print(f"No transcription_seconds to reset for {uid} in {month_label(now)} (already zero).")
        return 0

    verb = "APPLY" if args.apply else "DRY-RUN (no writes; pass --apply to commit)"
    print(f"[{verb}] reset-month for uid={uid} month={month_label(now)}")
    print(f"  before: {seconds_to_minutes(reset_plan.before_total_seconds)} min ({reset_plan.before_total_seconds} s)")
    print(f"  docs to zero: {reset_plan.touches}")
    print("  after:  0.0 min (0 s)")
    print(f"  reason: {args.reason}")
    print(f"  operator: {operator}")

    record = build_audit_record(
        uid=uid,
        email=email,
        plan=plan_name,
        month=month_label(now),
        reason=args.reason,
        operator=operator,
        applied=args.apply,
        before_seconds=reset_plan.before_total_seconds,
        after_seconds=0,
        docs_touched=reset_plan.touches,
        now=now,
    )

    if not args.apply:
        # Still emit the audit line so dry-run intent is captured in operator logs.
        print("audit (not persisted): " + json.dumps(_sanitized_audit_payload(record), sort_keys=True))
        print("Dry-run complete. Re-run with --apply to commit.")
        return 0

    # Write a pending audit record BEFORE mutation so a mid-reset failure
    # (partial batch commit or audit-write error) still leaves a durable trail
    # describing the intended mutation and the operator who initiated it.
    pending_record = build_audit_record(
        uid=uid,
        email=email,
        plan=plan_name,
        month=month_label(now),
        reason=args.reason,
        operator=operator,
        applied=False,  # updated to True after mutation completes
        before_seconds=reset_plan.before_total_seconds,
        after_seconds=-1,  # sentinel: outcome not yet known
        docs_touched=reset_plan.touches,
        now=now,
    )
    audit_id = write_audit(client, pending_record)

    apply_reset(client, uid, reset_plan)
    # All batched commits succeeded — finalize the audit record.
    final_record = replace(record, applied=True, after_seconds=0)
    update_audit(client, audit_id, final_record)
    print(f"Applied. Audit written: admin_audit_log/{audit_id}")
    print("audit: " + json.dumps(_sanitized_audit_payload(final_record), sort_keys=True))
    return 0


def cmd_reset_chat_month(args: argparse.Namespace) -> int:
    operator = _require_operator_on_apply(args)
    uid, email = resolve_uid(uid=args.uid, email=args.email)
    client = _firestore_client()
    now = datetime.now(timezone.utc)
    view = resolve_account_view(uid)
    docs = fetch_monthly_llm_usage_docs(client, uid, now)
    reset_plan = build_chat_reset_plan(docs)
    before_questions = _monthly_chat_questions(uid, now, client)

    if not reset_plan.touches and before_questions == 0:
        print(f"No chat quota_questions to reset for {uid} in {month_label(now)} (already zero).")
        return 0

    verb = "APPLY" if args.apply else "DRY-RUN (no writes; pass --apply to commit)"
    print(f"[{verb}] reset-chat-month for uid={uid} month={month_label(now)}")
    print(f"  before: {before_questions} questions")
    print(f"  docs to update: {reset_plan.touches}")
    print("  after:  0 questions")
    print(f"  reason: {args.reason}")
    print(f"  operator: {operator}")

    record = build_chat_quota_audit_record(
        uid=uid,
        email=email,
        plan=view.plan_name,
        month=month_label(now),
        reason=args.reason,
        operator=operator,
        applied=args.apply,
        before_questions=before_questions,
        after_questions=0,
        docs_touched=reset_plan.touches,
        now=now,
    )

    if not args.apply:
        print("audit (not persisted): " + json.dumps(_sanitized_audit_payload(record), sort_keys=True))
        print("Dry-run complete. Re-run with --apply to commit.")
        return 0

    pending_record = build_chat_quota_audit_record(
        uid=uid,
        email=email,
        plan=view.plan_name,
        month=month_label(now),
        reason=args.reason,
        operator=operator,
        applied=False,
        before_questions=before_questions,
        after_questions=-1,
        docs_touched=reset_plan.touches,
        now=now,
    )
    audit_id = write_audit(client, pending_record)

    apply_chat_reset(client, uid, reset_plan)
    after_questions = _monthly_chat_questions(uid, now, client)
    final_record = replace(record, applied=True, after_questions=after_questions)
    update_audit(client, audit_id, final_record)
    print(f"Applied. Audit written: admin_audit_log/{audit_id}")
    print(f"  after (re-read via get_monthly_chat_usage): {after_questions} questions")
    print("audit: " + json.dumps(_sanitized_audit_payload(final_record), sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def _add_target_args(p: argparse.ArgumentParser) -> None:
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--uid", help="Firebase Auth uid of the target user.")
    group.add_argument("--email", help="Resolve uid from this email via Firebase Auth.")


def _add_reset_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--reason", required=True, help="Operator reason string (required, audited).")
    p.add_argument("--apply", action="store_true", help="Commit the reset (default is dry-run).")
    p.add_argument(
        "--operator",
        default=os.getenv("USER", "unknown"),
        help="Operator identity for the audit record. Required with --apply (default: $USER).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reset_transcription_usage",
        description="Inspect / reset a user's monthly transcription minutes and chat-question quota.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser(
        "show",
        help="Show plan / status / listening / chat for the current UTC month (read-only).",
    )
    _add_target_args(p_show)
    p_show.set_defaults(func=cmd_show)

    p_reset = sub.add_parser(
        "reset-month",
        help="Zero current-month transcription_seconds. DRY-RUN by default. Refuses unlimited/unthrottled plans unless --force.",
    )
    _add_target_args(p_reset)
    _add_reset_flags(p_reset)
    p_reset.add_argument(
        "--force",
        action="store_true",
        help="Goodwill-zero listening minutes even when the plan is unlimited (not throttled).",
    )
    p_reset.set_defaults(func=cmd_reset_month)

    p_chat = sub.add_parser(
        "reset-chat-month",
        help="Zero current-month chat quota_questions. DRY-RUN by default.",
    )
    _add_target_args(p_chat)
    _add_reset_flags(p_chat)
    p_chat.set_defaults(func=cmd_reset_chat_month)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
