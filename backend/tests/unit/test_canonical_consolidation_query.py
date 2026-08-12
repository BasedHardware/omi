"""Bounded storage-port query contract for canonical consolidation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from database.store.records import StoredDocument
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
import utils.memory.canonical_consolidation as consolidation
from utils.memory.canonical_consolidation import list_pending_consolidation_items

UID = "uid-consolidation-query"
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def _nested_value(payload: dict[str, Any], field_path: str) -> Any:
    value: Any = payload
    for part in field_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class _RecordingStore:
    """In-memory recording fake of the ``DocumentStore.query`` port seam (WP2/ADR-0028).

    Replaces the retired injected Firestore client: the domain code now reaches storage through
    ``get_document_store().query(...)``. This fake records the bounded-query contract (filters,
    multi-field ordering, keyset cursor, limit) the test asserts on, then returns neutral
    ``StoredDocument`` rows just like a real adapter.
    """

    def __init__(self, rows: list[tuple[str, dict[str, Any]]]):
        self.rows = rows
        self.stream_limit: int | None = None
        self.streamed_count = 0
        self.filters: list[tuple[str, str, Any]] = []
        self.order_fields: list[str] = []

    def query(
        self,
        collection: str,
        *,
        filters: Any = None,
        order_by: Any = None,
        direction: str = "asc",
        limit: int | None = None,
        offset: int | None = None,
        fields: Any = None,
        start_after: dict[str, Any] | None = None,
    ) -> list[StoredDocument]:
        rows = list(self.rows)
        filter_list = [tuple(f) for f in (filters or [])]
        for field_path, op_string, expected in filter_list:
            if op_string != "==":
                raise AssertionError(f"unexpected operator: {op_string}")
            rows = [row for row in rows if _nested_value(row[1], field_path) == expected]

        order_fields = [field for field, _direction in (order_by or [])]
        primary = order_fields[0] if order_fields else None
        if primary is not None:
            # Single-field order_by with an implicit full-path (__name__/_id) tie-break, mirroring
            # the real adapters and FakeDocumentStore.
            rows.sort(key=lambda row: (_nested_value(row[1], primary), row[0]))

        if start_after is not None:
            # Neutral keyset cursor {value, id}: primary field value + full doc-path tie-break.
            cursor = (start_after["value"], f"{collection}/{start_after['id']}")
            rows = [row for row in rows if (_nested_value(row[1], primary), row[0]) > cursor]

        if limit is not None:
            rows = rows[:limit]

        self.stream_limit = limit
        self.streamed_count = len(rows)
        self.filters = filter_list
        self.order_fields = order_fields
        return [StoredDocument.present(path, dict(payload)) for path, payload in rows]


def _item(
    memory_id: str,
    *,
    captured_at: datetime,
    status: MemoryItemStatus = MemoryItemStatus.active,
    processing_state: ProcessingState = ProcessingState.processed,
    source_state: SourceState = SourceState.active,
) -> MemoryItem:
    evidence = MemoryEvidence(
        evidence_id=f"evidence-{memory_id}",
        source_id=f"source-{memory_id}",
        source_type="conversation",
        source_version="v1",
        source_state=source_state,
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    return MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=1,
        tier=MemoryLayer.short_term,
        status=status,
        processing_state=processing_state,
        content=f"Consolidation memory {memory_id}",
        evidence=[evidence],
        source_state=source_state,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=captured_at,
        updated_at=captured_at,
        expires_at=NOW + timedelta(days=30),
    )


def _store_for(items: list[MemoryItem]) -> _RecordingStore:
    return _RecordingStore(
        [(f"users/{UID}/memory_items/{item.memory_id}", item.model_dump(mode="python")) for item in items]
    )


def test_consolidation_query_filters_orders_and_limits_before_streaming(monkeypatch) -> None:
    same_capture = NOW - timedelta(days=2)
    store = _store_for(
        [
            _item("eligible-b", captured_at=same_capture),
            _item("eligible-a", captured_at=same_capture),
            _item("eligible-c", captured_at=NOW - timedelta(days=1)),
        ]
    )
    monkeypatch.setattr(consolidation, "get_document_store", lambda: store)

    pending = list_pending_consolidation_items(UID, now=NOW, limit=2)

    assert [item.memory_id for item in pending] == ["eligible-a", "eligible-b"]
    assert store.stream_limit == 2
    assert store.streamed_count == 2
    # Single-field order_by; the adapter appends the __name__/_id tie-break for a stable keyset.
    assert store.order_fields == ["captured_at"]
    assert ("tier", "==", MemoryLayer.short_term.value) in store.filters
    assert ("status", "==", MemoryItemStatus.active.value) in store.filters
    assert ("processing_state", "==", ProcessingState.processed.value) in store.filters
    assert ("source_state", "==", SourceState.active.value) in store.filters


def test_ineligible_earlier_ids_cannot_starve_consolidation_at_the_query_cap(monkeypatch) -> None:
    ineligible = [
        _item(
            f"a-ineligible-{index:03d}",
            captured_at=NOW - timedelta(days=100, minutes=index),
            status=MemoryItemStatus.superseded,
        )
        for index in range(251)
    ]
    eligible = _item("z-eligible", captured_at=NOW - timedelta(days=1))
    store = _store_for([*ineligible, eligible])
    monkeypatch.setattr(consolidation, "get_document_store", lambda: store)

    pending = list_pending_consolidation_items(UID, now=NOW)

    assert [item.memory_id for item in pending] == ["z-eligible"]
    assert store.stream_limit == 250
    assert store.streamed_count == 1


def test_quarantined_blocked_rows_cannot_fill_the_oldest_query_window(monkeypatch) -> None:
    quarantined = [
        _item(
            f"a-quarantined-{index:03d}",
            captured_at=NOW - timedelta(days=100, minutes=index),
            processing_state=ProcessingState.blocked,
        )
        for index in range(251)
    ]
    healthy = _item("z-healthy", captured_at=NOW - timedelta(days=1))
    store = _store_for([*quarantined, healthy])
    monkeypatch.setattr(consolidation, "get_document_store", lambda: store)

    pending = list_pending_consolidation_items(UID, now=NOW)

    assert [item.memory_id for item in pending] == ["z-healthy"]
    assert store.stream_limit == 250
    assert store.streamed_count == 1


def test_blocked_page_cursor_preserves_stable_order_while_advancing_the_window(monkeypatch) -> None:
    captured_at = NOW - timedelta(days=1)
    store = _store_for(
        [
            _item("memory-a", captured_at=captured_at),
            _item("memory-b", captured_at=captured_at),
            _item("memory-c", captured_at=captured_at),
        ]
    )
    monkeypatch.setattr(consolidation, "get_document_store", lambda: store)

    pending = list_pending_consolidation_items(
        UID,
        now=NOW,
        start_after=(captured_at, "memory-b"),
    )

    assert [item.memory_id for item in pending] == ["memory-c"]
