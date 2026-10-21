#!/usr/bin/env python3
"""Exercise one bounded legacy-to-ledger migration against Firestore emulator.

This is a non-production proof of the real migration transaction. It seeds two
synthetic active Long-term rows and their evidence, applies one row before an
intentional interruption, resumes the second row, and verifies persisted
canonical state, provenance, deterministic profile rendering, and a no-op full
rerun. It deliberately never writes a migration completion marker.
"""

from __future__ import annotations

# ruff: noqa: E402 -- emulator project/path bootstrapping must precede backend imports.

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-memory"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore

from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.knowledge_ledger import render_profile
from utils.memory.knowledge_ledger_migration import (
    LedgerMigrationAction,
    apply_ledger_migration_plan,
    migration_marker,
    plan_ledger_migration,
    read_ledger_migration_completion,
)

UID = "knowledge-ledger-migration-emulator-user"
NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)
LEGACY_HEAD = "legacy-migration-head"


def _stored_model(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _required_doc(db_client: Any, path: str) -> dict[str, Any]:
    snapshot = db_client.document(path).get()
    if not snapshot.exists:
        raise AssertionError(f"missing expected Firestore document: {path}")
    return snapshot.to_dict() or {}


def _document_ids(db_client: Any, collection_path: str) -> set[str]:
    return {snapshot.id for snapshot in db_client.collection(collection_path).stream()}


def _collection_snapshot(db_client: Any, collection_path: str) -> dict[str, dict[str, Any]]:
    return {snapshot.id: snapshot.to_dict() or {} for snapshot in db_client.collection(collection_path).stream()}


def _seed_legacy_row(
    db_client: Any,
    collections: MemoryCollections,
    *,
    memory_id: str,
    evidence_id: str,
    content: str,
    predicate: str,
    user_asserted: bool,
) -> MemoryItem:
    evidence = MemoryEvidence(
        evidence_id=evidence_id,
        source_type="conversation",
        source_id=f"conversation-{memory_id}",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    item = MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=1,
        tier=MemoryLayer.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=user_asserted,
        captured_at=NOW,
        updated_at=NOW,
        ledger_commit_id=LEGACY_HEAD,
        ledger_sequence=0,
        item_revision=1,
        account_generation=7,
        predicate=predicate,
    )
    if item.ledger_schema_version is not None or item.slot is not None or item.intent_backed:
        raise AssertionError(f"seed row {memory_id} was not legacy-shaped")
    db_client.document(f"{collections.memory_evidence}/{evidence_id}").set(_stored_model(evidence))
    db_client.document(f"{collections.memory_items}/{memory_id}").set(_stored_model(item))
    return item


def _assert_provenance_and_row(
    db_client: Any,
    collections: MemoryCollections,
    item: MemoryItem,
    *,
    expected_slot: str | None,
    expected_write_reason: str,
) -> None:
    raw = _required_doc(db_client, f"{collections.memory_items}/{item.memory_id}")
    if raw.get("ledger_schema_version") != "knowledge_ledger.v1":
        raise AssertionError("persisted migration row is not ledger v1")
    if raw.get("slot") != expected_slot:
        raise AssertionError("persisted migration row lost its deterministic slot")
    if raw.get("write_reason") != expected_write_reason:
        raise AssertionError("persisted migration row has the wrong write reason")
    raw_evidence = raw.get("evidence")
    if not isinstance(raw_evidence, list) or len(raw_evidence) != 1:
        raise AssertionError("persisted migration row does not contain exactly one evidence record")
    evidence = raw_evidence[0]
    if not all(str(evidence.get(field) or "").strip() for field in ("evidence_id", "source_id", "source_version")):
        raise AssertionError("persisted migration row has incomplete provenance")
    stored_evidence = _required_doc(db_client, f"{collections.memory_evidence}/{evidence['evidence_id']}")
    for field in ("evidence_id", "source_id", "source_version"):
        if stored_evidence.get(field) != evidence.get(field):
            raise AssertionError(f"evidence {field} did not round-trip through the authoritative store")


def _assert_apply_receipt(
    db_client: Any,
    collections: MemoryCollections,
    *,
    memory_id: str,
    control_before: dict[str, Any],
    operation_ids_before: set[str],
    commit_ids_before: set[str],
    outbox_ids_before: set[str],
) -> dict[str, Any]:
    control = _required_doc(db_client, collections.memory_apply_control_state)
    if control.get("commit_sequence") != control_before.get("commit_sequence", 0) + 1:
        raise AssertionError("migration did not advance the canonical control sequence exactly once")
    if control.get("head_commit_id") == control_before.get("head_commit_id"):
        raise AssertionError("migration did not advance the canonical control head")

    operation_ids = _document_ids(db_client, collections.memory_operations)
    commit_ids = _document_ids(db_client, collections.memory_commits)
    outbox_ids = _document_ids(db_client, collections.memory_outbox)
    new_operations = operation_ids - operation_ids_before
    new_commits = commit_ids - commit_ids_before
    new_outbox = outbox_ids - outbox_ids_before
    if len(new_operations) != 1 or len(new_commits) != 1 or len(new_outbox) != 2:
        raise AssertionError("migration transaction did not persist one operation, commit, and two outbox events")

    operation_id = next(iter(new_operations))
    commit_id = next(iter(new_commits))
    operation = _required_doc(db_client, f"{collections.memory_operations}/{operation_id}")
    commit = _required_doc(db_client, f"{collections.memory_commits}/{commit_id}")
    state_head = _required_doc(db_client, collections.memory_state_head)
    item = _required_doc(db_client, f"{collections.memory_items}/{memory_id}")
    if operation.get("status") != "committed":
        raise AssertionError("migration operation was not committed")
    if operation.get("committed_head_commit_id") != control["head_commit_id"]:
        raise AssertionError("operation and control heads disagree")
    if operation.get("committed_sequence") != control["commit_sequence"]:
        raise AssertionError("operation and control sequences disagree")
    if commit.get("operation_id") != operation_id or memory_id not in (commit.get("memory_item_ids") or []):
        raise AssertionError("commit does not identify the migration operation and item")
    if item.get("ledger_commit_id") != control["head_commit_id"]:
        raise AssertionError("migrated item does not reference the committed head")
    if item.get("ledger_sequence") != control["commit_sequence"]:
        raise AssertionError("migrated item does not reference the committed sequence")
    for key in ("uid", "account_generation", "head_commit_id", "commit_sequence"):
        if state_head.get(key) != control.get(key):
            raise AssertionError(f"state-head and control disagree on {key}")
    if set(commit.get("outbox_event_ids") or []) != new_outbox:
        raise AssertionError("commit does not identify exactly the persisted outbox events")
    if set(operation.get("committed_outbox_event_ids") or []) != new_outbox:
        raise AssertionError("operation does not identify exactly the persisted outbox events")
    for event_id in new_outbox:
        event = _required_doc(db_client, f"{collections.memory_outbox}/{event_id}")
        if event.get("commit_id") != control["head_commit_id"] or event.get("operation_id") != operation_id:
            raise AssertionError("outbox event is not joined to the committed operation/head")
    return control


def _apply_one(
    db_client: Any,
    collections: MemoryCollections,
    source: MemoryItem,
    *,
    expected_slot: str | None,
    expected_write_reason: str,
) -> tuple[MemoryItem, str]:
    plan = plan_ledger_migration(source)
    if plan.action != LedgerMigrationAction.adapt_long_term_history:
        raise AssertionError("synthetic legacy source did not produce an automatic migration plan")
    control_before = _required_doc(db_client, collections.memory_apply_control_state)
    operation_ids_before = _document_ids(db_client, collections.memory_operations)
    commit_ids_before = _document_ids(db_client, collections.memory_commits)
    outbox_ids_before = _document_ids(db_client, collections.memory_outbox)
    migrated = apply_ledger_migration_plan(UID, plan, db_client=db_client)
    if migrated.memory_id != source.memory_id or migrated.uid != UID:
        raise AssertionError("migration returned a row with the wrong authority")
    if migrated.ledger_schema_version != "knowledge_ledger.v1":
        raise AssertionError("migration did not return a ledger v1 row")
    _assert_provenance_and_row(
        db_client,
        collections,
        migrated,
        expected_slot=expected_slot,
        expected_write_reason=expected_write_reason,
    )
    control = _assert_apply_receipt(
        db_client,
        collections,
        memory_id=source.memory_id,
        control_before=control_before,
        operation_ids_before=operation_ids_before,
        commit_ids_before=commit_ids_before,
        outbox_ids_before=outbox_ids_before,
    )
    return migrated, control["head_commit_id"]


def _read_item(db_client: Any, collections: MemoryCollections, memory_id: str) -> MemoryItem:
    raw = _required_doc(db_client, f"{collections.memory_items}/{memory_id}")
    return MemoryItem.model_validate(raw)


def main() -> int:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")

    db_client: Any = firestore.Client(project=PROJECT_ID)
    collections = MemoryCollections(uid=UID)
    control = MemoryControlState(
        uid=UID,
        head_commit_id=LEGACY_HEAD,
        account_generation=7,
        source_generation=9,
        commit_sequence=0,
        updated_at=NOW,
    )
    db_client.document(collections.memory_apply_control_state).set(_stored_model(control))
    home = _seed_legacy_row(
        db_client,
        collections,
        memory_id="legacy-home-city",
        evidence_id="legacy-home-city-evidence",
        content="Lives in Brooklyn",
        predicate="resides_in",
        user_asserted=True,
    )
    passive = _seed_legacy_row(
        db_client,
        collections,
        memory_id="legacy-passive-observation",
        evidence_id="legacy-passive-observation-evidence",
        content="Likes obscure facts",
        predicate="likes",
        user_asserted=False,
    )
    if _document_ids(db_client, collections.memory_items) != {home.memory_id, passive.memory_id}:
        raise AssertionError("emulator fixture did not seed exactly two legacy memory rows")
    if len(_document_ids(db_client, collections.memory_evidence)) != 2:
        raise AssertionError("emulator fixture did not seed exactly two matching evidence rows")

    # Apply exactly the first row, then stop before the second to model an
    # interrupted bounded batch. The marker is local proof only; no migration
    # completion document is ever written by this harness.
    first_plan = plan_ledger_migration(home)
    first_marker = migration_marker(first_plan)
    if not first_marker:
        raise AssertionError("first migration plan did not produce a resumable marker")
    migrated_home, first_commit_id = _apply_one(
        db_client,
        collections,
        home,
        expected_slot="home_city",
        expected_write_reason="direct_user_statement",
    )
    completed_markers = {first_marker}

    # Resume from persisted rows. The first row is now an idempotent no-op and
    # the second row performs the only remaining canonical transaction.
    resumed_home = _read_item(db_client, collections, home.memory_id)
    resumed_passive = _read_item(db_client, collections, passive.memory_id)
    if plan_ledger_migration(resumed_home).action != LedgerMigrationAction.no_op:
        raise AssertionError("resume did not recognize the first persisted row as ledger history")
    if migration_marker(first_plan) not in completed_markers:
        raise AssertionError("interrupted first-row marker was not retained by the bounded runner")
    resume_no_op = apply_ledger_migration_plan(UID, plan_ledger_migration(resumed_home), db_client=db_client)
    if resume_no_op.memory_id != migrated_home.memory_id:
        raise AssertionError("resume no-op returned the wrong first row")
    before_second = _required_doc(db_client, collections.memory_apply_control_state)
    _, second_commit_id = _apply_one(
        db_client,
        collections,
        resumed_passive,
        expected_slot=None,
        expected_write_reason="legacy_migration",
    )
    if first_commit_id == second_commit_id:
        raise AssertionError("two migrated rows reused one canonical commit")
    if before_second["commit_sequence"] != 1:
        raise AssertionError("resume did not leave exactly one committed row before the second apply")
    completed_markers.add(migration_marker(plan_ledger_migration(resumed_passive)) or "")
    if len(completed_markers) != 2:
        raise AssertionError("interrupted/resumed run did not account for exactly two row markers")

    final_home = _read_item(db_client, collections, home.memory_id)
    final_passive = _read_item(db_client, collections, passive.memory_id)
    _assert_provenance_and_row(
        db_client,
        collections,
        final_home,
        expected_slot="home_city",
        expected_write_reason="direct_user_statement",
    )
    _assert_provenance_and_row(
        db_client,
        collections,
        final_passive,
        expected_slot=None,
        expected_write_reason="legacy_migration",
    )
    profile = render_profile([final_home, final_passive])
    if profile != "home_city: Lives in Brooklyn":
        raise AssertionError("profile rendering did not include only the user-asserted slotted row")
    profile_sha256 = hashlib.sha256(profile.encode("utf-8")).hexdigest()

    # A complete rerun is read-only at the transaction level: both rows plan as
    # no-op, and the canonical head/collections must not grow.
    before_rerun_control = _required_doc(db_client, collections.memory_apply_control_state)
    before_rerun_items = _collection_snapshot(db_client, collections.memory_items)
    before_rerun_evidence = _collection_snapshot(db_client, collections.memory_evidence)
    before_rerun_state_head = _required_doc(db_client, collections.memory_state_head)
    before_rerun_operations = _document_ids(db_client, collections.memory_operations)
    before_rerun_commits = _document_ids(db_client, collections.memory_commits)
    before_rerun_outbox = _document_ids(db_client, collections.memory_outbox)
    expected_final_counts = {
        collections.memory_items: 2,
        collections.memory_evidence: 2,
        collections.memory_operations: 2,
        collections.memory_commits: 2,
        collections.memory_outbox: 4,
    }
    for collection_path, expected_count in expected_final_counts.items():
        if len(_document_ids(db_client, collection_path)) != expected_count:
            raise AssertionError(f"unexpected final migration collection count for {collection_path}")
    for memory_id in (home.memory_id, passive.memory_id):
        row = _read_item(db_client, collections, memory_id)
        plan = plan_ledger_migration(row)
        if plan.action != LedgerMigrationAction.no_op:
            raise AssertionError("full rerun attempted to re-plan a migrated row")
        apply_ledger_migration_plan(UID, plan, db_client=db_client)
    after_rerun_control = _required_doc(db_client, collections.memory_apply_control_state)
    if after_rerun_control.get("ledger_migration_migrated_count") != 2:
        raise AssertionError("migration control did not retain the cumulative migrated-row count")
    if after_rerun_control.get("ledger_migration_adjudicated_count") != 0:
        raise AssertionError("migration control unexpectedly counted an adjudicated Short-term row")
    if after_rerun_control != before_rerun_control:
        raise AssertionError("full migration rerun changed canonical control state")
    if _collection_snapshot(db_client, collections.memory_items) != before_rerun_items:
        raise AssertionError("full migration rerun changed persisted memory items")
    if _collection_snapshot(db_client, collections.memory_evidence) != before_rerun_evidence:
        raise AssertionError("full migration rerun changed persisted evidence")
    if _required_doc(db_client, collections.memory_state_head) != before_rerun_state_head:
        raise AssertionError("full migration rerun changed the persisted state head")
    if _document_ids(db_client, collections.memory_operations) != before_rerun_operations:
        raise AssertionError("full migration rerun created a duplicate operation")
    if _document_ids(db_client, collections.memory_commits) != before_rerun_commits:
        raise AssertionError("full migration rerun created a duplicate commit")
    if _document_ids(db_client, collections.memory_outbox) != before_rerun_outbox:
        raise AssertionError("full migration rerun created duplicate outbox events")
    for collection_path, expected_count in expected_final_counts.items():
        if len(_document_ids(db_client, collection_path)) != expected_count:
            raise AssertionError(f"full migration rerun changed final collection count for {collection_path}")
    if read_ledger_migration_completion(UID, db_client=db_client) is not None:
        raise AssertionError("migration emulator harness must not write a completion marker")

    print(
        "PASS: Firestore emulator migration proof "
        "rows=2 migrated=2 cumulative_migrated=2 resumed=2 provenance_complete=2 "
        f"profile_sha256={profile_sha256} final_commit_sequence={after_rerun_control['commit_sequence']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
