#!/usr/bin/env python3
# LIFECYCLE: remediation (2026-10 stale-planner incident; retire after step 4 verify)
"""Restore memory_items archived by the stale dev planner (2026-10-19..10-22).

Between 2026-10-19 and the 2026-10-22 18:25Z pause, the dev
``memory-maintenance-hourly`` job ran a stale ``memory-maintenance-job`` image
against the shared prod customer project.  After the gateway ``memory_conflict``
lane was removed, every planner call failed and
``_escalate_to_terminal_review`` settled pending Short-term items as
``route=review`` → ``tier=archive`` with the retry-exhausted rationale, hiding
them from default reads.

Default mode is a read-only dry run: counts only.  It never prints uids,
memory ids, or memory text; at most five redacted structural samples.  Writes
(``--apply`` / ``--revert``) additionally require the exact remediation marker,
an explicit write budget, and the matching GCP operator tier
(``prod-operator`` for ``based-hardware``, ``dev-operator`` for dev):

    source ~/.local/bin/gcp-agent-env.sh ro-prod
    .venv/bin/python -m scripts.restore_stale_planner_archives --project based-hardware
    source ~/.local/bin/gcp-agent-env.sh prod-operator
    .venv/bin/python -m scripts.restore_stale_planner_archives --project based-hardware \
        --apply --marker remediation=stale-planner-2026-10-22 --max-writes 500 \
        --progress-file /tmp/restore_progress.jsonl

Restore re-applies each row as a ``short_term``-visible decision through the
canonical apply ledger (``apply_long_term_patch_firestore``, the same fenced
operator path as the legacy-backfill remediation): expected revision and
content hash, account/source generation and head-commit fences, projection
outbox events, and a ``promotion.remediation`` audit marker that makes the
whole action reversible with ``--revert``.  Restored rows leave the archive
tier, so re-running the tool is naturally idempotent.  TTL and required intake
settle them normally afterwards; nothing is bulk-promoted to long_term.

``memory_items`` has no prod collection-group indexes, so the scan iterates one
user subcollection at a time with a bounded, restartable keyset cursor under
``--max-reads``.  Per-user gate reads (account deletion marker, legal hold,
destructive-operation gate) fail closed: an unavailable authority excludes the
account from any write.  Set ``FIRESTORE_READ_LEDGER=1`` (service label
``restore-stale-planner-archives``) so billed reads also land in the Firestore
read ledger; the tool additionally reports the document reads it used.

Exit codes: 0 success, 1 operational failure (row errors, budget stop,
truncated scan), 2 usage/credential error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud.firestore_v1 import FieldFilter

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.firestore_index_registry import STALE_PLANNER_ARCHIVE_SCAN_QUERY, STALE_PLANNER_RESTORE_REVERT_QUERY
from database.legal_holds import (
    LegalHoldActive,
    LegalHoldAuthorityUnavailable,
    assert_account_deletion_permitted,
    external_write_fence,
)
from database.memory_collections import MemoryCollections
from database.memory_apply_store import apply_long_term_patch_firestore
from database.read_boundary import parse_snapshot_strict
from models.memory_apply import ApplyStatus, MemoryControlState, build_patch_mutation_identity
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer
from utils.log_sanitizer import sanitize
from utils.memory.memory_system import ensure_canonical_apply_control_state

MARKER = "stale-planner-2026-10-22"
MARKER_GATE = f"remediation={MARKER}"
CONSOLIDATION_BY = "canonical_batched_consolidation"
RETRY_EXHAUSTED_RATIONALE_MARKER = "exhausted its bounded retry budget"
DEFAULT_WINDOW_FROM = "2026-10-18T23:00:00+00:00"
DEFAULT_WINDOW_TO = "2026-10-22T18:30:00+00:00"
DEFAULT_MAX_READS = 200_000
USER_BUCKETS = ((1, "1"), (4, "2-4"), (20, "5-20"), (100, "21-100"), (None, ">100"))

PROJECTS = {
    "based-hardware": "prod-operator",
    "based-hardware-dev": "dev-operator",
}


class ReadBudgetExceeded(RuntimeError):
    """The scan hit its documented document-read budget."""


@dataclass
class ReadLedger:
    """Billed-equivalent document reads used by this run (see docs/firestore-read-attribution.md)."""

    budget: int
    used: int = 0
    exhausted: bool = False

    def charge_query(self, documents: int) -> None:
        # Firestore bills one read for an empty query result.
        self.charge_lookups(max(documents, 1))

    def charge_lookups(self, count: int) -> None:
        if self.exhausted:
            raise ReadBudgetExceeded("read budget already exhausted")
        self.used += count
        if self.used > self.budget:
            self.exhausted = True
            raise ReadBudgetExceeded(f"read budget exceeded: {self.used} > {self.budget}")


@dataclass
class RowDecision:
    memory_id: str
    item: MemoryItem
    matched: bool
    exclusion: Optional[str] = None


@dataclass
class UserScan:
    uid: str
    matched: List[MemoryItem] = field(default_factory=list)
    exclusions: Counter = field(default_factory=Counter)
    skipped_reason: Optional[str] = None


@dataclass
class RunReport:
    mode: str
    project: str
    window_from: str
    window_to: str
    users_scanned: int = 0
    users_matched: int = 0
    users_excluded: Counter = field(default_factory=Counter)
    users_errored: int = 0
    rows_matched: int = 0
    row_exclusions: Counter = field(default_factory=Counter)
    matched_per_day: Counter = field(default_factory=Counter)
    per_user_buckets: Dict[str, int] = field(default_factory=dict)
    writes_attempted: int = 0
    writes_committed: int = 0
    writes_idempotent: int = 0
    writes_failed: int = 0
    outbox_events_enqueued: int = 0
    write_budget: Optional[int] = None
    writes_stopped_early: bool = False
    errors: List[str] = field(default_factory=list)
    samples: List[Dict[str, Any]] = field(default_factory=list)
    reads_used: int = 0
    reads_budget: int = 0
    reads_exhausted: bool = False
    scan_truncated: bool = False

    def to_json(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "marker": MARKER,
            "project": self.project,
            "window": {"from": self.window_from, "to": self.window_to},
            "users": {
                "scanned": self.users_scanned,
                "matched": self.users_matched,
                "excluded": dict(sorted(self.users_excluded.items())),
                "errored": self.users_errored,
            },
            "rows": {
                "matched": self.rows_matched,
                "excluded_by_reason": dict(sorted(self.row_exclusions.items())),
            },
            "matched_per_day": dict(sorted(self.matched_per_day.items())),
            "per_user_buckets": self.per_user_buckets,
            "writes": {
                "attempted": self.writes_attempted,
                "committed": self.writes_committed,
                "idempotent_skip": self.writes_idempotent,
                "failed": self.writes_failed,
                "outbox_events_enqueued": self.outbox_events_enqueued,
                "budget": self.write_budget,
                "stopped_early": self.writes_stopped_early,
            },
            "samples": self.samples,
            "reads": {
                "documents": self.reads_used,
                "budget": self.reads_budget,
                "exhausted": self.reads_exhausted,
            },
            "scan_truncated": self.scan_truncated,
            "errors": self.errors[:20],
        }


def _coerce_utc(value: str, flag: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemExit(f"{flag} must include a UTC offset: {value}")
    return parsed.astimezone(timezone.utc)


def _coerce_promotion_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        try:
            return _coerce_utc(value, "promotion.processed_at")
        except (ValueError, SystemExit):
            return None
    return None


def user_skip_reason(uid: str, *, db_client: Any, ledger: ReadLedger) -> Optional[str]:
    """Fail-closed account gates: deletion marker, legal hold, destructive gate."""
    try:
        marker_snapshot = db_client.document(f"account_deletions/{uid}").get()
        ledger.charge_lookups(1)
        marker = marker_snapshot.to_dict() if getattr(marker_snapshot, "exists", False) else None
        status = normalize_account_deletion_status(
            marker_exists=marker is not None,
            raw_status=marker.get("wipe_status") if isinstance(marker, dict) else None,
        )
        if account_deletion_blocks_access(status):
            return "deleted_user"
    except ReadBudgetExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 - authority reads fail closed
        return f"authority_unavailable:{type(exc).__name__}"
    try:
        assert_account_deletion_permitted(uid, firestore_client=db_client)
        ledger.charge_lookups(1)
    except LegalHoldActive:
        return "legal_hold"
    except LegalHoldAuthorityUnavailable:
        return "authority_unavailable:legal_hold"
    except ReadBudgetExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 - authority reads fail closed
        return f"authority_unavailable:{type(exc).__name__}"
    try:
        with external_write_fence(uid, firestore_client=db_client):
            ledger.charge_lookups(2)
    except Exception:  # noqa: BLE001 - any fence failure blocks the account
        return "destructive_gate"
    return None


def _classify_restore_row(item: MemoryItem, *, window_from: datetime, window_to: datetime) -> Optional[str]:
    """Return an exclusion reason, or None when the row is an incident match."""
    promotion = item.promotion or {}
    if promotion.get("processed_by") != CONSOLIDATION_BY:
        return "processed_by_mismatch"
    route = promotion.get("route")
    rationale = str(promotion.get("rationale") or "")
    if route != "review":
        if route != "archive" or RETRY_EXHAUSTED_RATIONALE_MARKER not in rationale:
            return "route_not_incident"
    if promotion.get("user_review") is not None:
        return "user_reviewed"
    if (promotion.get("remediation") or {}).get("marker") == MARKER:
        return "already_marked"
    processed_at = _coerce_promotion_datetime(promotion.get("processed_at"))
    if processed_at is None or not (window_from <= processed_at <= window_to):
        return "processed_at_out_of_window"
    if item.updated_at is not None and item.updated_at > processed_at:
        return "edited_after_processing"
    return None


def _scan_user_rows(
    uid: str,
    *,
    db_client: Any,
    ledger: ReadLedger,
    window_from: datetime,
    window_to: datetime,
    page_size: int,
) -> UserScan:
    scan = UserScan(uid=uid)
    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    cursor: Optional[Dict[str, Any]] = None
    while True:
        query = (
            STALE_PLANNER_ARCHIVE_SCAN_QUERY.build(
                collection,
                {
                    "tier": MemoryLayer.archive.value,
                    "status": MemoryItemStatus.active.value,
                    "processed_from": window_from,
                    "processed_to": window_to,
                },
                field_filter_factory=FieldFilter,
            )
            .order_by("promotion.processed_at")
            .order_by("memory_id")
            .limit(page_size)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        snapshots = list(query.stream())
        ledger.charge_query(len(snapshots))
        if not snapshots:
            break
        for snapshot in snapshots:
            try:
                item = parse_snapshot_strict(MemoryItem, snapshot)
            except Exception:  # noqa: BLE001 - corrupt rows are counted, never fatal
                scan.exclusions["unparseable_row"] += 1
                continue
            exclusion = _classify_restore_row(item, window_from=window_from, window_to=window_to)
            if exclusion is not None:
                scan.exclusions[exclusion] += 1
            else:
                scan.matched.append(item)
        last = snapshots[-1].to_dict() or {}
        processed_at = _coerce_promotion_datetime((last.get("promotion") or {}).get("processed_at"))
        if processed_at is None or len(snapshots) < page_size:
            break
        cursor = {"promotion.processed_at": processed_at, "memory_id": last.get("memory_id")}
    return scan


def _scan_revert_rows(
    uid: str,
    *,
    db_client: Any,
    ledger: ReadLedger,
    page_size: int,
) -> UserScan:
    scan = UserScan(uid=uid)
    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    cursor: Optional[Dict[str, Any]] = None
    while True:
        query = (
            STALE_PLANNER_RESTORE_REVERT_QUERY.build(
                collection,
                {
                    "tier": MemoryLayer.short_term.value,
                    "status": MemoryItemStatus.active.value,
                    "marker": MARKER,
                },
                field_filter_factory=FieldFilter,
            )
            .order_by("memory_id")
            .limit(page_size)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        snapshots = list(query.stream())
        ledger.charge_query(len(snapshots))
        if not snapshots:
            break
        for snapshot in snapshots:
            try:
                item = parse_snapshot_strict(MemoryItem, snapshot)
            except Exception:  # noqa: BLE001 - corrupt rows are counted, never fatal
                scan.exclusions["unparseable_row"] += 1
                continue
            remediation = (item.promotion or {}).get("remediation") or {}
            if remediation.get("marker") != MARKER or remediation.get("reverted_at") is not None:
                scan.exclusions["marker_stale"] += 1
                continue
            scan.matched.append(item)
        if len(snapshots) < page_size:
            break
        last = snapshots[-1].to_dict() or {}
        cursor = {"memory_id": last.get("memory_id")}
    return scan


def _structural_sample(item: MemoryItem) -> Dict[str, Any]:
    """Redacted shape: no uid, no memory id, no content."""
    promotion = item.promotion or {}
    processed_at = _coerce_promotion_datetime(promotion.get("processed_at"))
    captured_to_processed_hours = (
        round((processed_at - item.captured_at).total_seconds() / 3600, 1)
        if processed_at is not None and item.captured_at is not None
        else None
    )
    return {
        "route": promotion.get("route"),
        "reconciliation": promotion.get("reconciliation"),
        "processing_status": promotion.get("processing_status"),
        "confidence": promotion.get("confidence"),
        "evidence_count": len(item.evidence or []),
        "sensitivity_label_count": len(item.sensitivity_labels or []),
        "user_asserted": bool(item.user_asserted),
        "captured_to_processed_hours": captured_to_processed_hours,
    }


def _tier_patch(
    item: MemoryItem,
    *,
    control: MemoryControlState,
    target_tier: MemoryLayer,
    action: str,
    run_id: str,
    now: datetime,
) -> tuple[Dict[str, Any], MemoryOperation, str]:
    """One archive<->short_term tier transition through the canonical apply ledger.

    Mirrors the sanctioned operator remediation in
    ``utils/memory/legacy_backfill.py``: the idempotency key, expected revision
    and content hash, generation/head-commit fences, and promotion audit marker
    all travel through ``apply_long_term_patch_firestore`` so the write is
    journalled in ``memory_commits`` and projects through the outbox.
    """
    evidence_ids = [evidence.evidence_id for evidence in item.evidence]
    logical_payload: Dict[str, Any] = {
        "decision": DurablePatchDecision.update.value,
        "target_memory_id": item.memory_id,
        "result_status": LifecycleState.active.value,
        "target_tier": target_tier.value,
    }
    idempotency_key = deterministic_contract_id(
        f"stale-planner-{action}",
        {
            "uid": item.uid,
            "memory_id": item.memory_id,
            "item_revision": item.item_revision,
            "content_hash": item.content_hash,
            "marker": MARKER,
        },
    )
    promotion_audit = dict(item.promotion or {})
    remediation = dict(promotion_audit.get("remediation") or {})
    remediation.update(
        {
            "marker": MARKER,
            "action": action,
            "run_id": run_id,
            "previous_tier": item.tier.value,
        }
    )
    if action == "restore":
        remediation["restored_at"] = now
    else:
        remediation["reverted_at"] = now
    promotion_audit["remediation"] = remediation
    patch_payload: Dict[str, Any] = {
        "patch_id": f"patch_stale_planner_{action}_{idempotency_key[:20]}",
        "packet_id": f"stale_planner_{action}:{item.memory_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        **logical_payload,
        "evidence_ids": evidence_ids,
        "expected_item_revision": item.item_revision,
        "expected_content_hash": item.content_hash,
        "promotion_audit": promotion_audit,
    }
    mutation_identity = build_patch_mutation_identity(patch_payload)
    patch_payload["mutation_metadata"] = mutation_identity
    logical_payload["mutation_metadata"] = mutation_identity
    operation = MemoryOperation.new(
        uid=item.uid,
        operation_type=MemoryOperationType.archive_transition,
        source_packet_id=f"stale_planner_{action}:{item.memory_id}:r{item.item_revision}",
        target_memory_id=item.memory_id,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    return patch_payload, operation, idempotency_key


def _apply_row(
    item: MemoryItem,
    *,
    target_tier: MemoryLayer,
    action: str,
    run_id: str,
    now: datetime,
    db_client: Any,
) -> tuple[str, int]:
    """Return (outcome, outbox_events). Raises on non-retryable failure."""
    control = ensure_canonical_apply_control_state(item.uid, db_client=db_client)
    result = None
    for _attempt in range(3):
        patch_payload, operation, _key = _tier_patch(
            item,
            control=control,
            target_tier=target_tier,
            action=action,
            run_id=run_id,
            now=now,
        )
        result = apply_long_term_patch_firestore(
            uid=item.uid,
            operation_id=operation.operation_id,
            patch_payload=patch_payload,
            proposed_operation=operation,
            db_client=db_client,
        )
        control = result.control_state
        if result.status != ApplyStatus.retryable_head_mismatch:
            break
    assert result is not None
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"apply status {result.status}: {result.reason}")
    settled = result.memory_items[0] if result.memory_items else None
    if settled is None or settled.tier != target_tier or settled.status != MemoryItemStatus.active:
        raise RuntimeError("tier transition did not persist the expected target state")
    outcome = "committed" if result.status == ApplyStatus.committed else "idempotent_skip"
    return outcome, len(result.outbox_events or [])


def _bucket_label(count: int) -> str:
    for bound, label in USER_BUCKETS:
        if bound is not None and count <= bound:
            return label
    return ">100"


def _iter_user_ids(
    *,
    db_client: Any,
    uid: Optional[str],
    users_from: Optional[Path],
    page_size: int,
    ledger: ReadLedger,
) -> Iterable[str]:
    if uid is not None:
        yield uid
        return
    if users_from is not None:
        for line in users_from.read_text(encoding="utf-8").splitlines():
            token = line.strip()
            if token and not token.startswith("#"):
                yield token
        return
    cursor_snapshot = None
    while True:
        query = db_client.collection("users").order_by("__name__").limit(page_size)
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        snapshots = list(query.stream())
        ledger.charge_query(len(snapshots))
        if not snapshots:
            break
        for snapshot in snapshots:
            yield snapshot.id
        if len(snapshots) < page_size:
            break
        cursor_snapshot = snapshots[-1]


def run(
    *,
    db_client: Any,
    mode: str,
    project: str,
    window_from: datetime,
    window_to: datetime,
    uid: Optional[str],
    users_from: Optional[Path],
    page_size: int,
    max_reads: int,
    max_writes: Optional[int],
    run_id: str,
    now: datetime,
    progress_file: Optional[Path] = None,
    sample_limit: int = 5,
) -> RunReport:
    report = RunReport(
        mode=mode,
        project=project,
        window_from=window_from.isoformat(),
        window_to=window_to.isoformat(),
        write_budget=max_writes if mode != "dry-run" else None,
        reads_budget=max_reads,
    )
    ledger = ReadLedger(budget=max_reads)
    target_tier = MemoryLayer.short_term if mode == "apply" else MemoryLayer.archive
    action = "restore" if mode == "apply" else "revert"
    progress_handle = progress_file.open("a", encoding="utf-8") if progress_file is not None else None
    user_match_counts: List[int] = []
    try:
        for user_id in _iter_user_ids(
            db_client=db_client, uid=uid, users_from=users_from, page_size=page_size, ledger=ledger
        ):
            if report.writes_stopped_early:
                report.scan_truncated = True
                break
            try:
                skip = user_skip_reason(user_id, db_client=db_client, ledger=ledger)
            except ReadBudgetExceeded:
                report.scan_truncated = True
                break
            if skip is not None:
                report.users_excluded[skip] += 1
                continue
            try:
                if mode == "revert":
                    scan = _scan_revert_rows(user_id, db_client=db_client, ledger=ledger, page_size=page_size)
                else:
                    scan = _scan_user_rows(
                        user_id,
                        db_client=db_client,
                        ledger=ledger,
                        window_from=window_from,
                        window_to=window_to,
                        page_size=page_size,
                    )
            except ReadBudgetExceeded:
                report.scan_truncated = True
                break
            report.users_scanned += 1
            report.row_exclusions.update(scan.exclusions)
            if not scan.matched:
                continue
            report.users_matched += 1
            report.rows_matched += len(scan.matched)
            user_match_counts.append(len(scan.matched))
            for item in scan.matched:
                processed_at = _coerce_promotion_datetime((item.promotion or {}).get("processed_at"))
                if mode != "revert" and processed_at is not None:
                    report.matched_per_day[processed_at.date().isoformat()] += 1
                if len(report.samples) < sample_limit:
                    report.samples.append(_structural_sample(item))
            if mode == "dry-run":
                continue
            applied_for_user = 0
            for item in scan.matched:
                if max_writes is not None and report.writes_committed + report.writes_idempotent >= max_writes:
                    report.writes_stopped_early = True
                    break
                report.writes_attempted += 1
                try:
                    outcome, events = _apply_row(
                        item,
                        target_tier=target_tier,
                        action=action,
                        run_id=run_id,
                        now=now,
                        db_client=db_client,
                    )
                except Exception as exc:  # noqa: BLE001 - one row never aborts the run
                    report.writes_failed += 1
                    report.errors.append(sanitize(str(exc))[:300])
                    continue
                if outcome == "committed":
                    report.writes_committed += 1
                else:
                    report.writes_idempotent += 1
                report.outbox_events_enqueued += events
                applied_for_user += 1
            if progress_handle is not None:
                progress_handle.write(
                    json.dumps(
                        {
                            "ts": now.isoformat(),
                            "uid": user_id,
                            "matched": len(scan.matched),
                            "applied": applied_for_user,
                        }
                    )
                    + "\n"
                )
                progress_handle.flush()
            if report.writes_stopped_early:
                report.scan_truncated = True
                break
    finally:
        if progress_handle is not None:
            progress_handle.close()
    bucket_counter = Counter(_bucket_label(count) for count in user_match_counts)
    report.per_user_buckets = {label: bucket_counter.get(label, 0) for _, label in USER_BUCKETS}
    report.reads_used = ledger.used
    report.reads_exhausted = ledger.exhausted
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", choices=sorted(PROJECTS), default="based-hardware")
    parser.add_argument("--from-iso", default=DEFAULT_WINDOW_FROM, help="window start (UTC, default %(default)s)")
    parser.add_argument("--to-iso", default=DEFAULT_WINDOW_TO, help="window end (UTC, default %(default)s)")
    parser.add_argument("--uid", default=None, help="restrict to one account (canary)")
    parser.add_argument("--users-from", type=Path, default=None, help="file with one uid per line")
    parser.add_argument("--page-size", type=int, default=300)
    parser.add_argument("--max-reads", type=int, default=DEFAULT_MAX_READS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="restore matched rows to short_term (requires gates)")
    mode.add_argument("--revert", action="store_true", help="re-archive rows carrying the marker (requires gates)")
    parser.add_argument(
        "--marker",
        default=None,
        help=f"required with --apply/--revert; must be exactly '{MARKER_GATE}'",
    )
    parser.add_argument("--max-writes", type=int, default=None, help="required with --apply/--revert")
    parser.add_argument("--progress-file", type=Path, default=None, help="JSONL per-user progress for resume")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    mode = "apply" if args.apply else "revert" if args.revert else "dry-run"
    window_from = _coerce_utc(args.from_iso, "--from-iso")
    window_to = _coerce_utc(args.to_iso, "--to-iso")
    if window_from >= window_to:
        print("--from-iso must be before --to-iso", file=sys.stderr)
        return 2
    if mode != "dry-run":
        if args.marker != MARKER_GATE:
            print(f"--{mode} requires --marker '{MARKER_GATE}'", file=sys.stderr)
            return 2
        if args.max_writes is None or args.max_writes <= 0:
            print(f"--{mode} requires a positive --max-writes budget", file=sys.stderr)
            return 2
        required_tier = PROJECTS[args.project]
        if os.environ.get("GCP_AGENT_TIER") != required_tier or not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            print("Select the matching GCP operator tier before writing.", file=sys.stderr)
            return 2
        if not args.uid and not args.users_from and required_tier == "prod-operator" and args.max_writes > 1:
            print("fleet writes on prod start with --uid (canary) or --users-from", file=sys.stderr)
            return 2

    from google.cloud import firestore

    db_client = firestore.Client(project=args.project)
    now = datetime.now(timezone.utc)
    run_id = f"stale_planner_{mode}_{now.strftime('%Y%m%dT%H%M%SZ')}"
    report = run(
        db_client=db_client,
        mode=mode,
        project=args.project,
        window_from=window_from,
        window_to=window_to,
        uid=args.uid,
        users_from=args.users_from,
        page_size=args.page_size,
        max_reads=args.max_reads,
        max_writes=args.max_writes,
        run_id=run_id,
        now=now,
        progress_file=args.progress_file,
    )
    print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    failed = bool(report.errors) or report.writes_failed > 0 or report.users_errored > 0
    stopped = report.writes_stopped_early or report.scan_truncated or report.reads_exhausted
    return 1 if (failed or stopped) else 0


if __name__ == "__main__":
    sys.exit(main())
