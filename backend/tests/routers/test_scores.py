from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


from models.score import DailyScore, Scores
import database.action_items as action_items_db
import database.notifications as notification_db
import routers.scores as scores_router
from utils.other import endpoints as auth


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(scores_router.router)
    return app


@pytest.fixture
def client(test_app):
    test_app.dependency_overrides[auth.get_current_user_uid] = lambda: "test-uid-123"
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


# ============================================================================
# Router direct-call and boundary tests
# ============================================================================


class TestScoresRouterDirect:
    """Direct-call tests on route handler functions."""

    def test_timezone_resolution_success(self):
        with patch.object(notification_db, "resolve_user_timezone", return_value="America/New_York"):
            tz = scores_router._resolve_safe_timezone("test-uid")
            assert str(tz) == "America/New_York"

    def test_timezone_resolution_fallback_on_invalid(self):
        with patch.object(notification_db, "resolve_user_timezone", return_value="Invalid/Nonexistent_Timezone"):
            tz = scores_router._resolve_safe_timezone("test-uid")
            assert tz == ZoneInfo("UTC")

    def test_timezone_resolution_fallback_on_exception(self):
        with patch.object(notification_db, "resolve_user_timezone", side_effect=RuntimeError("DB disconnected")):
            tz = scores_router._resolve_safe_timezone("test-uid")
            assert tz == ZoneInfo("UTC")

    def test_daily_score_rejects_empty_uid(self):
        with pytest.raises(HTTPException) as exc_info:
            scores_router.get_daily_score(date=None, uid="")
        assert exc_info.value.status_code == 401
        assert "User identification required" in exc_info.value.detail

    def test_daily_score_rejects_whitespace_uid(self):
        with pytest.raises(HTTPException) as exc_info:
            scores_router.get_daily_score(date=None, uid="   ")
        assert exc_info.value.status_code == 401

    def test_daily_score_sanitizes_upstream_storage_exception(self):
        with (
            patch.object(notification_db, "resolve_user_timezone", return_value="UTC"),
            patch.object(action_items_db, "get_daily_score", side_effect=Exception("Internal Firestore deadlock")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                scores_router.get_daily_score(date="2026-09-29", uid="test-uid")
            assert exc_info.value.status_code == 500
            assert "Failed to retrieve daily productivity score" in exc_info.value.detail
            # Must not leak internal raw exception string
            assert "deadlock" not in exc_info.value.detail

    def test_scores_rejects_empty_uid(self):
        with pytest.raises(HTTPException) as exc_info:
            scores_router.get_scores(date=None, uid="")
        assert exc_info.value.status_code == 401

    def test_scores_rejects_whitespace_uid(self):
        with pytest.raises(HTTPException) as exc_info:
            scores_router.get_scores(date=None, uid="   ")
        assert exc_info.value.status_code == 401

    def test_scores_sanitizes_upstream_storage_exception(self):
        with (
            patch.object(notification_db, "resolve_user_timezone", return_value="UTC"),
            patch.object(action_items_db, "get_scores", side_effect=Exception("Internal Firestore timeout")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                scores_router.get_scores(date="2026-09-29", uid="test-uid")
            assert exc_info.value.status_code == 500
            assert "Failed to retrieve productivity scores" in exc_info.value.detail
            assert "timeout" not in exc_info.value.detail


# ============================================================================
# FastAPI TestClient wire integration tests
# ============================================================================


class TestScoresClientWire:
    """Wire HTTP tests validating query params, response models, and status codes."""

    def test_get_daily_score_success(self, client):
        mock_result = {
            "date": "2026-09-29",
            "score": 75,
            "completed_tasks": 3,
            "total_tasks": 4,
        }
        with (
            patch.object(notification_db, "resolve_user_timezone", return_value="UTC"),
            patch.object(action_items_db, "get_daily_score", return_value=mock_result),
        ):
            resp = client.get("/v1/daily-score?date=2026-09-29")
            assert resp.status_code == 200
            data = resp.json()
            assert data["date"] == "2026-09-29"
            assert data["score"] == 75
            assert data["completed_tasks"] == 3
            assert data["total_tasks"] == 4
            # Validates against Pydantic schema
            DailyScore.model_validate(data)

    def test_get_daily_score_invalid_date_format_422(self, client):
        resp = client.get("/v1/daily-score?date=2026-99-99")
        assert resp.status_code == 422

    def test_get_daily_score_unauthenticated_empty_uid(self, test_app):
        test_app.dependency_overrides[auth.get_current_user_uid] = lambda: ""
        c = TestClient(test_app)
        resp = c.get("/v1/daily-score")
        assert resp.status_code == 401

    def test_get_scores_success(self, client):
        mock_result = {
            "daily": {"score": 80.0, "completed_tasks": 4, "total_tasks": 5},
            "weekly": {"score": 60.0, "completed_tasks": 6, "total_tasks": 10},
            "overall": {"score": 70.0, "completed_tasks": 14, "total_tasks": 20},
            "default_tab": "daily",
            "date": "2026-09-29",
        }
        with (
            patch.object(notification_db, "resolve_user_timezone", return_value="UTC"),
            patch.object(action_items_db, "get_scores", return_value=mock_result),
        ):
            resp = client.get("/v1/scores?date=2026-09-29")
            assert resp.status_code == 200
            data = resp.json()
            assert data["daily"]["score"] == 80.0
            assert data["weekly"]["score"] == 60.0
            assert data["overall"]["score"] == 70.0
            assert data["default_tab"] == "daily"
            assert data["date"] == "2026-09-29"
            # Validates against Pydantic schema
            Scores.model_validate(data)

    def test_get_scores_invalid_calendar_date_422(self, client):
        resp = client.get("/v1/scores?date=invalid-date")
        assert resp.status_code == 422


# ============================================================================
# Database layer resilience and calculation tests
# ============================================================================


class TestActionItemsScoreDatabase:
    """Hermetic unit tests on database.action_items get_daily_score and get_scores."""

    def test_get_daily_score_requires_valid_uid(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            action_items_db.get_daily_score("", date="2026-09-29")

        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            action_items_db.get_daily_score("   ", date="2026-09-29")

    def test_get_daily_score_invalid_date_raises(self):
        with pytest.raises(ValueError, match="Invalid date format or range"):
            action_items_db.get_daily_score("user-1", date="not-a-date")

    def test_get_scores_requires_valid_uid(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            action_items_db.get_scores("", date="2026-09-29")

        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            action_items_db.get_scores("   ", date="2026-09-29")

    def test_get_scores_invalid_date_raises(self):
        with pytest.raises(ValueError, match="Invalid date format or range"):
            action_items_db.get_scores("user-1", date="2026-99-99")

    def test_get_daily_score_mock_stream(self):
        """Verify daily score calculations and soft-deleted item skipping."""

        class MockDoc:
            def __init__(self, data):
                self._data = data

            def to_dict(self):
                return self._data

        docs = [
            MockDoc({"completed": True, "deleted": False}),
            MockDoc({"completed": True, "deleted": False}),
            MockDoc({"completed": False, "deleted": False}),
            MockDoc({"completed": True, "deleted": True}),  # Deleted -> ignored
        ]

        mock_query = MagicMock()
        mock_query.stream.return_value = docs
        mock_query.where.return_value = mock_query

        mock_col = MagicMock()
        mock_col.where.return_value = mock_query

        mock_client = MagicMock()
        mock_client.collection.return_value.document.return_value.collection.return_value = mock_col

        result = action_items_db.get_daily_score(
            "test-user",
            date="2026-09-29",
            firestore_client=mock_client,
            tz=timezone.utc,
        )

        assert result["date"] == "2026-09-29"
        assert result["total_tasks"] == 3
        assert result["completed_tasks"] == 2
        # 2 / 3 * 100 = 66.666... -> rounded to 67
        assert result["score"] == 67

    def test_get_daily_score_zero_tasks(self):
        mock_query = MagicMock()
        mock_query.stream.return_value = []
        mock_query.where.return_value = mock_query

        mock_col = MagicMock()
        mock_col.where.return_value = mock_query

        mock_client = MagicMock()
        mock_client.collection.return_value.document.return_value.collection.return_value = mock_col

        result = action_items_db.get_daily_score(
            "test-user",
            date="2026-09-29",
            firestore_client=mock_client,
            tz=timezone.utc,
        )

        assert result["total_tasks"] == 0
        assert result["completed_tasks"] == 0
        assert result["score"] == 0

    def test_get_daily_score_clamped_bounds(self):
        """Even if corrupted data reported completed > total, score must clamp to 100."""

        class MockDoc:
            def __init__(self, data):
                self._data = data

            def to_dict(self):
                return self._data

        docs = [MockDoc({"completed": True})]
        mock_query = MagicMock()
        mock_query.stream.return_value = docs
        mock_query.where.return_value = mock_query

        mock_col = MagicMock()
        mock_col.where.return_value = mock_query

        mock_client = MagicMock()
        mock_client.collection.return_value.document.return_value.collection.return_value = mock_col

        result = action_items_db.get_daily_score(
            "test-user",
            date="2026-09-29",
            firestore_client=mock_client,
            tz=timezone.utc,
        )
        assert 0 <= result["score"] <= 100
        assert result["completed_tasks"] <= result["total_tasks"]

    def test_get_scores_default_tab_resolution(self):
        """Verify tab selection logic: daily > weekly > overall precedence on ties."""

        def make_client(counts):
            mock_client = MagicMock()
            mock_col = MagicMock()
            mock_client.collection.return_value.document.return_value.collection.return_value = mock_col
            mock_col.where.return_value.order_by.return_value.limit.return_value.stream.return_value = []
            mock_col.order_by.return_value.limit.return_value.stream.return_value = []

            count_iter = iter(counts)

            def mock_count():
                cq = MagicMock()
                val = next(count_iter, 0)
                cq.get.return_value = [[MagicMock(value=val)]]
                return cq

            mock_col.count = mock_count
            mock_col.where.return_value.count = mock_count
            mock_col.where.return_value.where.return_value.count = mock_count
            mock_col.where.return_value.where.return_value.where.return_value.count = mock_count
            return mock_client

        # Case A: Daily highest (daily: 4/5 = 80%, weekly: 7/10 = 70%, overall: 12/20 = 60%)
        client_a = make_client([5, 4, 10, 7, 20, 12])
        res_a = action_items_db.get_scores("user-1", date="2026-09-29", firestore_client=client_a)
        assert res_a["default_tab"] == "daily"
        assert res_a["daily"]["score"] == 80.0

        # Case B: Weekly highest (daily: 2/5 = 40%, weekly: 8/10 = 80%, overall: 12/20 = 60%)
        client_b = make_client([5, 2, 10, 8, 20, 12])
        res_b = action_items_db.get_scores("user-1", date="2026-09-29", firestore_client=client_b)
        assert res_b["default_tab"] == "weekly"
        assert res_b["weekly"]["score"] == 80.0

        # Case C: Overall highest (daily: 2/5 = 40%, weekly: 5/10 = 50%, overall: 18/20 = 90%)
        client_c = make_client([5, 2, 10, 5, 20, 18])
        res_c = action_items_db.get_scores("user-1", date="2026-09-29", firestore_client=client_c)
        assert res_c["default_tab"] == "overall"
        assert res_c["overall"]["score"] == 90.0

        # Case D: Daily has 0 tasks, ties between weekly & overall go to weekly
        client_d = make_client([0, 0, 8, 6, 16, 12])
        res_d = action_items_db.get_scores("user-1", date="2026-09-29", firestore_client=client_d)
        assert res_d["default_tab"] == "weekly"
        assert res_d["weekly"]["score"] == 75.0
