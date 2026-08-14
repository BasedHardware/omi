"""POST /v1/apps/{app_id}/reject notification body and optional reason.

The rejection endpoint must remain callable without a body, must include the reason
when supplied, and must tag the notification with the app id and a deep link.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest
from fastapi import Body, FastAPI, Header, HTTPException

from routers import apps as apps_mod  # noqa: E402


@pytest.fixture
def _endpoint_app(monkeypatch):
    monkeypatch.setattr(apps_mod, 'change_app_approval_status', lambda _id, _status: None)
    monkeypatch.setattr(apps_mod, 'invalidate_approved_apps_cache', lambda: None)
    monkeypatch.setattr(apps_mod, 'delete_app_cache_by_id', lambda _id: None)
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda _id, _uid: {'id': _id, 'name': 'Weather'})
    monkeypatch.setattr(apps_mod.os, 'getenv', lambda key, default=None: 'admin' if key == 'ADMIN_KEY' else default)
    calls = []

    def send(uid, title, body, data=None):
        calls.append({'uid': uid, 'title': title, 'body': body, 'data': data})

    monkeypatch.setattr(apps_mod, 'send_notification', send)
    app = FastAPI()

    @app.post('/v1/apps/{app_id}/reject')
    def reject(
        app_id: str,
        uid: str,
        payload: apps_mod.RejectAppRequest = Body(default_factory=apps_mod.RejectAppRequest),
        secret_key: str = Header(...),
    ):
        return apps_mod.reject_app(app_id=app_id, uid=uid, payload=payload, secret_key=secret_key)

    from fastapi.testclient import TestClient

    return TestClient(app), calls


def _reject(monkeypatch, app_id='a1', reason=None, secret_key='admin'):
    calls = []

    monkeypatch.setattr(apps_mod, 'change_app_approval_status', lambda _id, _status: None)
    monkeypatch.setattr(apps_mod, 'invalidate_approved_apps_cache', lambda: None)
    monkeypatch.setattr(apps_mod, 'delete_app_cache_by_id', lambda _id: None)
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda _id, _uid: {'id': _id, 'name': 'Weather'})
    monkeypatch.setattr(
        apps_mod,
        'send_notification',
        lambda uid, title, body, data=None: calls.append({'uid': uid, 'title': title, 'body': body, 'data': data}),
    )
    monkeypatch.setattr(apps_mod.os, 'getenv', lambda key, default=None: 'admin' if key == 'ADMIN_KEY' else default)

    payload = apps_mod.RejectAppRequest(reason=reason)
    result = apps_mod.reject_app(app_id=app_id, uid='u1', payload=payload, secret_key=secret_key)
    return result, calls


def test_reject_without_reason_uses_default_body(monkeypatch):
    result, calls = _reject(monkeypatch, reason=None)
    assert result == {'status': 'ok'}
    assert len(calls) == 1
    assert calls[0]['title'] == 'App Rejected 😔'
    assert 'Weather has been rejected.' in calls[0]['body']
    assert 'Reason:' not in calls[0]['body']
    assert calls[0]['data'] == {'app_id': 'a1', 'type': 'app_rejected', 'navigate_to': '/apps/a1'}


def test_reject_with_reason_appends_reason_to_body(monkeypatch):
    result, calls = _reject(monkeypatch, reason='spam')
    assert result == {'status': 'ok'}
    assert 'Reason: spam.' in calls[0]['body']


def test_reject_with_wrong_secret_key_is_forbidden(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _reject(monkeypatch, secret_key='wrong')
    assert exc.value.status_code == 403


def test_reject_endpoint_without_body(_endpoint_app):
    client, calls = _endpoint_app
    response = client.post('/v1/apps/a1/reject?uid=u1', headers={'secret-key': 'admin'})
    assert response.status_code == 200
    assert len(calls) == 1
    assert 'Reason:' not in calls[0]['body']


def test_reject_endpoint_with_empty_object(_endpoint_app):
    client, calls = _endpoint_app
    response = client.post('/v1/apps/a1/reject?uid=u1', headers={'secret-key': 'admin'}, json={})
    assert response.status_code == 200
    assert len(calls) == 1
    assert 'Reason:' not in calls[0]['body']


def test_reject_endpoint_with_reason(_endpoint_app):
    client, calls = _endpoint_app
    response = client.post('/v1/apps/a1/reject?uid=u1', headers={'secret-key': 'admin'}, json={'reason': 'spam'})
    assert response.status_code == 200
    assert len(calls) == 1
    assert 'Reason: spam.' in calls[0]['body']
