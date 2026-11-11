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

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.conversations as conv

_FIRESTORE_IN_LIMIT = 30

_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
_END = datetime(2026, 9, 29, tzinfo=timezone.utc)


class _FirestoreLikeDB:
    """Records the filter it was asked for and raises past the real Firestore `in` limit."""

    def __init__(self):
        self.last_statuses = None
        self.last_sources = None
        self.last_include_discarded = None
        self.last_folder_id = None
        self.last_starred = None
        self.last_start_date = None
        self.last_end_date = None

    def _record(self, kwargs):
        self.last_folder_id = kwargs.get('folder_id')
        self.last_starred = kwargs.get('starred')
        self.last_start_date = kwargs.get('start_date')
        self.last_end_date = kwargs.get('end_date')

    def get_conversations_without_photos(self, uid, limit, offset, *, statuses=(), **kwargs):
        self.last_statuses = list(statuses)
        self.last_sources = list(kwargs.get('sources') or [])
        self.last_include_discarded = kwargs.get('include_discarded')
        self._record(kwargs)
        if len(statuses) > _FIRESTORE_IN_LIMIT or len(self.last_sources) > _FIRESTORE_IN_LIMIT:
            raise Exception("'in' filters support a maximum of 30 elements.")
        return []

    def get_conversations_count(self, uid, *, statuses=(), sources=(), **kwargs):
        self.last_statuses = list(statuses)
        self.last_sources = list(sources)
        self._record(kwargs)
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


def test_list_hides_discarded_rows_by_default(db):
    conv.get_conversations(statuses="processing,completed", sources=None, start_date=None, end_date=None, uid="u1")

    assert db.last_include_discarded is False


def test_list_can_explicitly_include_discarded_rows(db):
    conv.get_conversations(
        statuses="processing,completed",
        sources=None,
        start_date=None,
        end_date=None,
        include_discarded=True,
        uid="u1",
    )

    assert db.last_include_discarded is True


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


def test_list_multi_source_multi_status_rejected_before_db(db):
    with pytest.raises(HTTPException) as ei:
        conv.get_conversations(
            statuses="processing,completed",
            sources="omi,friend",
            start_date=None,
            end_date=None,
            uid="u1",
        )

    assert ei.value.status_code == 400
    assert db.last_statuses is None


def test_count_multi_source_multi_status_rejected_before_db(db):
    with pytest.raises(HTTPException) as ei:
        conv.get_conversations_count(
            statuses="processing,completed",
            sources="omi,friend",
            start_date=None,
            end_date=None,
            uid="u1",
        )

    assert ei.value.status_code == 400
    assert db.last_statuses is None
    assert db.last_sources is None


def test_list_single_source_multi_status_accepted(db):
    result = conv.get_conversations(
        statuses="processing,completed",
        sources="omi",
        start_date=_START,
        end_date=_END,
        folder_id="folder-a",
        starred=False,
        uid="u1",
    )

    assert result == []
    assert db.last_sources == ["omi"]
    assert db.last_statuses == ["processing", "completed"]
    assert db.last_folder_id == "folder-a"
    assert db.last_starred is False
    assert db.last_start_date == _START
    assert db.last_end_date == _END


def test_list_multi_source_single_status_accepted(db):
    result = conv.get_conversations(
        statuses="completed",
        sources="omi,friend",
        start_date=_START,
        end_date=_END,
        folder_id="folder-a",
        starred=False,
        uid="u1",
    )

    assert result == []
    assert db.last_sources == ["omi", "friend"]
    assert db.last_statuses == ["completed"]
    assert db.last_starred is False


def test_count_single_source_multi_status_accepted_and_echoed(db):
    result = conv.get_conversations_count(
        statuses="processing,completed",
        sources="omi",
        start_date=_START,
        end_date=_END,
        folder_id="folder-a",
        starred=False,
        uid="u1",
    )

    assert result == {"count": 0, "sources": ["omi"]}
    assert db.last_sources == ["omi"]
    assert db.last_statuses == ["processing", "completed"]
    assert db.last_folder_id == "folder-a"
    assert db.last_starred is False
    assert db.last_start_date == _START
    assert db.last_end_date == _END


def test_count_multi_source_single_status_accepted_and_echoed(db):
    result = conv.get_conversations_count(
        statuses="completed",
        sources="omi,friend",
        start_date=_START,
        end_date=_END,
        folder_id="folder-a",
        starred=False,
        uid="u1",
    )

    assert result == {"count": 0, "sources": ["omi", "friend"]}
    assert db.last_sources == ["omi", "friend"]
    assert db.last_statuses == ["completed"]
    assert db.last_starred is False


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(conv.router)
    app.dependency_overrides[conv.auth.get_current_user_uid] = lambda: "u1"
    with TestClient(app) as test_client:
        yield test_client


def test_wire_list_omitted_statuses_defaults_to_processing_completed(client, db):
    response = client.get("/v1/conversations")

    assert response.status_code == 200
    assert response.json() == []
    assert db.last_statuses == ["processing", "completed"]
    assert db.last_sources == []


def test_wire_list_empty_statuses_defaults_to_processing_completed(client, db):
    response = client.get("/v1/conversations", params={"statuses": ""})

    assert response.status_code == 200
    assert db.last_statuses == ["processing", "completed"]


def test_wire_count_omitted_statuses_counts_all_statuses(client, db):
    response = client.get("/v1/conversations/count")

    assert response.status_code == 200
    assert response.json() == {"count": 0, "sources": None}
    assert db.last_statuses == []


def test_wire_count_empty_statuses_counts_all_statuses(client, db):
    response = client.get("/v1/conversations/count", params={"statuses": ""})

    assert response.status_code == 200
    assert db.last_statuses == []


def test_wire_count_source_filter_echoed(client, db):
    response = client.get("/v1/conversations/count", params={"sources": "omi"})

    assert response.status_code == 200
    assert response.json() == {"count": 0, "sources": ["omi"]}
    assert db.last_sources == ["omi"]


def test_wire_list_dual_multi_rejected_before_db(client, db):
    response = client.get("/v1/conversations", params={"statuses": "processing,completed", "sources": "omi,friend"})

    assert response.status_code == 400
    assert db.last_statuses is None


def test_wire_count_dual_multi_rejected_before_db(client, db):
    response = client.get(
        "/v1/conversations/count", params={"statuses": "processing,completed", "sources": "omi,friend"}
    )

    assert response.status_code == 400
    assert db.last_statuses is None
    assert db.last_sources is None


def test_wire_count_single_axis_combinations_with_folder_starred_false_and_dates(client, db):
    response = client.get(
        "/v1/conversations/count",
        params={
            "statuses": "completed",
            "sources": "omi,friend",
            "folder_id": "folder-a",
            "starred": "false",
            "start_date": _START.isoformat(),
            "end_date": _END.isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"count": 0, "sources": ["omi", "friend"]}
    assert db.last_statuses == ["completed"]
    assert db.last_sources == ["omi", "friend"]
    assert db.last_folder_id == "folder-a"
    assert db.last_starred is False
    assert db.last_start_date == _START
    assert db.last_end_date == _END


def test_wire_list_single_source_multi_status_with_folder_starred_false_and_dates(client, db):
    response = client.get(
        "/v1/conversations",
        params={
            "statuses": "processing,completed",
            "sources": "omi",
            "folder_id": "folder-a",
            "starred": "false",
            "start_date": _START.isoformat(),
            "end_date": _END.isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json() == []
    assert db.last_statuses == ["processing", "completed"]
    assert db.last_sources == ["omi"]
    assert db.last_folder_id == "folder-a"
    assert db.last_starred is False
    assert db.last_start_date == _START
    assert db.last_end_date == _END
