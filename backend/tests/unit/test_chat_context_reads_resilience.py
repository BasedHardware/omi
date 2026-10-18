"""Tests for timestamp coercion and missing id resilience in chat_context_reads."""

from datetime import datetime, timezone
import pytest

from database.chat_context_reads import _coerce_datetime_sort_key, get_recent_activity


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", "01234567890123456789012345678901")


class _FakeDoc:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def document(self, doc_id):
        return self

    def collection(self, col_name):
        return self

    def order_by(self, field, direction=None):
        return self

    def limit(self, n):
        return self

    def stream(self, timeout=None, retry=None):
        return iter(self._docs)


class _FakeFirestoreClient:
    def __init__(self, docs):
        self._docs = docs

    def collection(self, col_name):
        return _FakeCollection(self._docs)


def test_coerce_datetime_sort_key():
    # Aware datetime
    dt_aware = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    assert _coerce_datetime_sort_key(dt_aware) == dt_aware

    # Naive datetime
    dt_naive = datetime(2026, 10, 18, 12, 0, 0)
    coerced_naive = _coerce_datetime_sort_key(dt_naive)
    assert coerced_naive.tzinfo == timezone.utc
    assert coerced_naive == dt_aware

    # ISO string with Z
    iso_z = "2026-10-18T12:00:00Z"
    assert _coerce_datetime_sort_key(iso_z) == dt_aware

    # ISO string with offset
    iso_offset = "2026-10-18T14:00:00+02:00"
    assert _coerce_datetime_sort_key(iso_offset) == dt_aware

    # Naive ISO string
    iso_naive = "2026-10-18T12:00:00"
    assert _coerce_datetime_sort_key(iso_naive) == dt_aware

    # None or invalid string falls back to datetime.min UTC
    min_utc = datetime.min.replace(tzinfo=timezone.utc)
    assert _coerce_datetime_sort_key(None) == min_utc
    assert _coerce_datetime_sort_key("invalid-date") == min_utc
    assert _coerce_datetime_sort_key(12345) == min_utc


def test_get_recent_activity_populates_missing_id():
    docs = [
        _FakeDoc("doc-1", {"text": "first", "created_at": datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)}),
        _FakeDoc("doc-2", {"text": "second", "created_at": datetime(2026, 10, 18, 11, 0, tzinfo=timezone.utc)}),
    ]
    client = _FakeFirestoreClient(docs)

    results = get_recent_activity("user-1", firestore_client=client)

    assert len(results) == 2
    assert results[0]["id"] == "doc-1"
    assert results[1]["id"] == "doc-2"


def test_get_recent_activity_handles_mixed_timestamp_types_and_since_filter():
    docs = [
        _FakeDoc("doc-1", {"id": "doc-1", "created_at": "2026-10-18T09:00:00Z", "text": "before since"}),
        _FakeDoc(
            "doc-2",
            {
                "id": "doc-2",
                "created_at": datetime(2026, 10, 18, 10, 30, tzinfo=timezone.utc),
                "text": "aware after since",
            },
        ),
        _FakeDoc(
            "doc-3",
            {
                "id": "doc-3",
                "created_at": datetime(2026, 10, 18, 10, 15),  # naive datetime
                "text": "naive after since",
            },
        ),
        _FakeDoc(
            "doc-4",
            {
                "id": "doc-4",
                "created_at": "2026-10-18T11:00:00Z",  # iso string
                "text": "string after since",
            },
        ),
    ]
    client = _FakeFirestoreClient(docs)

    # Filtering with ISO string 'since' parameter
    results = get_recent_activity("user-1", since="2026-10-18T10:00:00Z", firestore_client=client)

    assert len(results) == 3
    # Verify sorted ascending by coerced timestamp
    assert [r["id"] for r in results] == ["doc-3", "doc-2", "doc-4"]
