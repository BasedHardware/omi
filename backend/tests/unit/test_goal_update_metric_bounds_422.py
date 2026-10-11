"""``PATCH /v1/goals/{goal_id}`` with a released metric alias that contradicts the stored metric.

Released clients patch one numeric alias at a time (``min_value``, ``max_value``, ...). Each
alias is valid on its own, so request validation passes, but ``database.goals.update_goal``
merges it with the stored metric and ``GoalMetric`` rejects the result (a new min above the
stored max). That ``ValidationError`` escaped the route as a 500 instead of the 422 the
client can show. The route now maps the typed ``GoalValidationError`` to 422.
"""

import os

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.goals as goals_db
import routers.goals as goals_router


def _stored_goal() -> dict:
    return {
        'id': 'goal_1',
        'title': 'Lose weight',
        'desired_outcome': 'Lose weight',
        'status': 'background',
        'metric': {'type': 'numeric', 'current': 3.0, 'target': 10.0, 'min': 0.0, 'max': 20.0, 'unit': 'kg'},
        'goal_type': 'numeric',
        'current_value': 3.0,
        'target_value': 10.0,
        'min_value': 0.0,
        'max_value': 20.0,
        'unit': 'kg',
    }


def _fake_firestore(stored: dict):
    """Fake Firestore client wired to the users/{uid}/goals/{goal_id} chain with update capture."""
    client = MagicMock()
    chain = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    chain.get.side_effect = lambda *args, **kwargs: MagicMock(exists=True, to_dict=lambda: dict(stored))
    chain.update.side_effect = lambda patch: stored.update(patch)
    return client, chain


def _client(monkeypatch, stored: dict) -> tuple[TestClient, MagicMock]:
    client, chain = _fake_firestore(stored)
    monkeypatch.setattr(goals_db._client, 'get_firestore_client', lambda: client)
    app = FastAPI()
    app.include_router(goals_router.router)
    app.dependency_overrides[goals_router.auth.get_current_user_uid] = lambda: 'u1'
    return TestClient(app), chain


@pytest.mark.parametrize('body', [{'min_value': 30}, {'max_value': -1}])
def test_update_goal_alias_contradicting_stored_metric_is_422(monkeypatch, body):
    stored = _stored_goal()
    test_client, chain = _client(monkeypatch, stored)

    response = test_client.patch('/v1/goals/goal_1', json=body)

    assert response.status_code == 422, response.text
    assert response.json()['detail'] == 'metric min must not exceed max'
    chain.update.assert_not_called()


def test_update_goal_alias_consistent_with_stored_metric_still_merges(monkeypatch):
    stored = _stored_goal()
    test_client, chain = _client(monkeypatch, stored)

    response = test_client.patch('/v1/goals/goal_1', json={'min_value': 5})

    assert response.status_code == 200, response.text
    chain.update.assert_called_once()
    written = chain.update.call_args.args[0]
    assert written['metric']['min'] == 5.0
    assert written['metric']['max'] == 20.0
    assert written['min_value'] == 5.0
    assert response.json()['min_value'] == 5.0


def test_update_goal_raises_typed_validation_error_at_db_seam():
    stored = _stored_goal()
    client, chain = _fake_firestore(stored)

    with pytest.raises(goals_db.GoalValidationError) as error:
        goals_db.update_goal('u1', 'goal_1', {'max_value': -1}, firestore_client=client)

    assert str(error.value) == 'metric min must not exceed max'
    assert isinstance(error.value, goals_db.GoalStoreError)
    chain.update.assert_not_called()
