"""Real Firestore-emulator proof for writer cutover, rollback, and roll-forward."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState, WriterMode
from utils.memory.knowledge_ledger_migration import (
    publish_ledger_migration_cutover,
    read_ledger_migration_completion,
    read_ledger_prompt_projection_receipt,
    rollback_ledger_writer_to_compatibility,
)

PROJECT_ID = "demo-memory"
UID = "writer-transition-emulator-user"
NOW = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


def _required_control(db_client: Any, collections: MemoryCollections) -> MemoryControlState:
    snapshot = db_client.document(collections.memory_apply_control_state).get()
    if not snapshot.exists:
        raise AssertionError("writer transition control is missing")
    return MemoryControlState.model_validate(snapshot.to_dict() or {})


def _assert_current_projection(db_client: Any, collections: MemoryCollections) -> None:
    completion = read_ledger_migration_completion(UID, db_client=db_client)
    if completion is None:
        raise AssertionError("stable ledger mode lacks a current completion proof")
    receipt = read_ledger_prompt_projection_receipt(
        UID,
        db_client=db_client,
        completion=completion,
    )
    if receipt is None or receipt.rows or receipt.scanned_row_count != 0:
        raise AssertionError("empty-account prompt projection is not authoritative")
    transition_snapshot = db_client.document(collections.knowledge_ledger_writer_transition_receipt).get()
    if not transition_snapshot.exists:
        raise AssertionError("writer transition proof is missing")
    transition = transition_snapshot.to_dict() or {}
    if transition.get("target_mode") != WriterMode.ledger.value or transition.get("complete_union_count") != 0:
        raise AssertionError("writer transition proof does not describe the empty ledger union")


def main() -> int:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")

    db_client: Any = firestore.Client(project=PROJECT_ID)
    collections = MemoryCollections(uid=UID)
    initial = MemoryControlState(
        uid=UID,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        updated_at=NOW,
    )
    db_client.document(collections.memory_apply_control_state).set(initial.model_dump(mode="json"))

    publish_ledger_migration_cutover(
        UID,
        db_client=db_client,
        publication_authorizer=lambda: True,
        mutation_authorizer=lambda _memory_id: True,
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
        completed_at=NOW,
    )
    cutover = _required_control(db_client, collections)
    if cutover.writer_mode != WriterMode.ledger or cutover.writer_epoch != 1 or cutover.source_generation != 2:
        raise AssertionError("forward cutover did not advance the exact writer fences")
    _assert_current_projection(db_client, collections)

    rolled_back = rollback_ledger_writer_to_compatibility(
        UID,
        db_client=db_client,
        rollback_authorizer=lambda: True,
        completed_at=NOW,
    )
    if (
        rolled_back.writer_mode != WriterMode.compatibility
        or rolled_back.writer_epoch != 2
        or rolled_back.source_generation != 3
    ):
        raise AssertionError("bridge rollback did not restore compatibility at a new epoch")
    if read_ledger_migration_completion(UID, db_client=db_client) is not None:
        raise AssertionError("compatibility mode must invalidate the prior ledger completion")

    rollback_proof = db_client.document(collections.knowledge_ledger_writer_transition_receipt).get().to_dict() or {}
    if rollback_proof.get("target_mode") != WriterMode.compatibility.value:
        raise AssertionError("rollback proof did not target compatibility")

    publish_ledger_migration_cutover(
        UID,
        db_client=db_client,
        publication_authorizer=lambda: True,
        mutation_authorizer=lambda _memory_id: True,
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
        completed_at=NOW,
    )
    rolled_forward = _required_control(db_client, collections)
    if (
        rolled_forward.writer_mode != WriterMode.ledger
        or rolled_forward.writer_epoch != 3
        or rolled_forward.source_generation != 4
    ):
        raise AssertionError("roll-forward did not create a fresh stable ledger epoch")
    _assert_current_projection(db_client, collections)

    print("PASS: writer transition emulator proof cutover=1 rollback=2 rollforward=3 rows_preserved=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
