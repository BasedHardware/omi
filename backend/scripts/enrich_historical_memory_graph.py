"""Run one bounded, evidence-fenced historical canonical graph enrichment page.

Default mode is dry-run.  ``--apply`` requires exact UID confirmation and is
limited to 25 items so expansion is an explicit operational choice.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore  # noqa: E402
from google.cloud.firestore_v1 import FieldFilter  # noqa: E402
from google.oauth2 import service_account  # noqa: E402

from database.memory_apply_store import apply_long_term_patch_firestore  # noqa: E402
from database.memory_collections import MemoryCollections  # noqa: E402
from database.firestore_index_registry import CANONICAL_MEMORY_ATLAS_READ_QUERY  # noqa: E402
from models.memory_apply import ApplyStatus, MemoryControlState  # noqa: E402
from models.memory_promotion import PromotionGraphPlan  # noqa: E402
from models.product_memory import MemoryItem  # noqa: E402
from utils.llm.clients import get_llm  # noqa: E402
from utils.memory.graph_enrichment import prepare_graph_enrichment  # noqa: E402
from utils.memory.historical_graph_enrichment import (  # noqa: E402
    HISTORICAL_GRAPH_PLANNER_VERSION,
    plan_historical_graph_enrichment,
)

MAX_PAGE_SIZE = 25
MAX_STRUCTURED_SCAN_SIZE = 1250
HISTORICAL_GRAPH_PLANNER_TIMEOUT_SECONDS = 20.0


class HistoricalGraphPlannerTimeout(TimeoutError):
    """The planner did not return within its process-level deadline."""


@dataclass(frozen=True)
class HistoricalGraphEnrichmentCursor:
    """Server-owned progress fence for one user's rotating graph sweep."""

    generation: int = 0
    resume_after_updated_at: datetime | None = None
    resume_after_memory_id: str | None = None


@dataclass(frozen=True)
class HistoricalGraphCandidatePage:
    """One keyset page plus the cursor boundary for each examined item."""

    items: list[MemoryItem]
    last_scanned: MemoryItem | None
    exhausted: bool


class HistoricalGraphCursorStore(Protocol):
    def read(
        self, uid: str, *, control: MemoryControlState, replan_existing: bool
    ) -> HistoricalGraphEnrichmentCursor: ...

    def advance(
        self,
        uid: str,
        *,
        control: MemoryControlState,
        replan_existing: bool,
        expected_generation: int,
        resume_after: MemoryItem | None,
    ) -> bool: ...


def _cursor_mode_matches(payload: dict[str, Any], *, control: MemoryControlState, replan_existing: bool) -> bool:
    return (
        payload.get("account_generation") == control.account_generation
        and payload.get("planner_version") == HISTORICAL_GRAPH_PLANNER_VERSION
        and payload.get("replan_existing") is replan_existing
    )


class FirestoreHistoricalGraphCursorStore:
    """Persist a CAS-fenced per-user keyset cursor under ``memory_control``."""

    def __init__(self, db_client: Any):
        self._db_client = db_client

    def _ref(self, uid: str) -> Any:
        return self._db_client.document(MemoryCollections(uid=uid).historical_graph_enrichment_cursor)

    def read(self, uid: str, *, control: MemoryControlState, replan_existing: bool) -> HistoricalGraphEnrichmentCursor:
        snapshot = self._ref(uid).get()
        if not getattr(snapshot, "exists", False):
            return HistoricalGraphEnrichmentCursor()
        payload = snapshot.to_dict() or {}
        generation = int(payload.get("generation", 0))
        if not _cursor_mode_matches(payload, control=control, replan_existing=replan_existing):
            return HistoricalGraphEnrichmentCursor(generation=generation)
        updated_at = payload.get("resume_after_updated_at")
        memory_id = payload.get("resume_after_memory_id")
        if not isinstance(updated_at, datetime) or not isinstance(memory_id, str):
            return HistoricalGraphEnrichmentCursor(generation=generation)
        return HistoricalGraphEnrichmentCursor(generation, updated_at, memory_id)

    def advance(
        self,
        uid: str,
        *,
        control: MemoryControlState,
        replan_existing: bool,
        expected_generation: int,
        resume_after: MemoryItem | None,
    ) -> bool:
        ref = self._ref(uid)
        transaction = self._db_client.transaction()
        transactional = firestore.transactional(_advance_historical_graph_cursor_txn)
        return transactional(
            transaction,
            ref,
            control,
            replan_existing,
            expected_generation,
            resume_after,
            datetime.now(timezone.utc),
        )


def _advance_historical_graph_cursor_txn(
    transaction: Any,
    ref: Any,
    control: MemoryControlState,
    replan_existing: bool,
    expected_generation: int,
    resume_after: MemoryItem | None,
    now: datetime,
) -> bool:
    """Advance only the reader generation that examined this page.

    A losing writer cannot overwrite a newer boundary. ``resume_after=None`` is
    the durable tail-wrap marker: the next invocation starts from the head.
    """
    snapshot = ref.get(transaction=transaction)
    payload = (snapshot.to_dict() or {}) if getattr(snapshot, "exists", False) else {}
    if int(payload.get("generation", 0)) != expected_generation:
        return False
    update: dict[str, Any] = {
        "account_generation": control.account_generation,
        "planner_version": HISTORICAL_GRAPH_PLANNER_VERSION,
        "replan_existing": replan_existing,
        "generation": expected_generation + 1,
        "updated_at": now,
        "resume_after_updated_at": resume_after.updated_at if resume_after is not None else None,
        "resume_after_memory_id": resume_after.memory_id if resume_after is not None else None,
    }
    transaction.set(ref, update)
    return True


def _plan_with_deadline(*, item: MemoryItem, control: MemoryControlState, llm: Any):
    """Enforce the planner deadline even if a provider client ignores its timeout.

    Cloud Run runs this synchronous script in its main thread on POSIX.  The
    signal interrupts a stuck socket/read and is handled by the existing
    per-item error path, so the page can continue to another candidate.
    """
    previous_handler = signal.getsignal(signal.SIGALRM)

    def _expired(_signum, _frame):
        raise HistoricalGraphPlannerTimeout("historical graph planner deadline exceeded")

    signal.signal(signal.SIGALRM, _expired)
    signal.setitimer(signal.ITIMER_REAL, HISTORICAL_GRAPH_PLANNER_TIMEOUT_SECONDS)
    try:
        return plan_historical_graph_enrichment(item=item, control=control, llm=llm)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or apply one historical canonical graph enrichment page")
    parser.add_argument("--uid", required=True, help="Target canonical user UID")
    parser.add_argument("--firestore-project", required=True, help="Explicit Firestore data-plane project")
    parser.add_argument("--limit", type=int, default=1, help=f"Items to inspect (1-{MAX_PAGE_SIZE})")
    parser.add_argument(
        "--scan-limit",
        type=int,
        help=(
            f"Candidate rows to read before filtering (1-{MAX_STRUCTURED_SCAN_SIZE}); "
            "does not increase the apply bound"
        ),
    )
    parser.add_argument("--apply-limit", type=int, default=1, help=f"Ready plans to commit (1-{MAX_PAGE_SIZE})")
    parser.add_argument(
        "--structured-only",
        action="store_true",
        help="Use only pre-existing complete canonical graph fields; never call an LLM",
    )
    parser.add_argument(
        "--replan-existing",
        action="store_true",
        help="Replace only prior fenced graph-enrichment plans with the current planner version",
    )
    parser.add_argument("--apply", action="store_true", help="Commit plans through the canonical apply ledger")
    parser.add_argument("--confirm-uid", help="Required exact UID acknowledgement with --apply")
    return parser.parse_args()


def _control(uid: str, *, db_client: Any) -> MemoryControlState:
    snapshot = db_client.document(MemoryCollections(uid=uid).memory_apply_control_state).get()
    if not snapshot.exists:
        raise RuntimeError("missing canonical memory apply control state")
    payload = snapshot.to_dict() or {}
    return MemoryControlState(**payload)


def _firestore_client(*, project: str) -> Any:
    """Use an injected runtime service identity when present, else local ADC."""
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON", "").strip()
    if not service_account_json:
        return firestore.Client(project=project)
    credentials = service_account.Credentials.from_service_account_info(json.loads(service_account_json))
    return firestore.Client(project=project, credentials=credentials)


def _is_replan_candidate(item: MemoryItem) -> bool:
    promotion = item.promotion or {}
    return (
        item.graph_ready
        and bool(promotion.get("graph_enrichment"))
        and promotion.get("graph_enrichment_planner_version") != HISTORICAL_GRAPH_PLANNER_VERSION
    )


def _candidate_page(
    uid: str,
    *,
    control: MemoryControlState,
    cursor: HistoricalGraphEnrichmentCursor,
    limit: int,
    db_client: Any,
    replan_existing: bool = False,
) -> HistoricalGraphCandidatePage:
    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    # Historical canonical items predate graph_ready and omit the field rather
    # than storing false. Firestore equality filters exclude absent fields, so
    # use the canonical-atlas serving query and keep only absent-or-false rows
    # after decoding them.
    query = CANONICAL_MEMORY_ATLAS_READ_QUERY.build(
        collection,
        {
            "account_generation": control.account_generation,
            "tier": "long_term",
            "status": "active",
            "processing_state": "processed",
        },
        field_filter_factory=FieldFilter,
    )
    query = query.order_by("updated_at", direction=firestore.Query.DESCENDING).order_by(
        "__name__", direction=firestore.Query.DESCENDING
    )
    if cursor.resume_after_updated_at is not None and cursor.resume_after_memory_id is not None:
        query = query.start_after([cursor.resume_after_updated_at, collection.document(cursor.resume_after_memory_id)])
    snapshots = list(query.limit(limit).stream())
    scanned_items = [MemoryItem(**(snapshot.to_dict() or {})) for snapshot in snapshots]
    items = list(scanned_items)
    if replan_existing:
        items = [item for item in items if _is_replan_candidate(item)]
    else:
        items = [item for item in items if not item.graph_ready]
    return HistoricalGraphCandidatePage(
        items=items,
        last_scanned=scanned_items[-1] if scanned_items else None,
        exhausted=len(snapshots) < limit,
    )


def _candidates(
    uid: str, *, control: MemoryControlState, limit: int, db_client: Any, replan_existing: bool = False
) -> list[MemoryItem]:
    """Compatibility helper for callers that do not persist historical progress."""
    return _candidate_page(
        uid,
        control=control,
        cursor=HistoricalGraphEnrichmentCursor(),
        limit=limit,
        db_client=db_client,
        replan_existing=replan_existing,
    ).items


def _structured_plan(item: MemoryItem, control: MemoryControlState):
    if not (item.subject_entity_id and item.predicate and item.arguments):
        return None
    return prepare_graph_enrichment(
        item=item,
        plan=PromotionGraphPlan(
            subject_entity_id=item.subject_entity_id,
            predicate=item.predicate,
            arguments=item.arguments,
        ),
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        expected_item_revision=item.item_revision,
        expected_content_hash=item.content_hash,
        expected_evidence_ids=[evidence.evidence_id for evidence in item.evidence],
        observed_head_commit_id=control.head_commit_id,
    )


def run_enrichment(
    *,
    uid: str,
    firestore_project: str,
    limit: int,
    apply: bool,
    confirm_uid: str | None,
    structured_only: bool,
    apply_limit: int = 1,
    scan_limit: int | None = None,
    replan_existing: bool = False,
    db_client: Any | None = None,
    llm: Any | None = None,
    progress_reporter: Callable[[dict[str, int]], None] | None = None,
    cursor_store: HistoricalGraphCursorStore | None = None,
) -> dict[str, Any]:
    """Return aggregate outcomes for one bounded historical enrichment page."""
    if limit < 1 or limit > MAX_PAGE_SIZE or apply_limit < 1 or apply_limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit and apply_limit must be between 1 and {MAX_PAGE_SIZE}")
    candidate_limit = scan_limit if scan_limit is not None else limit
    if candidate_limit < 1 or candidate_limit > MAX_STRUCTURED_SCAN_SIZE:
        raise ValueError(f"scan_limit must be between 1 and {MAX_STRUCTURED_SCAN_SIZE}")
    # The serving query orders by recent mutation time. A successful graph
    # enrichment moves a row to the head of that ordering, so every backfill
    # mode needs a bounded scan to look past already graph-ready rows without
    # raising the per-execution write cap.
    if apply and confirm_uid != uid:
        raise ValueError("apply requires confirm_uid to exactly match uid")

    db_client = db_client or _firestore_client(project=firestore_project)
    if llm is None and not structured_only:
        # A page applies serially and may retry individual records. Keep the
        # per-item transport deadline below the Cloud Run task budget so one
        # silent upstream request cannot monopolize the full backfill page.
        llm = get_llm("memory_l2", request_timeout=HISTORICAL_GRAPH_PLANNER_TIMEOUT_SECONDS)
    report: Counter[str] = Counter()
    applied = 0
    if not apply:
        control = _control(uid, db_client=db_client)
        for item in _candidates(
            uid, control=control, limit=candidate_limit, db_client=db_client, replan_existing=replan_existing
        ):
            try:
                planned = (
                    _structured_plan(item, control)
                    if structured_only
                    else _plan_with_deadline(item=item, control=control, llm=llm)
                )
            # The planner is an external dependency. A transient transport or
            # provider failure must not make a bounded page fail closed for all
            # of a user's remaining historical memories; leave this item
            # unchanged and let a later page retry it.
            except Exception:
                report["planner_error"] += 1
                continue
            if planned is None:
                report["not_structured"] += 1
            elif planned.status == "ready" and planned.operation is not None:
                report["planned"] += 1
            else:
                report[planned.block_code or "blocked"] += 1
    else:
        initial_control = _control(uid, db_client=db_client)
        cursor_store = cursor_store or FirestoreHistoricalGraphCursorStore(db_client)
        cursor = cursor_store.read(uid, control=initial_control, replan_existing=replan_existing)
        page = _candidate_page(
            uid,
            control=initial_control,
            cursor=cursor,
            limit=candidate_limit,
            db_client=db_client,
            replan_existing=replan_existing,
        )
        # Every committed apply advances the canonical control head. Re-read the
        # control record before every candidate so no operation is submitted
        # against a stale observed_head_commit_id.
        retryable_head_mismatches = 0
        max_retryable_head_mismatches = apply_limit * 2
        last_examined: MemoryItem | None = None
        completed_page = True
        # ``scan_limit`` lets the cursor skip a run of already-enriched rows,
        # while ``limit`` remains the hard external-planner budget.  Without
        # this slice a sparse eligible page can invoke the model for every row
        # in the scan window while still seeking only ``apply_limit`` commits.
        # That turns a 25-item bounded job into up to 1,250 model calls.
        for item in page.items[:limit]:
            if applied >= apply_limit:
                break
            control = _control(uid, db_client=db_client)
            last_examined = item
            try:
                planned = (
                    _structured_plan(item, control)
                    if structured_only
                    else _plan_with_deadline(item=item, control=control, llm=llm)
                )
            # A failed planner is still an examined row. Advancing past it lets
            # a later candidate in this page make progress; a subsequent full
            # cursor rotation retries the failure without starving older rows.
            except Exception:
                report["planner_error"] += 1
                continue
            if planned is None:
                report["not_structured"] += 1
                continue
            if planned.status != "ready" or planned.operation is None:
                report[planned.block_code or "blocked"] += 1
                continue
            result = apply_long_term_patch_firestore(
                uid=uid,
                operation_id=planned.operation.operation_id,
                patch_payload=planned.patch_payload,
                proposed_operation=planned.operation,
                db_client=db_client,
            )
            if result.status in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
                report[result.status.value] += 1
                applied += 1
                retryable_head_mismatches = 0
                if progress_reporter is not None:
                    progress_reporter({result.status.value: applied})
            elif result.status == ApplyStatus.retryable_head_mismatch:
                report[result.status.value] += 1
                retryable_head_mismatches += 1
                if retryable_head_mismatches < max_retryable_head_mismatches:
                    continue
                completed_page = False
                break
            else:
                report[f"apply_{result.status.value}"] += 1
                completed_page = False
                break
        if last_examined is None:
            # An all-filtered scan still needs to move past its stable prefix.
            last_examined = page.last_scanned

        if completed_page:
            reached_scanned_tail = (
                last_examined is not None
                and page.last_scanned is not None
                and last_examined.memory_id == page.last_scanned.memory_id
                and last_examined.updated_at == page.last_scanned.updated_at
            )
            if page.exhausted and (page.last_scanned is None or reached_scanned_tail):
                # We examined the tail: persist a null boundary so the next
                # invocation wraps to the newest rows and retries failures.
                resume_after = None
            else:
                resume_after = last_examined
            if cursor_store.advance(
                uid,
                control=initial_control,
                replan_existing=replan_existing,
                expected_generation=cursor.generation,
                resume_after=resume_after,
            ):
                report["cursor_advanced"] += 1
            else:
                report["cursor_conflict"] += 1
    return {
        "dry_run": not apply,
        "limit": limit,
        "scan_limit": candidate_limit,
        "apply_limit": apply_limit,
        "structured_only": structured_only,
        "replan_existing": replan_existing,
        "outcomes": dict(sorted(report.items())),
    }


def main() -> int:
    args = _arguments()
    try:
        report = run_enrichment(
            uid=args.uid,
            firestore_project=args.firestore_project,
            limit=args.limit,
            apply=args.apply,
            confirm_uid=args.confirm_uid,
            structured_only=args.structured_only,
            apply_limit=args.apply_limit,
            scan_limit=args.scan_limit,
            replan_existing=args.replan_existing,
            progress_reporter=(
                (lambda progress: print(json.dumps({"progress": progress}), flush=True)) if args.apply else None
            ),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(report))
    return 0 if not any(key.startswith("apply_") for key in report["outcomes"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
