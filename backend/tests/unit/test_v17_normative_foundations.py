from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from config.v17_memory import V17Mode, V17RolloutConfig, V17RolloutState, decide_v17_capabilities
from database.v17_collections import V17Collections
from models.memory_evidence import MemoryEvidence, SourceState
from models.v17_product_memory import (
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    V17MemoryItem,
    V17MemoryItemAlias,
    derived_default_access_allowed,
    new_memory_id,
)


def test_rollout_modes_are_explicit_and_read_is_superset_of_write():
    non_allowlisted = V17RolloutConfig(enabled_users={"u1"}, mode=V17Mode.read).for_user("u2")
    assert non_allowlisted.mode == V17Mode.off
    assert non_allowlisted.legacy_only is True
    assert non_allowlisted.v17_writes_enabled is False
    assert non_allowlisted.v17_reads_enabled is False

    shadow = V17RolloutConfig(enabled_users={"u1"}, mode=V17Mode.shadow).for_user("u1")
    assert shadow.shadow_artifacts_enabled is True
    assert shadow.v17_writes_enabled is False
    assert shadow.v17_reads_enabled is False

    write = V17RolloutConfig(enabled_users={"u1"}, mode=V17Mode.write).for_user("u1")
    assert write.v17_writes_enabled is True
    assert write.v17_reads_enabled is False
    assert write.legacy_reads_authoritative is True

    read = V17RolloutConfig(enabled_users={"u1"}, mode=V17Mode.read).for_user("u1")
    assert read.v17_writes_enabled is True
    assert read.v17_reads_enabled is True
    assert read.legacy_reads_authoritative is False


def test_rollout_state_blocks_write_to_off_after_persistent_writes_without_reconciliation():
    state = V17RolloutState(
        uid="u1",
        mode=V17Mode.write,
        mode_epoch=2,
        persistent_v17_writes_started=True,
        fallback_projection_ready=True,
        decommission_reconciled=False,
    )

    assert state.can_transition_to(V17Mode.read) is True
    assert state.can_transition_to(V17Mode.off) is False

    state.decommission_reconciled = True
    assert state.can_transition_to(V17Mode.off) is True


def test_v17_collections_define_unified_memory_items_and_no_separate_short_term_archive_store():
    paths = V17Collections(uid="u1")

    assert paths.memory_items == "users/u1/memory_items"
    assert paths.memory_operations == "users/u1/memory_operations"
    assert paths.memory_outbox == "users/u1/memory_outbox"
    assert paths.memory_control_state == "users/u1/memory_control/state"
    assert paths.legacy_fallback == "users/u1/memory_legacy_fallback"
    assert "memory_short_term" not in paths.all_collection_paths()
    assert "memory_archive" not in paths.all_collection_paths()


def test_product_memory_item_invariants_short_term_long_term_archive():
    now = datetime.now(timezone.utc)
    evidence = MemoryEvidence(
        evidence_id="ev1",
        source_id="conv1",
        source_type="conversation",
        source_version="v1",
        quote_refs=[{"text": "I prefer concise updates"}],
        content_hash="hash1",
    )
    short = V17MemoryItem(
        memory_id=new_memory_id(),
        uid="u1",
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.pending,
        content="User prefers concise updates.",
        evidence=[evidence],
        captured_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=30),
    )
    assert short.tier == MemoryTier.short_term
    assert derived_default_access_allowed(short, consumer="omi_chat") is True

    with pytest.raises(ValidationError, match="expires_at"):
        V17MemoryItem(
            memory_id=new_memory_id(),
            uid="u1",
            tier=MemoryTier.short_term,
            status=MemoryItemStatus.active,
            processing_state=ProcessingState.pending,
            content="Missing expiry.",
            evidence=[evidence],
            captured_at=now,
            updated_at=now,
        )

    long = V17MemoryItem(
        memory_id=new_memory_id(),
        uid="u1",
        tier=MemoryTier.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="User prefers concise updates.",
        evidence=[evidence],
        ledger_commit_id="commit1",
        ledger_sequence=7,
        captured_at=now,
        updated_at=now,
    )
    assert derived_default_access_allowed(long, consumer="third_party") is True

    with pytest.raises(ValidationError, match="ledger_commit_id"):
        V17MemoryItem(
            memory_id=new_memory_id(),
            uid="u1",
            tier=MemoryTier.long_term,
            status=MemoryItemStatus.active,
            processing_state=ProcessingState.processed,
            content="No ledger.",
            evidence=[evidence],
            captured_at=now,
            updated_at=now,
        )

    archive = V17MemoryItem(
        memory_id=new_memory_id(),
        uid="u1",
        tier=MemoryTier.archive,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Older source-backed context.",
        evidence=[evidence],
        captured_at=now,
        updated_at=now,
    )
    assert derived_default_access_allowed(archive, consumer="omi_chat") is False
    assert derived_default_access_allowed(archive, consumer="archive_explicit") is True


def test_memory_item_alias_preserves_old_ids_after_many_to_one_merge():
    alias = V17MemoryItemAlias(
        old_memory_id="mem_old",
        canonical_memory_id="mem_new",
        uid="u1",
        reason="many_to_one_merge",
        created_at=datetime.now(timezone.utc),
    )

    assert alias.old_memory_id == "mem_old"
    assert alias.canonical_memory_id == "mem_new"
    assert alias.reason == "many_to_one_merge"


def test_evidence_requires_source_identity_or_typed_missing_reason():
    with pytest.raises(ValidationError, match="source_id"):
        MemoryEvidence(evidence_id="ev_bad", source_type="conversation", source_version="v1")

    missing = MemoryEvidence(
        evidence_id="ev_missing",
        source_type="conversation",
        source_state=SourceState.missing,
        missing_source_reason="ephemeral_already_missing",
    )
    assert missing.source_state == SourceState.missing
    assert missing.missing_source_reason == "ephemeral_already_missing"
