"""Run one bounded, evidence-fenced historical canonical graph enrichment page.

Default mode is dry-run.  ``--apply`` requires exact UID confirmation and is
limited to 25 items so expansion is an explicit operational choice.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore  # noqa: E402
from google.cloud.firestore_v1 import FieldFilter  # noqa: E402

from database.memory_apply_store import apply_long_term_patch_firestore  # noqa: E402
from database.memory_collections import MemoryCollections  # noqa: E402
from database.firestore_index_registry import CANONICAL_MEMORY_ATLAS_READ_QUERY  # noqa: E402
from models.memory_apply import ApplyStatus, MemoryControlState  # noqa: E402
from models.memory_promotion import PromotionGraphPlan  # noqa: E402
from models.product_memory import MemoryItem  # noqa: E402
from utils.llm.clients import get_llm  # noqa: E402
from utils.memory.graph_enrichment import prepare_graph_enrichment  # noqa: E402
from utils.memory.historical_graph_enrichment import plan_historical_graph_enrichment  # noqa: E402

MAX_PAGE_SIZE = 25
MAX_STRUCTURED_SCAN_SIZE = 1250


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or apply one historical canonical graph enrichment page")
    parser.add_argument("--uid", required=True, help="Target canonical user UID")
    parser.add_argument("--firestore-project", required=True, help="Explicit Firestore data-plane project")
    parser.add_argument("--limit", type=int, default=1, help=f"Items to inspect (1-{MAX_PAGE_SIZE})")
    parser.add_argument(
        "--scan-limit",
        type=int,
        help=(
            f"Candidate rows to read in structured-only mode (1-{MAX_STRUCTURED_SCAN_SIZE}); "
            "does not increase the apply bound"
        ),
    )
    parser.add_argument("--apply-limit", type=int, default=1, help=f"Ready plans to commit (1-{MAX_PAGE_SIZE})")
    parser.add_argument(
        "--structured-only",
        action="store_true",
        help="Use only pre-existing complete canonical graph fields; never call an LLM",
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


def _candidates(uid: str, *, control: MemoryControlState, limit: int, db_client: Any) -> list[MemoryItem]:
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
    query = (
        query.order_by("updated_at", direction=firestore.Query.DESCENDING)
        .order_by("__name__", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [item for snapshot in query.stream() if not (item := MemoryItem(**(snapshot.to_dict() or {}))).graph_ready]


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
    db_client: Any | None = None,
    llm: Any | None = None,
    progress_reporter: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, Any]:
    """Return aggregate outcomes for one bounded historical enrichment page."""
    if limit < 1 or limit > MAX_PAGE_SIZE or apply_limit < 1 or apply_limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit and apply_limit must be between 1 and {MAX_PAGE_SIZE}")
    candidate_limit = scan_limit if scan_limit is not None else limit
    if candidate_limit < 1 or candidate_limit > MAX_STRUCTURED_SCAN_SIZE:
        raise ValueError(f"scan_limit must be between 1 and {MAX_STRUCTURED_SCAN_SIZE}")
    if candidate_limit != limit and not structured_only:
        raise ValueError("scan_limit greater than limit requires structured_only mode")
    if apply and confirm_uid != uid:
        raise ValueError("apply requires confirm_uid to exactly match uid")

    db_client = db_client or firestore.Client(project=firestore_project)
    if llm is None and not structured_only:
        llm = get_llm("memory_l2")
    report: Counter[str] = Counter()
    applied = 0
    if not apply:
        control = _control(uid, db_client=db_client)
        for item in _candidates(uid, control=control, limit=candidate_limit, db_client=db_client):
            planned = (
                _structured_plan(item, control)
                if structured_only
                else plan_historical_graph_enrichment(item=item, control=control, llm=llm)
            )
            if planned is None:
                report["not_structured"] += 1
            elif planned.status == "ready" and planned.operation is not None:
                report["planned"] += 1
            else:
                report[planned.block_code or "blocked"] += 1
    else:
        # Every committed apply advances the canonical control head. Re-read the
        # control record and re-plan the next item so no operation is submitted
        # against a stale observed_head_commit_id.
        retryable_head_mismatches = 0
        max_retryable_head_mismatches = apply_limit * 2
        while applied < apply_limit:
            control = _control(uid, db_client=db_client)
            planned = None
            for item in _candidates(uid, control=control, limit=candidate_limit, db_client=db_client):
                candidate = (
                    _structured_plan(item, control)
                    if structured_only
                    else plan_historical_graph_enrichment(item=item, control=control, llm=llm)
                )
                if candidate is None:
                    continue
                if candidate.status == "ready" and candidate.operation is not None:
                    planned = candidate
                    break
            if planned is None:
                break
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
                break
            else:
                report[f"apply_{result.status.value}"] += 1
                break
    return {
        "dry_run": not apply,
        "limit": limit,
        "scan_limit": candidate_limit,
        "apply_limit": apply_limit,
        "structured_only": structured_only,
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
