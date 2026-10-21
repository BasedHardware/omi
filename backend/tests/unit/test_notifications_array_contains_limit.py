"""Deterministic reproduction test for Firestore 'in' / 'array_contains_any' 30-element query limit in database/notifications.py.

Firestore imposes a strict maximum of 30 elements on 'in' and 'array_contains_any' query filters.
When more than 30 elements are provided to a query filter, Firestore raises:
`google.api_core.exceptions.InvalidArgument: 400 'in' / 'array_contains_any' filters support up to 30 elements`.

In database/notifications.py:
1. Multi-user token retrieval `get_tokens_for_users` must chunk user IDs into slices of <= 30 items,
   querying each chunk and aggregating all tokens per user.
2. `remove_bulk_tokens` must chunk token lists into slices of <= 30 items when querying fcm_tokens.
3. `get_users_token_in_timezones` and `get_users_id_in_timezones` must chunk timezone lists into slices of <= 30 items.

This test simulates Firestore's server-side 30-element limit and proves:
- Direct unchunked queries exceeding 30 items deterministically fail with InvalidArgument (RED phase).
- Chunked functions safely handle > 30 items by slicing into batches of <= 30 items (GREEN phase).
- Empty inputs return immediately without issuing queries.
"""

import os
from typing import Any, List
from unittest.mock import MagicMock
import pytest
from google.api_core.exceptions import InvalidArgument
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.base_query import BaseCompositeFilter

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.notifications as notifications_db

_FIRESTORE_IN_LIMIT = 30


class _FirestoreLimitEnforcingQuery:
    """Mock query that enforces Firestore's strict limit of <= 30 items on 'in' and 'array_contains_any' filters."""

    def __init__(self, collection_name: str, parent_db: "_FakeFirestoreClient"):
        self.collection_name = collection_name
        self.parent_db = parent_db
        self.filters: List[Any] = []

    def where(
        self, filter: Any = None, *args: Any, **kwargs: Any
    ) -> "_FirestoreLimitEnforcingQuery":
        if filter is not None:
            self._validate_filter(filter)
            self.filters.append(filter)
        return self

    def _validate_filter(self, filter_obj: Any) -> None:
        if isinstance(filter_obj, BaseCompositeFilter):
            for subfilter in getattr(filter_obj, "filters", []):
                self._validate_filter(subfilter)
        elif isinstance(filter_obj, FieldFilter):
            op = getattr(filter_obj, "operator_string", None) or getattr(
                filter_obj, "op_string", None
            )
            val = getattr(filter_obj, "value", None)
            if (
                op in ("in", "not-in", "array_contains_any")
                and isinstance(val, (list, tuple, set))
                and len(val) > _FIRESTORE_IN_LIMIT
            ):
                raise InvalidArgument(
                    f"400 '{op}' filters require a non-empty array with at most {_FIRESTORE_IN_LIMIT} elements, got {len(val)}"
                )

    def limit(self, count: int) -> "_FirestoreLimitEnforcingQuery":
        return self

    def stream(self):
        # Record the executed query filter
        filter_tuples = []
        for f in self.filters:
            if isinstance(f, FieldFilter):
                field_path = getattr(f, "field_path", "")
                op = getattr(f, "operator_string", None) or getattr(f, "op_string", "")
                val = getattr(f, "value", None)
                filter_tuples.append((field_path, op, val))
        self.parent_db.executed_queries.append(filter_tuples)

        # Return simulated documents matching the filters
        if self.collection_name == "fcm_tokens":
            # Collection group fcm_tokens
            tokens_in_filter = []
            for f_path, op, val in filter_tuples:
                if (
                    f_path == "token"
                    and op == "in"
                    and isinstance(val, (list, tuple, set))
                ):
                    tokens_in_filter.extend(val)
            matched = []
            for t in tokens_in_filter:
                doc = MagicMock()
                doc.id = f"doc_{t}"
                doc.reference = MagicMock()
                doc.to_dict.return_value = {"token": t}
                matched.append(doc)
            return iter(matched)

        if self.collection_name == "users":
            # users collection
            matched = []
            for f_path, op, val in filter_tuples:
                if (
                    f_path in ("__name__", "id")
                    and op == "in"
                    and isinstance(val, (list, tuple, set))
                ):
                    for uid in val:
                        doc = MagicMock()
                        doc.id = uid
                        doc.to_dict.return_value = {
                            "time_zone": "UTC",
                            "fcm_token": f"legacy_{uid}",
                        }
                        matched.append(doc)
                elif (
                    f_path == "time_zone"
                    and op == "in"
                    and isinstance(val, (list, tuple, set))
                ):
                    for tz in val:
                        doc = MagicMock()
                        doc.id = f"user_tz_{tz}"
                        doc.to_dict.return_value = {
                            "time_zone": tz,
                            "fcm_token": f"token_{tz}",
                        }
                        matched.append(doc)
            return iter(matched)

        return iter([])


class _FakeBatch:
    def __init__(self, commit_sink: list[int]):
        self.commit_sink = commit_sink
        self.count = 0

    def delete(self, ref: Any) -> None:
        self.count += 1

    def commit(self) -> None:
        self.commit_sink.append(self.count)
        self.count = 0


class _FakeUserDocumentRef:
    def __init__(self, uid: str, client: "_FakeFirestoreClient"):
        self.uid = uid
        self.client = client

    def collection(self, name: str):
        assert name == "fcm_tokens"
        # Return subcollection tokens mock
        token_doc = MagicMock()
        token_doc.id = f"device_{self.uid}"
        token_doc.to_dict.return_value = {"token": f"fcm_{self.uid}"}
        col_mock = MagicMock()
        col_mock.stream.return_value = [token_doc]
        return col_mock


class _FakeFirestoreClient:
    def __init__(self):
        self.executed_queries: List[List[Any]] = []
        self.batch_commit_counts: List[int] = []

    def collection(self, name: str):
        query = _FirestoreLimitEnforcingQuery(name, self)
        col = MagicMock()
        col.where = query.where
        col.document.side_effect = lambda uid: _FakeUserDocumentRef(uid, self)
        return col

    def collection_group(self, name: str):
        return _FirestoreLimitEnforcingQuery(name, self)

    def batch(self) -> _FakeBatch:
        return _FakeBatch(self.batch_commit_counts)


def test_unchunked_in_filter_exceeding_30_raises_invalid_argument():
    """Verify that an unchunked query with > 30 items deterministically fails against Firestore limit."""
    client = _FakeFirestoreClient()
    excessive_tokens = [f"token_{i}" for i in range(35)]

    with pytest.raises(InvalidArgument) as exc_info:
        # Direct unchunked query with 35 items
        client.collection_group("fcm_tokens").where(
            filter=FieldFilter("token", "in", excessive_tokens)
        )
    assert "at most 30 elements" in str(exc_info.value)
    assert "got 35" in str(exc_info.value)


def test_get_tokens_for_users_handles_more_than_30_uids(monkeypatch):
    """When querying tokens for 35 user IDs, get_tokens_for_users must chunk into slices of <= 30."""
    fake_client = _FakeFirestoreClient()
    monkeypatch.setattr(notifications_db, "db", fake_client)
    monkeypatch.setattr(notifications_db, "get_firestore_client", lambda: fake_client)

    uids = [f"user_{i}" for i in range(35)]
    # In unpatched code, get_tokens_for_users does not exist
    results = notifications_db.get_tokens_for_users(uids, firestore_client=fake_client)

    # 35 users should be sliced into 2 query chunks (30 and 5)
    assert len(fake_client.executed_queries) == 2
    for query_filters in fake_client.executed_queries:
        for f_path, op, val in query_filters:
            assert len(val) <= _FIRESTORE_IN_LIMIT

    # All 35 users should have tokens returned
    assert len(results) == 35
    for uid in uids:
        assert uid in results
        assert f"fcm_{uid}" in results[uid]


def test_remove_bulk_tokens_handles_more_than_30_tokens(monkeypatch):
    """When deleting 35 invalid tokens, remove_bulk_tokens must chunk into slices of <= 30."""
    fake_client = _FakeFirestoreClient()
    monkeypatch.setattr(notifications_db, "db", fake_client)
    monkeypatch.setattr(notifications_db, "get_firestore_client", lambda: fake_client)

    tokens = [f"invalid_token_{i}" for i in range(35)]
    notifications_db.remove_bulk_tokens(tokens, firestore_client=fake_client)

    # Should execute in 2 query chunks (30 and 5)
    assert len(fake_client.executed_queries) == 2
    for query_filters in fake_client.executed_queries:
        for f_path, op, val in query_filters:
            assert len(val) <= _FIRESTORE_IN_LIMIT

    # Deletions were committed in batch
    assert sum(fake_client.batch_commit_counts) == 35


def test_get_users_token_in_timezones_handles_more_than_30_timezones(monkeypatch):
    """When querying users in 35 timezones, timezone filters must be chunked <= 30."""
    fake_client = _FakeFirestoreClient()
    monkeypatch.setattr(notifications_db, "db", fake_client)
    monkeypatch.setattr(notifications_db, "get_firestore_client", lambda: fake_client)

    timezones = [f"TZ_{i}" for i in range(35)]
    tokens = notifications_db.get_users_token_in_timezones(
        timezones, firestore_client=fake_client
    )

    assert len(fake_client.executed_queries) == 2
    for query_filters in fake_client.executed_queries:
        for f_path, op, val in query_filters:
            assert len(val) <= _FIRESTORE_IN_LIMIT
    assert len(tokens) > 0


def test_get_users_id_in_timezones_handles_more_than_30_timezones(monkeypatch):
    """When querying user IDs across 35 timezones, timezone filters must be chunked <= 30."""
    fake_client = _FakeFirestoreClient()
    monkeypatch.setattr(notifications_db, "db", fake_client)
    monkeypatch.setattr(notifications_db, "get_firestore_client", lambda: fake_client)

    timezones = [f"TZ_{i}" for i in range(35)]
    user_tuples = notifications_db.get_users_id_in_timezones(
        timezones, firestore_client=fake_client
    )

    assert len(fake_client.executed_queries) == 2
    for query_filters in fake_client.executed_queries:
        for f_path, op, val in query_filters:
            assert len(val) <= _FIRESTORE_IN_LIMIT
    assert len(user_tuples) == 35


def test_get_tokens_for_users_empty_noop(monkeypatch):
    """Empty uid list should immediately return an empty dictionary without querying."""
    fake_client = _FakeFirestoreClient()
    monkeypatch.setattr(notifications_db, "get_firestore_client", lambda: fake_client)

    results = notifications_db.get_tokens_for_users([], firestore_client=fake_client)
    assert results == {}
    assert len(fake_client.executed_queries) == 0


def test_chunked_filter_in_cleans_duplicates_and_nones():
    """Verify chunked_filter_in strips None and deduplicates values preserving order."""
    mock_collection = MagicMock()
    mock_query = MagicMock()
    mock_collection.where.return_value = mock_query
    mock_query.stream.return_value = []

    # 35 unique values, plus None and duplicates
    unique_tokens = [f"tok_{i}" for i in range(35)]
    raw_tokens = [None, unique_tokens[0], None, unique_tokens[1], unique_tokens[0]] + unique_tokens

    results = notifications_db.chunked_filter_in(mock_collection, "token", raw_tokens, op="in")
    assert results == []

    # Should have called where twice: chunk 1 (30 items), chunk 2 (5 items)
    assert mock_collection.where.call_count == 2
    first_call_filter = mock_collection.where.call_args_list[0].kwargs["filter"]
    second_call_filter = mock_collection.where.call_args_list[1].kwargs["filter"]
    assert len(first_call_filter.value) == 30
    assert len(second_call_filter.value) == 5
    assert None not in first_call_filter.value
    assert None not in second_call_filter.value


def test_chunked_filter_in_deduplicates_docs_across_chunks_for_array_contains_any():
    """Verify documents returned across multiple chunks in array_contains_any are deduplicated by doc.id."""
    mock_collection = MagicMock()

    doc_dup = MagicMock()
    doc_dup.id = "shared_doc_1"
    doc_chunk1 = MagicMock()
    doc_chunk1.id = "unique_doc_chunk1"
    doc_chunk2 = MagicMock()
    doc_chunk2.id = "unique_doc_chunk2"

    q1 = MagicMock()
    q1.stream.return_value = [doc_dup, doc_chunk1]
    q2 = MagicMock()
    q2.stream.return_value = [doc_dup, doc_chunk2]

    mock_collection.where.side_effect = [q1, q2]

    # 35 elements forces 2 chunks
    tags = [f"tag_{i}" for i in range(35)]
    results = notifications_db.chunked_filter_in(
        mock_collection, "tags", tags, op="array_contains_any"
    )

    # doc_dup must only appear once, preserving first-seen order
    assert len(results) == 3
    assert [d.id for d in results] == ["shared_doc_1", "unique_doc_chunk1", "unique_doc_chunk2"]


def test_chunked_filter_in_empty_returns_empty():
    """Verify empty or all-None input returns [] immediately without querying."""
    mock_collection = MagicMock()
    assert notifications_db.chunked_filter_in(mock_collection, "field", []) == []
    assert notifications_db.chunked_filter_in(mock_collection, "field", [None, None]) == []
    assert mock_collection.where.call_count == 0

