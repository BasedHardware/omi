"""Unit tests verifying defensive resilience and validation in sync_recording_lineage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import pytest

from database.sync_recording_lineage import (
    MAX_LINEAGE_LIMIT,
    get_origin_generation,
    get_recording_generations,
)


class _MockQuery:
    def __init__(self, items: list[dict[str, Any]] | None = None):
        self._items = items if items is not None else []
        self._limit: int | None = None

    def order_by(self, field: str, direction: Any = None) -> _MockQuery:
        return self

    def select(self, fields: list[str]) -> _MockQuery:
        return self

    def limit(self, count: int) -> _MockQuery:
        self._limit = count
        return self

    def where(self, filter: Any = None) -> _MockQuery:
        return self

    def stream(self) -> list[Any]:
        class _Doc:
            def __init__(self, data: dict[str, Any]):
                self._data = data
                self.id = data.get("id", "doc-1")

            def to_dict(self) -> dict[str, Any]:
                return dict(self._data)

        count = self._limit if self._limit is not None else len(self._items)
        return [_Doc(d) for d in self._items[:count]]


class _MockDoc:
    def __init__(self, query: _MockQuery):
        self._query = query

    def collection(self, name: str) -> Any:
        return self._query


class _MockClient:
    def __init__(self, query: _MockQuery):
        self._query = query

    def collection(self, name: str) -> Any:
        return self

    def document(self, doc_id: str) -> Any:
        return _MockDoc(self._query)


def test_get_recording_generations_validates_inputs() -> None:
    """Verify get_recording_generations strictly validates uid, origin_id, datetimes, and limit."""
    mock_query = _MockQuery([])
    mock_client = _MockClient(mock_query)
    now = datetime.now(timezone.utc)

    # Empty/invalid uid
    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        get_recording_generations("", "orig-1", started_before=now, finished_after=now, limit=10, firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        get_recording_generations("users/bad", "orig-1", started_before=now, finished_after=now, limit=10, firestore_client=mock_client)

    # Empty/invalid origin_id
    with pytest.raises(ValueError, match="origin_id must be a non-empty string"):
        get_recording_generations("u1", "", started_before=now, finished_after=now, limit=10, firestore_client=mock_client)

    # Invalid datetime types
    with pytest.raises(ValueError, match="started_before must be a datetime"):
        get_recording_generations("u1", "orig-1", started_before="2026-09-30", finished_after=now, limit=10, firestore_client=mock_client)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="finished_after must be a datetime"):
        get_recording_generations("u1", "orig-1", started_before=now, finished_after=12345, limit=10, firestore_client=mock_client)  # type: ignore[arg-type]

    # Invalid limits (0, negative, bool)
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        get_recording_generations("u1", "orig-1", started_before=now, finished_after=now, limit=0, firestore_client=mock_client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        get_recording_generations("u1", "orig-1", started_before=now, finished_after=now, limit=-5, firestore_client=mock_client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        get_recording_generations("u1", "orig-1", started_before=now, finished_after=now, limit=True, firestore_client=mock_client)  # type: ignore[arg-type]


def test_get_recording_generations_clamps_large_limit() -> None:
    """Verify limit is clamped to MAX_LINEAGE_LIMIT."""
    mock_query = _MockQuery([])
    mock_client = _MockClient(mock_query)
    now = datetime.now(timezone.utc)

    # Query with limit > MAX_LINEAGE_LIMIT
    get_recording_generations("u1", "orig-1", started_before=now, finished_after=now, limit=9999, firestore_client=mock_client)
    assert mock_query._limit == MAX_LINEAGE_LIMIT + 1


def test_get_origin_generation_validates_inputs() -> None:
    """Verify get_origin_generation strictly validates uid, origin_id, and limit."""
    mock_query = _MockQuery([])
    mock_client = _MockClient(mock_query)

    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        get_origin_generation("", "orig-1", limit=10, firestore_client=mock_client)

    with pytest.raises(ValueError, match="origin_id must be a non-empty string"):
        get_origin_generation("u1", "  ", limit=10, firestore_client=mock_client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        get_origin_generation("u1", "orig-1", limit=0, firestore_client=mock_client)


def test_get_origin_generation_clamps_large_limit() -> None:
    """Verify get_origin_generation clamps limit to MAX_LINEAGE_LIMIT."""
    mock_query = _MockQuery([])
    mock_client = _MockClient(mock_query)

    get_origin_generation("u1", "orig-1", limit=2000, firestore_client=mock_client)
    assert mock_query._limit == MAX_LINEAGE_LIMIT + 1
