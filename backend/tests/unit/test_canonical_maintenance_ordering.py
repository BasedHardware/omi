"""Canonical maintenance has one L2 mutation authority."""

from datetime import datetime, timezone
from unittest.mock import ANY, MagicMock, call, patch

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.canonical_consolidation import ConsolidationReport
from utils.memory.canonical_required_processing import RequiredMemoryProcessingReport
from utils.memory.memory_system import MemorySystem
from utils.memory.short_term_promotion import (
    CanonicalShortTermLifecycleReport,
    run_canonical_short_term_maintenance,
)

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _ready_universal_apply_control(monkeypatch):
    monkeypatch.setattr(
        "utils.memory.short_term_promotion.ensure_canonical_apply_control_state",
        lambda uid, **_: MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
        ),
    )


def test_maintenance_runs_ttl_and_one_consolidation_route_in_order():
    uid = "uid-canonical"
    order = MagicMock()
    lifecycle = CanonicalShortTermLifecycleReport(uid=uid)
    consolidation = ConsolidationReport(
        uid=uid,
        trigger_reason="pending_items",
        batched_memory_ids=["mem_a", "mem_b"],
        promoted_memory_ids=["mem_a"],
        archived_memory_ids=["mem_b"],
    )
    outbox_summaries = iter(
        [
            {
                "leased_count": 2,
                "delivered_count": 1,
                "retryable_failure_count": 1,
                "actions": [{"event_id": "pre-delete", "action": "vector_delete"}],
                "errors": [{"stage": "process", "event_id": "pre-retry", "code": "vector_delete_failed"}],
            },
            {
                "leased_count": 1,
                "delivered_count": 1,
                "retryable_failure_count": 0,
                "actions": [{"event_id": "post-upsert", "action": "vector_upsert"}],
                "errors": [],
            },
        ]
    )

    def run_outbox(*args, **kwargs):
        order("outbox")
        return next(outbox_summaries)

    with (
        patch(
            "utils.memory.short_term_promotion.resolve_memory_system",
            return_value=MemorySystem.CANONICAL,
        ),
        patch(
            "utils.memory.short_term_promotion.run_required_memory_processing",
            side_effect=lambda *args, **kwargs: (order("required"), required)[1],
        ) as required_tick,
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            side_effect=lambda *args, **kwargs: (order("ttl"), lifecycle)[1],
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            side_effect=lambda *args, **kwargs: (order("route"), consolidation)[1],
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_memory_outbox_worker_tick",
            side_effect=run_outbox,
        ) as outbox_tick,
    ):
        report = run_canonical_short_term_maintenance(
            uid,
            db_client=MagicMock(),
            now=NOW,
            run_id="run-order",
        )

    required_tick.assert_not_called()
    assert order.call_args_list == [
        call("outbox"),
        call("ttl"),
        call("route"),
        call("outbox"),
    ]
    assert report.required_processing is not None
    assert report.required_processing.attempted_count == 0
    assert report.lifecycle is lifecycle
    assert report.consolidation is consolidation
    assert report.outbox is not None
    assert report.outbox["delivered_count"] == 2
    assert report.outbox["retryable_failure_count"] == 1
    assert report.outbox["leased_count"] == 3
    assert report.outbox["ticks"] == 2
    assert report.outbox["actions"] == [
        {"event_id": "pre-delete", "action": "vector_delete"},
        {"event_id": "post-upsert", "action": "vector_upsert"},
    ]
    assert report.outbox["errors"] == [{"stage": "process", "event_id": "pre-retry", "code": "vector_delete_failed"}]
    assert report.routed_count == 2
    assert report.promoted_count == 1
    assert outbox_tick.call_count == 2
    for outbox_call in outbox_tick.call_args_list:
        assert outbox_call.kwargs["now"] == NOW
        assert outbox_call.kwargs["config"].limit == 100
        assert outbox_call.kwargs["config"].scan_limit == 500
        assert outbox_call.kwargs["config"].max_attempts == 5


def test_pending_delete_runs_before_malformed_short_term_row_aborts_maintenance():
    uid = "uid-canonical"
    order = MagicMock()
    vector_delete = MagicMock(return_value=True)

    def run_outbox(**kwargs):
        order("outbox")
        deleted = kwargs["side_effects"].vector_delete(uid, "mem-private")
        return {
            "leased_count": 1,
            "delivered_count": int(deleted),
            "actions": [{"event_id": "pending-delete", "action": "vector_delete"}],
        }

    def fail_ttl(*args, **kwargs):
        order("ttl")
        raise ValueError("malformed Short-term row")

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch(
            "utils.memory.short_term_promotion.run_canonical_memory_outbox_worker_tick",
            side_effect=run_outbox,
        ),
        patch(
            "utils.memory.short_term_promotion.delete_canonical_memory_vector",
            vector_delete,
        ),
        patch(
            "utils.memory.short_term_promotion.run_required_memory_processing",
            side_effect=AssertionError("job skips standalone L2"),
        ) as required_tick,
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            side_effect=fail_ttl,
        ),
        patch("utils.memory.short_term_promotion.run_canonical_consolidation") as consolidation,
    ):
        with pytest.raises(ValueError, match="malformed Short-term row"):
            run_canonical_short_term_maintenance(
                uid,
                db_client=MagicMock(),
                now=NOW,
                run_id="run-malformed",
            )

    required_tick.assert_not_called()
    assert order.call_args_list == [call("outbox"), call("ttl")]
    vector_delete.assert_called_once_with(uid, "mem-private")
    consolidation.assert_not_called()


def test_blocked_l2_output_never_falls_through_to_generic_promotion():
    uid = "uid-canonical"
    consolidation = ConsolidationReport(
        uid=uid,
        trigger_reason="pending_items",
        watermark_blocked=True,
        pending_count=1,
    )

    with (
        patch(
            "utils.memory.short_term_promotion.resolve_memory_system",
            return_value=MemorySystem.CANONICAL,
        ),
        patch(
            "utils.memory.short_term_promotion.run_required_memory_processing",
            return_value=RequiredMemoryProcessingReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            return_value=CanonicalShortTermLifecycleReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            return_value=consolidation,
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_memory_outbox_worker_tick",
            return_value={"delivered_count": 0},
        ),
    ):
        report = run_canonical_short_term_maintenance(
            uid,
            db_client=MagicMock(),
            now=NOW,
            run_id="run-blocked",
        )

    assert report.consolidation is consolidation
    assert report.routed_count == 0
    assert report.promoted_count == 0


def test_projection_delete_callback_invalidates_keyword_kg_and_review_citations():
    uid = "uid-canonical"
    client = MagicMock()
    client.document.return_value.get.return_value.exists = False
    keyword_delete = MagicMock(return_value=True)
    assertion_delete = MagicMock()
    kg_prune = MagicMock(return_value=2)
    review_purge = MagicMock(return_value=["review-1"])

    outbox_runs = []

    def run_outbox(**kwargs):
        outbox_runs.append(None)
        if len(outbox_runs) > 1:
            return {"leased_count": 0, "delivered_count": 0, "retryable_failure_count": 0}
        deleted = kwargs["side_effects"].projection_delete(uid, "mem-retired", 1)
        return {
            "leased_count": 1,
            "delivered_count": int(deleted),
            "retryable_failure_count": int(not deleted),
        }

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch(
            "utils.memory.short_term_promotion.run_required_memory_processing",
            return_value=RequiredMemoryProcessingReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            return_value=CanonicalShortTermLifecycleReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            return_value=ConsolidationReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_memory_outbox_worker_tick",
            side_effect=run_outbox,
        ),
        patch("utils.memory.short_term_promotion.delete_atom_keyword_doc", keyword_delete),
        patch(
            "utils.memory.short_term_promotion.kg_db.delete_memory_graph_assertion",
            assertion_delete,
        ),
        patch("utils.memory.short_term_promotion.kg_db.prune_memory_citations_from_kg", kg_prune),
        patch(
            "utils.memory.short_term_promotion.purge_stale_review_conflicts_for_memories",
            review_purge,
        ),
    ):
        report = run_canonical_short_term_maintenance(
            uid,
            db_client=client,
            now=NOW,
            run_id="run-delete",
        )

    assert report.outbox is not None
    assert report.outbox["delivered_count"] == 1
    assert report.outbox["retryable_failure_count"] == 0
    keyword_delete.assert_called_once_with(uid, "mem-retired", db_client=client)
    assertion_delete.assert_called_once_with(uid, "mem-retired", db_client=client)
    kg_prune.assert_called_once_with(uid, ["mem-retired"], db_client=client)
    review_purge.assert_called_once_with(
        uid,
        ["mem-retired"],
        reason="memory_outbox_projection_deleted",
        db_client=client,
    )


def test_projection_delete_preserves_pending_review_for_active_review_archive():
    uid = "uid-canonical"
    client = MagicMock()
    review_item = MemoryItem(
        memory_id="mem-review",
        uid=uid,
        version=2,
        tier=MemoryLayer.archive,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Potentially useful claim awaiting user review.",
        evidence=[
            MemoryEvidence(
                evidence_id="ev-review",
                source_type="conversation",
                source_id="conv-review",
                source_version="1",
                conversation_id="conv-review",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW,
        updated_at=NOW,
        item_revision=2,
        content_hash="review-content-hash",
        account_generation=1,
        promotion={"route": "review", "processing_status": "processed"},
    )
    snapshot = client.document.return_value.get.return_value
    snapshot.exists = True
    snapshot.to_dict.return_value = review_item.model_dump(mode="python")
    keyword_delete = MagicMock(return_value=True)
    assertion_delete = MagicMock()
    kg_prune = MagicMock(return_value=1)
    review_purge = MagicMock()

    outbox_runs = []

    def run_outbox(**kwargs):
        outbox_runs.append(None)
        if len(outbox_runs) > 1:
            return {"leased_count": 0, "delivered_count": 0, "retryable_failure_count": 0}
        deleted = kwargs["side_effects"].projection_delete(uid, review_item.memory_id, 1)
        return {
            "leased_count": 1,
            "delivered_count": int(deleted),
            "retryable_failure_count": int(not deleted),
        }

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch(
            "utils.memory.short_term_promotion.run_required_memory_processing",
            return_value=RequiredMemoryProcessingReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            return_value=CanonicalShortTermLifecycleReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            return_value=ConsolidationReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_memory_outbox_worker_tick",
            side_effect=run_outbox,
        ),
        patch("utils.memory.short_term_promotion.delete_atom_keyword_doc", keyword_delete),
        patch(
            "utils.memory.short_term_promotion.kg_db.delete_memory_graph_assertion",
            assertion_delete,
        ),
        patch("utils.memory.short_term_promotion.kg_db.prune_memory_citations_from_kg", kg_prune),
        patch(
            "utils.memory.short_term_promotion.purge_stale_review_conflicts_for_memories",
            review_purge,
        ),
    ):
        report = run_canonical_short_term_maintenance(
            uid,
            db_client=client,
            now=NOW,
            run_id="run-review-delete",
        )

    assert report.outbox is not None
    assert report.outbox["delivered_count"] == 1
    assert report.outbox["retryable_failure_count"] == 0
    keyword_delete.assert_called_once_with(uid, review_item.memory_id, db_client=client)
    assertion_delete.assert_called_once_with(uid, review_item.memory_id, db_client=client)
    kg_prune.assert_called_once_with(uid, [review_item.memory_id], db_client=client)
    review_purge.assert_not_called()


def test_projection_delete_failure_stays_retryable_and_does_not_partially_invalidate_citations():
    uid = "uid-canonical"
    keyword_delete = MagicMock(return_value=True)
    kg_prune = MagicMock()
    review_purge = MagicMock()

    outbox_runs = []

    def run_outbox(**kwargs):
        outbox_runs.append(None)
        if len(outbox_runs) > 1:
            return {"leased_count": 0, "delivered_count": 0, "retryable_failure_count": 0}
        try:
            deleted = kwargs["side_effects"].projection_delete(uid, "mem-retry", 1)
        except RuntimeError:
            deleted = False
        return {
            "leased_count": 1,
            "delivered_count": int(deleted),
            "retryable_failure_count": int(not deleted),
        }

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch(
            "utils.memory.short_term_promotion.run_required_memory_processing",
            return_value=RequiredMemoryProcessingReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            return_value=CanonicalShortTermLifecycleReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            return_value=ConsolidationReport(uid=uid),
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_memory_outbox_worker_tick",
            side_effect=run_outbox,
        ),
        patch("utils.memory.short_term_promotion.delete_atom_keyword_doc", keyword_delete),
        patch(
            "utils.memory.short_term_promotion.kg_db.delete_memory_graph_assertion",
            side_effect=RuntimeError("injected assertion delete failure"),
        ),
        patch("utils.memory.short_term_promotion.kg_db.prune_memory_citations_from_kg", kg_prune),
        patch(
            "utils.memory.short_term_promotion.purge_stale_review_conflicts_for_memories",
            review_purge,
        ),
    ):
        report = run_canonical_short_term_maintenance(
            uid,
            db_client=MagicMock(),
            now=NOW,
            run_id="run-retry",
        )

    assert report.outbox is not None
    assert report.outbox["delivered_count"] == 0
    assert report.outbox["retryable_failure_count"] == 1
    keyword_delete.assert_not_called()
    kg_prune.assert_not_called()
    review_purge.assert_not_called()
