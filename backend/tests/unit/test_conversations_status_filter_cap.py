"""GET /v1/conversations and /v1/conversations/count must bound their comma-separated filters.

Both endpoints split a comma-separated `statuses` (and the count route also `sources`) into a
list that reaches an unchunked Firestore `in` filter in database/conversations.py:

    conversations_ref.where(filter=FieldFilter('status', 'in', statuses))

Firestore rejects an `in` filter with more than 30 values, and nothing wraps the query, so a
request repeating the query key past thirty raises out of the client and surfaces as an unhandled
HTTP 500 on the core conversation-list route the app hits constantly. ConversationStatus has five
legitimate values, so this is malformed-input surface, not a real client shape.

The fakes here mirror Firestore by raising above thirty values, so the tests prove the guard
rejects with 400 before the query is built, rather than only checking the HTTP status.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import pytest
from fastapi import HTTPException

import routers.conversations as conv

_FIRESTORE_IN_LIMIT = 30


class _FirestoreLikeDB:
    """Records the filter it was asked for and raises past the real Firestore `in` limit."""

    def __init__(self):
        self.last_statuses = None
        self.last_sources = None

    def get_conversations_without_photos(self, uid, limit, offset, *, statuses=(), **kwargs):
        self.last_statuses = list(statuses)
        if len(statuses) > _FIRESTORE_IN_LIMIT:
            raise Exception("'in' filters support a maximum of 30 elements.")
        return []

    def get_conversations_count(self, uid, *, statuses=(), sources=(), **kwargs):
        self.last_statuses = list(statuses)
        self.last_sources = list(sources)
        if len(statuses) > _FIRESTORE_IN_LIMIT or len(sources) > _FIRESTORE_IN_LIMIT:
            raise Exception("'in' filters support a maximum of 30 elements.")
        return 0


@pytest.fixture
def db(monkeypatch):
    fake = _FirestoreLikeDB()
    monkeypatch.setattr(conv, "conversations_db", fake)
    monkeypatch.setattr(conv, "redact_conversations_for_list", lambda conversations: None)
    return fake


# --- list endpoint -----------------------------------------------------------------------


def test_list_oversized_statuses_rejected_before_db(db):
    oversized = ",".join(["completed"] * 40)

    with pytest.raises(HTTPException) as ei:
        conv.get_conversations(statuses=oversized, sources=None, start_date=None, end_date=None, uid="u1")

    assert ei.value.status_code == 400
    # The guard fires before the query is built: the Firestore-like fake never saw the filter.
    assert db.last_statuses is None


def test_list_normal_statuses_reach_db(db):
    result = conv.get_conversations(
        statuses="processing,completed", sources=None, start_date=None, end_date=None, uid="u1"
    )

    assert result == []
    assert db.last_statuses == ["processing", "completed"]


# --- count endpoint ----------------------------------------------------------------------


def test_count_oversized_statuses_rejected_before_db(db):
    oversized = ",".join(["completed"] * 40)

    with pytest.raises(HTTPException) as ei:
        conv.get_conversations_count(statuses=oversized, sources=None, start_date=None, end_date=None, uid="u1")

    assert ei.value.status_code == 400
    assert db.last_statuses is None


def test_count_oversized_sources_rejected_before_db(db):
    oversized = ",".join(["omi"] * 40)

    with pytest.raises(HTTPException) as ei:
        conv.get_conversations_count(statuses=None, sources=oversized, start_date=None, end_date=None, uid="u1")

    assert ei.value.status_code == 400
    assert db.last_sources is None


def test_count_normal_filters_reach_db(db):
    result = conv.get_conversations_count(
        statuses="processing,completed", sources=None, start_date=None, end_date=None, uid="u1"
    )

    assert result == {"count": 0}
    assert db.last_statuses == ["processing", "completed"]
