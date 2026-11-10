"""Regression: a released alias patch that contradicts the stored metric must
answer 422 at ``PATCH /v1/goals/{goal_id}``, not 500.

``GoalUpdate`` validates each alias in isolation, so ``{"min_value": 30}``
passes request validation; the contradiction only appears when the alias is
merged with the stored metric in ``database.goals.update_goal``. Before this
change the ``pydantic`` ``ValidationError`` escaped the store seam uncaught and
FastAPI answered 500, leaving the client unable to show why the edit failed.

Failure class: FC-request-input-rejection-escapes-as-server-fault.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "***")

import pytest
from fastapi import HTTPException

import database.goals as goals_db
from models.goal import GoalUpdate
from routers import goals as goals_router

_STORED = {
    "id": "goal_1",
    "title": "Lose weight",
    "metric": {"type": "numeric", "current": 3.0, "target": 10.0, "min": 0.0, "max": 20.0, "unit": "kg"},
}


def _fake_client(stored=None):
    client = MagicMock()
    chain = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    chain.get.return_value = MagicMock(exists=True, to_dict=lambda: dict(stored or _STORED))
    return client


# ---------------------------------------------------------------------------
# database seam: a contradiction raises the typed error, not a raw ValidationError
# ---------------------------------------------------------------------------
def test_update_goal_min_above_stored_max_raises_goal_validation_error():
    body = GoalUpdate.model_validate({"min_value": 30}).model_dump(exclude_unset=True)
    with pytest.raises(goals_db.GoalValidationError) as exc:
        goals_db.update_goal("u1", "goal_1", body, firestore_client=_fake_client())
    assert "min must not exceed max" in str(exc.value)


def test_update_goal_negative_max_below_stored_min_raises_goal_validation_error():
    body = GoalUpdate.model_validate({"max_value": -1}).model_dump(exclude_unset=True)
    with pytest.raises(goals_db.GoalValidationError):
        goals_db.update_goal("u1", "goal_1", body, firestore_client=_fake_client())


def test_update_goal_valid_alias_patch_still_writes():
    body = GoalUpdate.model_validate({"min_value": 1}).model_dump(exclude_unset=True)
    with patch.object(goals_db, "get_goal_by_id", return_value=dict(_STORED)):
        result = goals_db.update_goal("u1", "goal_1", body, firestore_client=_fake_client())
    assert result is not None


# ---------------------------------------------------------------------------
# route: the typed error maps to 422, not 500
# ---------------------------------------------------------------------------
def test_patch_goal_contradicting_alias_answers_422():
    body = GoalUpdate.model_validate({"min_value": 30})
    with patch.object(
        goals_router.goals_db,
        "update_goal",
        side_effect=goals_db.GoalValidationError("metric min must not exceed max"),
    ):
        with pytest.raises(HTTPException) as exc:
            goals_router.update_goal(goal_id="goal_1", updates=body, uid="u1")
    assert exc.value.status_code == 422
    assert exc.value.detail == "metric min must not exceed max"


def test_patch_goal_not_found_still_404():
    body = GoalUpdate.model_validate({"title": "New title"})
    with patch.object(goals_router.goals_db, "update_goal", return_value=None):
        with pytest.raises(HTTPException) as exc:
            goals_router.update_goal(goal_id="goal_1", updates=body, uid="u1")
    assert exc.value.status_code == 404
