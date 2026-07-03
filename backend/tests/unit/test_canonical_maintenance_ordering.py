"""GAP 4: canonical short-term maintenance runs consolidation before promotion."""

from __future__ import annotations

import os
import importlib
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
from utils.memory.canonical_kg_promotion import CanonicalKgPromotionResult
from utils.memory.memory_system import MemorySystem
from utils.memory.short_term_promotion import (
    CanonicalShortTermLifecycleReport,
    ShortTermPromotionReport,
    run_canonical_short_term_maintenance,
)

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _refresh_short_term_promotion_runtime():
    short_term_promotion = importlib.import_module("utils.memory.short_term_promotion")
    globals().update(
        {
            "CanonicalShortTermLifecycleReport": short_term_promotion.CanonicalShortTermLifecycleReport,
            "ShortTermPromotionReport": short_term_promotion.ShortTermPromotionReport,
            "run_canonical_short_term_maintenance": short_term_promotion.run_canonical_short_term_maintenance,
        }
    )


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


def test_maintenance_defers_promotion_when_consolidation_watermark_blocked():
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

    assert mock_promotion.call_args.kwargs["consolidation_batched_ids"] == set()


def test_maintenance_no_promotion_gate_when_consolidation_not_due():
    uid = "uid-maint-not-due"

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            return_value=CanonicalShortTermLifecycleReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            return_value=ConsolidationReport(uid=uid, skipped_reason="consolidation_not_due"),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_promotion",
            return_value=ShortTermPromotionReport(uid=uid),
        ) as mock_promotion,
    ):
        run_canonical_short_term_maintenance(uid, db_client=MagicMock(), run_id="run-not-due")

    assert mock_promotion.call_args.kwargs["consolidation_batched_ids"] is None


def _promotable_item(memory_id: str) -> MemoryItem:
    return MemoryItem(
        memory_id=memory_id,
        uid="uid-partial-promo",
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=f"fact {memory_id}",
        evidence=[
            MemoryEvidence(
                evidence_id=f"ev_{memory_id}",
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


def test_partial_apply_pass_does_not_promote_stale_or_survivor():
    """After partial consolidate (survivor updated, supersede failed), promotion is deferred."""
    uid = "uid-partial-promo"
    stale = _promotable_item("mem_old")
    survivor = _promotable_item("mem_new")

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
                batched_memory_ids=["mem_old", "mem_new"],
                watermark_blocked=True,
                decisions_partial=1,
            ),
        ),
        patch(
            "utils.memory.short_term_promotion.list_promotable_short_term_items",
            return_value=[stale, survivor],
        ),
        patch("utils.memory.short_term_promotion.list_fast_track_promotable_items", return_value=[]),
        patch("utils.memory.short_term_promotion._read_control_state") as mock_control,
        patch(
            "utils.memory.short_term_promotion.promote_short_term_item_via_apply",
        ) as mock_promote,
        patch("utils.memory.short_term_promotion._persist_control_state"),
    ):
        mock_control.return_value = MagicMock(last_promotion_run_at=None)
        report = run_canonical_short_term_maintenance(uid, db_client=MagicMock(), run_id="run-partial-promo")

    assert report.promotion.skipped_reason == "consolidation_watermark_blocked"
    mock_promote.assert_not_called()


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
            "utils.memory.short_term_promotion.promote_short_term_item_via_apply",
            return_value=(items[0], False, CanonicalKgPromotionResult(attempted=True, success=True), True),
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


def test_fast_track_respects_consolidation_batch_gate():
    uid = "uid-fast-track-gate"
    batched_item = _promotable_item("mem_batched")
    batched_item.user_asserted = True
    excluded_item = _promotable_item("mem_excluded")
    excluded_item.user_asserted = True

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch(
            "utils.memory.short_term_promotion.list_promotable_short_term_items",
            return_value=[batched_item, excluded_item],
        ),
        patch(
            "utils.memory.short_term_promotion.list_fast_track_promotable_items",
            return_value=[batched_item, excluded_item],
        ),
        patch("utils.memory.short_term_promotion.promotion_fast_track_enabled", return_value=True),
        patch("utils.memory.short_term_promotion._read_control_state") as mock_control,
        patch(
            "utils.memory.short_term_promotion.promote_short_term_item_via_apply",
            return_value=(batched_item, False, CanonicalKgPromotionResult(attempted=True, success=True), True),
        ) as mock_promote,
        patch("utils.memory.short_term_promotion._persist_control_state"),
        patch("utils.memory.short_term_promotion._audit_promotion_transition", return_value=MagicMock()),
    ):
        mock_control.return_value = MagicMock(last_promotion_run_at=NOW)
        from utils.memory.short_term_promotion import run_canonical_short_term_promotion

        report = run_canonical_short_term_promotion(
            uid,
            db_client=MagicMock(),
            run_id="run-fast-track-gate",
            now=NOW,
            consolidation_batched_ids={"mem_batched"},
        )

    assert report.trigger_reason == "user_asserted_fast_track"
    promoted_ids = {call.args[1].memory_id for call in mock_promote.call_args_list}
    assert promoted_ids == {"mem_batched"}
