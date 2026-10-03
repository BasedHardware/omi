"""Unit tests verifying resilience and input validation in database/focus_sessions.py."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from google.api_core.exceptions import NotFound

import database.focus_sessions as focus_db
from models.focus_session import FocusStats
from routers.focus_sessions import CreateFocusSessionRequest, create_focus_session as router_create_focus_session

# ============================================================================
# UID & USER_COL VALIDATION
# ============================================================================


def test_user_col_rejects_blank_and_invalid_uid():
    for invalid_uid in ["", "   ", None, 123]:
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            focus_db._user_col(invalid_uid, "focus_sessions")  # type: ignore[arg-type]


# ============================================================================
# CREATE FOCUS SESSION SANITIZATION
# ============================================================================


def test_create_focus_session_sanitizes_inputs():
    fake_doc_ref = MagicMock()
    fake_col = MagicMock()
    fake_col.document.return_value = fake_doc_ref

    with patch.object(focus_db, "_user_col", return_value=fake_col):
        # Unrecognized status falls back to 'focused', None app falls back to 'Unknown'
        doc = focus_db.create_focus_session(
            uid="  user-123  ",
            status="INVALID_STATUS",
            app_or_site=None,  # type: ignore[arg-type]
            description=None,  # type: ignore[arg-type]
            message="Test note",
            duration_seconds="120",
        )

        assert doc["status"] == "focused"
        assert doc["app_or_site"] == "Unknown"
        assert doc["description"] == ""
        assert doc["message"] == "Test note"
        assert doc["duration_seconds"] == 120
        assert fake_doc_ref.set.called


def test_create_focus_session_blank_uid_raises_value_error():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        focus_db.create_focus_session(uid="   ", status="focused", app_or_site="IDE", description="Work")


# ============================================================================
# GET FOCUS SESSIONS DATE & INPUT RESILIENCE
# ============================================================================


def test_get_focus_sessions_blank_uid_returns_empty():
    assert focus_db.get_focus_sessions("") == []
    assert focus_db.get_focus_sessions("   ") == []
    assert focus_db.get_focus_sessions(None) == []  # type: ignore[arg-type]


def test_get_focus_sessions_malformed_date_returns_empty_without_500():
    fake_query = MagicMock()
    fake_col = MagicMock()
    fake_col.order_by.return_value = fake_query
    with patch.object(focus_db, "_user_col", return_value=fake_col):
        # Malformed dates should not crash with unhandled ValueError
        assert focus_db.get_focus_sessions("user-1", date="not-a-date") == []
        assert focus_db.get_focus_sessions("user-1", date="2026-02-31") == []
        assert focus_db.get_focus_sessions("user-1", date="   ") == []
        fake_query.stream.assert_not_called()


def test_get_focus_sessions_clamps_limit_and_offset():
    fake_query = MagicMock()
    fake_col = MagicMock()
    fake_col.order_by.return_value = fake_query
    fake_query.offset.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.stream.return_value = []

    with patch.object(focus_db, "_user_col", return_value=fake_col):
        focus_db.get_focus_sessions("user-1", limit=99999, offset=-10)

        # Clamped: offset -> 0, limit -> 5000
        fake_query.offset.assert_called_once_with(0)
        fake_query.limit.assert_called_once_with(5000)


# ============================================================================
# DELETE FOCUS SESSION RESILIENCE
# ============================================================================


def test_delete_focus_session_blank_inputs_return_false():
    assert focus_db.delete_focus_session("", "sess-1") is False
    assert focus_db.delete_focus_session("   ", "sess-1") is False
    assert focus_db.delete_focus_session("user-1", "") is False
    assert focus_db.delete_focus_session("user-1", "   ") is False


def test_delete_focus_session_handles_not_found_gracefully():
    fake_ref = MagicMock()
    fake_ref.get.return_value.exists = True
    fake_ref.delete.side_effect = NotFound("Session document missing")

    fake_col = MagicMock()
    fake_col.document.return_value = fake_ref

    with patch.object(focus_db, "_user_col", return_value=fake_col):
        # Concurrent deletion between get() and delete() must not crash
        assert focus_db.delete_focus_session("user-1", "sess-1") is False


def test_delete_focus_session_success():
    fake_ref = MagicMock()
    fake_ref.get.return_value.exists = True

    fake_col = MagicMock()
    fake_col.document.return_value = fake_ref

    with patch.object(focus_db, "_user_col", return_value=fake_col):
        assert focus_db.delete_focus_session("user-1", "sess-1") is True
        fake_ref.delete.assert_called_once()


def test_get_focus_sessions_propagates_infrastructure_error():
    fake_query = MagicMock()
    fake_query.stream.side_effect = RuntimeError("Firestore unavailable")
    fake_col = MagicMock()
    fake_col.order_by.return_value = fake_query
    fake_query.offset.return_value = fake_query
    fake_query.limit.return_value = fake_query

    with patch.object(focus_db, "_user_col", return_value=fake_col):
        with pytest.raises(RuntimeError, match="Firestore unavailable"):
            focus_db.get_focus_sessions("user-1")


def test_delete_focus_session_propagates_infrastructure_error():
    fake_ref = MagicMock()
    fake_ref.get.return_value.exists = True
    fake_ref.delete.side_effect = RuntimeError("Network timeout")

    fake_col = MagicMock()
    fake_col.document.return_value = fake_ref

    with patch.object(focus_db, "_user_col", return_value=fake_col):
        with pytest.raises(RuntimeError, match="Network timeout"):
            focus_db.delete_focus_session("user-1", "sess-1")


# ============================================================================
# GET FOCUS STATS RESILIENCE
# ============================================================================


def test_get_focus_stats_blank_uid_returns_zeroed_stats():
    stats = focus_db.get_focus_stats("   ", date="2026-09-24")
    validated = FocusStats.model_validate(stats)
    assert validated.date == "2026-09-24"
    assert validated.session_count == 0
    assert validated.focused_minutes == 0
    assert validated.distracted_minutes == 0
    assert validated.top_distractions == []


def test_get_focus_stats_invalid_date_falls_back_to_today():
    fake_col = MagicMock()
    fake_query = MagicMock()
    fake_col.order_by.return_value = fake_query
    fake_query.offset.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.where.return_value = fake_query
    fake_query.stream.return_value = []

    with patch.object(focus_db, "_user_col", return_value=fake_col):
        stats = focus_db.get_focus_stats("user-1", date="not-a-valid-date")
        validated = FocusStats.model_validate(stats)
        today_str = focus_db.datetime.now(focus_db.timezone.utc).strftime("%Y-%m-%d")
        assert validated.date == today_str


# ============================================================================
# ROUTER ERROR MAPPING (ValueError -> 400)
# ============================================================================


def test_router_create_focus_session_maps_value_error_to_400():
    req = CreateFocusSessionRequest(
        status="focused",
        app_or_site="Terminal",
        description="Testing",
    )
    with patch.object(focus_db, "create_focus_session", side_effect=ValueError("Invalid uid")):
        with pytest.raises(HTTPException) as exc_info:
            router_create_focus_session(req, uid="invalid-uid")
        assert exc_info.value.status_code == 400
        assert "Invalid uid" in exc_info.value.detail
