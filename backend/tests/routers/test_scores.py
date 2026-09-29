import pytest
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from routers.scores import _resolve_safe_timezone, get_daily_score, get_scores


def test_resolve_safe_timezone_valid():
    with patch("database.notifications.resolve_user_timezone", return_value="America/New_York"):
        tz = _resolve_safe_timezone("valid_user")
        assert tz == ZoneInfo("America/New_York")


def test_resolve_safe_timezone_invalid_fallback():
    with patch("database.notifications.resolve_user_timezone", return_value="Invalid/Timezone"):
        tz = _resolve_safe_timezone("user_with_bad_tz")
        assert tz == ZoneInfo("UTC")


def test_resolve_safe_timezone_exception_fallback():
    with patch("database.notifications.resolve_user_timezone", side_effect=Exception("DB down")):
        tz = _resolve_safe_timezone("user_error")
        assert tz == ZoneInfo("UTC")


def test_get_daily_score_invalid_uid():
    with pytest.raises(HTTPException) as exc_info:
        get_daily_score(date=None, uid="")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        get_daily_score(date=None, uid="   ")
    assert exc_info.value.status_code == 400


def test_get_scores_invalid_uid():
    with pytest.raises(HTTPException) as exc_info:
        get_scores(date=None, uid="")
    assert exc_info.value.status_code == 400


def test_get_daily_score_db_error_handling():
    with patch("database.notifications.resolve_user_timezone", return_value="UTC"):
        with patch("database.action_items.get_daily_score", side_effect=RuntimeError("Firestore connection error")):
            with pytest.raises(HTTPException) as exc_info:
                get_daily_score(date="2026-09-29", uid="user_123")
            assert exc_info.value.status_code == 500
            assert "Failed to retrieve daily score" in exc_info.value.detail


def test_get_scores_db_error_handling():
    with patch("database.notifications.resolve_user_timezone", return_value="UTC"):
        with patch("database.action_items.get_scores", side_effect=RuntimeError("Firestore connection error")):
            with pytest.raises(HTTPException) as exc_info:
                get_scores(date="2026-09-29", uid="user_123")
            assert exc_info.value.status_code == 500
            assert "Failed to retrieve scores" in exc_info.value.detail


def test_get_daily_score_success():
    mock_res = {"date": "2026-09-29", "score": 85, "completed_tasks": 17, "total_tasks": 20}
    with patch("database.notifications.resolve_user_timezone", return_value="UTC"):
        with patch("database.action_items.get_daily_score", return_value=mock_res):
            res = get_daily_score(date="2026-09-29", uid="user_123")
            assert res == mock_res
