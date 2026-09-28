"""The Developer API goal routes must serve qualitative and legacy goals, not 500.

A goal created without metric fields (the Developer API documents "omit all metric fields
to create a qualitative goal") is stored with `metric: None` and none of the flat
`goal_type` / `target_value` / `current_value` / `min_value` / `max_value` aliases, which
`GoalResponse` requires. The dev routes returned the stored dict with only a datetime
pass, so listing, fetching or creating such a goal failed response validation (HTTP 500),
the write landing before the 500 on create. A legacy goal without `created_at` failed the
same way.

The app's own goal routes already serve these rows through
`utils.goals_response.normalize_goal_response`; the dev routes now do too.
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.goals as goals_db_module
import routers.developer as developer

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _qualitative_goal(goal_id='goal_q'):
    payload = goals_db_module._new_goal_payload({'title': 'Be kinder'}, goal_id=goal_id, now=NOW)
    return goals_db_module.normalize_goal_storage(payload, goal_id=goal_id)


def _metric_goal(goal_id='goal_m'):
    data = {'title': 'Run', 'goal_type': 'numeric', 'target_value': 10, 'current_value': 3, 'unit': 'km'}
    payload = goals_db_module._new_goal_payload(data, goal_id=goal_id, now=NOW)
    return goals_db_module.normalize_goal_storage(payload, goal_id=goal_id)


@pytest.fixture
def client(monkeypatch):
    stored = [_qualitative_goal(), _metric_goal()]
    app = FastAPI()
    app.include_router(developer.router)
    app.dependency_overrides[developer.get_uid_with_goals_read] = lambda: 'uid'
    app.dependency_overrides[developer.get_uid_with_goals_write] = lambda: 'uid'
    monkeypatch.setattr(developer.goals_db, 'get_user_goals', lambda uid, limit=3: [dict(g) for g in stored])
    monkeypatch.setattr(
        developer.goals_db, 'get_all_goals', lambda uid, include_inactive=False, limit=None: [dict(g) for g in stored]
    )
    return TestClient(app, raise_server_exceptions=False)


def test_listing_goals_serves_a_qualitative_goal(client):
    response = client.get('/v1/dev/user/goals')

    assert response.status_code == 200
    goals = {goal['id']: goal for goal in response.json()}
    assert goals['goal_q']['metric'] is None
    assert goals['goal_m']['target_value'] == 10 and goals['goal_m']['unit'] == 'km'


def test_fetching_a_qualitative_goal_succeeds(client):
    response = client.get('/v1/dev/user/goals/goal_q')

    assert response.status_code == 200
    assert response.json()['title'] == 'Be kinder'


def test_creating_a_qualitative_goal_returns_it(client, monkeypatch):
    def create_goal(uid, goal_data):
        payload = goals_db_module._new_goal_payload(goal_data, goal_id=goal_data['id'], now=NOW)
        return goals_db_module.normalize_goal_storage(payload, goal_id=goal_data['id'])

    monkeypatch.setattr(developer.goals_db, 'create_goal', create_goal)

    response = client.post('/v1/dev/user/goals', json={'title': 'Be kinder'})

    assert response.status_code == 200
    assert response.json()['metric'] is None


def test_a_legacy_goal_without_created_at_is_served(client, monkeypatch):
    legacy = {key: value for key, value in _metric_goal().items() if key != 'created_at'}
    monkeypatch.setattr(developer.goals_db, 'get_user_goals', lambda uid, limit=3: [legacy])

    response = client.get('/v1/dev/user/goals')

    assert response.status_code == 200
    assert response.json()[0]['created_at'] == response.json()[0]['updated_at']
