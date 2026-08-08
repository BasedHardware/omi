"""Canonical required-memory pending-selection contract over the storage port.

WP2/ADR-0028 migrated ``list_pending_required_processing_items`` off the injected Firestore
client: it now streams the whole ``memory_items`` collection through the neutral document store
and applies the eligibility filter, ``(captured_at, memory_id)`` ordering, and limit in Python.
These tests exercise that behavior through the ``FakeDocumentStore`` port seam. The former
query-level bounding assertions (server-side ``where``/``order_by``/``limit`` fan-out counters)
described a contract that no longer exists and were dropped with the migration.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from database import document_store
from models.memory_evidence import SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from tests.store_fakes import FakeDocumentStore
from utils.memory.canonical_required_processing import list_pending_required_processing_items
from utils.memory.required_promotion import (
    REQUIRED_PROCESSING_STATUS_PENDING,
    REQUIRED_PROCESSING_STATUS_REJECTED,
)

UID = "uid-required-query"
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def _item(
    memory_id: str,
    *,
    captured_at: datetime,
    required: bool = True,
    user_review: bool | None = None,
    tier: MemoryLayer = MemoryLayer.short_term,
    processing_status: str = REQUIRED_PROCESSING_STATUS_PENDING,
) -> MemoryItem:
    promotion: dict[str, Any] = {
        "required": required,
        "processing_status": processing_status,
    }
    if user_review is not None:
        promotion["user_review"] = user_review
    return MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=1,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.pending,
        content=f"Required memory {memory_id}",
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=True,
        captured_at=captured_at,
        updated_at=captured_at,
        expires_at=captured_at + timedelta(days=30),
        promotion=promotion,
    )


def _seed(monkeypatch, items: list[MemoryItem]) -> None:
    docs = {
        f"users/{UID}/memory_items/{item.memory_id}": item.model_dump(mode="python") for item in items
    }
    monkeypatch.setattr(document_store, "_store", lambda: FakeDocumentStore(backing=docs))


def test_required_processing_query_filters_orders_and_limits(monkeypatch) -> None:
    candidates = [
        _item("eligible-b", captured_at=NOW - timedelta(days=2)),
        _item("eligible-a", captured_at=NOW - timedelta(days=2)),
        *[
            _item(f"eligible-{index:02d}", captured_at=NOW - timedelta(days=1) + timedelta(minutes=index))
            for index in range(20)
        ],
    ]
    irrelevant = [
        _item(
            f"non-required-{index:03d}",
            captured_at=NOW - timedelta(days=100),
            required=False,
        )
        for index in range(200)
    ]
    _seed(monkeypatch, [*irrelevant, *candidates])

    pending = list_pending_required_processing_items(UID, limit=2)

    # Non-required items are filtered out; eligible-a/eligible-b share the earliest capture time
    # so ties break on memory_id, and the limit is applied after ordering.
    assert [item.memory_id for item in pending] == ["eligible-a", "eligible-b"]


def test_terminal_negative_reviews_cannot_starve_later_required_processing(monkeypatch) -> None:
    rejected = [
        _item(
            f"a-rejected-{index:03d}",
            captured_at=NOW - timedelta(days=100, minutes=index),
            user_review=False,
            processing_status=REQUIRED_PROCESSING_STATUS_REJECTED,
        )
        for index in range(101)
    ]
    eligible = _item("z-eligible", captured_at=NOW - timedelta(days=1))
    _seed(monkeypatch, [*rejected, eligible])

    pending = list_pending_required_processing_items(UID, limit=1)

    # Terminal negative-review/rejected items are ineligible, so despite sorting earliest they
    # never occupy the bounded result and cannot starve the one genuinely pending item.
    assert [item.memory_id for item in pending] == ["z-eligible"]
