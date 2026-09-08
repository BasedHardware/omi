"""Bounded Firestore query contract for canonical consolidation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.canonical_consolidation import list_pending_consolidation_items
from utils.memory.required_promotion import REQUIRED_PROCESSING_STATUS_PENDING

UID = "uid-consolidation-query"
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


class _Snapshot:
    exists = True

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def to_dict(self) -> dict[str, Any]:
        return dict(self._payload)


def _nested_value(payload: dict[str, Any], field_path: str) -> Any:
    value: Any = payload
    for part in field_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class _Query:
    def __init__(
        self,
        db: "_Db",
        filters: list[tuple[str, str, Any]] | None = None,
        order_fields: list[str] | None = None,
        limit_count: int | None = None,
        start_after_values: dict[str, Any] | None = None,
    ):
        self._db = db
        self._filters = list(filters or [])
        self._order_fields = list(order_fields or [])
        self._limit_count = limit_count
        self._start_after_values = dict(start_after_values or {})

    def where(
        self,
        field_path: str | None = None,
        op_string: str | None = None,
        value: Any = None,
        *,
        filter: Any = None,
    ) -> "_Query":
        if filter is not None:
            field_path = filter.field_path
            op_string = filter.op_string
            value = filter.value
        assert field_path is not None
        assert op_string is not None
        return _Query(
            self._db,
            [*self._filters, (field_path, op_string, value)],
            self._order_fields,
            self._limit_count,
            self._start_after_values,
        )

    def order_by(self, field_path: str) -> "_Query":
        return _Query(
            self._db,
            self._filters,
            [*self._order_fields, field_path],
            self._limit_count,
            self._start_after_values,
        )

    def limit(self, limit_count: int) -> "_Query":
        return _Query(
            self._db,
            self._filters,
            self._order_fields,
            limit_count,
            self._start_after_values,
        )

    def start_after(self, values: dict[str, Any]) -> "_Query":
        return _Query(
            self._db,
            self._filters,
            self._order_fields,
            self._limit_count,
            values,
        )

    def stream(self) -> list[_Snapshot]:
        rows = list(self._db.rows)
        for field_path, op_string, expected in self._filters:
            if op_string == "==":
                rows = [row for row in rows if _nested_value(row[1], field_path) == expected]
            elif op_string == "in":
                rows = [row for row in rows if _nested_value(row[1], field_path) in expected]
            else:
                raise AssertionError(f"unexpected operator: {op_string}")
        for field_path in reversed(self._order_fields):
            rows.sort(key=lambda row: _nested_value(row[1], field_path))
        if self._start_after_values:
            cursor = tuple(self._start_after_values[field_path] for field_path in self._order_fields)
            rows = [
                row
                for row in rows
                if tuple(_nested_value(row[1], field_path) for field_path in self._order_fields) > cursor
            ]
        if self._limit_count is not None:
            rows = rows[: self._limit_count]
        self._db.stream_limit = self._limit_count
        self._db.streamed_count = len(rows)
        self._db.filters = self._filters
        self._db.order_fields = self._order_fields
        return [_Snapshot(payload) for _path, payload in rows]


class _Db:
    def __init__(self, rows: list[tuple[str, dict[str, Any]]]):
        self.rows = rows
        self.stream_limit: int | None = None
        self.streamed_count = 0
        self.filters: list[tuple[str, str, Any]] = []
        self.order_fields: list[str] = []

    def collection(self, _path: str) -> _Query:
        return _Query(self)


def _item(
    memory_id: str,
    *,
    captured_at: datetime,
    status: MemoryItemStatus = MemoryItemStatus.active,
    processing_state: ProcessingState = ProcessingState.processed,
    source_state: SourceState = SourceState.active,
    promotion: dict[str, Any] | None = None,
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
        promotion=promotion or {},
    )


def _db_for(items: list[MemoryItem]) -> _Db:
    return _Db([(f"users/{UID}/memory_items/{item.memory_id}", item.model_dump(mode="python")) for item in items])


def test_consolidation_query_filters_orders_and_limits_before_streaming() -> None:
    same_capture = NOW - timedelta(hours=36)
    db = _db_for(
        [
            _item("eligible-b", captured_at=same_capture),
            _item("eligible-a", captured_at=same_capture),
            _item("eligible-c", captured_at=NOW - timedelta(days=1)),
        ]
    )

    pending = list_pending_consolidation_items(UID, db_client=db, now=NOW, limit=2)

    assert [item.memory_id for item in pending] == ["eligible-a", "eligible-b"]
    assert db.stream_limit == 2
    assert db.streamed_count == 2
    assert db.order_fields == ["captured_at", "memory_id"]
    assert ("tier", "==", MemoryLayer.short_term.value) in db.filters
    assert ("status", "==", MemoryItemStatus.active.value) in db.filters
    assert ("processing_state", "==", ProcessingState.processed.value) in db.filters
    assert ("source_state", "==", SourceState.active.value) in db.filters


def test_ineligible_earlier_ids_cannot_starve_consolidation_at_the_query_cap() -> None:
    ineligible = [
        _item(
            f"a-ineligible-{index:03d}",
            captured_at=NOW - timedelta(days=100, minutes=index),
            status=MemoryItemStatus.superseded,
        )
        for index in range(251)
    ]
    eligible = _item("z-eligible", captured_at=NOW - timedelta(days=1))
    db = _db_for([*ineligible, eligible])

    pending = list_pending_consolidation_items(UID, db_client=db, now=NOW)

    assert [item.memory_id for item in pending] == ["z-eligible"]
    assert db.stream_limit == 250
    assert db.streamed_count == 1


def test_quarantined_blocked_rows_cannot_fill_the_oldest_query_window() -> None:
    quarantined = [
        _item(
            f"a-quarantined-{index:03d}",
            captured_at=NOW - timedelta(days=100, minutes=index),
            processing_state=ProcessingState.blocked,
        )
        for index in range(251)
    ]
    healthy = _item("z-healthy", captured_at=NOW - timedelta(days=1))
    db = _db_for([*quarantined, healthy])

    pending = list_pending_consolidation_items(UID, db_client=db, now=NOW)

    assert [item.memory_id for item in pending] == ["z-healthy"]
    assert db.stream_limit == 250
    assert db.streamed_count == 1


def test_blocked_page_cursor_preserves_stable_order_while_advancing_the_window() -> None:
    captured_at = NOW - timedelta(days=1)
    db = _db_for(
        [
            _item("memory-a", captured_at=captured_at),
            _item("memory-b", captured_at=captured_at),
            _item("memory-c", captured_at=captured_at),
        ]
    )

    pending = list_pending_consolidation_items(
        UID,
        db_client=db,
        now=NOW,
        start_after=(captured_at, "memory-b"),
    )

    assert [item.memory_id for item in pending] == ["memory-c"]


def test_pending_required_items_merge_into_oldest_first_consolidation_batch() -> None:
    older = NOW - timedelta(hours=5)
    newer = NOW - timedelta(hours=1)
    required = _item(
        "req-explicit",
        captured_at=older,
        processing_state=ProcessingState.pending,
        promotion={
            "required": True,
            "processing_status": REQUIRED_PROCESSING_STATUS_PENDING,
        },
    )
    processed = _item("stm-processed", captured_at=newer)
    skipped = _item(
        "req-after-cursor",
        captured_at=newer + timedelta(minutes=1),
        processing_state=ProcessingState.pending,
        promotion={
            "required": True,
            "processing_status": REQUIRED_PROCESSING_STATUS_PENDING,
        },
    )
    db = _db_for([processed, required, skipped])

    pending = list_pending_consolidation_items(UID, db_client=db, now=NOW, limit=2)

    assert [item.memory_id for item in pending] == ["req-explicit", "stm-processed"]
    assert pending[0].processing_state == ProcessingState.pending
    assert pending[1].processing_state == ProcessingState.processed


def test_expired_required_submissions_stay_eligible_for_consolidation() -> None:
    required = _item(
        "req-expired",
        captured_at=NOW - timedelta(hours=60),
        processing_state=ProcessingState.pending,
        promotion={
            "required": True,
            "processing_status": REQUIRED_PROCESSING_STATUS_PENDING,
        },
    )
    required = required.model_copy(update={"expires_at": NOW - timedelta(hours=12)})
    processed_expired = _item("stm-expired", captured_at=NOW - timedelta(hours=60))
    processed_expired = processed_expired.model_copy(update={"expires_at": NOW - timedelta(hours=12)})
    db = _db_for([required, processed_expired])

    pending = list_pending_consolidation_items(UID, db_client=db, now=NOW, limit=10)

    assert [item.memory_id for item in pending] == ["req-expired"]
