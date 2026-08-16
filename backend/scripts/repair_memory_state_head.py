#!/usr/bin/env python3
"""Repair the trusted V3 fields on one user's ``memory_state/head`` document.

This is a narrow operator tool for the legacy-ledger collision where the state
head survived but no longer satisfied the V3 trusted account-generation
contract. Dry-run is the default. The tool never reads or writes memory item
content, compatibility-projection items, or rollout gates.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import transactional

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.google_credentials import prepare_google_credentials
from database.memory_collections import MemoryCollections
from models.memory_state_head import (
    trusted_memory_state_head_fields_from_control,
    trusted_memory_state_head_fields_from_state,
)
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation


@dataclass(frozen=True)
class StateHeadRepairPlan:
    status: str
    head_path: str
    control_path: str
    write_mode: str | None = None
    trusted_fields: dict[str, Any] | None = None

    def report(self, *, applied: bool) -> dict[str, Any]:
        return {
            "status": self.status,
            "head_path": self.head_path,
            "control_path": self.control_path,
            "write_mode": self.write_mode,
            "trusted_field_names": sorted((self.trusted_fields or {}).keys()),
            "applied": applied,
        }


def _snapshot_data(snapshot: Any) -> dict[str, Any] | None:
    if snapshot is None or getattr(snapshot, "exists", False) is False:
        return None
    raw: object = snapshot.to_dict()
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else None


def build_state_head_repair_plan(
    *, uid: str, head: Mapping[str, Any] | None, control: Mapping[str, Any] | None
) -> StateHeadRepairPlan:
    """Classify a repair without exposing memory payloads or writing anything."""
    collections = MemoryCollections(uid=uid)
    head_path = collections.memory_state_head
    control_path = collections.memory_apply_control_state
    if head is not None and trusted_memory_state_head_fields_from_state(head, uid=uid) is not None:
        return StateHeadRepairPlan(status="already_trusted", head_path=head_path, control_path=control_path)

    trusted_fields = trusted_memory_state_head_fields_from_control(control, uid=uid) if control is not None else None
    if trusted_fields is None:
        return StateHeadRepairPlan(
            status="blocked_invalid_apply_control", head_path=head_path, control_path=control_path
        )

    return StateHeadRepairPlan(
        status="repair_required",
        head_path=head_path,
        control_path=control_path,
        write_mode="update" if head is not None else "create",
        trusted_fields=trusted_fields,
    )


def inspect_state_head_repair(db_client: Any, *, uid: str) -> StateHeadRepairPlan:
    collections = MemoryCollections(uid=uid)
    head = _snapshot_data(db_client.document(collections.memory_state_head).get())
    control = _snapshot_data(db_client.document(collections.memory_apply_control_state).get())
    return build_state_head_repair_plan(uid=uid, head=head, control=control)


def _apply_state_head_repair_transaction_body(transaction: Any, db_client: Any, *, uid: str) -> StateHeadRepairPlan:
    """Read both authoritative documents before writing the minimal trusted patch."""
    collections = MemoryCollections(uid=uid)
    head_ref = db_client.document(collections.memory_state_head)
    control_ref = db_client.document(collections.memory_apply_control_state)
    head = _snapshot_data(head_ref.get(transaction=transaction))
    control = _snapshot_data(control_ref.get(transaction=transaction))
    plan = build_state_head_repair_plan(uid=uid, head=head, control=control)
    if plan.status != "repair_required":
        return plan

    assert plan.trusted_fields is not None
    if plan.write_mode == "create":
        transaction.set(head_ref, plan.trusted_fields)
    else:
        transaction.update(head_ref, plan.trusted_fields)
    return plan


@transactional
def _apply_state_head_repair_transaction(transaction: Any, db_client: Any, *, uid: str) -> StateHeadRepairPlan:
    return _apply_state_head_repair_transaction_body(transaction, db_client, uid=uid)


def apply_state_head_repair(db_client: Any, *, uid: str) -> StateHeadRepairPlan:
    return run_with_transaction_contention_retry(
        db_client.transaction,
        lambda transaction: _apply_state_head_repair_transaction(transaction, db_client, uid=uid),
        operation_name="repair_memory_state_head",
    )


def _load_firestore_client(*, firestore_project: str):
    prepare_google_credentials()
    return firestore.Client(project=firestore_project)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair trusted V3 memory state-head metadata for one UID.")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--firestore-project", required=True, help="Explicit Firestore project, e.g. based-hardware.")
    parser.add_argument("--apply", action="store_true", help="Write the minimal trusted state-head field patch.")
    parser.add_argument("--confirm-uid", help="Required with --apply; must exactly match --uid.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and args.confirm_uid != args.uid:
        raise SystemExit("--confirm-uid must exactly match --uid when --apply is used")

    db_client = _load_firestore_client(firestore_project=args.firestore_project)
    plan = (
        apply_state_head_repair(db_client, uid=args.uid)
        if args.apply
        else inspect_state_head_repair(db_client, uid=args.uid)
    )
    if args.apply and plan.status not in {"repair_required", "already_trusted"}:
        raise RuntimeError(f"state-head repair blocked: {plan.status}")
    trusted_after_apply = None
    if args.apply and plan.status in {"repair_required", "already_trusted"}:
        trusted_after_apply = read_memory_v3_trusted_account_generation(uid=args.uid, db_client=db_client)
        if trusted_after_apply.read_error_reason is not None:
            raise RuntimeError(
                f"state-head repair did not satisfy V3 trust contract: {trusted_after_apply.read_error_reason.value}"
            )

    print(
        json.dumps(
            {
                "artifact": "memory_state_head_repair",
                "uid": args.uid,
                "firestore_project": args.firestore_project,
                "dry_run": not args.apply,
                "repair": plan.report(applied=args.apply and plan.status == "repair_required"),
                "v3_state_head_valid_after_apply": trusted_after_apply is not None,
                "operator_notes": [
                    "This tool writes only trusted metadata on users/{uid}/memory_state/head.",
                    "It never writes memory content, compatibility-projection items, rollout gates, or vectors.",
                    "A blocked_invalid_apply_control result requires investigation; do not fabricate trusted fields.",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
