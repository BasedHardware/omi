"""Regression tests: GET /v1/dev/user/goals must project every stored row
through the released normalize+validate seam instead of 500ing.

``normalize_goal_storage`` intentionally omits the released numeric tracker
aliases for qualitative goals and leaves legacy missing dates missing, but the
developer ``GoalResponse`` schema requires non-null aliases and datetimes. Rows
that reach the response model unnormalized fail validation and turn the whole
list into a 500. These tests exercise the real FastAPI response boundary so the
projection is verified end to end.
"""

import logging
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.goals as goals_db_module
import routers.developer as developer
from dependencies import get_uid_with_goals_read

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


class _FakeGoalDocument:
    def __init__(self, doc_id, payload):
        self.id = doc_id
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _FakeGoalQuery:
    def __init__(self, documents, stream_error=None):
        self._documents = documents
        self._stream_error = stream_error
        self._limit = None

    def where(self, **kwargs):
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def stream(self):
        if self._stream_error is not None:

            def fail():
                raise self._stream_error
                yield  # Make this a generator so the failure occurs during fetch iteration.

            return fail()
        documents = self._documents if self._limit is None else self._documents[: self._limit]
        return iter(documents)


class _FakeGoalUser:
    def __init__(self, query):
        self._query = query

    def collection(self, name):
        assert name == 'goals'
        return self._query


class _FakeGoalUsers:
    def __init__(self, query):
        self._query = query

    def document(self, uid):
        assert uid == 'uid1'
        return _FakeGoalUser(self._query)


class _FakeGoalFirestore:
    def __init__(self, documents, stream_error=None):
        self._query = _FakeGoalQuery(documents, stream_error)

    def collection(self, name):
        assert name == 'users'
        return _FakeGoalUsers(self._query)


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(developer.router)
    app.dependency_overrides[get_uid_with_goals_read] = lambda: 'uid1'
    return TestClient(app, raise_server_exceptions=False)


def _qualitative_row(goal_id='g1', **overrides):
    row = {'title': 'Read nightly', 'status': 'achieved', 'created_at': NOW, 'updated_at': NOW}
    row.update(overrides)
    return goals_db_module.normalize_goal_storage(row, goal_id=goal_id)


def test_qualitative_goal_row_survives_response_validation(client, monkeypatch):
    """A qualitative goal has no released numeric aliases in storage; the list
    must still satisfy GoalResponse instead of 500ing."""
    monkeypatch.setattr(developer.goals_db, 'get_user_goals', lambda uid, limit: [_qualitative_row()])

    response = client.get('/v1/dev/user/goals')

    assert response.status_code == 200
    (goal,) = response.json()
    assert goal['id'] == 'g1'
    assert goal['goal_type'] == 'scale'
    assert goal['status'] == 'achieved'
    assert goal['is_active'] is False


def test_legacy_dateless_goal_survives_with_defaults(client, monkeypatch):
    row = goals_db_module.normalize_goal_storage({'title': 'legacy', 'status': 'background'}, goal_id='g-legacy')
    assert 'created_at' not in row
    monkeypatch.setattr(developer.goals_db, 'get_user_goals', lambda uid, limit: [row])

    response = client.get('/v1/dev/user/goals')

    assert response.status_code == 200
    (goal,) = response.json()
    assert goal['id'] == 'g-legacy'
    assert goal['created_at'] and goal['updated_at']


def test_null_aliases_normalized_and_metric_values_preserved(client, monkeypatch):
    null_alias_row = goals_db_module.normalize_goal_storage(
        {
            'title': 'Read nightly',
            'status': 'achieved',
            'goal_type': None,
            'target_value': None,
            'current_value': None,
            'min_value': None,
            'max_value': None,
            'unit': None,
            'created_at': NOW,
            'updated_at': NOW,
        },
        goal_id='g1',
    )
    metric_row = goals_db_module.normalize_goal_storage(
        {
            'title': 'Ship it',
            'status': 'background',
            'metric': {'type': 'numeric', 'target': 100, 'current': 42.5, 'min': 0, 'max': 200, 'unit': 'pts'},
            'created_at': NOW,
            'updated_at': NOW,
        },
        goal_id='g2',
    )
    monkeypatch.setattr(developer.goals_db, 'get_user_goals', lambda uid, limit: [null_alias_row, metric_row])

    response = client.get('/v1/dev/user/goals')

    assert response.status_code == 200
    goals = {goal['id']: goal for goal in response.json()}
    assert goals['g1']['goal_type'] == 'scale'
    assert goals['g1']['target_value'] == 0.0
    assert goals['g1']['current_value'] == 0.0
    assert goals['g1']['min_value'] == 0.0
    assert goals['g1']['max_value'] == 10.0
    assert goals['g1']['unit'] is None
    assert goals['g2']['target_value'] == 100.0
    assert goals['g2']['current_value'] == 42.5
    assert goals['g2']['unit'] == 'pts'


@pytest.mark.parametrize('include_inactive', [False, True])
def test_include_inactive_branches_return_normalized_rows(client, monkeypatch, include_inactive):
    calls = []

    def get_user_goals(uid, limit):
        calls.append(('active', limit))
        return [_qualitative_row()]

    def get_all_goals(uid, include_inactive=False, *, limit=None):
        calls.append(('all', include_inactive, limit))
        return [_qualitative_row()]

    monkeypatch.setattr(developer.goals_db, 'get_user_goals', get_user_goals)
    monkeypatch.setattr(developer.goals_db, 'get_all_goals', get_all_goals)

    response = client.get('/v1/dev/user/goals', params={'include_inactive': include_inactive, 'limit': 7})

    assert response.status_code == 200
    assert calls == [('all', True, 7)] if include_inactive else calls == [('active', 7)]


def test_malformed_row_is_skipped_and_healthy_rows_survive(client, monkeypatch, caplog):
    malformed = goals_db_module.normalize_goal_storage(
        {
            'title': 'broken',
            'status': 'background',
            'success_criteria': [{'zzz_marker': 1}],
            'created_at': NOW,
            'updated_at': NOW,
        },
        goal_id='bad-row',
    )
    monkeypatch.setattr(developer.goals_db, 'get_user_goals', lambda uid, limit: [malformed, _qualitative_row()])

    with caplog.at_level(logging.WARNING, logger='routers.developer'):
        response = client.get('/v1/dev/user/goals')

    assert response.status_code == 200
    assert [goal['id'] for goal in response.json()] == ['g1']
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == 'routers.developer']
    assert warnings, 'malformed row must log a skip warning'
    assert 'bad-row' in warnings[0].getMessage()
    assert 'success_criteria' in warnings[0].getMessage()
    assert 'zzz_marker' not in warnings[0].getMessage()


@pytest.mark.parametrize('malformed_criteria', [0, 'private malformed criteria', 987654321])
@pytest.mark.parametrize(
    ('include_inactive', 'limit', 'expected_ids'),
    [
        (False, 10, ['g-old', 'g-new']),
        (True, 1, ['g-new']),
    ],
)
def test_real_getter_skips_malformed_storage_row_and_preserves_healthy_rows(
    client, monkeypatch, caplog, include_inactive, limit, expected_ids, malformed_criteria
):
    """Exercise Firestore stream -> DB normalization -> endpoint validation."""
    documents = [
        _FakeGoalDocument(
            'g-broken',
            {
                'title': 'private malformed row',
                'status': 'background',
                'success_criteria': malformed_criteria,
                'created_at': NOW.replace(day=3),
                'updated_at': NOW,
            },
        ),
        _FakeGoalDocument(
            'g-old',
            {
                'title': 'older healthy goal',
                'status': 'background',
                'success_criteria': ['old criterion'],
                'created_at': NOW.replace(day=1),
                'updated_at': NOW,
            },
        ),
        _FakeGoalDocument(
            'g-new',
            {
                'title': 'newer healthy goal',
                'status': 'background',
                'success_criteria': ['new criterion'],
                'created_at': NOW.replace(day=2),
                'updated_at': NOW,
            },
        ),
    ]
    fake_db = _FakeGoalFirestore(documents)
    monkeypatch.setattr(goals_db_module._client, 'get_firestore_client', lambda: fake_db)

    with caplog.at_level(logging.WARNING, logger='database.goals'):
        response = client.get(
            '/v1/dev/user/goals',
            params={'include_inactive': include_inactive, 'limit': limit},
        )

    assert response.status_code == 200
    assert [goal['id'] for goal in response.json()] == expected_ids
    warnings = [record for record in caplog.records if record.name == 'database.goals']
    assert warnings
    assert 'ValueError' in warnings[0].getMessage()
    assert 'private malformed row' not in warnings[0].getMessage()
    assert str(malformed_criteria) not in warnings[0].getMessage()


def test_real_getter_propagates_firestore_stream_failure(client, monkeypatch):
    fake_db = _FakeGoalFirestore([], stream_error=RuntimeError('PRIVATE-STREAM-MARKER'))
    monkeypatch.setattr(goals_db_module._client, 'get_firestore_client', lambda: fake_db)

    response = client.get('/v1/dev/user/goals')

    assert response.status_code == 500


def test_database_failure_logs_sanitized_context_and_500s(client, monkeypatch, caplog):
    def boom(uid, limit):
        raise RuntimeError('PRIVATE-MARKER-7f3a')

    monkeypatch.setattr(developer.goals_db, 'get_user_goals', boom)

    with caplog.at_level(logging.ERROR, logger='routers.developer'):
        response = client.get('/v1/dev/user/goals', params={'limit': 25})

    assert response.status_code == 500
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and r.name == 'routers.developer']
    assert errors, 'failed fetch must log a sanitized ERROR'
    text = errors[0].getMessage()
    assert '/v1/dev/user/goals' in text
    assert 'uid1' in text
    assert '25' in text
    assert 'False' in text
    assert 'RuntimeError' in text
    assert 'PRIVATE-MARKER' not in text
