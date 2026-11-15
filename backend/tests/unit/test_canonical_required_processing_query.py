"""Bounded Firestore query contract for canonical required-memory processing."""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Any

from models.memory_evidence import SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.canonical_required_processing import (
    list_pending_required_processing_items,
    list_receipted_required_processing_items,
    run_required_memory_processing,
)
from utils.memory.required_promotion import (
    REQUIRED_PROCESSING_STATUS_PENDING,
    REQUIRED_PROCESSING_STATUS_REJECTED,
)

UID = "uid-required-query"
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
        after: dict[str, Any] | None = None,
    ):
        self._db = db
        self._filters = list(filters or [])
        self._order_fields = list(order_fields or [])
        self._limit_count = limit_count
        self._after = after

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
            self._after,
        )

    def order_by(self, field_path: str) -> "_Query":
        return _Query(
            self._db,
            self._filters,
            [*self._order_fields, field_path],
            self._limit_count,
            self._after,
        )

    def limit(self, limit_count: int) -> "_Query":
        return _Query(self._db, self._filters, self._order_fields, limit_count, self._after)

    def start_after(self, cursor):
        assert set(cursor) == {'captured_at', 'memory_id'}
        return _Query(self._db, self._filters, self._order_fields, self._limit_count, cursor)

    def stream(self) -> list[_Snapshot]:
        rows = list(self._db.rows)
        for field_path, op_string, expected in self._filters:
            if op_string == "==":
                rows = [row for row in rows if _nested_value(row[1], field_path) == expected]
            elif op_string == "in":
                rows = [row for row in rows if _nested_value(row[1], field_path) in expected]
            elif op_string == ">=":
                rows = [row for row in rows if _nested_value(row[1], field_path) >= expected]
            elif op_string == "<":
                rows = [row for row in rows if _nested_value(row[1], field_path) < expected]
            else:
                raise AssertionError(f"unexpected operator: {op_string}")

        for field_path in reversed(self._order_fields):
            rows.sort(key=lambda row: _nested_value(row[1], field_path))
        if self._after:
            boundary = tuple(self._after[key] for key in self._order_fields)
            rows = [row for row in rows if tuple(_nested_value(row[1], key) for key in self._order_fields) > boundary]

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


def test_required_processing_query_filters_orders_and_limits_before_streaming() -> None:
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
    rows = [
        (f"users/{UID}/memory_items/{item.memory_id}", item.model_dump(mode="python"))
        for item in [*irrelevant, *candidates]
    ]
    db = _Db(rows)

    pending = list_pending_required_processing_items(UID, db_client=db, limit=2)

    assert [item.memory_id for item in pending] == ["eligible-a", "eligible-b"]
    assert db.stream_limit == 8
    assert db.streamed_count == 8
    assert db.order_fields == ["captured_at", "memory_id"]
    assert ("tier", "==", MemoryLayer.short_term.value) in db.filters
    assert ("promotion.required", "==", True) in db.filters
    assert any(field == "promotion.processing_status" and operator == "in" for field, operator, _ in db.filters)


def test_terminal_negative_reviews_cannot_starve_later_required_processing() -> None:
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
    db = _Db(
        [
            (f"users/{UID}/memory_items/{item.memory_id}", item.model_dump(mode="python"))
            for item in [*rejected, eligible]
        ]
    )

    pending = list_pending_required_processing_items(UID, db_client=db, limit=1)

    assert [item.memory_id for item in pending] == ["z-eligible"]
    assert db.stream_limit == 4
    assert db.streamed_count == 1


def test_required_processing_limit_zero_does_not_query() -> None:
    class _Boom:
        def collection(self, _path):
            raise AssertionError("limit=0 must not scan required-processing items")

    report = run_required_memory_processing("uid-zero", db_client=_Boom(), limit=0)
    assert report.attempted_count == 0
    assert report.processed_memory_ids == []


def test_pending_query_is_unwindowed_after_maintenance_retirement() -> None:
    """The maintenance window (MEMORY_MAINTENANCE_CAPTURED_AFTER) was retired with
    memory-maintenance-job on 2026-10-26; pending intake decides every age."""
    items = [_item("old", captured_at=NOW - timedelta(days=30)), _item("new", captured_at=NOW)]
    db = _Db([(f"users/{UID}/memory_items/{item.memory_id}", item.model_dump(mode="python")) for item in items])

    pending = list_pending_required_processing_items(UID, db_client=db, limit=25)

    assert [item.memory_id for item in pending] == ["old", "new"]
    assert all(operator != ">=" for _field, operator, _value in db.filters)


def test_completion_query_excludes_observations_and_unprocessed_rows_before_stream():
    ordinary = [
        _item(f'ordinary-{index}', captured_at=NOW, required=False, processing_status='processed').model_copy(
            update={'processing_state': ProcessingState.processed}
        )
        for index in range(250)
    ]
    ready = _item('ready', captured_at=NOW, processing_status='processed').model_copy(
        update={'processing_state': ProcessingState.processed}
    )
    pending = _item('pending', captured_at=NOW)
    db = _Db(
        [
            (f'users/{UID}/memory_items/{row.memory_id}', row.model_dump(mode='python'))
            for row in [*ordinary, ready, pending]
        ]
    )
    result = list_receipted_required_processing_items(UID, db_client=db)
    assert [row.memory_id for row in result] == ['ready']
    assert db.streamed_count == 1 and db.stream_limit == 100


def test_retry_and_completion_cursors_preserve_same_time_tie_breaks():
    for processed in (False, True):
        rows = [
            _item(
                key, captured_at=NOW, processing_status='processed' if processed else REQUIRED_PROCESSING_STATUS_PENDING
            ).model_copy(
                update={'processing_state': ProcessingState.processed if processed else ProcessingState.pending}
            )
            for key in ('a', 'b', 'c')
        ]
        db = _Db([(f'users/{UID}/memory_items/{row.memory_id}', row.model_dump(mode='python')) for row in rows])
        read = list_receipted_required_processing_items if processed else list_pending_required_processing_items
        result = read(UID, db_client=db, cursor={'captured_at': NOW, 'memory_id': 'a'})
        assert [row.memory_id for row in result] == ['b', 'c']
