"""Unit tests for goals progress extraction null reasoning, cleared-metric advice, and partial PATCH null guards."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import database.goals as goals_db
from models.goal import GoalUpdate
import routers.goals as goals_router
import utils.llm.goals as goals_llm


def test_extract_and_update_progress_handles_missing_or_null_reasoning(monkeypatch):
    monkeypatch.setattr(goals_router, 'enforce_chat_quota', lambda *args, **kwargs: None)
    monkeypatch.setattr(goals_router, '_wake_goal_change', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        goals_router,
        'extract_and_update_goal_progress',
        lambda uid, text: {
            'status': 'updated',
            'updates': [
                {
                    'goal_id': 'goal-1',
                    'goal_title': 'Run 100km',
                    'old_value': 10.0,
                    'new_value': 25.0,
                    'reasoning': None,
                }
            ],
        },
    )
    payload = goals_router.extract_and_update_progress(
        request=goals_router.ProgressExtractRequest(text='Ran 15km today'),
        uid='uid-1',
    )
    validated = goals_router.ProgressExtractResponse.model_validate(payload)
    assert validated.updated is True
    assert validated.updates is not None
    assert validated.updates[0].reasoning == ''


def test_get_goal_advice_handles_cleared_metric_none_values(monkeypatch):
    monkeypatch.setattr(
        goals_llm.goals_db,
        'get_goal_by_id',
        lambda uid, gid: {
            'id': gid,
            'title': 'Meditate daily',
            'is_active': True,
            'current_value': None,
            'target_value': None,
        },
    )
    monkeypatch.setattr(
        goals_llm,
        '_get_goal_context',
        lambda uid, title: {
            'conversation_context': 'Talked about mindfulness',
            'chat_context': '',
            'memory_context': '',
        },
    )
    mock_client = MagicMock()
    mock_client.invoke.return_value = MagicMock(content='Start with 5 minutes after waking up.')
    monkeypatch.setattr(goals_llm, 'get_llm', lambda *args, **kwargs: mock_client)

    advice = goals_llm.get_goal_advice('uid-1', 'goal-1')
    assert advice == 'Start with 5 minutes after waking up.'
    mock_client.invoke.assert_called_once()


def test_update_goal_ignores_explicit_none_legacy_metric_keys_and_rejects_inverted_bounds(monkeypatch):
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    stored = {
        'id': 'goal-1',
        'title': 'Save money',
        'is_active': True,
        'status': 'active',
        'goal_type': 'numeric',
        'current_value': 200.0,
        'target_value': 1000.0,
        'min_value': 0.0,
        'max_value': 1000.0,
        'created_at': now,
        'updated_at': now,
    }
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.id = 'goal-1'
    snapshot.to_dict.return_value = dict(stored)

    ref = MagicMock()
    ref.get.return_value = snapshot

    def fake_update(patch):
        stored.update(patch)

    ref.update.side_effect = fake_update
    monkeypatch.setattr(goals_db, '_goal_ref', lambda uid, goal_id, firestore_client=None: ref)
    monkeypatch.setattr(goals_db, 'get_goal_by_id', lambda uid, goal_id, firestore_client=None: dict(stored))

    updated = goals_db.update_goal(
        'uid-1',
        'goal-1',
        {'title': 'Save more money', 'current_value': None, 'target_value': None, 'goal_type': None},
    )
    assert updated is not None
    assert updated['title'] == 'Save more money'
    assert updated['current_value'] == 200.0
    assert updated['target_value'] == 1000.0

    with pytest.raises(HTTPException) as exc_info:
        goals_router.update_goal(
            'goal-1',
            GoalUpdate(min_value=500.0, max_value=100.0),
            uid='uid-1',
        )
    assert exc_info.value.status_code == 422
