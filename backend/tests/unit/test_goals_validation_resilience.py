"""Unit tests for Goals response validation resilience.

Verifies that:
1. GET /v1/dev/user/goals skips malformed/corrupt goal records without failing
   the whole page with an HTTP 500 ResponseValidationError.
2. GET /v1/dev/user/goals/{goal_id} safely handles corrupt documents by raising
   HTTP 404 instead of an uncaught HTTP 500 ResponseValidationError.
3. GET /v1/dev/user/goals/{goal_id}/history skips malformed history entries without crashing.
4. GET /v1/goals returns None safely when the active goal is corrupt instead of 500.
5. GET /v1/goals/all skips malformed/corrupt goals without failing the whole response.
6. GET /v1/goals/canonical/list skips malformed/corrupt goals without failing.
7. GET /v1/goals/{goal_id} returns HTTP 404 when a document fails schema validation.
8. GET /v1/goals/{goal_id}/history skips malformed history records safely.
"""

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

import database.goals as goals_db
import routers.developer as developer_router
import routers.goals as goals_router
from models.goal import GoalHistoryEntryResponse, GoalResponse as UserGoalResponse
from routers.developer import GoalResponse as DevGoalResponse


def _make_valid_goal(goal_id="g-1", title="Exercise daily"):
    now = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "id": goal_id,
        "goal_id": goal_id,
        "title": title,
        "desired_outcome": title,
        "why_it_matters": "Health",
        "success_criteria": ["Run 5km"],
        "status": "background",
        "source": "user",
        "goal_type": "scale",
        "target_value": 10.0,
        "current_value": 2.0,
        "min_value": 0.0,
        "max_value": 10.0,
        "unit": "km",
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }


def _make_corrupt_goal(goal_id="g-corrupt"):
    # Carries an invalid metric bounds configuration (min > max)
    return {
        "id": goal_id,
        "goal_id": goal_id,
        "title": "Broken Goal",
        "desired_outcome": "Impossible bounds",
        "status": "background",
        "source": "user",
        "metric": {
            "type": "scale",
            "current": 5.0,
            "target": 10.0,
            "min": 100.0,
            "max": 10.0,  # min > max triggers ValidationError
        },
    }


class TestDeveloperGoalsValidationResilience:
    @patch.object(goals_db, "get_user_goals")
    def test_get_goals_skips_corrupt_and_non_dict_records(self, mock_get_user_goals):
        mock_get_user_goals.return_value = [
            _make_valid_goal("g-1", "Goal 1"),
            "not-a-dict",
            {"success_criteria": "not-a-list"},
            _make_corrupt_goal("g-corrupt"),
            _make_valid_goal("g-2", "Goal 2"),
        ]

        results = developer_router.get_goals(uid="uid1", limit=10, include_inactive=False)

        assert len(results) == 2
        assert DevGoalResponse.model_validate(results[0]).id == "g-1"
        assert DevGoalResponse.model_validate(results[1]).id == "g-2"

    @patch.object(goals_db, "get_all_goals")
    def test_get_goals_include_inactive_skips_malformed(self, mock_get_all_goals):
        mock_get_all_goals.return_value = [
            _make_valid_goal("g-1", "Goal 1"),
            None,
            _make_corrupt_goal("g-bad"),
            _make_valid_goal("g-2", "Goal 2"),
        ]

        results = developer_router.get_goals(uid="uid1", limit=10, include_inactive=True)

        assert len(results) == 2
        assert DevGoalResponse.model_validate(results[0]).id == "g-1"
        assert DevGoalResponse.model_validate(results[1]).id == "g-2"

    @patch.object(goals_db, "get_all_goals")
    def test_get_goal_valid(self, mock_get_all_goals):
        mock_get_all_goals.return_value = [_make_valid_goal("g-1", "Goal 1")]

        result = developer_router.get_goal(goal_id="g-1", uid="uid1")

        assert isinstance(result, DevGoalResponse)
        assert result.id == "g-1"

    @patch.object(goals_db, "get_all_goals")
    def test_get_goal_not_found_raises_404(self, mock_get_all_goals):
        mock_get_all_goals.return_value = [_make_valid_goal("g-1", "Goal 1")]

        with pytest.raises(HTTPException) as exc_info:
            developer_router.get_goal(goal_id="g-missing", uid="uid1")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Goal not found"

    @patch.object(goals_db, "get_all_goals")
    def test_get_goal_corrupt_raises_404_not_500(self, mock_get_all_goals):
        mock_get_all_goals.return_value = [_make_corrupt_goal("g-corrupt")]

        with pytest.raises(HTTPException) as exc_info:
            developer_router.get_goal(goal_id="g-corrupt", uid="uid1")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Goal not found"

    @patch.object(goals_db, "get_goal_history")
    def test_get_goal_history_skips_malformed(self, mock_get_history):
        valid_entry = {
            "date": "2026-10-15",
            "value": 5.0,
            "recorded_at": datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc),
        }
        mock_get_history.return_value = [
            valid_entry,
            "not-a-dict",
            {"missing_date": True},
        ]

        history = developer_router.get_goal_history(goal_id="g-1", days=30, uid="uid1")

        assert len(history) == 1
        assert history[0]["value"] == 5.0
        assert GoalHistoryEntryResponse.model_validate(history[0]).value == 5.0


class TestUserGoalsValidationResilience:
    @patch.object(goals_db, "get_user_goal")
    def test_get_current_goal_valid(self, mock_get_user_goal):
        mock_get_user_goal.return_value = _make_valid_goal("g-1", "Active Goal")

        result = goals_router.get_current_goal(uid="uid1")

        assert result is not None
        assert result["id"] == "g-1"
        assert UserGoalResponse.model_validate(result).id == "g-1"

    @patch.object(goals_db, "get_user_goal")
    def test_get_current_goal_none_when_empty(self, mock_get_user_goal):
        mock_get_user_goal.return_value = None

        result = goals_router.get_current_goal(uid="uid1")

        assert result is None

    @patch.object(goals_db, "get_user_goal")
    def test_get_current_goal_corrupt_returns_none_not_500(self, mock_get_user_goal):
        mock_get_user_goal.return_value = _make_corrupt_goal("g-corrupt")

        result = goals_router.get_current_goal(uid="uid1")

        assert result is None

    @patch.object(goals_db, "get_all_goals")
    def test_get_all_goals_skips_malformed(self, mock_get_all_goals):
        mock_get_all_goals.return_value = [
            _make_valid_goal("g-1", "Goal 1"),
            "not-a-dict",
            {"bad": 123},
            _make_corrupt_goal("g-bad"),
            _make_valid_goal("g-2", "Goal 2"),
        ]

        results = goals_router.get_all_goals(include_ended=False, uid="uid1")

        assert len(results) == 2
        assert results[0]["id"] == "g-1"
        assert results[1]["id"] == "g-2"

    @patch.object(goals_db, "get_all_goals")
    def test_get_canonical_goals_skips_malformed(self, mock_get_all_goals):
        mock_get_all_goals.return_value = [
            _make_valid_goal("g-1", "Goal 1"),
            None,
            _make_corrupt_goal("g-bad"),
            _make_valid_goal("g-2", "Goal 2"),
        ]

        results = goals_router.get_canonical_goals(include_ended=False, uid="uid1")

        assert len(results) == 2
        assert results[0]["id"] == "g-1"
        assert results[1]["id"] == "g-2"

    @patch.object(goals_db, "get_goal_by_id")
    def test_get_goal_by_id_valid(self, mock_get_goal_by_id):
        mock_get_goal_by_id.return_value = _make_valid_goal("g-1", "Goal 1")

        result = goals_router.get_goal_by_id(goal_id="g-1", uid="uid1")

        assert result["id"] == "g-1"

    @patch.object(goals_db, "get_goal_by_id")
    def test_get_goal_by_id_missing_raises_404(self, mock_get_goal_by_id):
        mock_get_goal_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            goals_router.get_goal_by_id(goal_id="g-missing", uid="uid1")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Goal not found"

    @patch.object(goals_db, "get_goal_by_id")
    def test_get_goal_by_id_corrupt_raises_404(self, mock_get_goal_by_id):
        mock_get_goal_by_id.return_value = _make_corrupt_goal("g-corrupt")

        with pytest.raises(HTTPException) as exc_info:
            goals_router.get_goal_by_id(goal_id="g-corrupt", uid="uid1")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Goal not found"

    @patch.object(goals_db, "get_goal_history")
    def test_get_user_goal_history_skips_malformed(self, mock_get_history):
        valid_entry = {
            "date": "2026-10-15",
            "value": 3.0,
            "recorded_at": datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc),
        }
        mock_get_history.return_value = [
            valid_entry,
            "bad-record",
            {"missing_date": True},
        ]

        history = goals_router.get_goal_history(goal_id="g-1", days=30, uid="uid1")

        assert len(history) == 1
        assert history[0]["value"] == 3.0
        assert GoalHistoryEntryResponse.model_validate(history[0]).value == 3.0
