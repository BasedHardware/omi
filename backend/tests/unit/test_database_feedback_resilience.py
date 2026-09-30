"""Hermetic unit tests for input validation, boundary guards, and error resilience
in backend/database/feedback.py and routers/mobile_feedback.py.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import database.feedback as feedback_db
from models.feedback import (
    FeedbackEvent,
    FeedbackReport,
    FeedbackSurface,
    FeedbackTargetKind,
    MobileFeedbackKind,
)


class _FakeSnapshot:
    def __init__(self, doc_id: str, exists: bool = True, data: dict | None = None):
        self.id = doc_id
        self.exists = exists
        self._data = data if data is not None else {}

    def to_dict(self):
        return self._data if self.exists else None


# ---------------------------------------------------------------------------
# record_feedback_event: validation & normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_record_feedback_event_invalid_uid_returns_none(invalid_uid):
    fake_client = MagicMock()
    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        res = feedback_db.record_feedback_event(
            invalid_uid,  # type: ignore[arg-type]
            FeedbackSurface.chat_text,
            FeedbackTargetKind.chat_message,
            "msg-1",
            1,
        )
    assert res is None
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_record_feedback_event_invalid_uid_raise_on_error(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        feedback_db.record_feedback_event(
            invalid_uid,  # type: ignore[arg-type]
            FeedbackSurface.chat_text,
            FeedbackTargetKind.chat_message,
            "msg-1",
            1,
            raise_on_error=True,
        )


@pytest.mark.parametrize("invalid_target_id", [None, "", "   "])
def test_record_feedback_event_invalid_target_id_returns_none(invalid_target_id):
    fake_client = MagicMock()
    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        res = feedback_db.record_feedback_event(
            "uid-1",
            FeedbackSurface.chat_text,
            FeedbackTargetKind.chat_message,
            invalid_target_id,  # type: ignore[arg-type]
            1,
        )
    assert res is None
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_target_id", [None, "", "   "])
def test_record_feedback_event_invalid_target_id_raise_on_error(invalid_target_id):
    with pytest.raises(ValueError, match="target_id must be a non-empty string"):
        feedback_db.record_feedback_event(
            "uid-1",
            FeedbackSurface.chat_text,
            FeedbackTargetKind.chat_message,
            invalid_target_id,  # type: ignore[arg-type]
            1,
            raise_on_error=True,
        )


@pytest.mark.parametrize("invalid_val", ["abc", None, [], 2, -2, 99])
def test_record_feedback_event_invalid_value_returns_none(invalid_val):
    fake_client = MagicMock()
    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        res = feedback_db.record_feedback_event(
            "uid-1",
            FeedbackSurface.chat_text,
            FeedbackTargetKind.chat_message,
            "msg-1",
            invalid_val,  # type: ignore[arg-type]
        )
    assert res is None
    fake_client.collection.assert_not_called()


def test_record_feedback_event_normalizes_uid_and_target_id():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value = doc_ref

    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        res = feedback_db.record_feedback_event(
            "  user-123  ",
            FeedbackSurface.chat_text,
            FeedbackTargetKind.chat_message,
            "  target-456  ",
            1,
        )

    assert res is not None
    doc_ref.set.assert_called_once()
    payload = doc_ref.set.call_args[0][0]
    assert payload["uid"] == "user-123"
    assert payload["target_id"] == "target-456"


# ---------------------------------------------------------------------------
# Idempotent hashing and record_feedback_event_idempotent
# ---------------------------------------------------------------------------


def test_idempotent_event_id_normalizes_whitespace():
    id1 = feedback_db._idempotent_event_id("  user-1  ", "  fb-99  ")
    id2 = feedback_db._idempotent_event_id("user-1", "fb-99")
    assert id1 == id2
    assert id1.startswith("mobile-feedback-")


@pytest.mark.parametrize("invalid_arg", [None, "", "   "])
def test_record_feedback_event_idempotent_rejects_empty_coords(invalid_arg):
    with pytest.raises(ValueError, match="uid is required"):
        feedback_db.record_feedback_event_idempotent(
            invalid_arg,  # type: ignore[arg-type]
            FeedbackSurface.conversation_summary,
            FeedbackTargetKind.conversation,
            "c-1",
            1,
            feedback_id="fb-1",
        )

    with pytest.raises(ValueError, match="feedback_id is required"):
        feedback_db.record_feedback_event_idempotent(
            "u-1",
            FeedbackSurface.conversation_summary,
            FeedbackTargetKind.conversation,
            "c-1",
            1,
            feedback_id=invalid_arg,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="target_id is required"):
        feedback_db.record_feedback_event_idempotent(
            "u-1",
            FeedbackSurface.conversation_summary,
            FeedbackTargetKind.conversation,
            invalid_arg,  # type: ignore[arg-type]
            1,
            feedback_id="fb-1",
        )


# ---------------------------------------------------------------------------
# get_feedback_event validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123, []])
def test_get_feedback_event_invalid_id_returns_none(invalid_id):
    fake_client = MagicMock()
    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        assert feedback_db.get_feedback_event(invalid_id) is None  # type: ignore[arg-type]
    fake_client.collection.assert_not_called()


def test_get_feedback_event_valid_id_fetches_and_parses():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value = doc_ref
    doc_ref.get.return_value = _FakeSnapshot(
        "ev-1",
        exists=True,
        data={
            "id": "ev-1",
            "uid": "u-1",
            "surface": "chat_text",
            "target_kind": "chat_message",
            "target_id": "msg-1",
            "value": 1,
            "created_at": datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        },
    )

    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        event = feedback_db.get_feedback_event("  ev-1  ")

    assert event is not None
    assert event.id == "ev-1"
    assert event.uid == "u-1"
    fake_client.collection.return_value.document.assert_called_with("ev-1")


# ---------------------------------------------------------------------------
# get_report & save_report validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_date", [None, "", "   ", 123, {}])
def test_get_report_invalid_date_returns_none(invalid_date):
    fake_client = MagicMock()
    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        assert feedback_db.get_report(invalid_date) is None  # type: ignore[arg-type]
    fake_client.collection.assert_not_called()


def test_save_report_rejects_invalid_type_or_date():
    with pytest.raises(ValueError, match="report must be an instance of FeedbackReport"):
        feedback_db.save_report({"date": "2026-09-01"})  # type: ignore[arg-type]

    bad_report = MagicMock(spec=FeedbackReport)
    bad_report.date = "   "
    with pytest.raises(ValueError, match="report.date must be a non-empty date string"):
        feedback_db.save_report(bad_report)


def test_save_report_persists_valid_report():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value = doc_ref

    report = FeedbackReport(
        date="2026-09-01",
        total_negative=0,
        entries=[],
        truncated=False,
        generated_at=datetime.now(timezone.utc),
    )

    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        feedback_db.save_report(report)

    fake_client.collection.return_value.document.assert_called_with("2026-09-01")
    doc_ref.set.assert_called_once()


# ---------------------------------------------------------------------------
# list_negative_events & list_report_dates validation
# ---------------------------------------------------------------------------


def test_list_negative_events_rejects_non_datetime_or_inverted_range():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="start_at and end_at must be datetime instances"):
        feedback_db.list_negative_events("2026-09-01", now)  # type: ignore[arg-type]

    earlier = datetime(2026, 9, 1, tzinfo=timezone.utc)
    later = datetime(2026, 9, 2, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="start_at cannot be after end_at"):
        feedback_db.list_negative_events(later, earlier)


def test_list_negative_events_zero_or_negative_limit_returns_empty():
    now = datetime.now(timezone.utc)
    res = feedback_db.list_negative_events(now, now, limit=0)
    assert res == []


def test_list_report_dates_zero_or_negative_limit_returns_empty():
    res = feedback_db.list_report_dates(limit=0)
    assert res == []


def test_list_report_dates_handles_client_exception():
    fake_client = MagicMock()
    fake_client.collection.side_effect = RuntimeError("Firestore unavailable")

    with patch.object(feedback_db, "get_firestore_client", return_value=fake_client):
        res = feedback_db.list_report_dates(limit=10)

    assert res == []
