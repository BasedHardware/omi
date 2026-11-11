"""Regression tests for two goals bugs:

1. ``GET /v1/goals/advice`` (get_current_goal_advice) passed arguments to
   ``get_goal_advice_llm`` in the wrong order — ``(goal['id'], uid)`` instead of
   ``(uid, goal['id'])``. The util looked up goals by ``uid=goal_id``, found none,
   raised, and the broad except returned the canned fallback. Every caller got the
   generic sentence, never real advice.

2. ``database.goals.update_goal`` with ``clear_metric=True`` (or ``metric=null``)
   wrote ``metric: None`` but left the released numeric aliases (``goal_type``,
   ``current_value``, ``target_value``, ...) in the document. On the next read,
   ``_metric_from_storage`` rebuilt a metric from those stale aliases, so the
   "cleared" metric silently came back.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import pytest
from fastapi import HTTPException

import database.goals as goals_db
from routers import goals as goals_router


# ---------------------------------------------------------------------------
# Bug 1: get_current_goal_advice argument order
# ---------------------------------------------------------------------------
def test_current_goal_advice_passes_uid_then_goal_id():
    """The route must forward (uid, goal_id) to the advice helper — the util's real signature."""
    with patch.object(
        goals_router.goals_db, "get_user_goal", return_value={"id": "goal_abc", "title": "Run a 5k"}
    ), patch.object(goals_router, "get_goal_advice_llm", return_value="real advice") as advice_mock:
        result = goals_router.get_current_goal_advice(uid="u1")

    advice_mock.assert_called_once_with("u1", "goal_abc")
    assert result == {"advice": "real advice"}


def test_current_goal_advice_no_goal_returns_setup_message():
    with patch.object(goals_router.goals_db, "get_user_goal", return_value=None), patch.object(
        goals_router, "get_goal_advice_llm"
    ) as advice_mock:
        result = goals_router.get_current_goal_advice(uid="u1")

    advice_mock.assert_not_called()
    assert result == {"advice": "Set a goal to get personalized advice!"}


def test_goal_advice_by_id_still_correct():
    """The by-id sibling route must keep passing (uid, goal_id)."""
    with patch.object(goals_router, "get_goal_advice_llm", return_value="advice") as advice_mock:
        result = goals_router.get_goal_advice(goal_id="g1", uid="u1")

    advice_mock.assert_called_once_with("u1", "g1")
    assert result == {"advice": "advice"}


# ---------------------------------------------------------------------------
# Bug 2: clear_metric must actually clear (db level, injectable client seam)
# ---------------------------------------------------------------------------
def _goal_doc(metric_aliases=None):
    """A stored goal row with the released numeric aliases a created goal carries."""
    aliases = (
        metric_aliases
        if metric_aliases is not None
        else {
            "goal_type": "numeric",
            "current_value": 3.0,
            "target_value": 10.0,
            "min_value": 0.0,
            "max_value": 20.0,
            "unit": "kg",
        }
    )
    return {
        "id": "goal_1",
        "title": "Lose weight",
        "metric": {
            "type": "numeric",
            "current": 3.0,
            "target": 10.0,
            "min": 0.0,
            "max": 20.0,
            "unit": "kg",
        },
        **aliases,
    }


def _fake_client_with_goal(doc_data, *, updated_store=None):
    """Fake Firestore client wired to the _goal_ref chain + update capture."""
    client = MagicMock()
    chain = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = doc_data
    chain.get.return_value = snapshot
    return client, chain


def test_clear_metric_nulls_legacy_aliases_in_stored_patch():
    """clear_metric=True must null the numeric aliases so the metric stays cleared."""
    client, chain = _fake_client_with_goal(_goal_doc())
    # get_goal_by_id (called after update) must read the *updated* doc; wire it to return
    # a snapshot of whatever update() wrote so we assert the stored shape.
    stored = {}

    def _fake_update(patch):
        stored.update(patch)

    chain.update.side_effect = _fake_update
    chain.get.side_effect = [
        MagicMock(exists=True, to_dict=lambda: _goal_doc()),
        MagicMock(exists=True, to_dict=lambda: {**_goal_doc(), **stored}),
    ]

    goals_db.update_goal("u1", "goal_1", {"clear_metric": True}, firestore_client=client)

    assert stored["metric"] is None
    for key in ("goal_type", "current_value", "target_value", "min_value", "max_value", "unit"):
        assert stored[key] is None, f"{key} should be nulled on clear, got {stored[key]}"


def test_metric_null_explicitly_also_clears_aliases():
    """Sending metric: null must behave like clear_metric (no stale alias resurrection)."""
    client, chain = _fake_client_with_goal(_goal_doc())
    stored = {}
    chain.update.side_effect = lambda patch: stored.update(patch)
    chain.get.side_effect = [
        MagicMock(exists=True, to_dict=lambda: _goal_doc()),
        MagicMock(exists=True, to_dict=lambda: {**_goal_doc(), **stored}),
    ]

    goals_db.update_goal("u1", "goal_1", {"metric": None}, firestore_client=client)

    assert stored["metric"] is None
    assert stored["goal_type"] is None
    assert stored["current_value"] is None


def test_metric_update_still_writes_aliases():
    """Updating a metric (not clearing) must keep writing the released aliases."""
    client, chain = _fake_client_with_goal(_goal_doc())
    stored = {}
    chain.update.side_effect = lambda patch: stored.update(patch)
    chain.get.side_effect = [
        MagicMock(exists=True, to_dict=lambda: _goal_doc()),
        MagicMock(exists=True, to_dict=lambda: {**_goal_doc(), **stored}),
    ]

    goals_db.update_goal(
        "u1", "goal_1", {"metric": {"type": "numeric", "current": 5.0, "target": 10.0}}, firestore_client=client
    )

    assert stored["metric"]["current"] == 5.0
    assert stored["current_value"] == 5.0
    assert stored["target_value"] == 10.0


def test_update_goal_missing_returns_none():
    doc = MagicMock()
    doc.exists = False
    client = MagicMock()
    chain = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    chain.get.return_value = doc

    assert goals_db.update_goal("u1", "missing", {"title": "x"}, firestore_client=client) is None
