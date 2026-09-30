"""Hermetic unit tests for database/mcp_conversation_pages resilience and validation.

Verifies:
- User ID validation against empty, non-string, and path traversal strings.
- Parameter boundary clamping for limit and offset.
- Date range inversion guards and timezone normalization.
- Safe handling of soft-deleted tombstones with missing or null created_at timestamps.
- Keyset cursor position validation and graceful stream fault recovery.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import database.mcp_conversation_pages as pages_db

UID = "user-test-123"


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeDocRef:
    def __init__(self, doc_id):
        self.id = doc_id


class _DescKeysetQuery:
    def __init__(self, docs, stream_error=None):
        self.docs = docs
        self.stream_error = stream_error
        self.order_fields = []
        self.after_values = None
        self.limit_value = None
        self.offset_value = None

    def order_by(self, field, direction=None):
        self.order_fields.append(field)
        return self

    def where(self, filter=None):
        return self

    def select(self, _fields):
        return self

    def document(self, doc_id):
        return _FakeDocRef(doc_id)

    def start_after(self, values):
        self.after_values = dict(values)
        return self

    def limit(self, n):
        self.limit_value = n
        return self

    def offset(self, n):
        self.offset_value = n
        return self

    def stream(self):
        if self.stream_error:
            raise self.stream_error
        rows = self.docs
        if self.after_values is not None:
            ts = self.after_values["created_at"]
            doc_id = self.after_values["__name__"].id
            rows = [d for d in rows if (d._data.get("created_at"), d.id) < (ts, doc_id)]
        start = self.offset_value or 0
        end = start + self.limit_value if self.limit_value is not None else None
        return iter(rows[start:end])


def _stub_client(query):
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = query
    return patch.object(pages_db, "get_firestore_client", return_value=client)


# --- UID Validation Tests ---


@pytest.mark.parametrize(
    "bad_uid",
    [
        "",
        "   ",
        None,
        12345,
        "user/traversal",
        "user\\backslash",
        "../parent/dir",
        "nested/path/to/doc",
    ],
)
def test_validate_uid_rejects_invalid_values(bad_uid):
    with pytest.raises(ValueError, match="Invalid user identifier"):
        pages_db._validate_uid(bad_uid)


def test_validate_uid_accepts_clean_strings():
    assert pages_db._validate_uid("user-12345") == "user-12345"
    assert pages_db._validate_uid("  user-abc_def  ") == "user-abc_def"


# --- Parameter Clamping Tests ---


def test_clamp_limit_handles_boundaries():
    assert pages_db._clamp_limit(-10) == 1
    assert pages_db._clamp_limit(0) == 1
    assert pages_db._clamp_limit(25) == 25
    assert pages_db._clamp_limit(10_000) == 1000
    assert pages_db._clamp_limit("invalid") == 25


def test_clamp_offset_handles_boundaries():
    assert pages_db._clamp_offset(-5) == 0
    assert pages_db._clamp_offset(0) == 0
    assert pages_db._clamp_offset(100) == 100
    assert pages_db._clamp_offset(1_000_000) == 100000
    assert pages_db._clamp_offset("invalid") == 0


# --- Date Filter & Inversion Tests ---


def test_inverted_date_range_returns_empty_fast():
    t0 = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
    t1 = t0 - timedelta(hours=1)

    cards = pages_db.get_mcp_conversation_cards(UID, 10, 0, start_date=t0, end_date=t1)
    assert cards == []

    page, resume = pages_db.get_mcp_conversation_cards_page(UID, 10, start_date=t0, end_date=t1)
    assert page == []
    assert resume is None


def test_normalize_datetime_attaches_utc_timezone():
    naive = datetime(2026, 6, 11, 10, 0)
    aware = pages_db._normalize_datetime(naive)
    assert aware.tzinfo == timezone.utc

    already_aware = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
    assert pages_db._normalize_datetime(already_aware) is already_aware

    assert pages_db._normalize_datetime(None) is None
    assert pages_db._normalize_datetime("not-a-datetime") is None


def test_clean_categories_sanitizes_input():
    assert pages_db._clean_categories(["work", " personal ", ""]) == ["work", "personal"]
    assert pages_db._clean_categories([]) is None
    assert pages_db._clean_categories(None) is None
    assert pages_db._clean_categories(["   "]) is None


# --- Keyset Pagination & Tombstone Resilience Tests ---


def test_keyset_page_handles_tombstones_with_missing_created_at():
    """Verify that tombstones with missing or null created_at do not corrupt last_position or crash pagination."""
    t0 = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
    docs = [
        _FakeDoc("v1", {"created_at": t0 + timedelta(minutes=2), "deleted": False}),
        _FakeDoc("tombstone-corrupt", {"deleted": True}),
        _FakeDoc("v0", {"created_at": t0, "deleted": False}),
    ]
    query = _DescKeysetQuery(docs)
    with _stub_client(query):
        page, resume = pages_db.get_mcp_conversation_cards_page(UID, 2)

    assert [d["id"] for d in page] == ["v1", "v0"]
    assert resume is None


def test_keyset_page_validates_after_position():
    query = _DescKeysetQuery([])
    with _stub_client(query):
        with pytest.raises(ValueError, match="keyset timestamp is invalid"):
            pages_db.get_mcp_conversation_cards_page(UID, 5, after=(None, "doc-1"))

        with pytest.raises(ValueError, match="keyset doc id is invalid"):
            pages_db.get_mcp_conversation_cards_page(UID, 5, after=(datetime.now(timezone.utc), "path/traversal"))

        with pytest.raises(ValueError, match="keyset doc id is invalid"):
            pages_db.get_mcp_conversation_cards_page(UID, 5, after=(datetime.now(timezone.utc), "   "))


def test_get_mcp_conversation_cards_clamps_parameters():
    t0 = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
    docs = [_FakeDoc("c1", {"created_at": t0, "deleted": False})]
    query = _DescKeysetQuery(docs)
    with _stub_client(query):
        cards = pages_db.get_mcp_conversation_cards(UID, limit=-1, offset=-10)

    assert len(cards) == 1
    assert query.limit_value == 1
    assert query.offset_value == 0


def test_query_stream_failure_recovers_gracefully():
    query = _DescKeysetQuery([], stream_error=RuntimeError("Transient Firestore transport error"))
    with _stub_client(query):
        cards = pages_db.get_mcp_conversation_cards(UID, 10, 0)
        assert cards == []

        page, resume = pages_db.get_mcp_conversation_cards_page(UID, 10)
        assert page == []
        assert resume is None
