#!/usr/bin/env python3
"""Prove explicit ledger correction and retry semantics on Firestore emulator only."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-memory"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ledger_correction_emulator_test_key_32_bytes")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore

from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItem, MemoryItemStatus, MemorySubjectScope
from utils.memory.knowledge_ledger import LedgerProvenance, LedgerWrite, save_ledger_write
from utils.memory.memory_service import MemoryService
from models.product_memory import LedgerWriteReason

NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)
INITIAL_HEAD = "ledger-correction-emulator-head"
ORIGINAL_CONTENT = "Lives in Boston"
CORRECTED_CONTENT = "Lives in Brooklyn"


def _assert_emulator_only() -> None:
    host = (os.environ.get("FIRESTORE_EMULATOR_HOST") or "").strip()
    if not host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"refusing non-loopback Firestore emulator host: {hostname}")
    if not PROJECT_ID.startswith("demo-"):
        raise RuntimeError(f"refusing non-demo Firestore project: {PROJECT_ID}")


def _stored_model(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _required_doc(db_client: Any, path: str) -> dict[str, Any]:
    snapshot = db_client.document(path).get()
    if not snapshot.exists:
        raise AssertionError(f"missing expected Firestore document: {path}")
    return snapshot.to_dict() or {}


def _read_item(db_client: Any, collections: MemoryCollections, memory_id: str) -> MemoryItem:
    return MemoryItem.model_validate(_required_doc(db_client, f"{collections.memory_items}/{memory_id}"))


def _collection_snapshot(db_client: Any, collection_path: str) -> dict[str, dict[str, Any]]:
    return {snapshot.id: snapshot.to_dict() or {} for snapshot in db_client.collection(collection_path).stream()}


def _authority_snapshot(db_client: Any, collections: MemoryCollections) -> dict[str, Any]:
    return {
        "control": _required_doc(db_client, collections.memory_apply_control_state),
        "items": _collection_snapshot(db_client, collections.memory_items),
        "evidence": _collection_snapshot(db_client, collections.memory_evidence),
        "operations": _collection_snapshot(db_client, collections.memory_operations),
        "commits": _collection_snapshot(db_client, collections.memory_commits),
        "outbox": _collection_snapshot(db_client, collections.memory_outbox),
        "state": _collection_snapshot(db_client, collections.memory_state),
    }


def _cleanup(db_client: Any, collections: MemoryCollections) -> None:
    for collection_path in reversed(collections.all_collection_paths()):
        for snapshot in db_client.collection(collection_path).stream():
            snapshot.reference.delete()
    db_client.document(collections.user_root).delete()
    leftovers = {
        path: sorted(_collection_snapshot(db_client, path))
        for path in collections.all_collection_paths()
        if _collection_snapshot(db_client, path)
    }
    if leftovers:
        raise AssertionError(f"emulator cleanup left synthetic documents: {leftovers}")


def main() -> int:
    _assert_emulator_only()
    uid = f"knowledge-ledger-correction-emulator-{uuid.uuid4().hex}"
    collections = MemoryCollections(uid=uid)
    db_client: Any = firestore.Client(project=PROJECT_ID)

    try:
        control = MemoryControlState(
            uid=uid,
            head_commit_id=INITIAL_HEAD,
            account_generation=11,
            source_generation=13,
            commit_sequence=0,
            updated_at=NOW,
        )
        db_client.document(collections.memory_apply_control_state).set(_stored_model(control))
        prior_id = save_ledger_write(
            uid,
            LedgerWrite(
                kind="fact",
                content=ORIGINAL_CONTENT,
                provenance=LedgerProvenance(
                    source_id="explicit-seed",
                    source_type="explicit_user_statement",
                    source_version="v1",
                    action_id="ledger-correction-emulator-seed",
                ),
                write_reason=LedgerWriteReason.direct_user_statement,
                slot="home_city",
                subject_scope=MemorySubjectScope.third_party,
                subject_entity_id="person:sam",
                curation_weight=17,
                visibility="shared",
            ),
            db_client=db_client,
        )
        prior_before = _read_item(db_client, collections, prior_id)
        before = _authority_snapshot(db_client, collections)

        service = MemoryService(db_client=db_client)
        observed_invalidation = Mock()
        service._invalidate_prompt_cache = observed_invalidation  # type: ignore[method-assign]
        authoritative = service.update_content(uid, prior_id, CORRECTED_CONTENT)

        after = _authority_snapshot(db_client, collections)
        replacement_id = authoritative.id
        prior_after = _read_item(db_client, collections, prior_id)
        replacement = _read_item(db_client, collections, replacement_id)

        if replacement_id == prior_id or set(after["items"]) != {prior_id, replacement_id}:
            raise AssertionError("correction did not append exactly one replacement row")
        if len(after["operations"]) != len(before["operations"]) + 1:
            raise AssertionError("correction did not add exactly one canonical operation")
        if len(after["commits"]) != len(before["commits"]) + 1:
            raise AssertionError("correction did not add exactly one canonical commit")
        if after["control"]["commit_sequence"] != before["control"]["commit_sequence"] + 1:
            raise AssertionError("correction did not advance canonical sequence exactly once")
        correction_head = after["control"]["head_commit_id"]
        if correction_head == before["control"]["head_commit_id"]:
            raise AssertionError("correction did not advance the canonical head")
        if set(after["commits"]) - set(before["commits"]) != {correction_head}:
            raise AssertionError("canonical head does not identify the single new correction commit")
        correction_commit = after["commits"].get(correction_head)
        if correction_commit is None or set(correction_commit.get("memory_item_ids") or []) != {
            prior_id,
            replacement_id,
        }:
            raise AssertionError("single correction commit does not contain both lineage rows")
        new_operation_ids = set(after["operations"]) - set(before["operations"])
        if len(new_operation_ids) != 1:
            raise AssertionError("correction did not create exactly one operation receipt")
        correction_operation_id = next(iter(new_operation_ids))
        correction_operation = after["operations"][correction_operation_id]
        if correction_commit.get("operation_id") != correction_operation_id:
            raise AssertionError("correction commit is not joined to its one operation")
        if correction_operation.get("committed_head_commit_id") != correction_head or set(
            correction_operation.get("committed_memory_item_ids") or []
        ) != {prior_id, replacement_id}:
            raise AssertionError("correction operation does not commit both lineage rows under the new head")
        new_outbox_ids = set(after["outbox"]) - set(before["outbox"])
        if not new_outbox_ids:
            raise AssertionError("correction commit did not persist any outbox events")
        if set(correction_commit.get("outbox_event_ids") or []) != new_outbox_ids:
            raise AssertionError("correction commit does not identify exactly its outbox events")
        if any(
            after["outbox"][event_id].get("commit_id") != correction_head
            or after["outbox"][event_id].get("operation_id") != correction_operation_id
            for event_id in new_outbox_ids
        ):
            raise AssertionError("correction outbox events are not joined to the one operation and commit")
        if {after["outbox"][event_id].get("payload", {}).get("action") for event_id in new_outbox_ids} != {
            "upsert",
            "delete",
        }:
            raise AssertionError("correction outbox is not the exact replacement-upsert/prior-delete pair")

        if prior_after.status != MemoryItemStatus.superseded or prior_after.superseded_by != replacement_id:
            raise AssertionError("prior row was not superseded by the authoritative replacement")
        if prior_after.valid_to is None or prior_after.item_revision != prior_before.item_revision + 1:
            raise AssertionError("prior row closure did not advance its revision exactly once")
        if (
            replacement.valid_to is not None
            or replacement.superseded_by
            or replacement.valid_from is None
            or prior_after.valid_to < replacement.valid_from
        ):
            raise AssertionError("prior/replacement validity windows do not form an exact active lineage")
        if prior_after.ledger_commit_id != correction_head or replacement.ledger_commit_id != correction_head:
            raise AssertionError("both lineage rows were not persisted under the one correction commit")
        if replacement.status != MemoryItemStatus.active or replacement.content != CORRECTED_CONTENT:
            raise AssertionError("replacement is not the active corrected fact")
        preserved = (
            replacement.slot,
            replacement.subject_scope,
            replacement.subject_entity_id,
            replacement.curation_weight,
            replacement.visibility,
        )
        expected = (
            prior_before.slot,
            prior_before.subject_scope,
            prior_before.subject_entity_id,
            prior_before.curation_weight,
            prior_before.visibility,
        )
        if preserved != expected:
            raise AssertionError(f"replacement lost fact authority fields: {preserved!r} != {expected!r}")
        correction_evidence = [
            evidence
            for evidence in replacement.evidence
            if evidence.source_type == "explicit_user_correction" and evidence.source_id == prior_id
        ]
        if len(correction_evidence) != 1:
            raise AssertionError("replacement lacks exactly one explicit-user correction evidence record")
        if correction_evidence[0].source_version != f"item_revision:{prior_before.item_revision}":
            raise AssertionError("correction evidence does not name the pre-close revision")
        if authoritative.id != replacement.memory_id or authoritative.content != replacement.content:
            raise AssertionError("MemoryService did not return the authoritative persisted replacement")
        observed_invalidation.assert_called_once_with(uid)

        before_retry = _authority_snapshot(db_client, collections)
        retried = service.update_content(uid, prior_id, CORRECTED_CONTENT)
        after_retry = _authority_snapshot(db_client, collections)
        if retried.id != replacement_id:
            raise AssertionError("retry on the original ID did not return the same replacement")
        if after_retry != before_retry:
            raise AssertionError("retry changed canonical rows, evidence, operations, commits, outbox, or control")
        if observed_invalidation.call_args_list != [((uid,), {}), ((uid,), {})]:
            raise AssertionError("correction and idempotent retry did not both invalidate prompt caches")

        print(
            "PASS: Firestore emulator explicit ledger correction proof "
            f"prior={prior_id} replacement={replacement_id} correction_commit={correction_head} "
            f"preclose_revision={prior_before.item_revision} closed_revision={prior_after.item_revision} retry=no-op"
        )
        return 0
    finally:
        _cleanup(db_client, collections)


if __name__ == "__main__":
    raise SystemExit(main())
