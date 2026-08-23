#!/usr/bin/env python3
"""Admin CLI: inspect / reset a user's monthly transcription usage.

Support-ops tool for the free-tier monthly transcription (listening) minutes
quota. Reads the same surface the cap enforces — ``transcription_seconds``
summed across ``users/{uid}/hourly_usage/{YYYY-MM-DD-HH}`` for the current
calendar month (see ``database/user_usage.get_monthly_usage_stats`` and
``utils/subscription.get_remaining_transcription_seconds``).

Commands
--------
``show``       Lookup by --uid (or --email) and print plan / used / limit /
               remaining for the current month, plus the top hourly buckets.
               Metadata only — never prints transcripts or memories.
               (Collapses the issue's ``lookup`` + ``usage show``: a lookup that
               does not also aggregate has no extra signal, so one command does
               both.)
``reset-month``Zero ``transcription_seconds`` on every current-month hourly_usage doc
               for the user. DRY-RUN by default; requires ``--reason`` and
               ``--apply`` to write. Prints before/after totals and writes a
               durable audit record (Firestore ``admin_audit_log`` + a JSON
               stdout line).

Credentials
-----------
Uses the same loader as the backend (``database.google_credentials``): set
``GOOGLE_APPLICATION_CREDENTIALS`` to a service-account JSON file with Firestore
write on the prod project, or run ``gcloud auth application-default login`` for
ADC. ``--email`` additionally initializes firebase_admin to resolve the uid
(Auth lookup); ``--uid`` needs no Auth SDK.

Examples
--------
    # Inspect (read-only):
    GOOGLE_APPLICATION_CREDENTIALS=svc.json python -m scripts.admin.reset_transcription_usage \
        show --uid <UID>

    # Dry-run reset (default — writes nothing):
    python -m scripts.admin.reset_transcription_usage reset-month --uid <UID> --reason "goodwill: silent open-mic"

    # Apply:
    python -m scripts.admin.reset_transcription_usage reset-month --uid <UID> \
        --reason "goodwill: silent open-mic" --apply --operator "david@"

This is an ops tool, not a service: keep heavy backend imports inside the
command/I-O functions so the pure helpers stay importable without GCP and
unit-testable.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Firestore batch write limit.
_BATCH_LIMIT = 400

# How many top hourly buckets ``show`` prints.
_TOP_BUCKETS = 5


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
    ``utils.subscription.get_plan_limits``.
    """
    from database import users as users_db
    from utils.subscription import (
        get_default_basic_subscription,
        get_plan_display_name,
        get_plan_limits,
    )

    # get_user_valid_subscription returns None when the stored plan is expired;
    # enforcement treats that user as Basic, so we do the same here.
    subscription = users_db.get_user_valid_subscription(uid)
    if subscription is None:
        subscription = get_default_basic_subscription()
    plan = subscription.plan
    limits = get_plan_limits(plan)
    limit_seconds = limits.transcription_seconds
    # `limit_seconds` is None for unlimited plans (typed catalog representation) and a
    # positive int otherwise. `or None` would also fold a genuine finite 0 into "unlimited",
    # which is the exact ambiguity the catalog retired — so branch on None explicitly.
    return get_plan_display_name(plan), (None if limit_seconds is None else limit_seconds)


def apply_reset(client: Any, uid: str, plan: ResetPlan) -> None:
    """Zero ``transcription_seconds`` on every doc in the reset plan (batched).."""
    if not plan.doc_ids:
        return
    hourly = client.collection("users").document(uid).collection("hourly_usage")
    for chunk_start in range(0, len(plan.doc_ids), _BATCH_LIMIT):
        batch = client.batch()
        for doc_id in plan.doc_ids[chunk_start : chunk_start + _BATCH_LIMIT]:
            batch.set(hourly.document(doc_id), {"transcription_seconds": 0}, merge=True)
        batch.commit()


def write_audit(client: Any, record: AuditRecord) -> str:
    """Persist the audit record to ``admin_audit_log`` and return its doc id."""
    doc_ref = client.collection("admin_audit_log").document()
    doc_ref.set(record.to_dict())
    return doc_ref.id


def update_audit(client: Any, audit_id: str, record: AuditRecord) -> None:
    """Update an existing audit record after the mutation outcome is known."""
    client.collection("admin_audit_log").document(audit_id).set(record.to_dict())


# ---------------------------------------------------------------------------
# Audit payload sanitization — stdout/logs get redacted PII; the Firestore
# record retains the full fields (access-controlled).
# ---------------------------------------------------------------------------


def _sanitized_audit_payload(record: AuditRecord) -> dict[str, Any]:
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
    uid: str, email: Optional[str], plan: str, limit_seconds: Optional[int], usage: MonthlyUsage, month: str
) -> None:
    used = usage.used_seconds
    if limit_seconds is None:
        limit_min_s = "unlimited"
        remaining_s = "unlimited"
        pct_s = "n/a"
    else:
        limit_min_s = f"{seconds_to_minutes(limit_seconds)} min"
        remaining = max(0, limit_seconds - used)
        remaining_s = f"{seconds_to_minutes(remaining)} min ({remaining} s)"
        pct_s = f"{round(100.0 * used / limit_seconds, 1)}%" if limit_seconds else "n/a"
    print(f"uid:           {uid}")
    if email:
        print(f"email:         {email}")
    print(f"plan:          {plan}")
    print(f"month:         {month} (UTC)")
    print(f"used:          {seconds_to_minutes(used)} min ({used} s) across {usage.document_count} hourly bucket(s)")
    print(f"limit:         {limit_min_s}")
    print(f"remaining:     {remaining_s}")
    print(f"used of limit: {pct_s}")
    if usage.top_buckets:
        print("top buckets:")
        for b in usage.top_buckets:
            share = f" ({round(100.0 * b.seconds / used, 1)}%)" if used else ""
            print(f"  {b.doc_id}: {seconds_to_minutes(b.seconds)} min ({b.seconds} s){share}")


def cmd_show(args: argparse.Namespace) -> int:
    uid, email = resolve_uid(uid=args.uid, email=args.email)
    client = _firestore_client()
    now = datetime.now(timezone.utc)
    plan, limit_seconds = resolve_plan_and_limit(uid)
    docs = fetch_monthly_hourly_docs(client, uid, now.year, now.month)
    usage = aggregate_monthly_usage(docs)
    _print_usage(uid, email, plan, limit_seconds, usage, month_label(now))
    return 0


def cmd_reset_month(args: argparse.Namespace) -> int:
    uid, email = resolve_uid(uid=args.uid, email=args.email)
    client = _firestore_client()
    now = datetime.now(timezone.utc)
    plan_name, _limit = resolve_plan_and_limit(uid)
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
    print(f"  operator: {args.operator}")

    record = build_audit_record(
        uid=uid,
        email=email,
        plan=plan_name,
        month=month_label(now),
        reason=args.reason,
        operator=args.operator,
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
        operator=args.operator,
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


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def _add_target_args(p: argparse.ArgumentParser) -> None:
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--uid", help="Firebase Auth uid of the target user.")
    group.add_argument("--email", help="Resolve uid from this email via Firebase Auth.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reset_transcription_usage",
        description="Inspect / reset a user's monthly free-tier transcription (listening) minutes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="Show plan / used / limit / top buckets for the current month (read-only).")
    _add_target_args(p_show)
    p_show.set_defaults(func=cmd_show)

    p_reset = sub.add_parser(
        "reset-month",
        help="Zero current-month transcription_seconds. DRY-RUN by default.",
    )
    _add_target_args(p_reset)
    p_reset.add_argument("--reason", required=True, help="Operator reason string (required, audited).")
    p_reset.add_argument("--apply", action="store_true", help="Commit the reset (default is dry-run).")
    p_reset.add_argument(
        "--operator",
        default=os.getenv("USER", "unknown"),
        help="Operator identity for the audit record (default: $USER).",
    )
    p_reset.set_defaults(func=cmd_reset_month)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
