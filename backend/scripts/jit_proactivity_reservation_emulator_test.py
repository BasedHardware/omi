#!/usr/bin/env python3
"""Real Firestore contention proof for cross-device JIT work admission."""

from __future__ import annotations

import hashlib
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from typing import Any

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-memory"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import google.cloud.firestore as firestore

from database.jit_proactivity_store import JITProactivityReservationError, reserve_jit_proactivity_event
from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)

NOW = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _reserve_once(barrier: Barrier, uid: str, event_label: str, **kwargs: Any) -> str:
    client: Any = firestore.Client(project=PROJECT_ID)
    barrier.wait(timeout=15)
    try:
        _, reserved = reserve_jit_proactivity_event(
            uid,
            event_id=_digest(event_label),
            now=NOW,
            db_client=client,
            **kwargs,
        )
    except JITProactivityReservationError:
        return "rejected"
    return "reserved" if reserved else "replayed"


def _run_pair(uid: str, prefix: str, **kwargs: Any) -> list[str]:
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_reserve_once, barrier, uid, f"{prefix}-{index}", **kwargs) for index in range(2)]
        return [future.result(timeout=30) for future in futures]


def main() -> int:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")

    uid = f"jit-proactivity-emulator-{uuid.uuid4().hex}"
    collections = MemoryCollections(uid=uid)
    client: Any = firestore.Client(project=PROJECT_ID)
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head-1",
        account_generation=1,
        source_generation=1,
    )
    trigger = MemoryItem(
        memory_id="trigger-1",
        uid=uid,
        version=1,
        tier=MemoryLayer.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Release trigger",
        evidence=[
            MemoryEvidence(
                evidence_id="evidence-1",
                source_type="chat_turn",
                source_id="turn-1",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=True,
        captured_at=NOW,
        updated_at=NOW,
        ledger_commit_id="head-1",
        ledger_sequence=1,
        account_generation=1,
        ledger_schema_version="knowledge_ledger.v1",
        kind=MemoryKind.trigger,
        subject_scope=MemorySubjectScope.primary_user,
        trigger_condition={
            "keywords": ["release"],
            "action": {"type": "agent_prompt", "prompt": "Find the next release step."},
        },
        arguments={"wakeup_budget_per_day": 1},
        intent_backed=True,
        write_reason=LedgerWriteReason.standing_trigger,
    )
    client.document(f"users/{uid}").set({"time_zone": "UTC"}, merge=True)
    client.document(collections.memory_apply_control_state).set(control.model_dump(mode="python"))
    client.document(f"{collections.memory_items}/{trigger.memory_id}").set(trigger.model_dump(mode="python"))

    planned = _run_pair(
        uid,
        "planned",
        candidate_id=_digest("planned-candidate"),
        operation="planned_notification",
        account_generation=1,
        device_id=_digest("shared-device"),
        trigger_memory_id=trigger.memory_id,
        trigger_revision=trigger.item_revision,
    )
    if sorted(planned) != ["rejected", "reserved"]:
        raise AssertionError(f"planned-notification contention did not serialize: {planned}")

    parent_event_id = _digest("ambient-parent")
    parent, reserved = reserve_jit_proactivity_event(
        uid,
        event_id=parent_event_id,
        candidate_id=_digest("full-turn-candidate"),
        operation="ambient_notification",
        account_generation=1,
        device_id=_digest("shared-device"),
        now=NOW,
        db_client=client,
    )
    if not reserved:
        raise AssertionError("ambient notification parent was not reserved")
    full_turns = _run_pair(
        uid,
        "full-turn",
        candidate_id=parent.candidate_id,
        operation="full_turn",
        account_generation=1,
        device_id=parent.device_id,
        parent_event_id=parent.event_id,
    )
    if sorted(full_turns) != ["rejected", "reserved"]:
        raise AssertionError(f"full-turn candidate contention did not serialize: {full_turns}")

    budget = client.document(f"{collections.jit_proactivity_daily_budgets}/2026-08-24").get().to_dict() or {}
    if budget.get("total_notifications") != 2 or budget.get("full_turns") != 1:
        raise AssertionError(f"contention left an invalid daily budget: {budget}")
    if budget.get("planned_by_trigger") != {trigger.memory_id: 1}:
        raise AssertionError(f"contention left an invalid per-trigger budget: {budget}")
    candidate = client.document(f"{collections.jit_proactivity_candidate_turns}/{parent.candidate_id}").get().to_dict()
    if not isinstance(candidate, dict) or candidate.get("parent_event_id") != parent.event_id:
        raise AssertionError("winning full-turn candidate receipt was not committed atomically")

    print(
        "PASS: Firestore emulator serialized cross-device JIT planned-notification and full-turn contention "
        f"(uid={uid}, planned={planned}, full_turns={full_turns})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
