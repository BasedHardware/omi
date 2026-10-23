"""Bounded Firestore query contract for canonical consolidation."""

from __future__ import annotations

import os
import pytest
from datetime import datetime, timedelta, timezone
from typing import Any

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.canonical_consolidation import _required_intake_page
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
        source_state_reason='deleted_by_user' if source_state != SourceState.active else None,
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


def test_required_intake_page_filters_orders_and_bounds_before_streaming():
    same_capture = NOW - timedelta(hours=36)
    db = _db_for([_item("b", captured_at=same_capture), _item("a", captured_at=same_capture)])
    snapshots = _required_intake_page(UID, db_client=db)
    assert [row.to_dict()["memory_id"] for row in snapshots] == ["a", "b"]
    assert db.stream_limit == 100
    assert db.order_fields == ["captured_at", "memory_id"]
    assert db.filters == [
        ("tier", "==", "short_term"),
        ("status", "==", "active"),
        ("processing_state", "==", "processed"),
        ("source_state", "==", "active"),
    ]


def test_required_intake_page_paginates_and_wraps():
    db = _db_for([_item("a", captured_at=NOW), _item("b", captured_at=NOW)])
    rows = _required_intake_page(UID, db_client=db, cursor={"captured_at": NOW, "memory_id": "a"})
    assert [row.to_dict()["memory_id"] for row in rows] == ["b"]
    rows = _required_intake_page(UID, db_client=db, cursor={"captured_at": NOW, "memory_id": "z"})
    assert [row.to_dict()["memory_id"] for row in rows] == ["a", "b"]


def test_ordinary_stale_or_pending_observations_are_not_semantically_promoted():
    items = [
        _item("hidden", captured_at=NOW, status=MemoryItemStatus.hidden),
        _item("pending", captured_at=NOW, processing_state=ProcessingState.pending),
        _item("deleted-source", captured_at=NOW, source_state=SourceState.tombstoned),
        _item("visible", captured_at=NOW),
    ]
    db = _db_for(items)
    assert [row.to_dict()["memory_id"] for row in _required_intake_page(UID, db_client=db)] == ["visible"]


class _CursorDb(_Db):
    def __init__(self, rows):
        super().__init__(rows)
        from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

        self.store = StrictFirestore()

    def document(self, path):
        return self.store.document(path)

    def transaction(self):
        return self.store.transaction()


def test_observation_recovery_rotates_bounded_pages_and_ignores_expiry():
    from utils.memory.canonical_consolidation import _pending_observation_ids

    db = _CursorDb(_db_for([_item(f'a{i:02}', captured_at=NOW - timedelta(days=5)) for i in range(30)]).rows)
    first = _pending_observation_ids(UID, db_client=db)
    second = _pending_observation_ids(UID, db_client=db)
    assert first == [f'a{i:02}' for i in range(25)]
    assert second == [f'a{i:02}' for i in range(25, 30)]
    assert _pending_observation_ids(UID, db_client=db) == first
    assert db.stream_limit == 100


def test_observation_recovery_scans_past_a_page_of_review_rows():
    from utils.memory.canonical_consolidation import _pending_observation_ids

    reviews = [
        _item(f'r{i:03}', captured_at=NOW - timedelta(days=5), promotion={'route': 'review'}) for i in range(100)
    ]
    ordinary = _item('z-pending', captured_at=NOW - timedelta(days=4))
    db = _CursorDb(_db_for([*reviews, ordinary]).rows)
    assert _pending_observation_ids(UID, db_client=db) == []
    assert _pending_observation_ids(UID, db_client=db) == [ordinary.memory_id]


def test_recovery_checkpoint_cannot_recreate_metadata_during_account_deletion(monkeypatch):
    from utils.memory import canonical_consolidation as intake

    db = _CursorDb(_db_for([_item('pending', captured_at=NOW)]).rows)
    page = intake._required_intake_page

    def deletion_after_scan(*args, **kwargs):
        rows = page(*args, **kwargs)
        db.store.rows[('account_deletions', UID)] = {'wipe_status': 'completed'}
        return rows

    monkeypatch.setattr(intake, '_required_intake_page', deletion_after_scan)
    with pytest.raises(RuntimeError, match='deletion_fenced'):
        intake._pending_observation_ids(UID, db_client=db)
    assert ('users', UID, 'memory_runs', 'observation_intake_cursor') not in db.store.rows
