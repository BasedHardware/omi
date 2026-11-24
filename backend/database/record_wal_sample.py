"""A global, create-only sample slot and point-read-limited privacy snapshots."""

from typing import Any

from google.api_core.exceptions import AlreadyExists

from database.batch_pipeline_reads import read_snapshot
from database.batch_pipeline_store import FirestoreStore, FirestoreTransaction
from database.record_wal_capacity import NAMESPACE
from database.record_wal_handoff import check_owner_authority
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget


def claim_slot(store: FirestoreStore, slot: int, budget: ArtifactReadBudget, *, duplicate_shadow=False) -> bool:
    kind = 'record_wal_duplicate_shadow_slot' if duplicate_shadow else 'record_wal_sample_slot'
    prefix = 'wal_duplicate_shadow_slot_v1' if duplicate_shadow else 'wal_sample_slot_v1'
    ref = FirestoreTransaction.intake_reference(store.client, NAMESPACE, f'{prefix}_{slot}')
    try:
        ref.create({'kind': kind, 'slot': slot}, timeout=budget.timeout(0.25), retry=None)
    except AlreadyExists:
        return False
    return True


def authority(
    store: FirestoreStore,
    uid: str,
    cid: str,
    source: str,
    device: str,
    budget: ArtifactReadBudget,
    reads: Any,
    *,
    expected_generation: int | None = None,
) -> tuple[int, dict[str, Any]]:
    def get(view: Any):
        generation, _, row = check_owner_authority(
            store.client,
            view.transaction,
            uid,
            cid,
            source,
            device,
            expected_generation,
            sampling_read_budget=reads,
        )
        return generation, row

    return read_snapshot(store, get, budget)
