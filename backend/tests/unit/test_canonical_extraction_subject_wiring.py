"""GAP 1: subject_entity_id / predicate / arguments persist through canonical extraction."""

from __future__ import annotations

import os
import importlib
from datetime import datetime, timezone
from unittest.mock import patch
import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from database.entities import USER_ENTITY_ID
from models.memories import Memory, MemoryCategory, MemoryDB, SubjectAttribution
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItemStatus, MemoryTier
from utils.memory.canonical_memory_adapter import (
    extraction_memory_id,
    read_canonical_memories,
    write_canonical_extraction_memory,
    write_canonical_external_memory,
)
from utils.memory.canonical_kg_promotion import extract_kg_for_promoted_memory
from utils.memory.memory_service import MemoryService
from utils.memory.required_promotion import required_processing_payload
from utils.client_device import DeviceScopeRequest
from tests.unit.fixtures.canonical_memory_fakes import _FakeDb, _trusted_account_generation


def _refresh_canonical_runtime() -> None:
    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    kg_promotion = importlib.import_module("utils.memory.canonical_kg_promotion")
    globals().update(
        {
            "read_canonical_memories": canonical_adapter.read_canonical_memories,
            "write_canonical_extraction_memory": canonical_adapter.write_canonical_extraction_memory,
            "write_canonical_external_memory": canonical_adapter.write_canonical_external_memory,
            "extract_kg_for_promoted_memory": kg_promotion.extract_kg_for_promoted_memory,
        }
    )


@pytest.fixture(autouse=True)
def _refresh_canonical_runtime_fixture():
    _refresh_canonical_runtime()


def _control_seed(uid: str) -> dict:
    return {
        f"users/{uid}/memory_state/apply_control": MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
        ).model_dump(mode="json"),
    }


def _rollout_control_doc(uid: str) -> dict:
    return {
        "uid": uid,
        "schema_version": 1,
        "mode": "write",
        "mode_epoch": 1,
        "cutover_epoch": 0,
        "account_generation": 1,
        "fallback_projection_ready": False,
        "persistent_memory_writes_started": True,
        "decommission_reconciled": False,
        "writes_blocked": False,
        "stage_gates": {"shadow": "passed", "write": "passed", "read": "blocked"},
        "grants": {"omi_chat": {"default_memory": False, "archive": False}},
        "vector_repair_outbox_enabled": False,
    }


@pytest.fixture
def monkeypatch_trusted_account(monkeypatch):
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )


def test_memory_service_write_persists_subject_and_predicate(monkeypatch_trusted_account):
    uid = "uid-subject-wire"
    conversation_id = "conv-subject"
    content = "User lives in San Francisco"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    memory = Memory(content=content, category=MemoryCategory.interesting)
    memory_db = MemoryDB.from_memory(
        memory,
        uid,
        conversation_id,
        False,
        subject_entity_id=USER_ENTITY_ID,
        subject_attribution=SubjectAttribution.user,
    )
    memory_db.id = "mem_subject_test"
    memory_db.memory_tier = MemoryTier.short_term
    memory_db.created_at = now
    memory_db.updated_at = now

    payload = memory_db.model_dump(mode="json")
    assert payload.get("subject_entity_id") == USER_ENTITY_ID

    db = _FakeDb(_control_seed(uid))
    service = MemoryService(db_client=db)
    service.write(uid, payload)

    items = read_canonical_memories(uid, db_client=db)
    assert len(items) == 1
    stored = db.docs[f"users/{uid}/memory_items/{items[0].id}"]
    assert stored["subject_entity_id"] == USER_ENTITY_ID
    assert stored["predicate"] == "resides_in"
    assert stored["arguments"] == {"location": "San Francisco"}


def test_memory_service_write_round_trips_locked_state(monkeypatch_trusted_account):
    uid = "uid-lock-wire"
    memory_db = MemoryDB.from_memory(
        Memory(content="Locked canonical secret", category=MemoryCategory.interesting),
        uid,
        "conv-lock-wire",
        False,
    )
    memory_db.id = "mem_lock_wire"
    memory_db.memory_tier = MemoryTier.short_term
    memory_db.is_locked = True
    db = _FakeDb(_control_seed(uid))
    service = MemoryService(db_client=db)

    service.write(uid, memory_db.model_dump(mode="json"))

    stored = db.docs[f"users/{uid}/memory_items/{memory_db.id}"]
    assert stored["promotion"]["is_locked"] is True
    canonical = read_canonical_memories(uid, db_client=db)
    assert len(canonical) == 1
    assert canonical[0].is_locked is True


def test_extraction_memory_id_is_deterministic_and_partitions_non_user_subjects():
    identity = {
        "uid": "uid-subject-id",
        "source_id": "conv-subject-id",
        "content": "Prefers tea",
    }

    alice_id = extraction_memory_id(**identity, subject_entity_id="person:alice")
    bob_id = extraction_memory_id(**identity, subject_entity_id="person:bob")

    assert alice_id == extraction_memory_id(**identity, subject_entity_id="person:alice")
    assert alice_id != bob_id
    assert extraction_memory_id(**identity, subject_entity_id=USER_ENTITY_ID) == extraction_memory_id(**identity)


def test_canonical_manual_memory_matches_its_request_device(monkeypatch_trusted_account):
    uid = "uid-manual-device-wire"
    device_id = "macos_a1b2c3d4"
    memory_db = MemoryDB.from_memory(
        Memory(content="User explicitly prefers dark mode", category=MemoryCategory.manual),
        uid,
        None,
        True,
        client_device_id=device_id,
    )
    memory_db.id = "mem_manual_device_wire"
    db = _FakeDb(_control_seed(uid))
    service = MemoryService(db_client=db)

    service.write(
        uid,
        required_processing_payload(memory_db.model_dump(mode="json"), source_surface="v3_manual"),
    )

    current_device = read_canonical_memories(
        uid,
        db_client=db,
        device_scope_request=DeviceScopeRequest(device_scope="current", client_device_id=device_id),
        include_pending_processing=True,
    )
    another_device = read_canonical_memories(
        uid,
        db_client=db,
        device_scope_request=DeviceScopeRequest(device_scope="current", client_device_id="ios_deadbeef"),
        include_pending_processing=True,
    )

    assert [memory.id for memory in current_device] == [memory_db.id]
    assert another_device == []


def test_write_mode_rollout_doc_does_not_collide_with_apply_control_state(monkeypatch_trusted_account):
    uid = "uid-rollout-doc-present"
    payload = {
        "id": "mem_rollout_collision",
        "uid": uid,
        "content": "Canonical write works with rollout state present",
        "conversation_id": "conv-rollout-collision",
        "memory_tier": MemoryTier.short_term.value,
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }
    db = _FakeDb({f"users/{uid}/memory_control/state": _rollout_control_doc(uid)})
    service = MemoryService(db_client=db)

    service.write(uid, payload)

    apply_control = db.docs[f"users/{uid}/memory_state/apply_control"]
    rollout_control = db.docs[f"users/{uid}/memory_control/state"]
    assert apply_control["head_commit_id"] != "head0"
    assert apply_control["source_generation"] == 1
    assert rollout_control["mode"] == "write"
    assert rollout_control["stage_gates"]["read"] == "blocked"
    assert f"users/{uid}/memory_items/mem_rollout_collision" in db.docs


def test_kg_promotion_uses_stored_subject_entity_id(monkeypatch_trusted_account):
    from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
    from models.product_memory import MemoryItem, ProcessingState

    item = MemoryItem(
        memory_id="mem_lt",
        uid="uid-kg",
        version=1,
        tier=MemoryTier.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="lives in San Francisco",
        evidence=[
            MemoryEvidence(
                evidence_id="ev1",
                source_id="conv-1",
                source_type="conversation",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        expires_at=None,
        ledger_commit_id="c1",
        ledger_sequence=1,
        item_revision=1,
        source_commit_id="c1",
        content_hash="hash",
        account_generation=1,
        subject_entity_id=USER_ENTITY_ID,
        predicate="resides_in",
        arguments={"location": "San Francisco"},
        kg_extracted=False,
    )
    with (
        patch("utils.memory.canonical_kg_promotion.ensure_canonical_apply_control_state"),
        patch(
            "utils.memory.canonical_kg_promotion.extract_knowledge_from_memory",
            return_value={"nodes": [{}], "edges": []},
        ) as mock_extract,
        patch("utils.memory.canonical_kg_promotion.set_canonical_memory_kg_extracted"),
    ):
        assert extract_kg_for_promoted_memory("uid-kg", item).success is True
        mock_extract.assert_called_once()
        kg_content = mock_extract.call_args[0][1]
        assert kg_content == f"[{USER_ENTITY_ID}] resides_in (location=San Francisco): lives in San Francisco"


def test_write_canonical_extraction_memory_threads_explicit_triple_fields(monkeypatch_trusted_account):
    uid = "uid-explicit"
    conversation_id = "conv-explicit"
    content = "Prefers dark mode"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    payload = {
        "id": "mem_explicit",
        "uid": uid,
        "content": content,
        "conversation_id": conversation_id,
        "subject_entity_id": USER_ENTITY_ID,
        "predicate": "prefers",
        "arguments": {"thing": "dark mode"},
        "memory_tier": MemoryTier.short_term.value,
        "created_at": now,
        "updated_at": now,
        "evidence": [
            {
                "evidence_id": "ev1",
                "source_id": conversation_id,
                "source_type": "conversation",
                "source_signal": "transcription",
                "extractor_id": "test",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": conversation_id,
                "redaction_status": "active",
                "created_at": now,
            }
        ],
    }
    write_canonical_extraction_memory(uid, payload, db_client=db)
    stored = db.docs[f"users/{uid}/memory_items/mem_explicit"]
    assert stored["subject_entity_id"] == USER_ENTITY_ID
    assert stored["predicate"] == "prefers"
    assert stored["arguments"] == {"thing": "dark mode"}


def test_extraction_write_does_not_default_third_party_to_primary_user(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    uid = "uid-scope"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    payload = {
        "id": "mem_third_party",
        "uid": uid,
        "content": "Sam is a teammate on the launch",
        "conversation_id": "conv-scope",
        "subject_attribution": "third_party",
        "belief_class": "relationship",
        "memory_tier": MemoryTier.short_term.value,
        "created_at": now,
        "updated_at": now,
        "evidence": [
            {
                "evidence_id": "ev-scope",
                "source_id": "conv-scope",
                "source_type": "conversation",
                "source_signal": "transcription",
                "extractor_id": "test",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": "conv-scope",
                "redaction_status": "active",
                "created_at": now,
            }
        ],
    }
    write_canonical_extraction_memory(uid, payload, db_client=db)
    stored = db.docs[f"users/{uid}/memory_items/mem_third_party"]
    assert stored["subject_scope"] == "third_party"
    assert stored["belief_class"] == "relationship"
    assert stored.get("half_life_days") is None


def test_extraction_write_stores_named_date_valid_to_from_invalid_at(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    uid = "uid-valid-to"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    valid_to = datetime(2026, 12, 15, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    payload = {
        "id": "mem_named_date",
        "uid": uid,
        "content": "Ship the launch on Friday",
        "conversation_id": "conv-valid-to",
        "subject_attribution": "user",
        "belief_class": "plan",
        "invalid_at": valid_to,
        "memory_tier": MemoryTier.short_term.value,
        "created_at": now,
        "updated_at": now,
        "evidence": [
            {
                "evidence_id": "ev-valid-to",
                "source_id": "conv-valid-to",
                "source_type": "conversation",
                "source_signal": "transcription",
                "extractor_id": "test",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": "conv-valid-to",
                "redaction_status": "active",
                "created_at": now,
            }
        ],
    }
    write_canonical_extraction_memory(uid, payload, db_client=db)
    stored = db.docs[f"users/{uid}/memory_items/mem_named_date"]
    assert stored["subject_scope"] == "primary_user"
    assert stored["belief_class"] == "plan"
    assert stored["valid_to"] == valid_to


def test_extraction_write_keeps_primary_user_default_when_flag_off(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.delenv("MEMORY_BELIEF_MODEL_ENABLED", raising=False)
    uid = "uid-scope-off"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    payload = {
        "id": "mem_flag_off",
        "uid": uid,
        "content": "Sam is a teammate on the launch",
        "conversation_id": "conv-scope-off",
        "subject_attribution": "third_party",
        "memory_tier": MemoryTier.short_term.value,
        "created_at": now,
        "updated_at": now,
        "evidence": [
            {
                "evidence_id": "ev-off",
                "source_id": "conv-scope-off",
                "source_type": "conversation",
                "source_signal": "transcription",
                "extractor_id": "test",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": "conv-scope-off",
                "redaction_status": "active",
                "created_at": now,
            }
        ],
    }
    write_canonical_extraction_memory(uid, payload, db_client=db)
    stored = db.docs[f"users/{uid}/memory_items/mem_flag_off"]
    assert stored["subject_scope"] == "primary_user"
    assert stored.get("belief_class") is None


def _evidence(source_id: str, now: datetime, *, source_type: str = "conversation") -> dict:
    return {
        "evidence_id": f"ev-{source_id}",
        "source_id": source_id,
        "source_type": source_type,
        "source_signal": "transcription" if source_type == "conversation" else "integration",
        "extractor_id": "test",
        "extractor_version": "v1",
        "artifact_ref": {},
        "capture_confidence": 0.5,
        "independence_group": source_id,
        "redaction_status": "active",
        "created_at": now,
    }


def test_api_create_without_attribution_is_primary_user(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    monkeypatch.setattr("utils.memory.belief_evidence.schedule_belief_admission", lambda *a, **k: None)
    uid = "uid-api-scope"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    write_canonical_external_memory(
        uid,
        {
            "id": "mem_api",
            "uid": uid,
            "content": "I prefer dark mode",
            "created_at": now,
            "updated_at": now,
            "evidence": [_evidence("external:mem_api", now, source_type="api")],
        },
        db_client=db,
    )
    stored = db.docs[f"users/{uid}/memory_items/mem_api"]
    assert stored["subject_scope"] == "primary_user"


def test_x_post_legacy_assumed_is_primary_user(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    monkeypatch.setattr("utils.memory.belief_evidence.schedule_belief_admission", lambda *a, **k: None)
    uid = "uid-x-scope"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    write_canonical_external_memory(
        uid,
        {
            "id": "mem_x",
            "uid": uid,
            "content": "Posted about the launch",
            "subject_attribution": "legacy_assumed",
            "created_at": now,
            "updated_at": now,
            "evidence": [_evidence("integration:x", now, source_type="integration:x")],
        },
        db_client=db,
    )
    stored = db.docs[f"users/{uid}/memory_items/mem_x"]
    assert stored["subject_scope"] == "primary_user"


def test_conversation_about_user_name_is_primary_user(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    uid = "uid-about-user"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    write_canonical_extraction_memory(
        uid,
        {
            "id": "mem_david",
            "uid": uid,
            "content": "David prefers dark mode",
            "conversation_id": "conv-david",
            "about": "David",
            "user_name": "David Zheng",
            "subject_attribution": "unknown",
            "memory_tier": MemoryTier.short_term.value,
            "created_at": now,
            "updated_at": now,
            "evidence": [_evidence("conv-david", now)],
        },
        db_client=db,
    )
    stored = db.docs[f"users/{uid}/memory_items/mem_david"]
    assert stored["subject_scope"] == "primary_user"


def test_conversation_about_other_person_is_third_party(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    uid = "uid-about-sam"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    write_canonical_extraction_memory(
        uid,
        {
            "id": "mem_sam",
            "uid": uid,
            "content": "Sam is a teammate on the launch",
            "conversation_id": "conv-sam",
            "about": "Sam",
            "user_name": "David Zheng",
            "subject_attribution": "third_party",
            "memory_tier": MemoryTier.short_term.value,
            "created_at": now,
            "updated_at": now,
            "evidence": [_evidence("conv-sam", now)],
        },
        db_client=db,
    )
    stored = db.docs[f"users/{uid}/memory_items/mem_sam"]
    assert stored["subject_scope"] == "third_party"


def test_extractor_media_screen_is_stored_as_third_party(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    uid = "uid-media"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    write_canonical_extraction_memory(
        uid,
        {
            "id": "mem_media",
            "uid": uid,
            "content": "Watched a YouTube video about rust",
            "conversation_id": "conv-media",
            "subject_scope": "media_screen",
            "memory_tier": MemoryTier.short_term.value,
            "created_at": now,
            "updated_at": now,
            "evidence": [_evidence("conv-media", now)],
        },
        db_client=db,
    )
    stored = db.docs[f"users/{uid}/memory_items/mem_media"]
    assert stored["subject_scope"] == "third_party"


def test_api_create_does_not_block_on_admission_judge(monkeypatch_trusted_account, monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    scheduled = []

    def _schedule(*args, **kwargs):
        scheduled.append((args, kwargs))

    def _admit(*_args, **_kwargs):
        raise AssertionError("admission judge must not run on the API create path")

    monkeypatch.setattr("utils.memory.belief_evidence.schedule_belief_admission", _schedule)
    monkeypatch.setattr("utils.memory.belief_evidence.admit_claim_against_neighbors", _admit)
    uid = "uid-api-defer"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _FakeDb(_control_seed(uid))
    write_canonical_external_memory(
        uid,
        {
            "id": "mem_api_defer",
            "uid": uid,
            "content": "I prefer dark mode",
            "created_at": now,
            "updated_at": now,
            "evidence": [_evidence("external:mem_api_defer", now, source_type="api")],
        },
        db_client=db,
    )
    assert scheduled
    assert scheduled[0][0][:3] == (uid, "mem_api_defer", "I prefer dark mode")
    assert f"users/{uid}/memory_items/mem_api_defer" in db.docs
