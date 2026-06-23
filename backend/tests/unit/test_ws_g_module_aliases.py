"""WS-G additive module alias shims — import parity only."""

import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

sys.modules.setdefault("database._client", MagicMock())


def test_product_memory_alias_reexports_match_v17():
    from models import product_memory, v17_product_memory

    assert product_memory.MemoryItemStatus is v17_product_memory.MemoryItemStatus
    assert product_memory.MemoryTier is v17_product_memory.MemoryTier
    assert product_memory.V17MemoryItem is v17_product_memory.V17MemoryItem


def test_memory_contracts_alias_reexports_match_v17():
    from models import memory_contracts, v17_memory_contracts

    assert memory_contracts.LifecycleState is v17_memory_contracts.LifecycleState
    assert memory_contracts.DurablePatchDecision is v17_memory_contracts.DurablePatchDecision
    assert memory_contracts.deterministic_contract_id is v17_memory_contracts.deterministic_contract_id


def test_memory_collections_alias_reexports_match_v17():
    from database import memory_collections, v17_collections

    assert memory_collections.V17Collections is v17_collections.V17Collections


def test_memory_apply_store_alias_reexports_match_v17():
    from database import memory_apply_store, v17_memory_apply_store

    assert memory_apply_store.V17FirestoreApplyError is v17_memory_apply_store.V17FirestoreApplyError
    assert memory_apply_store.MissingV17Document is v17_memory_apply_store.MissingV17Document
    assert memory_apply_store.apply_long_term_patch_firestore is v17_memory_apply_store.apply_long_term_patch_firestore
    assert memory_apply_store.atomic_bump_source_generation is v17_memory_apply_store.atomic_bump_source_generation


def test_memory_vector_metadata_alias_reexports_match_v17():
    from database import memory_vector_metadata, v17_vector_metadata

    assert (
        memory_vector_metadata.V17_MEMORY_VECTOR_SCHEMA_VERSION is v17_vector_metadata.V17_MEMORY_VECTOR_SCHEMA_VERSION
    )
    assert memory_vector_metadata.V17_MEMORY_VECTOR_ID_PREFIX is v17_vector_metadata.V17_MEMORY_VECTOR_ID_PREFIX
    assert memory_vector_metadata.RESTRICTED_SENSITIVITY_LABELS is v17_vector_metadata.RESTRICTED_SENSITIVITY_LABELS
    assert memory_vector_metadata.ParsedV17VectorHit is v17_vector_metadata.ParsedV17VectorHit
    assert (
        memory_vector_metadata.deterministic_v17_memory_vector_id
        is v17_vector_metadata.deterministic_v17_memory_vector_id
    )
    assert (
        memory_vector_metadata.build_v17_memory_vector_metadata is v17_vector_metadata.build_v17_memory_vector_metadata
    )
    assert (
        memory_vector_metadata.build_v17_default_memory_vector_filter
        is v17_vector_metadata.build_v17_default_memory_vector_filter
    )
    assert (
        memory_vector_metadata.build_v17_archive_memory_vector_filter
        is v17_vector_metadata.build_v17_archive_memory_vector_filter
    )
    assert memory_vector_metadata.parse_v17_search_vector_hit is v17_vector_metadata.parse_v17_search_vector_hit
