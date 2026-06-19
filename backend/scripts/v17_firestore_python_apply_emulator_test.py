#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-v17-memory"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import google.cloud.firestore as firestore

from database.v17_collections import V17Collections
from database.v17_memory_apply_store import apply_long_term_patch_firestore
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence
from models.v17_memory_apply import ApplyStatus, MemoryControlState
from models.v17_memory_contracts import DurablePatchDecision, LifecycleState
from models.v17_memory_operations import MemoryOperation, MemoryOperationType


def _stored_model(model):
    return model.model_dump(mode="json")


def _required_doc(db_client, path):
    snapshot = db_client.document(path).get()
    if not snapshot.exists:
        raise AssertionError(f"missing expected Firestore document: {path}")
    return snapshot.to_dict() or {}


def main() -> int:
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not emulator_host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")

    uid = "v17-python-apply-emulator-user"
    collections = V17Collections(uid=uid)
    db_client = firestore.Client(project=PROJECT_ID)

    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=3, source_generation=5)
    evidence = MemoryEvidence(
        evidence_id="ev-python-apply-1",
        source_type="conversation",
        source_id="conv-python-apply-1",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    logical_payload = {
        "decision": "add",
        "memory_text": "User prefers concise Python emulator validation updates.",
        "result_status": "active",
    }
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id="packet-python-apply-1",
        target_memory_id=None,
        evidence_ids=[evidence.evidence_id],
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    patch_payload = {
        "patch_id": "patch-python-apply-1",
        "packet_id": "packet-python-apply-1",
        "run_id": "run-python-apply-1",
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": "idem-python-apply-1",
        "decision": DurablePatchDecision.add.value,
        "result_status": LifecycleState.active.value,
        "evidence_ids": [evidence.evidence_id],
        "memory_text": logical_payload["memory_text"],
        "confidence": "medium",
        "relationship_to_user": "self",
        "subject_entity_id": "user",
        "subject_label": "the user",
        "aboutness": "primary_user",
    }

    db_client.document(collections.memory_control_state).set(_stored_model(control))
    db_client.document(f"{collections.memory_evidence}/{evidence.evidence_id}").set(_stored_model(evidence))
    db_client.document(f"{collections.memory_operations}/{operation.operation_id}").set(_stored_model(operation))

    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=db_client,
    )
    if result.status != ApplyStatus.committed:
        raise AssertionError(f"expected committed apply result, got {result.status}: {result.reason}")
    if len(result.memory_items) != 1:
        raise AssertionError(f"expected one materialized memory item, got {len(result.memory_items)}")
    if len(result.outbox_events) != 2:
        raise AssertionError(f"expected two outbox events, got {len(result.outbox_events)}")

    stored_control = _required_doc(db_client, collections.memory_control_state)
    stored_operation = _required_doc(db_client, f"{collections.memory_operations}/{operation.operation_id}")
    stored_memory = _required_doc(db_client, f"{collections.memory_items}/{result.memory_items[0].memory_id}")
    stored_commit = _required_doc(db_client, f"{collections.memory_commits}/{result.control_state.head_commit_id}")
    stored_outbox = [
        _required_doc(db_client, f"{collections.memory_outbox}/{event.event_id}") for event in result.outbox_events
    ]

    if stored_control["head_commit_id"] != result.control_state.head_commit_id:
        raise AssertionError("control head did not advance to committed head")
    if stored_operation["status"] != "committed":
        raise AssertionError("operation replay metadata was not committed")
    if stored_operation["committed_head_commit_id"] != result.control_state.head_commit_id:
        raise AssertionError("operation committed head mismatch")
    if stored_memory["uid"] != uid or stored_memory["ledger_commit_id"] != result.control_state.head_commit_id:
        raise AssertionError("materialized memory item does not reference committed ledger head")
    if stored_memory["account_generation"] != control.account_generation:
        raise AssertionError("materialized memory item lost account generation fence")
    if stored_commit["memory_item_ids"] != [result.memory_items[0].memory_id]:
        raise AssertionError("commit document did not record materialized memory identity")
    if sorted(event["event_type"] for event in stored_outbox) != ["projection_sync", "vector_sync"]:
        raise AssertionError("outbox did not contain projection and vector sync events")

    retry = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=db_client,
    )
    if retry.status != ApplyStatus.idempotent_skip:
        raise AssertionError(f"expected idempotent replay on retry, got {retry.status}")
    if retry.operation.committed_memory_item_ids != [result.memory_items[0].memory_id]:
        raise AssertionError("retry did not return stored committed memory item metadata")

    print(
        "PASS: Python apply_long_term_patch_firestore committed and replayed V17 docs on Firestore emulator "
        f"(uid={uid}, operation={operation.operation_id}, commit={result.control_state.head_commit_id})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
