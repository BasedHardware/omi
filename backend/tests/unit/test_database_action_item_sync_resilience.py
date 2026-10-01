"""Unit tests verifying defensive resilience and validation in action_item_sync."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import pytest

from database.action_item_sync import (
    MAX_ACTION_ITEMS_SYNC_LIMIT,
    get_action_items_sync_page,
)


class _MockQuery:
    def __init__(self, items: list[dict[str, Any]] | None = None):
        self._items = items if items is not None else []
        self._limit = 100

    def where(self, *args: Any, **kwargs: Any) -> _MockQuery:
        return self

    def order_by(self, field: str, direction: Any = None) -> _MockQuery:
        return self

    def start_after(self, cursor: dict[str, Any]) -> _MockQuery:
        return self

    def select(self, fields: list[str]) -> _MockQuery:
        return self

    def limit(self, count: int) -> _MockQuery:
        self._limit = count
        return self

    def stream(self) -> list[Any]:
        class _Doc:
            def __init__(self, data: dict[str, Any]):
                self._data = data
                self.id = data.get("id", "doc-1")

            def to_dict(self) -> dict[str, Any]:
                return dict(self._data)

        return [_Doc(d) for d in self._items[:self._limit]]


class _MockDocRef:
    def __init__(self, query: _MockQuery):
        self._query = query

    def collection(self, name: str) -> Any:
        return self._query

    def document(self, doc_id: str) -> Any:
        return self


class _MockClient:
    def __init__(self, query: _MockQuery):
        self._query = query

    def collection(self, name: str) -> Any:
        return self

    def document(self, doc_id: str) -> Any:
        return _MockDocRef(self._query)


def test_get_action_items_sync_page_validates_inputs() -> None:
    """Verify get_action_items_sync_page validates uid, limit, and after parameters."""
    mock_query = _MockQuery([])
    mock_client = _MockClient(mock_query)

    # Empty / invalid uid
    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        get_action_items_sync_page("", limit=10, firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        get_action_items_sync_page("bad/uid", limit=10, firestore_client=mock_client)

    # Invalid limits
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        get_action_items_sync_page("u1", limit=0, firestore_client=mock_client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        get_action_items_sync_page("u1", limit=-10, firestore_client=mock_client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        get_action_items_sync_page("u1", limit=True, firestore_client=mock_client)  # type: ignore[arg-type]

    # Invalid after cursor
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="after must be a tuple of"):
        get_action_items_sync_page("u1", after="not-a-tuple", limit=10, firestore_client=mock_client)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="action item sync timestamp is invalid"):
        get_action_items_sync_page("u1", after=(None, "doc-1"), limit=10, firestore_client=mock_client)

    with pytest.raises(ValueError, match="action item sync doc id is invalid"):
        get_action_items_sync_page("u1", after=(now, ""), limit=10, firestore_client=mock_client)

    with pytest.raises(ValueError, match="action item sync doc id is invalid"):
        get_action_items_sync_page("u1", after=(now, "bad/doc"), limit=10, firestore_client=mock_client)


def test_get_action_items_sync_page_clamps_limit() -> None:
    """Verify get_action_items_sync_page clamps limit to MAX_ACTION_ITEMS_SYNC_LIMIT."""
    mock_query = _MockQuery([])
    mock_client = _MockClient(mock_query)

    get_action_items_sync_page("u1", limit=9999, firestore_client=mock_client)
    assert mock_query._limit == MAX_ACTION_ITEMS_SYNC_LIMIT + 1
