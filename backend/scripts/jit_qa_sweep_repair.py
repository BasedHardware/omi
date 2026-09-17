#!/usr/bin/env python3
"""Explicit repair operator for tombstoned JIT QA daily-sweep model invocations.

A sweep model invocation that ends ``pending``, ``indeterminate``, or
``payload_expired`` is closed forever by design: its provider outcome cannot be
proven, so an implicit retry could charge the same logical invocation twice.
This command is the sanctioned operator path.  It proves what the durable
gateway accounting recorded for the tombstoned window, then writes the one
explicit repair receipt that reopens exactly one further bounded attempt.

The command is fail-closed to the isolated QA plane: it refuses to run unless
the environment selects the named QA database, the QA auth fence, and the
fixed QA UID allowlist.  It never prints or stores model, transcript, or
memory content — only resource identities and content-free counters.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.memory.daily_memory_sweep import (  # noqa: E402
    MODEL_INVOCATION_FENCE_COLLECTION,
    MODEL_INVOCATION_LEASE,
    MODEL_INVOCATION_REPAIR_MARGIN,
    MODEL_INVOCATION_PATH,
    MODEL_INVOCATION_REPAIR_PATH,
    QA_SWEEP_UID,
    repair_daily_sweep_model_invocation,
)

QA_SWEEP_PROJECT = "based-hardware-dev"
QA_SWEEP_DATABASE = "jit-qa"
QA_INVOCATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
GATEWAY_ATTEMPT_COLLECTION = "llm_gateway_attempts"
GATEWAY_ATTEMPT_PAGE_LIMIT = 50
EVIDENCE_WINDOW_MARGIN = MODEL_INVOCATION_REPAIR_MARGIN
GATEWAY_ATTEMPT_MAX_PAGES = 1000
TOMBSTONED_STATES = ("pending", "indeterminate", "payload_expired", "pre_dispatch_exhausted")


class JITQASweepRepairError(RuntimeError):
    """A QA sweep repair precondition or proof assertion failed."""


def validate_repair_environment(environ: Mapping[str, str] | None = None) -> None:
    """Require the closed QA-plane environment before any read or write."""

    env = environ if environ is not None else os.environ
    required = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": QA_SWEEP_PROJECT,
        "FIRESTORE_DATABASE_ID": QA_SWEEP_DATABASE,
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": QA_SWEEP_UID,
    }
    for name, expected in required.items():
        if env.get(name, "").strip().casefold() != expected.casefold():
            raise JITQASweepRepairError(f"QA sweep repair requires {name}={expected!r}")


def validate_invocation_id(invocation_id: str) -> str:
    normalized = (invocation_id or "").strip()
    if not QA_INVOCATION_ID_RE.fullmatch(normalized):
        raise JITQASweepRepairError("invocation id must match [a-z0-9][a-z0-9_-]{0,127}")
    return normalized


def _client() -> Any:
    return firestore.Client(project=QA_SWEEP_PROJECT, database=QA_SWEEP_DATABASE)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def collect_provider_outcome_evidence(
    db_client: Any,
    *,
    uid: str,
    claimed_at: datetime,
    now: datetime,
) -> dict[str, Any]:
    """Read the durable gateway accounting window for one invocation claim.

    Only content-free fields are kept: request identity, outcome, token totals,
    micro-USD cost, and the owning JIT run id.  A missing accounting row is
    reported as ``no_recorded_attempt`` — never as proof that the provider was
    not charged.
    """

    if claimed_at.tzinfo is None or now <= claimed_at + MODEL_INVOCATION_LEASE + EVIDENCE_WINDOW_MARGIN:
        raise JITQASweepRepairError("QA sweep repair requires an expired invocation lease plus margin")
    window_start = claimed_at - EVIDENCE_WINDOW_MARGIN
    window_end = now
    day = window_start.date()
    attempts: list[dict[str, Any]] = []
    jit_run_id = ""
    while day <= window_end.date():
        query = (
            db_client.collection(GATEWAY_ATTEMPT_COLLECTION)
            .where(filter=FieldFilter("date", "==", day.isoformat()))
            .order_by("__name__")
        )
        cursor = None
        for _page in range(GATEWAY_ATTEMPT_MAX_PAGES):
            page_query = query.start_after(cursor) if cursor is not None else query
            try:
                page = list(page_query.limit(GATEWAY_ATTEMPT_PAGE_LIMIT).stream())
            except Exception as exc:
                raise JITQASweepRepairError("QA sweep accounting read may be incomplete") from exc
            for snapshot in page:
                raw = snapshot.to_dict() or {}
                if raw.get("user_uid") != uid or raw.get("feature") != "memories":
                    continue
                occurred_at = _parse_timestamp(raw.get("occurred_at"))
                if occurred_at is None:
                    raise JITQASweepRepairError("QA sweep accounting read has an unbounded attempt timestamp")
                if occurred_at < window_start or occurred_at > window_end:
                    continue
                attempts.append(
                    {
                        "request_id": raw.get("request_id"),
                        "outcome": raw.get("outcome"),
                        "total_tokens": raw.get("total_tokens"),
                        "estimated_cost_micro_usd": raw.get("estimated_cost_micro_usd"),
                        "occurred_at": occurred_at.isoformat(),
                        "jit_run_id": raw.get("jit_run_id"),
                    }
                )
                if len(attempts) > 4:
                    raise JITQASweepRepairError("QA sweep accounting exceeds the bounded provider attempt page")
            if len(page) < GATEWAY_ATTEMPT_PAGE_LIMIT:
                break
            if cursor is not None and page[-1].id <= cursor.id:
                raise JITQASweepRepairError("QA sweep accounting pagination did not advance; read may be incomplete")
            cursor = page[-1]
        else:
            raise JITQASweepRepairError("QA sweep accounting read may be incomplete: page limit reached")
        day += timedelta(days=1)
    attempts.sort(key=lambda item: str(item.get("occurred_at") or ""))
    for attempt in attempts:
        run_id = str(attempt.get("jit_run_id") or "").strip()
        if run_id:
            jit_run_id = run_id
            break
    if not attempts:
        return {
            "provider_outcome": "no_recorded_attempt",
            "attempts": [],
            "accounting_read_complete": True,
            "uid": uid,
            "feature": "memories",
            "claimed_at": claimed_at.isoformat(),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        }
    if not jit_run_id:
        raise JITQASweepRepairError(
            "QA sweep repair could not join the tombstoned claim to a sweep run id in gateway accounting"
        )
    return {"provider_outcome": "recorded_attempt", "jit_run_id": jit_run_id, "attempts": attempts}


def list_tombstones(db_client: Any, *, uid: str = QA_SWEEP_UID) -> list[dict[str, Any]]:
    """Enumerate tombstoned invocations with their repair state, content-free."""

    invocations = db_client.collection(f"users/{uid}/{MODEL_INVOCATION_PATH}").limit(200).stream()
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for snapshot in invocations:
        payload = snapshot.to_dict() or {}
        state = payload.get("state")
        if state not in TOMBSTONED_STATES:
            continue
        invocation_id = str(snapshot.id)
        lease_expires_at = _parse_timestamp(payload.get("lease_expires_at"))
        repair_snapshot = db_client.document(f"users/{uid}/{MODEL_INVOCATION_REPAIR_PATH}/{invocation_id}").get()
        repair_payload = repair_snapshot.to_dict() if getattr(repair_snapshot, "exists", False) else None
        rows.append(
            {
                "invocation_id": invocation_id,
                "window_id": payload.get("window_id"),
                "state": state,
                "pre_dispatch_releases": payload.get("pre_dispatch_releases", 0),
                "failure_reason": payload.get("failure_reason"),
                "blocked_reason": payload.get("blocked_reason"),
                "claimed_at": str(payload.get("claimed_at") or ""),
                "lease_expired": lease_expires_at is None or lease_expires_at <= now,
                "repair_receipt": bool(repair_payload),
                "repair_consumed": bool(repair_payload and repair_payload.get("consumed")),
            }
        )
    rows.sort(key=lambda row: row["invocation_id"])
    return rows


def _claim_time(db_client: Any, *, uid: str, invocation_id: str) -> datetime:
    """Read the authoritative claim time from the durable fence."""

    fence_snapshot = db_client.document(f"{MODEL_INVOCATION_FENCE_COLLECTION}/{invocation_id}").get()
    fence_payload = fence_snapshot.to_dict() if getattr(fence_snapshot, "exists", False) else None
    claimed_at = _parse_timestamp((fence_payload or {}).get("claimed_at"))
    if claimed_at is None:
        raise JITQASweepRepairError("tombstoned invocation does not record its claim time")
    return claimed_at


def repair_tombstone(
    db_client: Any,
    *,
    invocation_id: str,
    repair_authority: str,
    uid: str = QA_SWEEP_UID,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Prove the provider outcome and write the single repair receipt."""

    invocation_id = validate_invocation_id(invocation_id)
    repaired_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    claimed_at = _claim_time(db_client, uid=uid, invocation_id=invocation_id)
    evidence = collect_provider_outcome_evidence(
        db_client,
        uid=uid,
        claimed_at=claimed_at,
        now=repaired_now,
    )
    return repair_daily_sweep_model_invocation(
        db_client,
        uid=uid,
        invocation_id=invocation_id,
        provider_outcome_evidence=evidence,
        repair_authority=repair_authority,
        now=repaired_now,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", default=QA_SWEEP_UID)
    parser.add_argument("--authority", help="bounded operator identity recorded on the repair receipt")
    parser.add_argument("--invocation-id")
    parser.add_argument("command", choices=("list", "repair"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_repair_environment()
        if args.uid != QA_SWEEP_UID:
            raise JITQASweepRepairError("QA sweep repair requires the fixed QA UID")
        db_client = _client()
        if args.command == "list":
            print(json.dumps(list_tombstones(db_client, uid=args.uid), default=str, sort_keys=True))
            return 0
        if not args.authority:
            raise JITQASweepRepairError("repair requires --authority")
        if not args.invocation_id:
            raise JITQASweepRepairError("repair requires --invocation-id")
        receipt = repair_tombstone(
            db_client,
            invocation_id=args.invocation_id,
            repair_authority=args.authority,
            uid=args.uid,
        )
        print(json.dumps(receipt, default=str, sort_keys=True))
        return 0
    except (JITQASweepRepairError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
