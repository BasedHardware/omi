#!/usr/bin/env python3
"""Run or preview one user's durable canonical-memory migration.

The CLI owns operator confirmation and inventory acquisition only.  Canonical
processing, graph planning, apply, projection delivery, and verification are
injected controller hooks so this command cannot bypass the canonical apply
boundary or fabricate LLM/processing receipts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore

from database.google_credentials import prepare_google_credentials
from database.memory_migration_store import FirestoreMigrationStore
from models.memory_apply import MemoryControlState
from models.memory_contracts import deterministic_contract_id
from models.memory_migration import MigrationInventory, MigrationPhase
from utils.memory.canonical_migration_controller import (
    CanonicalMigrationController,
    ControllerHooks,
    MigrationVerificationResult,
)

APPLY_CONFIRMATION = "canonical-memory-migration"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview or run a durable per-user canonical-memory migration")
    parser.add_argument("--uid", required=True, help="Firebase UID to migrate")
    parser.add_argument("--owner", required=True, help="Stable worker/operator owner identifier")
    parser.add_argument("--firestore-project", help="Explicit Firestore project (required for apply)")
    parser.add_argument("--inventory-json", type=Path, help="Offline inventory JSON for dry-run tests/previews")
    parser.add_argument("--apply", action="store_true", help="Persist checkpoints/manifests and run controller hooks")
    parser.add_argument("--confirm-apply", help=f"Required with --apply; must equal {APPLY_CONFIRMATION!r}")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON (default)")
    return parser


def validate_confirmation(*, apply: bool, confirm_apply: str | None) -> None:
    if apply and confirm_apply != APPLY_CONFIRMATION:
        raise ValueError(f"--confirm-apply must be exactly {APPLY_CONFIRMATION!r}")


def _inventory_from_json(path: Path, uid: str) -> MigrationInventory:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "uid" not in payload:
        payload = {**payload, "uid": uid}
    return MigrationInventory.model_validate(payload)


def _firestore_inventory(db_client: Any, uid: str) -> MigrationInventory:
    control_snapshot = db_client.document(f"users/{uid}/memory_control/state").get()
    control_payload = control_snapshot.to_dict() if getattr(control_snapshot, "exists", False) else {}
    control = MemoryControlState.model_validate({"uid": uid, **control_payload})
    item_snapshots = db_client.collection(f"users/{uid}/memory_items").stream()
    item_rows = [snapshot.to_dict() or {} for snapshot in item_snapshots]
    item_ids = sorted(str(row.get("memory_id") or "") for row in item_rows if row.get("memory_id"))
    item_revisions = {
        str(row["memory_id"]): int(row.get("item_revision", 0)) for row in item_rows if row.get("memory_id")
    }
    item_content_hashes = {
        str(row["memory_id"]): str(row.get("content_hash") or f"inventory_missing:{row['memory_id']}")
        for row in item_rows
        if row.get("memory_id")
    }
    item_evidence_ids = {
        str(row["memory_id"]): sorted(
            str(value.get("evidence_id"))
            for value in (row.get("evidence") or [])
            if isinstance(value, dict) and value.get("evidence_id")
        )
        for row in item_rows
        if row.get("memory_id")
    }
    fingerprint = deterministic_contract_id(
        "canonical-memory-migration-inventory",
        {"uid": uid, "items": [{"id": item_id, "revision": item_revisions[item_id]} for item_id in item_ids]},
    )
    return MigrationInventory(
        uid=uid,
        inventory_id=f"inventory_{fingerprint[:24]}",
        fingerprint=fingerprint,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        head_commit_id=control.head_commit_id,
        head_sequence=control.commit_sequence,
        item_ids=item_ids,
        item_revisions=item_revisions,
        item_content_hashes=item_content_hashes,
        item_evidence_ids=item_evidence_ids,
        stable=False,
        bounded_delta=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_confirmation(apply=args.apply, confirm_apply=args.confirm_apply)
        if args.apply and not args.firestore_project:
            raise ValueError("--firestore-project is required with --apply")
        if not args.apply and args.inventory_json is None:
            raise ValueError("dry-run requires --inventory-json or --apply for a live inventory")
    except ValueError as exc:
        parser.error(str(exc))

    db_client: Any = None
    store: Any
    if args.apply:
        prepare_google_credentials()
        db_client = firestore.Client(project=args.firestore_project)
        store = FirestoreMigrationStore(db_client)
        inventory_fn = lambda uid: _firestore_inventory(db_client, uid)
    else:
        inventory_fn = lambda uid: _inventory_from_json(args.inventory_json, uid)
        # Dry-run does not write, so a store is never consulted.
        store = None

    hooks = ControllerHooks(
        inventory=inventory_fn,
        verify=lambda _uid, _manifest: MigrationVerificationResult(
            passed=False,
            errors=("no processing/projection verifier hook configured by CLI",),
        ),
    )
    if args.apply:
        controller = CanonicalMigrationController(store=store, hooks=hooks)
        result = controller.run_user(uid=args.uid, owner_id=args.owner, dry_run=False, confirm=True)
    else:
        # Construct a lightweight controller only to exercise the same typed
        # inventory/manifests and emit the planned phase.
        controller = CanonicalMigrationController(store=object(), hooks=hooks)
        result = controller.run_user(uid=args.uid, owner_id=args.owner, dry_run=True, confirm=False)
    print(
        json.dumps(
            {
                "uid": args.uid,
                "phase": result.phase.value,
                "dry_run": result.dry_run,
                "manifest_id": result.manifest_id,
            },
            sort_keys=True,
        )
    )
    return 0 if result.phase in {MigrationPhase.inventoried, MigrationPhase.read_cutover} else 1


if __name__ == "__main__":
    raise SystemExit(main())
