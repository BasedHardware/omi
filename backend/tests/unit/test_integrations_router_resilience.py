import os
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault('ENCRYPTION_SECRET', '01234567890123456789012345678901')
os.environ.setdefault('BASE_API_URL', 'https://api.example.com')

from routers import integrations as integrations_router
from utils.other import endpoints as auth

app = FastAPI()
app.include_router(integrations_router.router)


@pytest.fixture
def client():
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'test_uid_123'
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_apple_health_sync_success(client, monkeypatch):
    monkeypatch.setattr(integrations_router.users_db, 'set_integration', MagicMock())
    resp = client.put(
        '/v1/integrations/apple-health/sync',
        json={'period_days': 14, 'total_steps': 10000},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'ok'
    assert data['app_key'] == 'apple_health'
    assert 'steps' in data['data_types_synced']


def test_apple_health_sync_db_exception(client, monkeypatch):
    monkeypatch.setattr(
        integrations_router.users_db,
        'set_integration',
        MagicMock(side_effect=RuntimeError('Database disk write error')),
    )
    resp = client.put('/v1/integrations/apple-health/sync', json={'period_days': 7})
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to save health data'


def test_get_oauth_url_redis_failure_handled(client, monkeypatch):
    monkeypatch.setenv('BASE_API_URL', 'https://api.example.com')
    monkeypatch.setattr(
        integrations_router.redis_db.r,
        'setex',
        MagicMock(side_effect=RuntimeError('Redis connection refused')),
    )
    # google_calendar is a registered oauth integration
    resp = client.get('/v1/integrations/google_calendar/oauth-url')
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to initialize OAuth flow'


def test_get_integration_db_exception_handled(client, monkeypatch):
    monkeypatch.setattr(
        integrations_router.users_db,
        'get_integration',
        MagicMock(side_effect=RuntimeError('Firestore transport failure')),
    )
    resp = client.get('/v1/integrations/custom_app')
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to retrieve integration status'


def test_save_integration_db_exception_handled(client, monkeypatch):
    monkeypatch.setattr(
        integrations_router.users_db,
        'set_integration',
        MagicMock(side_effect=RuntimeError('Write error')),
    )
    resp = client.put('/v1/integrations/custom_app', json={'connected': True})
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to save integration'


def test_delete_integration_db_exception_handled(client, monkeypatch):
    monkeypatch.setattr(
        integrations_router.users_db,
        'delete_integration',
        MagicMock(side_effect=RuntimeError('Delete error')),
    )
    resp = client.delete('/v1/integrations/custom_app')
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to delete integration'
