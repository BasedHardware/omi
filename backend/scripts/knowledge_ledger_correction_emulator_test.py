#!/usr/bin/env python3
"""Prove explicit ledger correction/revert and retry semantics on Firestore emulator only."""

from __future__ import annotations

# ruff: noqa: E402 -- emulator safety/env bootstrapping must precede backend imports.

import os
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
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
from fastapi import HTTPException

from database.memory_apply_store import tombstone_memory_items_firestore
from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState, WriterMode
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryKind, MemorySubjectScope
from utils.memory.knowledge_ledger import LedgerProvenance, LedgerWrite, close_fact, save_ledger_write
from utils.memory.knowledge_ledger_migration import rollback_ledger_writer_to_compatibility
from utils.memory import memory_service as memory_service_module
from utils.memory.memory_service import MemoryService
from models.product_memory import LedgerWriteReason

NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)
INITIAL_HEAD = "ledger-correction-emulator-head"
ORIGINAL_CONTENT = "Lives in Boston"
CORRECTED_CONTENT = "Lives in Brooklyn"
REVERT_OPERATION_ID = "5f95a7a1-10c6-4ec3-946d-e76a0a2f7cc5"
RACING_REVERT_OPERATION_ID = "e23f4058-49c3-4783-a750-377cfd9979b1"
STANDALONE_REOPEN_OPERATION_ID = "a5cb390c-17f2-44db-a303-c6a7453b4975"
STANDALONE_REOPEN_COMPETING_OPERATION_ID = "6a6164a0-46e9-4c96-92b0-95f63f7e76a9"
STANDALONE_CONCURRENT_REOPEN_OPERATION_IDS = (
    "26c4c933-da46-43d7-b2b7-e3d26e6e3fc6",
    "3776d38f-b4e3-4639-b7f8-9bcf38d5bdef",
)
STANDALONE_PRIVACY_REOPEN_OPERATION_ID = "27a1ab89-b5e3-42f3-9d6a-d07e53bb8d49"


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
        "reopens": _collection_snapshot(db_client, collections.memory_ledger_reopens),
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
            writer_mode=WriterMode.ledger,
            writer_epoch=1,
            commit_sequence=0,
            updated_at=NOW,
        )
        db_client.document(collections.memory_apply_control_state).set(_stored_model(control))
        prior_id = save_ledger_write(
            uid,
            LedgerWrite(
                kind=MemoryKind.fact,
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
        rolled_back = rollback_ledger_writer_to_compatibility(
            uid,
            db_client=db_client,
            rollback_authorizer=lambda: True,
            completed_at=NOW,
        )
        if rolled_back.writer_mode != WriterMode.compatibility or rolled_back.writer_epoch != 2:
            raise AssertionError("correction harness did not enter bridge compatibility mode")
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

        before_revert = _authority_snapshot(db_client, collections)
        restored_authoritative = service.revert_superseded_ledger_fact(uid, prior_id, REVERT_OPERATION_ID)
        after_revert = _authority_snapshot(db_client, collections)
        restored_id = restored_authoritative.id
        prior_after_revert = _read_item(db_client, collections, prior_id)
        corrected_after_revert = _read_item(db_client, collections, replacement_id)
        restored = _read_item(db_client, collections, restored_id)

        if restored_id in {prior_id, replacement_id} or set(after_revert["items"]) != {
            prior_id,
            replacement_id,
            restored_id,
        }:
            raise AssertionError("revert did not append exactly one fresh lineage row")
        if len(after_revert["operations"]) != len(before_revert["operations"]) + 1:
            raise AssertionError("revert did not add exactly one canonical operation")
        if len(after_revert["commits"]) != len(before_revert["commits"]) + 1:
            raise AssertionError("revert did not add exactly one canonical commit")
        if after_revert["control"]["commit_sequence"] != before_revert["control"]["commit_sequence"] + 1:
            raise AssertionError("revert did not advance canonical sequence exactly once")
        revert_head = after_revert["control"]["head_commit_id"]
        revert_commit = after_revert["commits"].get(revert_head)
        if revert_commit is None or set(revert_commit.get("memory_item_ids") or []) != {
            replacement_id,
            restored_id,
        }:
            raise AssertionError("single revert commit does not contain the prior tail and restored row")
        new_revert_operation_ids = set(after_revert["operations"]) - set(before_revert["operations"])
        if len(new_revert_operation_ids) != 1:
            raise AssertionError("revert did not create exactly one operation receipt")
        revert_operation_id = next(iter(new_revert_operation_ids))
        if revert_commit.get("operation_id") != revert_operation_id:
            raise AssertionError("revert commit is not joined to its one operation")
        new_revert_outbox_ids = set(after_revert["outbox"]) - set(before_revert["outbox"])
        if set(revert_commit.get("outbox_event_ids") or []) != new_revert_outbox_ids:
            raise AssertionError("revert commit does not identify exactly its outbox events")
        if {
            after_revert["outbox"][event_id].get("payload", {}).get("action") for event_id in new_revert_outbox_ids
        } != {
            "upsert",
            "delete",
        }:
            raise AssertionError("revert outbox is not the exact restored-upsert/prior-tail-delete pair")
        if prior_after_revert != prior_after:
            raise AssertionError("revert mutated the selected historical row")
        if (
            corrected_after_revert.status != MemoryItemStatus.superseded
            or corrected_after_revert.superseded_by != restored_id
            or corrected_after_revert.valid_to is None
        ):
            raise AssertionError("revert did not supersede the current tail")
        if (
            restored.status != MemoryItemStatus.active
            or restored.content != ORIGINAL_CONTENT
            or restored.valid_to is not None
            or restored.superseded_by
            or restored.visibility != replacement.visibility
            or restored.slot != prior_after.slot
            or restored.subject_scope != prior_after.subject_scope
            or restored.subject_entity_id != prior_after.subject_entity_id
            or restored.curation_weight != prior_after.curation_weight
        ):
            raise AssertionError("revert did not restore selected authority fields on a fresh current row")
        revert_evidence = [
            evidence
            for evidence in restored.evidence
            if evidence.source_type == "explicit_user_revert" and evidence.source_id == prior_id
        ]
        if len(revert_evidence) != 1:
            raise AssertionError("restored row lacks exactly one explicit-user revert evidence record")
        if revert_evidence[0].source_version != f"item_revision:{prior_after.item_revision}":
            raise AssertionError("revert evidence does not name the selected historical revision")
        if (
            not revert_evidence[0].artifact_refs
            or revert_evidence[0].artifact_refs[0].artifact_id != f"memory-history-revert:{REVERT_OPERATION_ID}"
        ):
            raise AssertionError("revert evidence does not preserve the client operation identity")

        before_revert_retry = _authority_snapshot(db_client, collections)
        restored_retry = service.revert_superseded_ledger_fact(uid, prior_id, REVERT_OPERATION_ID)
        after_revert_retry = _authority_snapshot(db_client, collections)
        if restored_retry.id != restored_id:
            raise AssertionError("revert retry did not return the same current append")
        if after_revert_retry != before_revert_retry:
            raise AssertionError(
                "revert retry changed canonical rows, evidence, operations, commits, outbox, or control"
            )
        if observed_invalidation.call_args_list != [((uid,), {}), ((uid,), {}), ((uid,), {}), ((uid,), {})]:
            raise AssertionError("correction/revert and their retries did not invalidate prompt caches")

        before_privacy_race = _authority_snapshot(db_client, collections)
        race_state: dict[str, Any] = {}
        original_amend_fact = memory_service_module.amend_fact

        def tombstone_selected_before_append(*args: Any, **kwargs: Any) -> str:
            selected_before_delete = _read_item(db_client, collections, replacement_id)
            observed_control = MemoryControlState.model_validate(
                _required_doc(db_client, collections.memory_apply_control_state)
            )
            tombstone_memory_items_firestore(
                uid=uid,
                reason="knowledge_ledger_revert_privacy_race",
                observed_control=observed_control,
                expected_items=[selected_before_delete],
                preserved_evidence_ids=[],
                db_client=db_client,
            )
            race_state["after_privacy"] = _authority_snapshot(db_client, collections)
            return original_amend_fact(*args, **kwargs)

        memory_service_module.amend_fact = tombstone_selected_before_append
        try:
            try:
                service.revert_superseded_ledger_fact(uid, replacement_id, RACING_REVERT_OPERATION_ID)
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise AssertionError(f"privacy-raced revert returned unexpected status: {exc.status_code}") from exc
            else:
                raise AssertionError("privacy-raced revert resurrected the selected historical content")
        finally:
            memory_service_module.amend_fact = original_amend_fact

        after_privacy = race_state.get("after_privacy")
        if not isinstance(after_privacy, dict):
            raise AssertionError("privacy race did not execute the selected-row tombstone")
        after_blocked_revert = _authority_snapshot(db_client, collections)
        tombstoned_selected = _read_item(db_client, collections, replacement_id)
        surviving_tail = _read_item(db_client, collections, restored_id)
        if (
            tombstoned_selected.status != MemoryItemStatus.tombstoned
            or tombstoned_selected.content is not None
            or surviving_tail.status != MemoryItemStatus.active
            or surviving_tail.content != ORIGINAL_CONTENT
        ):
            raise AssertionError("privacy race did not leave the selected row tombstoned and current tail intact")
        if set(after_privacy["items"]) != set(before_privacy_race["items"]):
            raise AssertionError("privacy tombstone unexpectedly changed the ledger row set")
        for authority in ("control", "items", "evidence", "commits", "outbox", "state"):
            if after_blocked_revert[authority] != after_privacy[authority]:
                raise AssertionError(f"blocked privacy-raced revert mutated canonical {authority}")
        if after_blocked_revert["operations"] != after_privacy["operations"]:
            raise AssertionError("blocked privacy-raced revert persisted stale content in an operation receipt")
        if observed_invalidation.call_args_list != [
            ((uid,), {}),
            ((uid,), {}),
            ((uid,), {}),
            ((uid,), {}),
        ]:
            raise AssertionError("blocked privacy-raced revert invalidated prompt caches without a commit")

        standalone_source_id = save_ledger_write(
            uid,
            LedgerWrite(
                kind=MemoryKind.fact,
                content="Keeps a winter base in Montreal",
                provenance=LedgerProvenance(
                    source_id="explicit-standalone-seed",
                    source_type="explicit_user_statement",
                    source_version="v1",
                    action_id="ledger-correction-emulator-standalone-seed",
                ),
                write_reason=LedgerWriteReason.direct_user_statement,
                slot="winter_base",
                curation_weight=5,
                visibility="private",
            ),
            db_client=db_client,
        )
        standalone_before_close = _read_item(db_client, collections, standalone_source_id)
        standalone_closed = close_fact(
            uid,
            standalone_source_id,
            valid_to=datetime.now(timezone.utc),
            db_client=db_client,
        )
        if (
            standalone_closed.status != MemoryItemStatus.superseded
            or standalone_closed.valid_to is None
            or standalone_closed.superseded_by
            or standalone_closed.canonical_memory_id
        ):
            raise AssertionError("standalone seed did not become a closed, unlinked ledger row")

        before_standalone_reopen = _authority_snapshot(db_client, collections)
        reopened_authoritative = service.revert_superseded_ledger_fact(
            uid, standalone_source_id, STANDALONE_REOPEN_OPERATION_ID
        )
        after_standalone_reopen = _authority_snapshot(db_client, collections)
        reopened_id = reopened_authoritative.id
        reopened_source = _read_item(db_client, collections, standalone_source_id)
        reopened = _read_item(db_client, collections, reopened_id)
        if reopened_id == standalone_source_id or set(after_standalone_reopen["items"]) != set(
            before_standalone_reopen["items"]
        ) | {reopened_id}:
            raise AssertionError("standalone reopen did not append exactly one new current row")
        if reopened_source != standalone_closed:
            raise AssertionError("standalone reopen mutated the immutable closed source row")
        if len(after_standalone_reopen["reopens"]) != len(before_standalone_reopen["reopens"]) + 1:
            raise AssertionError("standalone reopen did not persist exactly one source receipt")
        if (
            reopened.status != MemoryItemStatus.active
            or reopened.valid_to is not None
            or reopened.superseded_by
            or reopened.canonical_memory_id
            or reopened.content != standalone_before_close.content
            or reopened.slot != standalone_before_close.slot
            or reopened.visibility != standalone_before_close.visibility
            or not any(
                evidence.source_type == "explicit_user_statement" and evidence.source_id == "explicit-standalone-seed"
                for evidence in reopened.evidence
            )
            or not any(
                evidence.source_type == "explicit_user_reopen"
                and evidence.source_id == standalone_source_id
                and evidence.source_version == f"item_revision:{standalone_closed.item_revision}"
                for evidence in reopened.evidence
            )
        ):
            raise AssertionError("standalone reopen did not preserve authority and provenance on the new tail")

        before_standalone_retry = _authority_snapshot(db_client, collections)
        reopened_retry = service.revert_superseded_ledger_fact(
            uid, standalone_source_id, STANDALONE_REOPEN_OPERATION_ID
        )
        after_standalone_retry = _authority_snapshot(db_client, collections)
        if reopened_retry.id != reopened_id or after_standalone_retry != before_standalone_retry:
            raise AssertionError("standalone reopen retry was not an exact canonical no-op")

        before_competing_reopen = _authority_snapshot(db_client, collections)
        try:
            service.revert_superseded_ledger_fact(uid, standalone_source_id, STANDALONE_REOPEN_COMPETING_OPERATION_ID)
        except HTTPException as exc:
            if exc.status_code != 409:
                raise AssertionError(
                    f"competing standalone reopen returned unexpected status: {exc.status_code}"
                ) from exc
        else:
            raise AssertionError("competing standalone reopen created a duplicate current tail")
        after_competing_reopen = _authority_snapshot(db_client, collections)
        if after_competing_reopen != before_competing_reopen:
            raise AssertionError("rejected competing standalone reopen mutated canonical state")

        concurrent_source_id = save_ledger_write(
            uid,
            LedgerWrite(
                kind=MemoryKind.fact,
                content="Keeps a spring base in Reykjavik",
                provenance=LedgerProvenance(
                    source_id="explicit-standalone-concurrent-seed",
                    source_type="explicit_user_statement",
                    source_version="v1",
                    action_id="ledger-correction-emulator-standalone-concurrent-seed",
                ),
                write_reason=LedgerWriteReason.direct_user_statement,
                slot="spring_base",
                curation_weight=5,
                visibility="private",
            ),
            db_client=db_client,
        )
        concurrent_closed = close_fact(
            uid,
            concurrent_source_id,
            valid_to=datetime.now(timezone.utc),
            db_client=db_client,
        )
        before_concurrent_reopen = _authority_snapshot(db_client, collections)
        concurrent_barrier = threading.Barrier(2)
        original_concurrent_reopen = memory_service_module.reopen_standalone_fact

        def synchronize_reopen_transactions(*args: Any, **kwargs: Any) -> str:
            concurrent_barrier.wait(timeout=10)
            return original_concurrent_reopen(*args, **kwargs)

        def run_competing_reopen(operation_id: str) -> tuple[str, str | int]:
            try:
                result = service.revert_superseded_ledger_fact(uid, concurrent_source_id, operation_id)
                return ("committed", result.id)
            except HTTPException as exc:
                return ("rejected", exc.status_code)

        memory_service_module.reopen_standalone_fact = synchronize_reopen_transactions
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                concurrent_results = list(
                    executor.map(run_competing_reopen, STANDALONE_CONCURRENT_REOPEN_OPERATION_IDS)
                )
        finally:
            memory_service_module.reopen_standalone_fact = original_concurrent_reopen

        committed_results = [value for status, value in concurrent_results if status == "committed"]
        rejected_results = [value for status, value in concurrent_results if status == "rejected"]
        if len(committed_results) != 1 or rejected_results != [409]:
            raise AssertionError(f"concurrent standalone reopen did not commit once: {concurrent_results}")
        concurrent_reopened_id = str(committed_results[0])
        after_concurrent_reopen = _authority_snapshot(db_client, collections)
        if set(after_concurrent_reopen["items"]) != set(before_concurrent_reopen["items"]) | {concurrent_reopened_id}:
            raise AssertionError("concurrent standalone reopen did not append exactly one current tail")
        if len(after_concurrent_reopen["reopens"]) != len(before_concurrent_reopen["reopens"]) + 1:
            raise AssertionError("concurrent standalone reopen did not persist exactly one source receipt")
        if _read_item(db_client, collections, concurrent_source_id) != concurrent_closed:
            raise AssertionError("concurrent standalone reopen mutated the immutable closed source row")

        privacy_source_id = save_ledger_write(
            uid,
            LedgerWrite(
                kind=MemoryKind.fact,
                content="Keeps a privacy-raced summer base in Lisbon",
                provenance=LedgerProvenance(
                    source_id="explicit-standalone-privacy-seed",
                    source_type="explicit_user_statement",
                    source_version="v1",
                    action_id="ledger-correction-emulator-standalone-privacy-seed",
                ),
                write_reason=LedgerWriteReason.direct_user_statement,
                slot="summer_base",
                curation_weight=5,
                visibility="private",
            ),
            db_client=db_client,
        )
        privacy_closed = close_fact(
            uid,
            privacy_source_id,
            valid_to=datetime.now(timezone.utc),
            db_client=db_client,
        )
        privacy_evidence_id = privacy_closed.evidence[0].evidence_id
        before_privacy_standalone = _authority_snapshot(db_client, collections)
        privacy_race_state: dict[str, Any] = {}
        original_reopen_fact = memory_service_module.reopen_standalone_fact

        def tombstone_selected_evidence_before_append(*args: Any, **kwargs: Any) -> str:
            evidence_path = f"{collections.memory_evidence}/{privacy_evidence_id}"
            evidence_payload = _required_doc(db_client, evidence_path)
            evidence_payload["redaction_status"] = "tombstoned"
            evidence_payload["encryption_or_redaction_status"] = "tombstoned"
            db_client.document(evidence_path).set(evidence_payload)
            privacy_race_state["after_privacy"] = _authority_snapshot(db_client, collections)
            return original_reopen_fact(*args, **kwargs)

        memory_service_module.reopen_standalone_fact = tombstone_selected_evidence_before_append
        try:
            try:
                service.revert_superseded_ledger_fact(uid, privacy_source_id, STANDALONE_PRIVACY_REOPEN_OPERATION_ID)
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise AssertionError(
                        f"privacy-raced standalone reopen returned unexpected status: {exc.status_code}"
                    ) from exc
            else:
                raise AssertionError("privacy-raced standalone reopen resurrected deleted source evidence")
        finally:
            memory_service_module.reopen_standalone_fact = original_reopen_fact

        after_privacy_standalone = privacy_race_state.get("after_privacy")
        if not isinstance(after_privacy_standalone, dict):
            raise AssertionError("standalone privacy race did not execute the evidence tombstone")
        after_blocked_privacy_standalone = _authority_snapshot(db_client, collections)
        privacy_source_after = _read_item(db_client, collections, privacy_source_id)
        if privacy_source_after != privacy_closed:
            raise AssertionError("standalone evidence privacy race mutated the closed source row")
        if after_blocked_privacy_standalone != after_privacy_standalone:
            raise AssertionError("blocked standalone evidence privacy race mutated canonical state")

        print(
            "PASS: Firestore emulator explicit ledger correction and revert proof "
            f"prior={prior_id} replacement={replacement_id} correction_commit={correction_head} "
            f"restored={restored_id} revert_commit={revert_head} "
            f"standalone_source={standalone_source_id} standalone_reopened={reopened_id} "
            f"preclose_revision={prior_before.item_revision} closed_revision={prior_after.item_revision} "
            "retries=no-op competing_reopen=blocked concurrent_reopen=commit-once "
            "privacy_race=blocked standalone_evidence_race=blocked"
        )
        return 0
    finally:
        _cleanup(db_client, collections)


if __name__ == "__main__":
    raise SystemExit(main())
