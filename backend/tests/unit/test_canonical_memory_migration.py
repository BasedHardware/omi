from datetime import datetime, timezone

import pytest

from database.memory_migration_store import (
    InMemoryMigrationStore,
    MigrationCheckpointConflict,
    MigrationLeaseUnavailable,
)
from models.memory_migration import (
    CanonicalMigrationCheckpoint,
    CanonicalMigrationManifest,
    MigrationFence,
    MigrationInventory,
    MigrationPhase,
    MigrationTransitionError,
    validate_migration_transition,
)
from utils.memory.canonical_migration_controller import _projection_matches_item, verify_migration_postconditions
from utils.memory.graph_enrichment import GraphEnrichmentPlan


def _inventory(*, stable: bool = True) -> MigrationInventory:
    return MigrationInventory(
        uid="u1",
        inventory_id="inv1",
        fingerprint="fp1",
        account_generation=1,
        source_generation=2,
        head_commit_id="head1",
        head_sequence=4,
        item_ids=["m1"],
        item_revisions={"m1": 3},
        item_content_hashes={"m1": "hash-m1"},
        item_evidence_ids={"m1": ["e1"]},
        stable=stable,
    )


def test_transition_validation_does_not_allow_staging_to_verified_or_cutover_skip():
    validate_migration_transition(MigrationPhase.inventoried, MigrationPhase.write_enrolled)
    with pytest.raises(MigrationTransitionError):
        validate_migration_transition(MigrationPhase.staged, MigrationPhase.verified)
    with pytest.raises(MigrationTransitionError):
        validate_migration_transition(MigrationPhase.read_cutover, MigrationPhase.failed)


def test_checkpoint_cas_and_lease_epoch_reject_races():
    store = InMemoryMigrationStore()
    inventory = _inventory()
    fence = MigrationFence(
        account_generation=1,
        source_generation=2,
        inventory_id=inventory.inventory_id,
        inventory_fingerprint=inventory.fingerprint,
        observed_head_commit_id=inventory.head_commit_id,
        observed_head_sequence=inventory.head_sequence,
    )
    checkpoint = CanonicalMigrationCheckpoint(uid="u1", fence=fence)
    store.compare_and_set_checkpoint("u1", -1, checkpoint)
    lease = store.acquire_lease("u1", "worker-a")
    current = store.read_checkpoint("u1")
    assert current is not None
    owned = store.compare_and_set_checkpoint(
        "u1",
        current.version,
        current.model_copy(update={"lease": lease}),
        owner_id="worker-a",
        ownership_epoch=lease.ownership_epoch,
    )
    with pytest.raises(MigrationCheckpointConflict):
        store.compare_and_set_checkpoint("u1", owned.version - 1, owned)
    with pytest.raises(MigrationLeaseUnavailable):
        store.acquire_lease("u1", "worker-b")
    store.release_lease("u1", "worker-a", lease.ownership_epoch)
    takeover = store.acquire_lease("u1", "worker-b")
    assert takeover.ownership_epoch > lease.ownership_epoch


def test_graph_plan_rejects_non_snake_case_predicate():
    with pytest.raises(ValueError):
        GraphEnrichmentPlan(subject_entity_id="self", predicate="LIKES-FOOD", arguments={"value": "x"})


def test_projection_freshness_uses_compatibility_payload_and_migration_fence():
    fence = MigrationFence(
        account_generation=1,
        source_generation=2,
        inventory_id="inv1",
        inventory_fingerprint="fp1",
        observed_head_commit_id="head1",
        observed_head_sequence=4,
    )
    item = {
        "uid": "u1",
        "memory_id": "m1",
        "item_revision": 3,
        "content_hash": "hash-m1",
        "content": "current text",
        "tier": "short_term",
    }
    row = {
        "uid": "u1",
        "schema_version": 1,
        "source": "memory_items_projection",
        "memory_id": "m1",
        "account_generation": 1,
        "projection_generation": 1,
        "source_commit_id": "head1",
        "projection_commit_id": "commit-head1",
        "projection_evidence_fence": "head-head1",
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "memorydb": {"content": "current text", "memory_tier": "short_term"},
    }

    assert _projection_matches_item(row, item, fence)
    assert not _projection_matches_item({**row, "source_commit_id": "older-head"}, item, fence)
    assert not _projection_matches_item(
        {**row, "memorydb": {"content": "stale", "memory_tier": "short_term"}}, item, fence
    )


def test_final_verifier_blocks_unstable_inventory_and_missing_graph_projection():
    manifest = CanonicalMigrationManifest.from_inventory(_inventory(stable=False))
    result = verify_migration_postconditions(
        manifest=manifest,
        canonical_items=[
            {
                "memory_id": "m1",
                "tier": "long_term",
                "status": "active",
                "processing_state": "processed",
                "sensitivity_labels": [],
                "promotion": {"user_review": True},
            }
        ],
        graph_assertions=[],
        compatibility_projection=[],
        outbox_events=[],
    )
    assert not result.passed
    assert any(block.code.value == "inventory_unstable" for block in result.blocking)
