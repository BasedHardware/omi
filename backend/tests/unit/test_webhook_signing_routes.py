"""Signing-secret endpoints (#20939): show-once issue, rotate, status, delete, ownership."""

import os
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

from database.webhook_signing import WebhookSigningSecrets  # noqa: E402
from routers import webhook_signing as routes  # noqa: E402
from utils.other import endpoints  # noqa: E402
from utils.webhook_signing import SECRET_PREFIX  # noqa: E402


class _Store:
    """In-memory stand-in for the user/app signing stores, keyed by owner id."""

    def __init__(self):
        self.records = {}

    def get(self, key, **_):
        return self.records.get(key)

    def rotate(self, key, secret, **_):
        record = WebhookSigningSecrets.issue(secret, previous=self.records.get(key))
        self.records[key] = record
        return record

    def delete(self, key, **_):
        self.records.pop(key, None)


@pytest.fixture
def user_store(monkeypatch):
    store = _Store()
    monkeypatch.setattr(routes, 'get_user_webhook_signing_db', store.get)
    monkeypatch.setattr(routes, 'rotate_user_webhook_signing_db', store.rotate)
    monkeypatch.setattr(routes, 'delete_user_webhook_signing_db', store.delete)
    return store


@pytest.fixture
def app_store(monkeypatch):
    store = _Store()
    monkeypatch.setattr(routes, 'get_app_webhook_signing_db', store.get)
    monkeypatch.setattr(routes, 'rotate_app_webhook_signing_db', store.rotate)
    monkeypatch.setattr(routes, 'delete_app_webhook_signing_db', store.delete)
    return store


def test_user_secret_is_shown_once_then_only_its_status_is_readable(user_store):
    assert routes.get_user_webhook_signing_secret_status(uid='uid-1') == {'configured': False}

    response = Response()
    issued = routes.issue_user_webhook_signing_secret(response, uid='uid-1')
    assert issued['secret'].startswith(SECRET_PREFIX)
    assert issued['previous_valid_until'] is None
    assert response.headers['Cache-Control'] == 'no-store'
    assert user_store.records['uid-1'].current == issued['secret']

    status = routes.get_user_webhook_signing_secret_status(uid='uid-1')
    assert status == {'configured': True, 'created_at': issued['created_at'], 'previous_valid_until': None}
    assert 'secret' not in status


def test_issuing_again_rotates_and_keeps_the_old_secret_for_the_grace_window(user_store):
    first = routes.issue_user_webhook_signing_secret(Response(), uid='uid-1')
    second = routes.issue_user_webhook_signing_secret(Response(), uid='uid-1')
    assert second['secret'] != first['secret']
    assert second['previous_valid_until'] is not None
    record = user_store.records['uid-1']
    assert record.active() == [second['secret'], first['secret']]
    assert routes.get_user_webhook_signing_secret_status(uid='uid-1')['previous_valid_until'] == (
        second['previous_valid_until']
    )


def test_deleting_the_user_secret_turns_signing_off(user_store):
    routes.issue_user_webhook_signing_secret(Response(), uid='uid-1')
    assert routes.delete_user_webhook_signing_secret(uid='uid-1') == {'status': 'ok'}
    assert user_store.records == {}
    assert routes.get_user_webhook_signing_secret_status(uid='uid-1') == {'configured': False}


def test_user_routes_serialize_through_their_response_models(user_store):
    app = FastAPI()
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'uid-1'
    app.include_router(routes.router)
    with TestClient(app) as client:
        issued = client.post('/v1/users/developer/webhook-signing-secret')
        assert issued.status_code == 200
        assert issued.headers['cache-control'] == 'no-store'
        body = issued.json()
        assert set(body) == {'secret', 'created_at', 'previous_valid_until'}
        assert body['secret'].startswith(SECRET_PREFIX)

        status = client.get('/v1/users/developer/webhook-signing-secret')
        assert status.status_code == 200
        assert status.json() == {'configured': True, 'created_at': body['created_at'], 'previous_valid_until': None}

        assert client.delete('/v1/users/developer/webhook-signing-secret').status_code == 200
        assert client.get('/v1/users/developer/webhook-signing-secret').json() == {
            'configured': False,
            'created_at': None,
            'previous_valid_until': None,
        }


def _apps_visible(monkeypatch, apps):
    monkeypatch.setattr(routes, 'get_available_app_by_id', lambda app_id, uid: apps.get(app_id))


def test_app_secret_requires_an_existing_app_owned_by_the_caller(app_store, monkeypatch):
    _apps_visible(monkeypatch, {'app-1': {'id': 'app-1', 'uid': 'owner'}})

    with pytest.raises(HTTPException) as missing:
        routes.issue_app_webhook_signing_secret('app-404', Response(), uid='owner')
    assert missing.value.status_code == 404

    for call in (
        lambda: routes.issue_app_webhook_signing_secret('app-1', Response(), uid='someone-else'),
        lambda: routes.get_app_webhook_signing_secret_status('app-1', uid='someone-else'),
        lambda: routes.delete_app_webhook_signing_secret('app-1', uid='someone-else'),
    ):
        with pytest.raises(HTTPException) as forbidden:
            call()
        assert forbidden.value.status_code == 403
    assert app_store.records == {}


def test_app_secret_issue_status_rotate_and_delete(app_store, monkeypatch):
    _apps_visible(monkeypatch, {'app-1': {'id': 'app-1', 'uid': 'owner'}})
    assert routes.get_app_webhook_signing_secret_status('app-1', uid='owner') == {'configured': False}

    response = Response()
    first = routes.issue_app_webhook_signing_secret('app-1', response, uid='owner')
    assert first['secret'].startswith(SECRET_PREFIX) and first['previous_valid_until'] is None
    assert response.headers['Cache-Control'] == 'no-store'
    assert app_store.records['app-1'].current == first['secret']

    second = routes.issue_app_webhook_signing_secret('app-1', Response(), uid='owner')
    assert app_store.records['app-1'].active() == [second['secret'], first['secret']]
    status = routes.get_app_webhook_signing_secret_status('app-1', uid='owner')
    assert status == {
        'configured': True,
        'created_at': second['created_at'],
        'previous_valid_until': second['previous_valid_until'],
    }

    assert routes.delete_app_webhook_signing_secret('app-1', uid='owner') == {'status': 'ok'}
    assert app_store.records == {}


def test_app_record_is_never_read_or_rotated_for_a_foreign_app(app_store, monkeypatch):
    _apps_visible(monkeypatch, {'app-1': {'id': 'app-1', 'uid': 'owner'}})
    read = MagicMock(return_value=None)
    rotate = MagicMock()
    monkeypatch.setattr(routes, 'get_app_webhook_signing_db', read)
    monkeypatch.setattr(routes, 'rotate_app_webhook_signing_db', rotate)
    with pytest.raises(HTTPException):
        routes.get_app_webhook_signing_secret_status('app-1', uid='someone-else')
    with pytest.raises(HTTPException):
        routes.issue_app_webhook_signing_secret('app-1', Response(), uid='someone-else')
    read.assert_not_called()
    rotate.assert_not_called()


def _client(monkeypatch, decisions):
    """A test app whose rate limiter answers from ``decisions``; records every consulted key."""
    consulted = []

    def check_rate_limit(key, policy, max_requests, window):
        consulted.append((key, policy, max_requests, window))
        return decisions.pop(0) if decisions else (True, max_requests, 0)

    monkeypatch.setattr(endpoints, 'check_rate_limit', check_rate_limit)
    app = FastAPI()
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'uid-1'
    app.include_router(routes.router)
    return TestClient(app), consulted


def test_issue_and_delete_are_rate_limited_per_uid_but_status_is_not(user_store, monkeypatch):
    client, consulted = _client(monkeypatch, [])
    with client:
        assert client.get('/v1/users/developer/webhook-signing-secret').status_code == 200
        assert consulted == []
        assert client.post('/v1/users/developer/webhook-signing-secret').status_code == 200
        assert client.delete('/v1/users/developer/webhook-signing-secret').status_code == 200
    assert [(key, policy) for key, policy, _, _ in consulted] == [
        ('uid-1', 'webhook_signing:secret'),
        ('uid-1', 'webhook_signing:secret'),
    ]
    assert consulted[0][2:] == (10, 3600)


def test_rotating_past_the_limit_answers_429_before_touching_the_store(user_store, app_store, monkeypatch):
    _apps_visible(monkeypatch, {'app-1': {'id': 'app-1', 'uid': 'uid-1'}})
    client, _ = _client(monkeypatch, [(False, 0, 17), (False, 0, 17)])
    with client:
        refused = client.post('/v1/users/developer/webhook-signing-secret')
        assert refused.status_code == 429
        assert refused.headers['retry-after'] == '17'
        assert client.post('/v1/apps/app-1/webhook-signing-secret').status_code == 429
    assert user_store.records == {} and app_store.records == {}
