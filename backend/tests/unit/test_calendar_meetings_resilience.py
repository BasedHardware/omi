"""Hermetic unit tests for calendar_meetings resilience and input validation."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from google.api_core.exceptions import NotFound

import database.calendar_meetings as calendar_meetings_db


class _FakeSnapshot:
    def __init__(self, exists: bool = True, data: dict | None = None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, doc_id: str, exists: bool = True, data: dict | None = None):
        self.id = doc_id
        self._exists = exists
        self._data = data or {}
        self.update_called_with = None
        self.delete_called = False

    def get(self, transaction=None):
        return _FakeSnapshot(exists=self._exists, data=self._data)

    def set(self, payload, merge=False):
        self._data = payload

    def update(self, payload):
        if not self._exists:
            raise NotFound("Document not found")
        self.update_called_with = payload

    def delete(self):
        if not self._exists:
            raise NotFound("Document not found")
        self.delete_called = True


def test_create_meeting_rejects_empty_or_invalid_uid():
    for invalid_uid in ["", "   ", "user/traversal", "user\\sub", "..", "."]:
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            calendar_meetings_db.create_meeting(
                invalid_uid, {"calendar_source": "google", "calendar_event_id": "evt-1"}
            )


def test_create_meeting_rejects_non_dict_payload():
    with pytest.raises(ValueError, match="meeting_data must be a dictionary"):
        calendar_meetings_db.create_meeting("user-1", "not-a-dict")  # type: ignore[arg-type]


def test_create_meeting_auto_allocates_source_and_event_id_when_missing(monkeypatch):
    fake_ref = _FakeDocRef("test-doc-id")
    mock_col = MagicMock()
    mock_col.return_value.document.return_value = fake_ref
    monkeypatch.setattr(calendar_meetings_db, "_get_meetings_collection", mock_col)

    mock_db = MagicMock()
    mock_db.transaction.return_value = MagicMock()
    monkeypatch.setattr(calendar_meetings_db, "db", mock_db)

    # Missing calendar_source and calendar_event_id should not raise KeyError
    meeting_id = calendar_meetings_db.create_meeting("valid-uid", {"title": "Team Sync"})
    assert isinstance(meeting_id, str)
    assert len(meeting_id) > 0


def test_create_meeting_uses_transaction_contention_retry(monkeypatch):
    fake_ref = _FakeDocRef("test-doc-id")
    mock_col = MagicMock()
    mock_col.return_value.document.return_value = fake_ref
    monkeypatch.setattr(calendar_meetings_db, "_get_meetings_collection", mock_col)

    mock_retry = MagicMock()
    monkeypatch.setattr(calendar_meetings_db, "run_with_transaction_contention_retry", mock_retry)

    mock_db = MagicMock()
    mock_db.transaction.return_value = MagicMock()
    monkeypatch.setattr(calendar_meetings_db, "db", mock_db)

    calendar_meetings_db.create_meeting(
        "user-1",
        {"calendar_source": "google", "calendar_event_id": "evt-1", "title": "Standup"},
    )
    assert mock_retry.call_count == 1
    assert mock_retry.call_args[1]["operation_name"] == "create_calendar_meeting"


def test_update_meeting_safely_noops_on_empty_uid_or_meeting_id():
    with patch.object(calendar_meetings_db, "_get_meetings_collection") as mock_col:
        # Invalid / empty identifiers should safely no-op without Firestore calls
        calendar_meetings_db.update_meeting("", "meeting-1", {"title": "Updated"})
        calendar_meetings_db.update_meeting("uid-1", "", {"title": "Updated"})
        calendar_meetings_db.update_meeting("uid/bad", "meeting-1", {"title": "Updated"})
        calendar_meetings_db.update_meeting("uid-1", "meeting/bad", {"title": "Updated"})
        calendar_meetings_db.update_meeting("uid-1", "meeting-1", "not-a-dict")  # type: ignore[arg-type]
        assert mock_col.call_count == 0


def test_update_meeting_catches_not_found_safely():
    fake_ref = _FakeDocRef("m-1", exists=False)
    with patch.object(calendar_meetings_db, "_get_meetings_collection") as mock_col:
        mock_col.return_value.document.return_value = fake_ref
        # Updating a missing meeting should not raise NotFound
        calendar_meetings_db.update_meeting("uid-1", "m-1", {"title": "Non-existent"})


def test_get_meeting_returns_none_for_invalid_identifiers_or_missing_doc():
    with patch.object(calendar_meetings_db, "_get_meetings_collection") as mock_col:
        assert calendar_meetings_db.get_meeting("", "m-1") is None
        assert calendar_meetings_db.get_meeting("uid-1", "") is None
        assert calendar_meetings_db.get_meeting("uid/bad", "m-1") is None
        assert mock_col.call_count == 0

    fake_ref = _FakeDocRef("m-missing", exists=False)
    with patch.object(calendar_meetings_db, "_get_meetings_collection") as mock_col:
        mock_col.return_value.document.return_value = fake_ref
        assert calendar_meetings_db.get_meeting("uid-1", "m-missing") is None


def test_list_meetings_clamps_negative_and_excessive_limits():
    assert calendar_meetings_db.list_meetings("") == []

    captured_limit = []
    fake_query = MagicMock()
    fake_query.order_by.return_value = fake_query
    fake_query.limit.side_effect = lambda lim: captured_limit.append(lim) or fake_query
    fake_query.stream.return_value = []

    with patch.object(calendar_meetings_db, "_get_meetings_collection", return_value=fake_query):
        calendar_meetings_db.list_meetings("uid-1", limit=-10)
        assert captured_limit[-1] == 1

        calendar_meetings_db.list_meetings("uid-1", limit=99999)
        assert captured_limit[-1] == 500

        calendar_meetings_db.list_meetings("uid-1", limit=25)
        assert captured_limit[-1] == 25


def test_get_meeting_id_by_calendar_event_handles_invalid_inputs():
    assert calendar_meetings_db.get_meeting_id_by_calendar_event("", "evt-1", "google") is None
    assert calendar_meetings_db.get_meeting_id_by_calendar_event("uid-1", "", "google") is None
    assert calendar_meetings_db.get_meeting_id_by_calendar_event("uid-1", "evt-1", "") is None


def test_get_meetings_in_time_range_rejects_inverted_range_or_invalid_uid():
    assert (
        calendar_meetings_db.get_meetings_in_time_range("", datetime.now(timezone.utc), datetime.now(timezone.utc))
        == []
    )

    t_start = datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)
    t_end = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)  # inverted
    assert calendar_meetings_db.get_meetings_in_time_range("uid-1", t_start, t_end) == []
