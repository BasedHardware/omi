"""GET /v1/goals/{goal_id} fetches a single goal by id, 404 when absent.

The goals router already exposed list, create, update, delete, progress, history, and advice by
id, but no plain read of one goal. This adds the matching endpoint on top of the existing
database helper `goals_db.get_goal_by_id`, rather than a second single-goal reader: that helper
already normalizes storage and now reads through the neutral storage port (`_store()`), so the
route inherits the same shape and the same seam every other goals read uses.

routers.goals imports cleanly, so the handler is called directly. The database-level tests drive
the helper against a `FakeDocumentStore` bound through the module-level `_store()` seam, the same
seam production and the migrated siblings read through.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from unittest.mock import patch

import pytest
from fastapi import HTTPException

import database.goals as goals_db
from routers import goals as goals_router
from tests.store_fakes import FakeDocumentStore


# ---------------------------------------------------------------------------
# router: fetch -> 404 or normalize
# ---------------------------------------------------------------------------
def test_get_goal_by_id_returns_normalized_goal():
    goal = {"id": "goal_1", "title": "Read more"}
    with patch.object(goals_router.goals_db, "get_goal_by_id", return_value=goal) as get_mock, patch.object(
        goals_router, "normalize_goal_response", return_value={"normalized": True}
    ) as norm_mock:
        result = goals_router.get_goal_by_id(goal_id="goal_1", uid="u1")
    # The route must go through the canonical reader, not a second single-goal helper.
    get_mock.assert_called_once_with("u1", "goal_1")
    norm_mock.assert_called_once_with(goal)
    assert result == {"normalized": True}


def test_get_goal_by_id_404_when_missing():
    with patch.object(goals_router.goals_db, "get_goal_by_id", return_value=None):
        with pytest.raises(HTTPException) as ei:
            goals_router.get_goal_by_id(goal_id="missing", uid="u1")
    assert ei.value.status_code == 404


# ---------------------------------------------------------------------------
# db: get_goal_by_id through the neutral storage port
# ---------------------------------------------------------------------------
def test_db_get_goal_by_id_returns_none_when_absent(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(goals_db, "_store", lambda: store)

    assert goals_db.get_goal_by_id("u1", "missing") is None


def test_db_get_goal_by_id_returns_normalized_goal_with_id(monkeypatch):
    store = FakeDocumentStore()
    store.set("users/u1/goals/goal_1", {"title": "Read more"})  # no 'id' -> stamped from goal_id
    monkeypatch.setattr(goals_db, "_store", lambda: store)

    out = goals_db.get_goal_by_id("u1", "goal_1")

    assert out is not None
    # normalize_goal_storage stamps the id and fills storage defaults. Reusing this helper is
    # what gives the route the same normalization every other goals read already gets; the
    # removed helper returned the raw document instead.
    assert out["id"] == "goal_1"
    assert out["title"] == "Read more"


def test_db_get_goal_by_id_reads_through_the_store_seam(monkeypatch):
    """The store seam must be the one actually queried, at the uid-scoped goal path.

    The removed Firestore-ref seam reached for the module-level ``db`` proxy, so a test could pass
    while production read through a different boundary. Reading through ``_store()`` keeps the path
    uid-scoped: another user's collection cannot serve this goal.
    """
    store = FakeDocumentStore()
    store.set("users/u1/goals/goal_1", {"title": "Read more"})
    monkeypatch.setattr(goals_db, "_store", lambda: store)

    assert goals_db.get_goal_by_id("u1", "goal_1")["id"] == "goal_1"
    assert goals_db.get_goal_by_id("another", "goal_1") is None
