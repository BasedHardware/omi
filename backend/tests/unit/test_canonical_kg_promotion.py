"""WS-O KG promotion + invalidation tests."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_kg_promotion import extract_kg_for_promoted_memory
from utils.memory.canonical_memory_adapter import invalidate_kg_for_memory_retraction

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


def _long_term_item(**overrides) -> MemoryItem:
    base = MemoryItem(
        memory_id="mem_lt",
        uid="uid-canonical",
        version=1,
        tier=MemoryTier.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="User works at Omi",
        evidence=[
            MemoryEvidence(
                evidence_id="ev_1",
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
        captured_at=NOW - timedelta(days=1),
        updated_at=NOW,
        expires_at=None,
        ledger_commit_id="commit-1",
        ledger_sequence=1,
        item_revision=1,
        source_commit_id="commit-1",
        content_hash="hash",
        account_generation=1,
        kg_extracted=False,
    )
    return base.model_copy(update=overrides)


def test_extract_kg_skips_when_already_extracted():
    item = _long_term_item(kg_extracted=True)
    with patch("utils.memory.canonical_kg_promotion.extract_knowledge_from_memory") as mock_extract:
        assert extract_kg_for_promoted_memory("uid-canonical", item) is False
        mock_extract.assert_not_called()


def test_extract_kg_on_promotion():
    item = _long_term_item()
    db = MagicMock()
    with (
        patch(
            "utils.memory.canonical_kg_promotion.extract_knowledge_from_memory",
            return_value={"nodes": [{}], "edges": []},
        ),
        patch("utils.memory.canonical_kg_promotion.set_canonical_memory_kg_extracted") as mock_flag,
    ):
        assert extract_kg_for_promoted_memory("uid-canonical", item, db_client=db) is True
        mock_flag.assert_called_once_with("uid-canonical", "mem_lt", db_client=db)


def test_invalidate_kg_prunes_citations():
    with patch(
        "utils.memory.canonical_memory_adapter.kg_db.prune_memory_citations_from_kg", return_value=3
    ) as mock_prune:
        invalidate_kg_for_memory_retraction("uid-canonical", ["mem_a", "mem_b"])
        mock_prune.assert_called_once_with("uid-canonical", ["mem_a", "mem_b"])
