"""Regression tests for GoalUpdate alias patch metric contradictions (#21197).

When editing a goal's numeric scale aliases (min_value, max_value, target_value, etc.),
contradicting the stored metric previously raised pydantic ValidationError escaping as a 500.
The fix raises a typed GoalValidationError in database.goals and maps it to HTTP 422 at the route.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

import database.goals as goals_db
from models.goal import GoalUpdate
from routers import goals as goals_router


def _stored_goal(min_val=0.0, max_val=20.0):
    return {
        "id": "goal_1",
        "title": "Lose weight",
        "metric": {
            "type": "numeric",
            "current": 3.0,
            "target": 10.0,
            "min": min_val,
            "max": max_val,
            "unit": "kg",
        },
    }


def _mock_firestore(stored_doc):
    client = MagicMock()
    chain = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    chain.get.return_value = MagicMock(exists=True, to_dict=lambda: dict(stored_doc))
    return client


def test_update_goal_raises_goal_validation_error_on_min_exceeding_max():
    stored = _stored_goal(min_val=0.0, max_val=20.0)
    client = _mock_firestore(stored)
    body = GoalUpdate.model_validate({"min_value": 30}).model_dump(exclude_unset=True)

    with pytest.raises(goals_db.GoalValidationError) as exc_info:
        goals_db.update_goal("u1", "goal_1", body, firestore_client=client)

    assert "metric min must not exceed max" in str(exc_info.value)
    # Ensure no write was attempted
    client.collection.return_value.document.return_value.collection.return_value.document.return_value.update.assert_not_called()


def test_update_goal_raises_goal_validation_error_on_max_below_min():
    stored = _stored_goal(min_val=0.0, max_val=20.0)
    client = _mock_firestore(stored)
    body = GoalUpdate.model_validate({"max_value": -1}).model_dump(exclude_unset=True)

    with pytest.raises(goals_db.GoalValidationError) as exc_info:
        goals_db.update_goal("u1", "goal_1", body, firestore_client=client)

    assert "metric min must not exceed max" in str(exc_info.value)
    client.collection.return_value.document.return_value.collection.return_value.document.return_value.update.assert_not_called()


def test_update_goal_route_maps_validation_error_to_422():
    with patch.object(
        goals_router.goals_db,
        "update_goal",
        side_effect=goals_db.GoalValidationError("metric min must not exceed max"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            goals_router.update_goal(
                goal_id="goal_1",
                updates=GoalUpdate(min_value=30),
                uid="u1",
            )

        assert exc_info.value.status_code == 422
        assert "metric min must not exceed max" in str(exc_info.value.detail)


def test_update_goal_valid_alias_patch_succeeds():
    stored = _stored_goal(min_val=0.0, max_val=20.0)
    client = _mock_firestore(stored)
    body = GoalUpdate.model_validate({"min_value": 5.0}).model_dump(exclude_unset=True)

    with patch.object(goals_db, "get_goal_by_id", return_value={"id": "goal_1", "min_value": 5.0}):
        result = goals_db.update_goal("u1", "goal_1", body, firestore_client=client)

    assert result is not None
    client.collection.return_value.document.return_value.collection.return_value.document.return_value.update.assert_called_once()
