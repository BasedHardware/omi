"""Hermetic unit tests verifying defensive boundary guards in database.product_memory_items."""

from datetime import datetime, timedelta, timezone
import pytest

from database.product_memory_items import (
    ProductMemoryItemDecision,
    _current_time,
    _decision_from_lifecycle,
    filter_default_product_memory_items,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import AccessDecision, MemoryAccessPolicy, MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.short_term_lifecycle import ShortTermLifecycleDecision, ShortTermLifecycleOutcome


def _sample_item(memory_id: str = "mem-123") -> MemoryItem:
    evidence = MemoryEvidence(
        evidence_id="ev-1",
        source_id="conv-1",
        source_type="conversation",
        source_version="v1",
        quote_refs=[{"text": "Sample text"}],
        content_hash="hash-1",
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    return MemoryItem(
        memory_id=memory_id,
        uid="usr-123",
        version=1,
        tier=MemoryTier.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Sample content",
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc),
        ledger_commit_id="commit-1",
        ledger_sequence=1,
    )


def test_current_time_normalizes_iso_string_to_utc():
    """Verify ISO strings with Z or offsets are properly normalized to UTC."""
    res_z = _current_time("2026-09-30T15:30:00Z")
    assert res_z.tzinfo == timezone.utc
    assert res_z == datetime(2026, 9, 30, 15, 30, 0, tzinfo=timezone.utc)

    res_offset = _current_time("2026-09-30T17:30:00+02:00")
    assert res_offset.tzinfo == timezone.utc
    assert res_offset == datetime(2026, 9, 30, 15, 30, 0, tzinfo=timezone.utc)


def test_current_time_coerces_naive_datetime():
    """Verify naive datetimes are automatically coerced to UTC timezone."""
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    aware_dt = _current_time(naive_dt)
    assert aware_dt.tzinfo == timezone.utc
    assert aware_dt.year == 2026
    assert aware_dt.hour == 12


def test_current_time_rejects_empty_and_invalid_string():
    """Verify empty, whitespace, and malformed strings raise ValueError."""
    with pytest.raises(ValueError, match="timestamp string cannot be empty or whitespace"):
        _current_time("")
    with pytest.raises(ValueError, match="timestamp string cannot be empty or whitespace"):
        _current_time("   ")
    with pytest.raises(ValueError, match="Invalid ISO timestamp string"):
        _current_time("invalid-datetime-value")


def test_current_time_rejects_invalid_type():
    """Verify non-datetime, non-string, non-None types raise TypeError."""
    with pytest.raises(TypeError, match="now must be a datetime, ISO timestamp string, or None"):
        _current_time(12345)  # type: ignore[arg-type]


def test_filter_rejects_non_iterable_items():
    """Verify passing non-iterable items raises TypeError."""
    policy = MemoryAccessPolicy.for_omi_chat()
    with pytest.raises(TypeError, match="items must be an iterable of MemoryItem"):
        filter_default_product_memory_items(None, policy=policy)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="items must be an iterable of MemoryItem"):
        filter_default_product_memory_items(123, policy=policy)  # type: ignore[arg-type]


def test_filter_rejects_invalid_policy():
    """Verify passing invalid policy raises TypeError."""
    with pytest.raises(TypeError, match="policy must be a MemoryAccessPolicy instance"):
        filter_default_product_memory_items([], policy=None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="policy must be a MemoryAccessPolicy instance"):
        filter_default_product_memory_items([], policy="not-a-policy")  # type: ignore[arg-type]


def test_filter_rejects_non_memory_item_element():
    """Verify non-MemoryItem elements raise TypeError."""
    policy = MemoryAccessPolicy.for_omi_chat()
    with pytest.raises(TypeError, match="Expected MemoryItem instance, got dict"):
        filter_default_product_memory_items([{"memory_id": "123"}], policy=policy)  # type: ignore[list-item]


def test_filter_rejects_empty_or_whitespace_memory_id():
    """Verify MemoryItem with empty or whitespace memory_id raises ValueError."""
    policy = MemoryAccessPolicy.for_omi_chat()
    item_empty = _sample_item("valid-id")
    object.__setattr__(item_empty, "memory_id", "")
    with pytest.raises(ValueError, match="memory_id must be a non-empty, non-whitespace string"):
        filter_default_product_memory_items([item_empty], policy=policy)

    item_whitespace = _sample_item("valid-id")
    object.__setattr__(item_whitespace, "memory_id", "   ")
    with pytest.raises(ValueError, match="memory_id must be a non-empty, non-whitespace string"):
        filter_default_product_memory_items([item_whitespace], policy=policy)


def test_decision_from_lifecycle_handles_missing_decision_reason_key():
    """Verify missing decision_reason in audit_metadata does not crash with KeyError."""
    access = AccessDecision(allowed=True, reason="access_granted")
    lifecycle = ShortTermLifecycleDecision(
        default_access_allowed=True,
        requires_lifecycle_decision=False,
        outcome=ShortTermLifecycleOutcome.remain_short_term,
        audit_metadata={},
    )
    decision = _decision_from_lifecycle(access, lifecycle)
    assert isinstance(decision, ProductMemoryItemDecision)
    assert decision.allowed is True
    assert decision.lifecycle_reason == "unknown"

