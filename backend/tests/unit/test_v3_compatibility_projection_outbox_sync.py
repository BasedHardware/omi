"""Behavioral tests for the ``/v3`` compatibility projection normal-outbox writer.

Reshaped onto the neutral storage port (WP2): the projection writer and reader are driven against a
``FakeDocumentStore`` seeded at the module's real logical paths, so the transactions run through
``FakeDocumentStore.run_transaction`` exactly as production runs them through the store adapter.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from database import knowledge_graph as kg_db
from database import memory_compatibility_projection as projection_reader
from database.memory_collections import MemoryCollections
from database.memory_compatibility_projection import read_v3_compatibility_projection_page
from models.memory_evidence import SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from tests.store_fakes import FakeDocumentStore
from utils.memory.short_term_promotion import _canonical_outbox_side_effects
from utils.memory.v3 import compatibility_projection_sync
from utils.memory.v3.compatibility_projection_sync import CompatibilityProjectionSyncError
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3_COMPATIBILITY_PROJECTION_SOURCE,
    V3_COMPATIBILITY_PROJECTION_VERSION,
    V3ProjectionReadRequest,
)

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
UID = "uid-compat-outbox"
MEMORY_ID = "mem-compat"


def _install_store(monkeypatch, docs: dict[str, dict[str, Any]]) -> FakeDocumentStore:
    """Seed a shared-backing fake store and route both port callers through it."""
    fake = FakeDocumentStore(backing=docs)
    monkeypatch.setattr(compatibility_projection_sync, "_store", lambda: fake)
    monkeypatch.setattr(projection_reader, "_store", lambda: fake)
    monkeypatch.setattr(kg_db, "_store", lambda: fake)
    return fake


def _projection_state() -> dict[str, Any]:
    return {
        "uid": UID,
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "source": V3_COMPATIBILITY_PROJECTION_SOURCE,
        "ready": True,
        "account_generation": 7,
        "projection_generation": 7,
        "freshness_fence_generation": 7,
        "tombstone_fence_generation": 7,
        "vector_cleanup_fence_generation": 7,
        "source_commit_id": "head-enrollment",
        "projection_commit_id": "commit-head-enrollment",
        "source_evidence_fence": "head-head-enrollment",
        "projection_evidence_fence": "head-head-enrollment",
        "projection_version": V3_COMPATIBILITY_PROJECTION_VERSION,
        "source_version": "memory_state_head:4",
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "empty_projection": False,
    }


def _item(
    *,
    content: str = "Original durable preference",
    revision: int = 1,
    tier: MemoryLayer = MemoryLayer.long_term,
) -> MemoryItem:
    captured_at = NOW - timedelta(days=2)
    return MemoryItem(
        memory_id=MEMORY_ID,
        uid=UID,
        version=revision,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=True,
        captured_at=captured_at,
        updated_at=captured_at + timedelta(minutes=revision),
        expires_at=NOW + timedelta(days=28) if tier == MemoryLayer.short_term else None,
        ledger_commit_id=f"commit_{revision}",
        ledger_sequence=revision,
        item_revision=revision,
        content_hash=f"hash-{revision}",
        account_generation=7,
        promotion={
            "category": "interesting",
            "tags": ["preference"],
            "reviewed": True,
            "user_review": True,
        },
    )


def _read() -> list[dict[str, Any]]:
    return read_v3_compatibility_projection_page(
        request=V3ProjectionReadRequest(
            uid=UID,
            limit=10,
            expected_account_generation=7,
        ),
    ).items


def test_normal_projection_callback_creates_then_updates_the_v3_read_model(monkeypatch):
    paths = MemoryCollections(uid=UID)
    original_state = _projection_state()
    docs = {paths.v3_compatibility_projection_state: dict(original_state)}
    _install_store(monkeypatch, docs)
    keyword_sync = MagicMock(return_value=True)
    side_effects = _canonical_outbox_side_effects()

    with patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", keyword_sync):
        assert side_effects.projection_upsert(_item(), 7) is True
        assert [row["content"] for row in _read()] == ["Original durable preference"]

        updated = _item(content="Updated durable preference", revision=2)
        assert side_effects.projection_upsert(updated, 7) is True

    rows = _read()
    assert [row["content"] for row in rows] == ["Updated durable preference"]
    assert rows[0]["updated_at"] == updated.updated_at
    assert rows[0]["memory_tier"] == MemoryLayer.long_term.value
    assert "evidence" not in rows[0]
    assert docs[paths.v3_compatibility_projection_state] == original_state
    assert keyword_sync.call_count == 2


def test_processed_short_term_is_compatibility_visible_without_becoming_a_keyword_atom(monkeypatch):
    paths = MemoryCollections(uid=UID)
    docs = {paths.v3_compatibility_projection_state: _projection_state()}
    _install_store(monkeypatch, docs)
    keyword_sync = MagicMock(return_value=True)
    side_effects = _canonical_outbox_side_effects()

    with patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", keyword_sync):
        short_term = _item(content="Fresh source-backed context", tier=MemoryLayer.short_term)
        assert side_effects.projection_upsert(short_term, 7) is True

    assert [row["memory_tier"] for row in _read()] == [MemoryLayer.short_term.value]
    keyword_sync.assert_called_once_with(short_term)


def test_normal_projection_delete_hides_v3_content_before_retryable_external_cleanup(monkeypatch):
    paths = MemoryCollections(uid=UID)
    graph_assertion_path = f"users/{UID}/memory_graph_assertions/{MEMORY_ID}"
    docs = {
        paths.v3_compatibility_projection_state: _projection_state(),
        graph_assertion_path: {"memory_id": MEMORY_ID},
    }
    _install_store(monkeypatch, docs)
    side_effects = _canonical_outbox_side_effects()
    with patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", return_value=True):
        assert side_effects.projection_upsert(_item(), 7) is True
    assert len(_read()) == 1

    kg_prune = MagicMock()
    review_purge = MagicMock()
    with (
        patch("utils.memory.short_term_promotion.delete_atom_keyword_doc", return_value=False),
        patch("utils.memory.short_term_promotion.kg_db.prune_memory_citations_from_kg", kg_prune),
        patch(
            "utils.memory.short_term_promotion.purge_stale_review_conflicts_for_memories",
            review_purge,
        ),
    ):
        assert side_effects.projection_delete(UID, MEMORY_ID, 7) is False

    assert _read() == []
    assert f"{paths.v3_compatibility_projection_items}/{MEMORY_ID}" not in docs
    assert graph_assertion_path not in docs
    kg_prune.assert_not_called()
    review_purge.assert_not_called()


@pytest.mark.parametrize(
    "state_patch",
    [
        None,
        {"account_generation": 6, "projection_generation": 6},
        {"write_convergence_complete": False},
    ],
)
def test_projection_upsert_fails_closed_without_valid_enrollment_fences(monkeypatch, state_patch):
    paths = MemoryCollections(uid=UID)
    docs: dict[str, dict[str, Any]] = {}
    if state_patch is not None:
        docs[paths.v3_compatibility_projection_state] = {**_projection_state(), **state_patch}
    _install_store(monkeypatch, docs)
    side_effects = _canonical_outbox_side_effects()

    with (
        patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", return_value=True),
        pytest.raises(CompatibilityProjectionSyncError),
    ):
        side_effects.projection_upsert(_item(), 7)

    assert f"{paths.v3_compatibility_projection_items}/{MEMORY_ID}" not in docs


def test_stale_generation_delete_cannot_remove_a_new_generation_projection_row(monkeypatch):
    paths = MemoryCollections(uid=UID)
    new_generation_state = {
        **_projection_state(),
        "account_generation": 8,
        "projection_generation": 8,
        "freshness_fence_generation": 8,
        "tombstone_fence_generation": 8,
        "vector_cleanup_fence_generation": 8,
    }
    item_path = f"{paths.v3_compatibility_projection_items}/{MEMORY_ID}"
    docs = {
        paths.v3_compatibility_projection_state: new_generation_state,
        item_path: {"new_generation_private_content": True},
    }
    _install_store(monkeypatch, docs)
    side_effects = _canonical_outbox_side_effects()

    with pytest.raises(CompatibilityProjectionSyncError):
        side_effects.projection_delete(UID, MEMORY_ID, 7)

    assert docs[item_path] == {"new_generation_private_content": True}
