"""GET /v1/goals/{goal_id} fetches a single goal by id, 404 when absent.

The goals router already exposed list, create, update, delete, progress, history, and advice by
id, but no plain read of one goal. This adds get_goal(uid, goal_id) in the DB layer plus the
matching endpoint. routers.goals imports cleanly, so the handler is called directly with
patch.object; database.goals binds db at import, so the DB function is exercised against an
explicit fake db chain.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import database.goals as goals_db
from routers import goals as goals_router


# ---------------------------------------------------------------------------
# router: fetch -> 404 or normalize
# ---------------------------------------------------------------------------
def test_get_goal_by_id_returns_normalized_goal():
    goal = {"id": "goal_1", "title": "Read more"}
    with patch.object(goals_router.goals_db, "get_goal", return_value=goal) as get_mock, patch.object(
        goals_router, "normalize_goal_response", return_value={"normalized": True}
    ) as norm_mock:
        result = goals_router.get_goal_by_id(goal_id="goal_1", uid="u1")
    get_mock.assert_called_once_with("u1", "goal_1")
    norm_mock.assert_called_once_with(goal)
    assert result == {"normalized": True}


def test_get_goal_by_id_404_when_missing():
    with patch.object(goals_router.goals_db, "get_goal", return_value=None):
        with pytest.raises(HTTPException) as ei:
            goals_router.get_goal_by_id(goal_id="missing", uid="u1")
    assert ei.value.status_code == 404


# ---------------------------------------------------------------------------
# db: get_goal against a fake Firestore chain
# ---------------------------------------------------------------------------
def _fake_db(doc):
    fake = MagicMock()
    fake.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        doc
    )
    return fake


def test_db_get_goal_returns_none_when_absent():
    doc = MagicMock()
    doc.exists = False
    with patch.object(goals_db, "db", _fake_db(doc)):
        assert goals_db.get_goal("u1", "missing") is None


def test_db_get_goal_returns_dict_and_fills_id():
    doc = MagicMock()
    doc.exists = True
    doc.id = "goal_1"
    doc.to_dict.return_value = {"title": "Read more"}  # no 'id' -> _goal_dict fills it from doc.id
    with patch.object(goals_db, "db", _fake_db(doc)):
        out = goals_db.get_goal("u1", "goal_1")
    # _goal_dict fills both id and the goal_id alias from doc.id when absent.
    assert out == {"title": "Read more", "id": "goal_1", "goal_id": "goal_1"}
