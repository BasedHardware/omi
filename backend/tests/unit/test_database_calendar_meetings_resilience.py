"""Hermetic unit tests for input validation, boundary guards, and resilience in database/calendar_meetings.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import database.calendar_meetings as cm_db


def _make_mock_snapshot(doc_id: str = "meeting_1", data: dict | None = None, exists: bool = True):
    snap = MagicMock()
    snap.id = doc_id
    snap.exists = exists
    snap.to_dict.return_value = data if data is not None else {}
    return snap


@pytest.fixture(autouse=True)
def hermetic_firestore(monkeypatch):
    """Enforce hermetic test isolation by replacing Firestore client with a mock."""
    fake_db = MagicMock()
    monkeypatch.setattr(cm_db, "db", fake_db)
    return fake_db


# ---------------------------------------------------------------------------
# Input validation: uid rejection across all functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_create_meeting_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        data = {"calendar_source": "google", "calendar_event_id": "e1"}
        cm_db.create_meeting(invalid_uid, data)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_update_meeting_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cm_db.update_meeting(invalid_uid, "m1", {"title": "new"})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_meeting_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cm_db.get_meeting(invalid_uid, "m1")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_meeting_id_by_calendar_event_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cm_db.get_meeting_id_by_calendar_event(invalid_uid, "e1", "google")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_list_meetings_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cm_db.list_meetings(invalid_uid)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_delete_meeting_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cm_db.delete_meeting(invalid_uid, "m1")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_delete_old_meetings_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cm_db.delete_old_meetings(invalid_uid, datetime.now(timezone.utc))  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_meetings_in_time_range_rejects_invalid_uid(invalid_uid):
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cm_db.get_meetings_in_time_range(invalid_uid, now, now)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# meeting_id input validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_mid", [None, "", "   ", 123, []])
def test_update_meeting_rejects_invalid_meeting_id(invalid_mid):
    with pytest.raises(ValueError, match="meeting_id must be a non-empty string"):
        cm_db.update_meeting("u1", invalid_mid, {"title": "new"})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_mid", [None, "", "   ", 123, []])
def test_get_meeting_rejects_invalid_meeting_id(invalid_mid):
    with pytest.raises(ValueError, match="meeting_id must be a non-empty string"):
        cm_db.get_meeting("u1", invalid_mid)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_mid", [None, "", "   ", 123, []])
def test_delete_meeting_rejects_invalid_meeting_id(invalid_mid):
    with pytest.raises(ValueError, match="meeting_id must be a non-empty string"):
        cm_db.delete_meeting("u1", invalid_mid)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# create_meeting validation and upsert
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_data", [None, "not-a-dict", 123, []])
def test_create_meeting_rejects_non_dict(invalid_data):
    with pytest.raises(ValueError, match="meeting_data must be a dictionary"):
        cm_db.create_meeting("u1", invalid_data)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_src", [None, "", "   ", 123])
def test_create_meeting_rejects_invalid_calendar_source(invalid_src):
    with pytest.raises(ValueError, match="calendar_source must be a non-empty string"):
        data = {"calendar_source": invalid_src, "calendar_event_id": "e1"}
        cm_db.create_meeting("u1", data)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_eid", [None, "", "   ", 123])
def test_create_meeting_rejects_invalid_calendar_event_id(invalid_eid):
    with pytest.raises(ValueError, match="calendar_event_id must be a non-empty string"):
        data = {"calendar_source": "google", "calendar_event_id": invalid_eid}
        cm_db.create_meeting("u1", data)  # type: ignore[arg-type]


def test_create_meeting_creates_new_document_with_created_at():
    fake_doc_ref = MagicMock()
    fake_tx = MagicMock()
    fake_doc_ref.get.return_value = _make_mock_snapshot("m1", exists=False)

    with patch.object(cm_db.db, "collection") as mock_col, patch.object(cm_db.db, "transaction", return_value=fake_tx):
        mock_col.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref

        meeting_data = {"calendar_source": "google", "calendar_event_id": "evt-123", "title": "Team Standup"}
        meeting_id = cm_db.create_meeting("  user_abc  ", meeting_data)

        assert meeting_id is not None
        fake_tx.set.assert_called_once()
        saved_payload = fake_tx.set.call_args[0][1]
        assert saved_payload["title"] == "Team Standup"
        assert "created_at" in saved_payload
        assert "synced_at" in saved_payload


def test_create_meeting_preserves_created_at_on_existing_document():
    fake_doc_ref = MagicMock()
    fake_tx = MagicMock()
    fake_doc_ref.get.return_value = _make_mock_snapshot("m1", exists=True, data={"title": "Old"})

    with patch.object(cm_db.db, "collection") as mock_col, patch.object(cm_db.db, "transaction", return_value=fake_tx):
        mock_col.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref

        meeting_data = {"calendar_source": "google", "calendar_event_id": "evt-123", "title": "Updated Standup"}
        meeting_id = cm_db.create_meeting("user_abc", meeting_data)

        assert meeting_id is not None
        fake_tx.set.assert_called_once()
        saved_payload = fake_tx.set.call_args[0][1]
        assert saved_payload["title"] == "Updated Standup"
        assert "created_at" not in saved_payload
        assert "synced_at" in saved_payload


# ---------------------------------------------------------------------------
# update_meeting
# ---------------------------------------------------------------------------


def test_update_meeting_rejects_non_dict():
    with pytest.raises(ValueError, match="meeting_data must be a dictionary"):
        cm_db.update_meeting("u1", "m1", "not-a-dict")  # type: ignore[arg-type]


def test_update_meeting_empty_dict_noop():
    with patch.object(cm_db.db, "collection") as mock_col:
        cm_db.update_meeting("u1", "m1", {})
        mock_col.assert_not_called()


def test_update_meeting_applies_synced_at():
    fake_doc_ref = MagicMock()
    with patch.object(cm_db.db, "collection") as mock_col:
        mock_col.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref

        cm_db.update_meeting("  u1  ", "  m1  ", {"title": "New Title"})
        fake_doc_ref.update.assert_called_once()
        payload = fake_doc_ref.update.call_args[0][0]
        assert payload["title"] == "New Title"
        assert "synced_at" in payload


# ---------------------------------------------------------------------------
# get_meeting and get_meeting_id_by_calendar_event
# ---------------------------------------------------------------------------


def test_get_meeting_returns_none_when_missing():
    fake_doc_ref = MagicMock()
    fake_doc_ref.get.return_value = _make_mock_snapshot("m1", exists=False)

    with patch.object(cm_db.db, "collection") as mock_col:
        mock_col.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref
        assert cm_db.get_meeting("u1", "m1") is None


def test_get_meeting_returns_dict_with_id():
    fake_doc_ref = MagicMock()
    fake_doc_ref.get.return_value = _make_mock_snapshot("doc_123", {"title": "Meeting"}, exists=True)

    with patch.object(cm_db.db, "collection") as mock_col:
        mock_col.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref
        res = cm_db.get_meeting("u1", "doc_123")
        assert res is not None
        assert res["id"] == "doc_123"
        assert res["title"] == "Meeting"


@pytest.mark.parametrize("invalid_val", [None, "", "   ", 123])
def test_get_meeting_id_by_calendar_event_rejects_invalid_inputs(invalid_val):
    with pytest.raises(ValueError, match="calendar_event_id must be a non-empty string"):
        cm_db.get_meeting_id_by_calendar_event("u1", invalid_val, "google")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="calendar_source must be a non-empty string"):
        cm_db.get_meeting_id_by_calendar_event("u1", "e1", invalid_val)  # type: ignore[arg-type]


def test_get_meeting_id_by_calendar_event_found_and_not_found():
    fake_query = MagicMock()
    with patch.object(cm_db.db, "collection") as mock_col:
        coll = mock_col.return_value.document.return_value.collection.return_value
        coll.where.return_value.where.return_value.limit.return_value = fake_query

        # Found case
        mock_doc = MagicMock()
        mock_doc.id = "found_doc_id"
        fake_query.stream.return_value = [mock_doc]
        assert cm_db.get_meeting_id_by_calendar_event("u1", "e1", "google") == "found_doc_id"

        # Not found case
        fake_query.stream.return_value = []
        assert cm_db.get_meeting_id_by_calendar_event("u1", "e1", "google") is None


# ---------------------------------------------------------------------------
# list_meetings
# ---------------------------------------------------------------------------


def test_list_meetings_zero_or_negative_limit_returns_empty():
    assert cm_db.list_meetings("u1", limit=0) == []
    assert cm_db.list_meetings("u1", limit=-5) == []


@pytest.mark.parametrize("invalid_date", ["2026-09-27", 123, []])
def test_list_meetings_rejects_invalid_dates(invalid_date):
    with pytest.raises(ValueError, match="start_date must be a datetime"):
        cm_db.list_meetings("u1", start_date=invalid_date)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="end_date must be a datetime"):
        cm_db.list_meetings("u1", end_date=invalid_date)  # type: ignore[arg-type]


def test_list_meetings_streams_and_collects():
    fake_query = MagicMock()
    mock_doc1 = _make_mock_snapshot("m1", {"title": "Meeting 1"})
    mock_doc2 = _make_mock_snapshot("m2", {"title": "Meeting 2"})
    fake_query.stream.return_value = [mock_doc1, mock_doc2]

    with patch.object(cm_db.db, "collection") as mock_col:
        coll = mock_col.return_value.document.return_value.collection.return_value
        coll.order_by.return_value.limit.return_value = fake_query

        res = cm_db.list_meetings("  u1  ", limit=50)
        assert len(res) == 2
        assert res[0]["id"] == "m1"
        assert res[1]["id"] == "m2"


# ---------------------------------------------------------------------------
# delete_meeting and delete_old_meetings
# ---------------------------------------------------------------------------


def test_delete_meeting_deletes_ref():
    fake_doc_ref = MagicMock()
    with patch.object(cm_db.db, "collection") as mock_col:
        mock_col.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref

        cm_db.delete_meeting("  u1  ", "  m1  ")
        fake_doc_ref.delete.assert_called_once()


@pytest.mark.parametrize("invalid_date", [None, "2026-09-27", 123, []])
def test_delete_old_meetings_rejects_non_datetime(invalid_date):
    with pytest.raises(ValueError, match="before_date must be a datetime"):
        cm_db.delete_old_meetings("u1", invalid_date)  # type: ignore[arg-type]


def test_delete_old_meetings_commits_in_batches():
    mock_docs = [MagicMock() for _ in range(502)]
    for i, d in enumerate(mock_docs):
        d.reference = f"ref_{i}"

    fake_query = MagicMock()
    fake_query.stream.return_value = mock_docs

    fake_batch = MagicMock()

    with patch.object(cm_db.db, "collection") as mock_col, patch.object(cm_db.db, "batch", return_value=fake_batch):
        coll = mock_col.return_value.document.return_value.collection.return_value
        coll.where.return_value = fake_query

        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        count = cm_db.delete_old_meetings("u1", now)

        assert count == 502
        assert fake_batch.delete.call_count == 502
        # First batch committed at 500, second batch committed with remaining 2
        assert fake_batch.commit.call_count >= 2


# ---------------------------------------------------------------------------
# get_meetings_in_time_range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_date", [None, "2026-09-27", 123, []])
def test_get_meetings_in_time_range_rejects_non_datetime(invalid_date):
    valid_dt = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="start_time must be a datetime"):
        cm_db.get_meetings_in_time_range("u1", invalid_date, valid_dt)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="end_time must be a datetime"):
        cm_db.get_meetings_in_time_range("u1", valid_dt, invalid_date)  # type: ignore[arg-type]


def test_get_meetings_in_time_range_queries_overlapping_range():
    fake_query = MagicMock()
    mock_doc = _make_mock_snapshot("m1", {"title": "Overlap Meeting"})
    fake_query.stream.return_value = [mock_doc]

    with patch.object(cm_db.db, "collection") as mock_col:
        coll = mock_col.return_value.document.return_value.collection.return_value
        coll.where.return_value.where.return_value.order_by.return_value.limit.return_value = fake_query

        t1 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        res = cm_db.get_meetings_in_time_range("  u1  ", t1, t2)

        assert len(res) == 1
        assert res[0]["id"] == "m1"
        assert res[0]["title"] == "Overlap Meeting"
