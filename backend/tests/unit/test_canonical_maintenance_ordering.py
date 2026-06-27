"""GAP 4: canonical short-term maintenance runs consolidation before promotion."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_consolidation import ConsolidationReport
from utils.memory.memory_system import MemorySystem
from utils.memory.short_term_promotion import (
    CanonicalShortTermLifecycleReport,
    ShortTermPromotionReport,
    run_canonical_short_term_maintenance,
)


NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


def test_maintenance_runs_consolidation_before_promotion():
    call_order: list[str] = []
    uid = "uid-maint-order"

    with (
        patch(
            "utils.memory.short_term_promotion.resolve_memory_system",
            return_value=MemorySystem.CANONICAL,
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            side_effect=lambda *args, **kwargs: (
                call_order.append("lifecycle"),
                CanonicalShortTermLifecycleReport(uid=uid),
            )[1],
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            side_effect=lambda *args, **kwargs: (
                call_order.append("consolidation"),
                ConsolidationReport(uid=uid, trigger_reason="batch_threshold", batched_memory_ids=["mem_a"]),
            )[1],
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_promotion",
            side_effect=lambda *args, **kwargs: (
                call_order.append("promotion"),
                ShortTermPromotionReport(uid=uid),
            )[1],
        ) as mock_promotion,
    ):
        run_canonical_short_term_maintenance(uid, db_client=MagicMock(), run_id="run-order-test")

    assert call_order == ["lifecycle", "consolidation", "promotion"]
    assert mock_promotion.call_args.kwargs["consolidation_batched_ids"] == {"mem_a"}


def test_maintenance_skips_promotion_gate_when_consolidation_watermark_blocked():
    uid = "uid-maint-blocked"

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            return_value=CanonicalShortTermLifecycleReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            return_value=ConsolidationReport(
                uid=uid,
                trigger_reason="batch_threshold",
                batched_memory_ids=["mem_a", "mem_b"],
                watermark_blocked=True,
            ),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_promotion",
            return_value=ShortTermPromotionReport(uid=uid),
        ) as mock_promotion,
    ):
        run_canonical_short_term_maintenance(uid, db_client=MagicMock(), run_id="run-blocked")

    assert mock_promotion.call_args.kwargs["consolidation_batched_ids"] is None


def test_promotion_defers_items_not_in_consolidation_batch():
    uid = "uid-promo-gate"
    items = [
        MemoryItem(
            memory_id=f"mem_{idx}",
            uid=uid,
            version=1,
            tier=MemoryTier.short_term,
            status=MemoryItemStatus.active,
            processing_state=ProcessingState.processed,
            content=f"fact {idx}",
            evidence=[
                MemoryEvidence(
                    evidence_id=f"ev_{idx}",
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
            captured_at=NOW,
            updated_at=NOW,
            expires_at=NOW + timedelta(days=30),
            ledger_commit_id="c1",
            ledger_sequence=1,
            item_revision=1,
            source_commit_id="c1",
            source_commit_sequence=1,
            content_hash="h",
            account_generation=1,
        )
        for idx in range(15)
    ]
    batched = {f"mem_{idx}" for idx in range(10)}

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.short_term_promotion.list_promotable_short_term_items", return_value=items),
        patch("utils.memory.short_term_promotion.list_fast_track_promotable_items", return_value=[]),
        patch("utils.memory.short_term_promotion._read_control_state") as mock_control,
        patch(
            "utils.memory.short_term_promotion.promote_short_term_item_via_apply", return_value=(items[0], False)
        ) as mock_promote,
        patch("utils.memory.short_term_promotion._persist_control_state"),
        patch("utils.memory.short_term_promotion._audit_promotion_transition", return_value=MagicMock()),
    ):
        mock_control.return_value = MagicMock(last_promotion_run_at=None)
        from utils.memory.short_term_promotion import run_canonical_short_term_promotion

        run_canonical_short_term_promotion(
            uid,
            db_client=MagicMock(),
            run_id="run-gate",
            now=NOW,
            batch_threshold=10,
            consolidation_batched_ids=batched,
        )

    promoted_ids = {call.args[1].memory_id for call in mock_promote.call_args_list}
    assert promoted_ids == batched
