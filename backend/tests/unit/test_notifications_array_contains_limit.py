"""Deterministic reproduction test for Firestore 'in' 30-element query limit in database/notifications.py.

Firestore imposes a strict maximum of 30 elements on 'in' query filters.
When more than 30 elements are provided to a query filter, Firestore raises:
`google.api_core.exceptions.InvalidArgument: 400 'in' filters support up to 30 elements`.

In database/notifications.py:
1. `remove_bulk_tokens` chunks token lists into slices of <= 30 items when querying fcm_tokens.
2. `get_users_token_in_timezones` and `get_users_id_in_timezones` chunk timezone lists into slices of <= 30 items.
3. Partial failure in `_get_users_in_timezones` logs the error and continues to resolve remaining chunks.

This test simulates Firestore's server-side 30-element limit and proves:
- Direct unchunked queries exceeding 30 items deterministically fail with InvalidArgument.
- Chunked functions safely handle > 30 items by slicing into batches of <= 30 items.
- Empty inputs return immediately without issuing queries.
- Partial chunk failures are logged without aborting remaining chunks.
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
    """Mock query that enforces Firestore's strict limit of <= 30 items on 'in' filters."""

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
        filter_tuples = []
        for f in self.filters:
            if isinstance(f, FieldFilter):
                field_path = getattr(f, "field_path", "")
                op = getattr(f, "operator_string", None) or getattr(f, "op_string", "")
                val = getattr(f, "value", None)
                filter_tuples.append((field_path, op, val))
        self.parent_db.executed_queries.append(filter_tuples)

        if self.parent_db.fail_on_chunk and any(
            self.parent_db.fail_on_chunk in val
            for _, _, val in filter_tuples
            if isinstance(val, (list, tuple, set))
        ):
            raise RuntimeError(f"Simulated transient error on chunk containing {self.parent_db.fail_on_chunk}")

        if self.collection_name == "fcm_tokens":
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
            matched = []
            for f_path, op, val in filter_tuples:
                if (
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
        token_doc = MagicMock()
        token_doc.id = f"device_{self.uid}"
        token_doc.to_dict.return_value = {"token": f"fcm_{self.uid}"}
        col_mock = MagicMock()
        col_mock.stream.return_value = [token_doc]
        return col_mock


class _FakeFirestoreClient:
    def __init__(self, fail_on_chunk: str | None = None):
        self.executed_queries: List[List[Any]] = []
        self.batch_commit_counts: List[int] = []
        self.fail_on_chunk = fail_on_chunk

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
        client.collection_group("fcm_tokens").where(
            filter=FieldFilter("token", "in", excessive_tokens)
        )
    assert "at most 30 elements" in str(exc_info.value)
    assert "got 35" in str(exc_info.value)


def test_remove_bulk_tokens_handles_more_than_30_tokens():
    """When deleting 35 invalid tokens, remove_bulk_tokens must chunk into slices of <= 30."""
    fake_client = _FakeFirestoreClient()
    tokens = [f"invalid_token_{i}" for i in range(35)]

    notifications_db.remove_bulk_tokens(tokens, firestore_client=fake_client)

    # 35 items sliced into 2 chunks (30 and 5)
    assert len(fake_client.executed_queries) == 2
    for query_filters in fake_client.executed_queries:
        for f_path, op, val in query_filters:
            assert len(val) <= _FIRESTORE_IN_LIMIT

    assert sum(fake_client.batch_commit_counts) == 35


def test_remove_bulk_tokens_empty_noop():
    """Empty token list should return immediately without issuing queries."""
    fake_client = _FakeFirestoreClient()
    notifications_db.remove_bulk_tokens([], firestore_client=fake_client)
    assert len(fake_client.executed_queries) == 0


def test_get_users_token_in_timezones_handles_more_than_30_timezones():
    """When querying users in 35 timezones, timezone filters must be chunked <= 30."""
    fake_client = _FakeFirestoreClient()
    timezones = [f"TZ_{i}" for i in range(35)]

    tokens = notifications_db.get_users_token_in_timezones(
        timezones, firestore_client=fake_client
    )

    assert len(fake_client.executed_queries) == 2
    for query_filters in fake_client.executed_queries:
        for f_path, op, val in query_filters:
            assert len(val) <= _FIRESTORE_IN_LIMIT
    assert len(tokens) > 0


def test_get_users_token_in_timezones_empty():
    """Empty timezone list should return [] immediately without querying."""
    fake_client = _FakeFirestoreClient()
    tokens = notifications_db.get_users_token_in_timezones([], firestore_client=fake_client)
    assert tokens == []
    assert len(fake_client.executed_queries) == 0


def test_get_users_id_in_timezones_handles_more_than_30_timezones():
    """When querying user IDs across 35 timezones, timezone filters must be chunked <= 30."""
    fake_client = _FakeFirestoreClient()
    timezones = [f"TZ_{i}" for i in range(35)]

    user_tuples = notifications_db.get_users_id_in_timezones(
        timezones, firestore_client=fake_client
    )

    assert len(fake_client.executed_queries) == 2
    for query_filters in fake_client.executed_queries:
        for f_path, op, val in query_filters:
            assert len(val) <= _FIRESTORE_IN_LIMIT

    # Count derived from mock documents: 1 mock user per timezone in mock
    assert len(user_tuples) == len(timezones)
    for uid, tokens, tz in user_tuples:
        assert uid.startswith("user_tz_")
        assert len(tokens) > 0
        assert tz in timezones


def test_get_users_in_timezones_partial_failure_logs_and_continues():
    """Verify partial failure semantics: one failed chunk logs error without aborting remaining chunks."""
    # Chunk 1 (TZ_0..TZ_29) has TZ_0 which will fail; Chunk 2 (TZ_30..TZ_34) should still resolve
    fake_client = _FakeFirestoreClient(fail_on_chunk="TZ_0")
    timezones = [f"TZ_{i}" for i in range(35)]

    user_tuples = notifications_db.get_users_id_in_timezones(
        timezones, firestore_client=fake_client
    )

    # 2 query attempts were made
    assert len(fake_client.executed_queries) == 2
    # Only Chunk 2 (5 timezones: TZ_30..TZ_34) succeeded and returned records
    assert len(user_tuples) == 5
    for uid, tokens, tz in user_tuples:
        assert tz in timezones[30:]
