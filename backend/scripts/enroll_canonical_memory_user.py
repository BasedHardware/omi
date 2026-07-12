#!/usr/bin/env python3
"""Prepare or apply canonical-memory rollout Firestore docs for explicit UIDs.

Dry-run is the default. Applying writes requires an explicit Firestore project,
UID confirmation, and an existing-doc update acknowledgement. The script writes
only rollout control documents; it validates v3 read-proof prerequisites instead
of fabricating projection data.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from google.cloud import firestore

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.memory_rollout import MemoryRolloutMode, PASSED
from database.google_credentials import prepare_google_credentials
from database.memory_collections import MemoryCollections
from utils.memory.default_read_rollout import DEFAULT_READ_ROLLOUT_SCHEMA_VERSION
from utils.memory.v3.limited_rollout_config import GLOBAL_READ_GATE_PATH, WRITE_CONVERGENCE_GATE_PATH

FIRST_USER_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
DEFAULT_OWNER = "memory_platform"
DEFAULT_ROUTE_SCOPE = "get_v3_memories"


@dataclass(frozen=True)
class RolloutDocumentPlan:
    path: str
    payload: dict[str, Any]


def build_global_read_gate(*, stage: str, owner: str = DEFAULT_OWNER) -> dict[str, Any]:
    read_enabled = stage == "read"
    return {
        "route_scope": DEFAULT_ROUTE_SCOPE,
        "purpose": "v3_runtime_enablement",
        "owner": owner,
        "config_schema_version": 1,
        "memory_reads_enabled": read_enabled,
        "kill_switch_active": not read_enabled,
    }


def build_write_convergence_gate(*, stage: str, owner: str = DEFAULT_OWNER) -> dict[str, Any]:
    ready = stage in {"write", "read"}
    return {
        "route_scope": DEFAULT_ROUTE_SCOPE,
        "purpose": "v3_write_convergence_gate",
        "owner": owner,
        "config_schema_version": 1,
        "durable_outbox_enabled": ready,
        "dual_write_projection_ready": ready,
        "delete_convergence_ready": ready,
        "idempotency_contract_ready": ready,
    }


def build_user_control_state(
    *,
    uid: str,
    stage: str,
    account_generation: int,
    default_memory_grant: bool | None = None,
    archive_grant: bool = False,
) -> dict[str, Any]:
    if not uid:
        raise ValueError("uid is required")
    if account_generation < 0:
        raise ValueError("account_generation must be nonnegative")
    mode = MemoryRolloutMode(stage)
    read_stage = stage == "read"
    write_stage = stage in {"write", "read"}
    default_memory = read_stage if default_memory_grant is None else default_memory_grant
    return {
        "uid": uid,
        "schema_version": DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        "mode": mode.value,
        "mode_epoch": 1,
        "cutover_epoch": 1 if read_stage else 0,
        "account_generation": account_generation,
        "fallback_projection_ready": read_stage,
        "persistent_memory_writes_started": write_stage,
        "decommission_reconciled": False,
        "writes_blocked": not write_stage,
        "stage_gates": {
            "shadow": PASSED if write_stage else "blocked",
            "write": PASSED if write_stage else "blocked",
            "read": PASSED if read_stage else "blocked",
        },
        "grants": {"omi_chat": {"default_memory": default_memory, "archive": archive_grant}},
        "vector_repair_outbox_enabled": False,
    }


def build_rollout_documents(
    *,
    uid: str,
    stage: str,
    account_generation: int,
    default_memory_grant: bool | None = None,
    archive_grant: bool = False,
    owner: str = DEFAULT_OWNER,
) -> list[RolloutDocumentPlan]:
    paths = MemoryCollections(uid=uid)
    return [
        RolloutDocumentPlan(GLOBAL_READ_GATE_PATH, build_global_read_gate(stage=stage, owner=owner)),
        RolloutDocumentPlan(WRITE_CONVERGENCE_GATE_PATH, build_write_convergence_gate(stage=stage, owner=owner)),
        RolloutDocumentPlan(
            paths.memory_control_state,
            build_user_control_state(
                uid=uid,
                stage=stage,
                account_generation=account_generation,
                default_memory_grant=default_memory_grant,
                archive_grant=archive_grant,
            ),
        ),
    ]


def v3_read_prerequisite_paths(uid: str) -> list[str]:
    paths = MemoryCollections(uid=uid)
    return [
        paths.memory_state_head,
        paths.v3_compatibility_projection_state,
    ]


def _snapshot_data(snapshot: Any) -> dict[str, Any] | None:
    if not getattr(snapshot, "exists", False):
        return None
    raw: object = snapshot.to_dict()
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else None


def inspect_existing_docs(db_client: Any, documents: list[RolloutDocumentPlan]) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    for document in documents:
        existing[document.path] = _snapshot_data(db_client.document(document.path).get())
    return existing


def inspect_v3_read_prerequisites(db_client: Any, *, uid: str) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for path in v3_read_prerequisite_paths(uid):
        result[path] = _snapshot_data(db_client.document(path).get()) is not None
    return result


def assert_v3_read_prerequisites_ready(prerequisites: dict[str, bool]) -> None:
    missing = [path for path, exists in prerequisites.items() if not exists]
    if missing:
        raise RuntimeError("--stage read --apply requires existing v3 read prerequisite docs: " + ", ".join(missing))


def apply_documents(
    db_client: Any,
    documents: list[RolloutDocumentPlan],
    *,
    allow_existing_update: bool,
) -> dict[str, Any]:
    existing = inspect_existing_docs(db_client, documents)
    changed_existing = [
        path
        for path, current in existing.items()
        if current is not None and current != _payload_by_path(documents)[path]
    ]
    if changed_existing and not allow_existing_update:
        raise RuntimeError(
            "Refusing to update existing differing docs without --allow-existing-update: " + ", ".join(changed_existing)
        )

    for document in documents:
        db_client.document(document.path).set(document.payload, merge=True)
    return {
        "written_paths": [document.path for document in documents],
        "updated_existing_paths": changed_existing,
    }


def _payload_by_path(documents: list[RolloutDocumentPlan]) -> dict[str, dict[str, Any]]:
    return {document.path: document.payload for document in documents}


def build_report(
    *,
    uid: str,
    stage: str,
    account_generation: int,
    firestore_project: str | None,
    documents: list[RolloutDocumentPlan],
    existing_docs: dict[str, Any] | None = None,
    v3_read_prerequisites: dict[str, bool] | None = None,
    writes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact": "canonical_memory_user_enrollment",
        "uid": uid,
        "stage": stage,
        "account_generation": account_generation,
        "firestore_project": firestore_project,
        "dry_run": writes is None,
        "document_count": len(documents),
        "documents": _payload_by_path(documents),
        "existing_docs": existing_docs,
        "v3_read_prerequisites": v3_read_prerequisites,
        "writes": writes,
        "operator_notes": [
            "This script writes only rollout control docs when --apply is supplied.",
            "It does not add users to CANONICAL_MEMORY_USERS or MEMORY_ENABLED_USERS.",
            "It does not fabricate memory_state/head or v3 compatibility projection data.",
            "For first-user dev launch, target Firestore project is based-hardware.",
        ],
    }


def _load_firestore_client(*, firestore_project: str):
    prepare_google_credentials()
    return firestore.Client(project=firestore_project)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare/apply canonical memory rollout Firestore docs for a UID.")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--stage", choices=("off", "write", "read"), default="write")
    parser.add_argument("--account-generation", type=int, default=1)
    parser.add_argument(
        "--firestore-project", help="Explicit Firestore project for inspection/apply, e.g. based-hardware."
    )
    parser.add_argument(
        "--default-memory-grant", action="store_true", help="Force grants.omi_chat.default_memory=true."
    )
    parser.add_argument("--archive-grant", action="store_true", help="Set grants.omi_chat.archive=true.")
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument(
        "--inspect-existing", action="store_true", help="Read existing target docs and include them in output."
    )
    parser.add_argument(
        "--check-v3-read-prereqs",
        action="store_true",
        help="Read-only check for memory_state/head and v3 compatibility projection state.",
    )
    parser.add_argument("--apply", action="store_true", help="Write docs. Default is dry-run only.")
    parser.add_argument("--confirm-uid", help="Required with --apply; must exactly match --uid.")
    parser.add_argument(
        "--allow-existing-update",
        action="store_true",
        help="Required with --apply if existing target docs differ from the requested payload.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    default_memory_grant: bool | None = True if args.default_memory_grant else None
    documents = build_rollout_documents(
        uid=args.uid,
        stage=args.stage,
        account_generation=args.account_generation,
        default_memory_grant=default_memory_grant,
        archive_grant=args.archive_grant,
        owner=args.owner,
    )

    existing_docs = None
    v3_read_prerequisites = None
    writes = None
    db_client = None
    needs_firestore = args.inspect_existing or args.check_v3_read_prereqs or args.apply
    if needs_firestore:
        if not args.firestore_project:
            raise SystemExit("--firestore-project is required for inspection or apply")
        db_client = _load_firestore_client(firestore_project=args.firestore_project)
    if args.inspect_existing or args.apply:
        existing_docs = inspect_existing_docs(db_client, documents)
    if args.check_v3_read_prereqs or (args.apply and args.stage == "read"):
        v3_read_prerequisites = inspect_v3_read_prerequisites(db_client, uid=args.uid)

    if args.apply:
        if args.confirm_uid != args.uid:
            raise SystemExit("--confirm-uid must exactly match --uid when --apply is used")
        if args.stage == "read":
            assert_v3_read_prerequisites_ready(v3_read_prerequisites or {})
        writes = apply_documents(db_client, documents, allow_existing_update=args.allow_existing_update)

    print(
        json.dumps(
            build_report(
                uid=args.uid,
                stage=args.stage,
                account_generation=args.account_generation,
                firestore_project=args.firestore_project,
                documents=documents,
                existing_docs=existing_docs,
                v3_read_prerequisites=v3_read_prerequisites,
                writes=writes,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
