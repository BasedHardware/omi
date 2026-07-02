from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from config.memory_rollout import (
    MemoryRolloutMode,
    MemoryRolloutConfig,
    MemoryRolloutState,
    MemoryRolloutStageGate,
    decide_memory_rollout_capabilities,
)
from database.memory_collections import MemoryCollections
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryConsumer,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
    MemoryItemAlias,
    derived_default_access_allowed,
    is_archive_access_eligible,
    is_default_access_eligible,
    new_memory_id,
)


def _evidence(**overrides):
    base = {
        "evidence_id": "ev1",
        "source_id": "conv1",
        "source_type": "conversation",
        "source_version": "v1",
        "quote_refs": [{"text": "I prefer concise updates"}],
        "content_hash": "hash1",
        "artifact_preservation": ArtifactPreservationState.preserved,
    }
    base.update(overrides)
    return MemoryEvidence(**base)


def _item(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "memory_id": new_memory_id(),
        "uid": "u1",
        "version": 1,
        "tier": MemoryTier.short_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.pending,
        "content": "User prefers concise updates.",
        "evidence": [_evidence()],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": False,
        "captured_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=30),
    }
    base.update(overrides)
    return MemoryItem(**base)


def test_rollout_modes_are_explicit_and_read_is_superset_of_write_after_gates_pass():
    state = MemoryRolloutState(
        uid="u1",
        mode=MemoryRolloutMode.read,
        mode_epoch=2,
        fallback_projection_ready=True,
        stage_gates={
            MemoryRolloutStageGate.shadow: "passed",
            MemoryRolloutStageGate.write: "passed",
            MemoryRolloutStageGate.read: "passed",
        },
    )
    non_allowlisted = MemoryRolloutConfig(enabled_users={"u1"}, mode=MemoryRolloutMode.read).for_user("u2")
    assert non_allowlisted.mode == MemoryRolloutMode.off
    assert non_allowlisted.legacy_only is True
    assert non_allowlisted.memory_writes_enabled is False
    assert non_allowlisted.memory_reads_enabled is False

    shadow = MemoryRolloutConfig(enabled_users={"u1"}, mode=MemoryRolloutMode.shadow).for_user("u1", state)
    assert shadow.shadow_artifacts_enabled is True
    assert shadow.memory_writes_enabled is False
    assert shadow.memory_reads_enabled is False

    write = MemoryRolloutConfig(enabled_users={"u1"}, mode=MemoryRolloutMode.write).for_user("u1", state)
    assert write.memory_writes_enabled is True
    assert write.memory_reads_enabled is False
    assert write.legacy_reads_authoritative is True

    read = MemoryRolloutConfig(enabled_users={"u1"}, mode=MemoryRolloutMode.read).for_user("u1", state)
    assert read.memory_writes_enabled is True
    assert read.memory_reads_enabled is True
    assert read.legacy_reads_authoritative is False


def test_rollout_capabilities_fail_closed_without_required_state_and_gates():
    cfg = MemoryRolloutConfig(enabled_users={"u1"}, mode=MemoryRolloutMode.read)

    no_state = cfg.for_user("u1")
    assert no_state.memory_writes_enabled is False
    assert no_state.memory_reads_enabled is False
    assert no_state.shadow_artifacts_enabled is True

    gates_missing = cfg.for_user(
        "u1",
        MemoryRolloutState(uid="u1", mode=MemoryRolloutMode.read, fallback_projection_ready=True, stage_gates={}),
    )
    assert gates_missing.memory_writes_enabled is False
    assert gates_missing.memory_reads_enabled is False

    no_fallback = cfg.for_user(
        "u1",
        MemoryRolloutState(
            uid="u1",
            mode=MemoryRolloutMode.read,
            fallback_projection_ready=False,
            stage_gates={
                MemoryRolloutStageGate.shadow: "passed",
                MemoryRolloutStageGate.write: "passed",
                MemoryRolloutStageGate.read: "passed",
            },
        ),
    )
    assert no_fallback.memory_writes_enabled is True
    assert no_fallback.memory_reads_enabled is False

    writes_blocked = cfg.for_user(
        "u1",
        MemoryRolloutState(
            uid="u1",
            mode=MemoryRolloutMode.read,
            fallback_projection_ready=True,
            writes_blocked=True,
            stage_gates={
                MemoryRolloutStageGate.shadow: "passed",
                MemoryRolloutStageGate.write: "passed",
                MemoryRolloutStageGate.read: "passed",
            },
        ),
    )
    assert writes_blocked.memory_writes_enabled is False
    assert writes_blocked.memory_reads_enabled is False


def test_rollout_state_transitions_increment_epoch_and_protect_legacy_authoritative_downgrades():
    state = MemoryRolloutState(
        uid="u1",
        mode=MemoryRolloutMode.read,
        mode_epoch=2,
        persistent_memory_writes_started=True,
        fallback_projection_ready=False,
        decommission_reconciled=False,
    )

    assert state.can_transition_to(MemoryRolloutMode.write) is False
    assert state.can_transition_to(MemoryRolloutMode.shadow) is False
    assert state.can_transition_to(MemoryRolloutMode.off) is False

    state.fallback_projection_ready = True
    next_state = state.transition_to(MemoryRolloutMode.write)
    assert next_state.mode == MemoryRolloutMode.write
    assert next_state.mode_epoch == 3

    assert next_state.can_transition_to(MemoryRolloutMode.off) is False
    next_state.decommission_reconciled = True
    assert next_state.can_transition_to(MemoryRolloutMode.off) is True


def test_memory_collections_define_unified_memory_items_and_no_separate_short_term_archive_store():
    paths = MemoryCollections(uid="u1")

    assert paths.memory_items == "users/u1/memory_items"
    assert paths.memory_operations == "users/u1/memory_operations"
    assert paths.memory_outbox == "users/u1/memory_outbox"
    assert paths.memory_control_state == "users/u1/memory_control/state"
    assert paths.memory_apply_control_state == "users/u1/memory_state/apply_control"
    assert paths.legacy_fallback == "users/u1/memory_legacy_fallback"
    assert "memory_short_term" not in paths.all_collection_paths()
    assert "memory_archive" not in paths.all_collection_paths()


def test_product_memory_item_invariants_short_term_long_term_archive():
    now = datetime.now(timezone.utc)
    short = _item(captured_at=now, updated_at=now, expires_at=now + timedelta(days=30))
    assert short.tier == MemoryTier.short_term
    assert is_default_access_eligible(short, MemoryAccessPolicy.for_omi_chat(), now=now).allowed is True

    with pytest.raises(ValidationError, match="expires_at"):
        _item(expires_at=None)

    long = _item(
        tier=MemoryTier.long_term,
        processing_state=ProcessingState.processed,
        expires_at=None,
        ledger_commit_id="commit1",
        ledger_sequence=7,
    )
    assert (
        is_default_access_eligible(
            long, MemoryAccessPolicy.for_third_party(app_has_default_memory_grant=True), now=now
        ).allowed
        is True
    )

    with pytest.raises(ValidationError, match="ledger_commit_id"):
        _item(tier=MemoryTier.long_term, processing_state=ProcessingState.processed, expires_at=None)

    archive = _item(tier=MemoryTier.archive, processing_state=ProcessingState.processed, expires_at=None)
    assert is_default_access_eligible(archive, MemoryAccessPolicy.for_omi_chat(), now=now).allowed is False
    assert (
        is_archive_access_eligible(archive, MemoryAccessPolicy.for_omi_chat(archive_capability=True), now=now).allowed
        is True
    )
    assert derived_default_access_allowed(archive, consumer="archive_explicit") is False


def test_persisted_memory_item_metadata_is_required_and_timestamps_are_valid():
    now = datetime.now(timezone.utc)
    payload = _item().model_dump()
    for field in [
        "version",
        "status",
        "processing_state",
        "source_state",
        "sensitivity_labels",
        "visibility",
        "user_asserted",
    ]:
        broken = dict(payload)
        broken.pop(field)
        with pytest.raises(ValidationError):
            MemoryItem(**broken)

    naive = dict(payload)
    naive["captured_at"] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError, match="timezone"):
        MemoryItem(**naive)

    backwards = dict(payload)
    backwards["updated_at"] = now - timedelta(days=1)
    backwards["captured_at"] = now
    with pytest.raises(ValidationError, match="updated_at"):
        MemoryItem(**backwards)


def test_access_policy_fails_closed_for_unknown_consumers_expiry_blocked_and_archive_default():
    now = datetime.now(timezone.utc)
    item = _item()

    unknown = MemoryAccessPolicy(consumer=MemoryConsumer.unknown)
    assert is_default_access_eligible(item, unknown, now=now).allowed is False

    expired = _item(
        captured_at=now - timedelta(days=31), updated_at=now - timedelta(days=1), expires_at=now - timedelta(seconds=1)
    )
    assert is_default_access_eligible(expired, MemoryAccessPolicy.for_omi_chat(), now=now).allowed is False

    blocked = _item(processing_state=ProcessingState.blocked)
    assert is_default_access_eligible(blocked, MemoryAccessPolicy.for_omi_chat(), now=now).allowed is False

    restricted = _item(sensitivity_labels=["Health"])
    assert (
        is_default_access_eligible(
            restricted, MemoryAccessPolicy.for_third_party(app_has_default_memory_grant=True), now=now
        ).allowed
        is False
    )


def test_archive_transition_preserves_user_asserted_provenance_and_identity():
    memory_id = new_memory_id()
    now = datetime.now(timezone.utc)
    archived = _item(
        memory_id=memory_id,
        version=2,
        tier=MemoryTier.archive,
        processing_state=ProcessingState.processed,
        user_asserted=True,
        expires_at=None,
        updated_at=now + timedelta(seconds=1),
    )

    assert archived.memory_id == memory_id
    assert archived.version == 2
    assert archived.user_asserted is True
    assert archived.tier == MemoryTier.archive


def test_memory_item_alias_rejects_self_aliases():
    with pytest.raises(ValidationError, match="self"):
        MemoryItemAlias(
            old_memory_id="mem_same",
            canonical_memory_id="mem_same",
            uid="u1",
            reason="many_to_one_merge",
            created_at=datetime.now(timezone.utc),
        )

    alias = MemoryItemAlias(
        old_memory_id="mem_old",
        canonical_memory_id="mem_new",
        uid="u1",
        reason="many_to_one_merge",
        created_at=datetime.now(timezone.utc),
    )
    assert alias.old_memory_id == "mem_old"
    assert alias.canonical_memory_id == "mem_new"


def test_evidence_requires_source_identity_or_typed_missing_reason_and_artifact_outcome():
    with pytest.raises(ValidationError, match="source_id"):
        MemoryEvidence(
            evidence_id="ev_bad",
            source_type="conversation",
            source_version="v1",
            artifact_preservation=ArtifactPreservationState.preserved,
        )

    with pytest.raises(ValidationError, match="artifact_preservation"):
        MemoryEvidence(evidence_id="ev_bad", source_id="conv1", source_type="conversation", source_version="v1")

    missing = MemoryEvidence(
        evidence_id="ev_missing",
        source_type="conversation",
        source_state=SourceState.missing,
        source_state_reason=SourceStateReason.ephemeral_already_missing,
        artifact_preservation=ArtifactPreservationState.ephemeral_already_missing,
    )
    assert missing.source_state == SourceState.missing
    assert missing.source_state_reason == SourceStateReason.ephemeral_already_missing

    with pytest.raises(ValidationError, match="whitespace"):
        MemoryEvidence(
            evidence_id="  ",
            source_id="conv1",
            source_type="conversation",
            source_version="v1",
            artifact_preservation=ArtifactPreservationState.preserved,
        )


def test_item_source_state_requires_consistent_active_evidence():
    with pytest.raises(ValidationError, match="active evidence"):
        _item(
            evidence=[
                _evidence(
                    source_state=SourceState.tombstoned,
                    source_state_reason=SourceStateReason.deleted_by_user,
                    artifact_preservation=ArtifactPreservationState.deleted_by_user,
                )
            ],
            source_state=SourceState.active,
        )
