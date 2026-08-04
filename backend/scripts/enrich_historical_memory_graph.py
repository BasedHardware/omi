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
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore  # noqa: E402
from google.cloud.firestore_v1 import FieldFilter  # noqa: E402

from database.memory_apply_store import apply_long_term_patch_firestore  # noqa: E402
from database.memory_collections import MemoryCollections  # noqa: E402
from models.memory_apply import ApplyStatus, MemoryControlState  # noqa: E402
from models.product_memory import MemoryItem  # noqa: E402
from utils.llm.clients import get_llm  # noqa: E402
from utils.memory.historical_graph_enrichment import plan_historical_graph_enrichment  # noqa: E402

MAX_PAGE_SIZE = 25


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or apply one historical canonical graph enrichment page")
    parser.add_argument("--uid", required=True, help="Target canonical user UID")
    parser.add_argument("--firestore-project", required=True, help="Explicit Firestore data-plane project")
    parser.add_argument("--limit", type=int, default=1, help=f"Items to inspect (1-{MAX_PAGE_SIZE})")
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
    query = (
        collection.where(filter=FieldFilter("account_generation", "==", control.account_generation))
        .where(filter=FieldFilter("tier", "==", "long_term"))
        .where(filter=FieldFilter("status", "==", "active"))
        .where(filter=FieldFilter("processing_state", "==", "processed"))
        .where(filter=FieldFilter("graph_ready", "==", False))
        .order_by("updated_at")
        .order_by("memory_id")
        .limit(limit)
    )
    return [MemoryItem(**(snapshot.to_dict() or {})) for snapshot in query.stream()]


def main() -> int:
    args = _arguments()
    if args.limit < 1 or args.limit > MAX_PAGE_SIZE:
        raise SystemExit(f"--limit must be between 1 and {MAX_PAGE_SIZE}")
    if args.apply and args.confirm_uid != args.uid:
        raise SystemExit("--apply requires --confirm-uid to exactly match --uid")

    db_client = firestore.Client(project=args.firestore_project)
    control = _control(args.uid, db_client=db_client)
    llm = get_llm("memory_l2")
    report: Counter[str] = Counter()
    for item in _candidates(args.uid, control=control, limit=args.limit, db_client=db_client):
        planned = plan_historical_graph_enrichment(item=item, control=control, llm=llm)
        if planned.status != "ready" or planned.operation is None:
            report[planned.block_code or "blocked"] += 1
            continue
        if not args.apply:
            report["planned"] += 1
            continue
        result = apply_long_term_patch_firestore(
            uid=args.uid,
            operation_id=planned.operation.operation_id,
            patch_payload=planned.patch_payload,
            proposed_operation=planned.operation,
            db_client=db_client,
        )
        if result.status in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
            report[result.status.value] += 1
        else:
            report[f"apply_{result.status.value}"] += 1
    print(json.dumps({"dry_run": not args.apply, "limit": args.limit, "outcomes": dict(sorted(report.items()))}))
    return 0 if not any(key.startswith("apply_") for key in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
