import os
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure ENCRYPTION_SECRET is set before importing app modules
os.environ.setdefault('ENCRYPTION_SECRET', '01234567890123456789012345678901')
os.environ.setdefault('ADMIN_KEY', 'test_admin_key_secret')

from routers import fair_use_admin as fair_use_router
from utils.other.endpoints import get_current_user_uid

app = FastAPI()
app.include_router(fair_use_router.router)
fair_use_router.ADMIN_KEY = 'test_admin_key_secret'

ADMIN_HEADERS = {'X-Admin-Key': 'test_admin_key_secret'}


@pytest.fixture
def client():
    return TestClient(app)


def test_lookup_case_invalid_format(client):
    response = client.get('/v1/admin/fair-use/case/invalid-format', headers=ADMIN_HEADERS)
    assert response.status_code == 400
    assert response.json()['detail'] == 'Invalid case reference format'


def test_lookup_case_sql_injection_attempt(client):
    response = client.get('/v1/admin/fair-use/case/FU-1234%27%20OR%201=1--', headers=ADMIN_HEADERS)
    assert response.status_code == 400
    assert response.json()['detail'] == 'Invalid case reference format'


def test_lookup_case_not_found(client, monkeypatch):
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = []
    mock_db.collection_group.return_value = mock_query
    monkeypatch.setattr(fair_use_router, 'db', mock_db)

    response = client.get('/v1/admin/fair-use/case/FU-A1B2C3D4E5F6', headers=ADMIN_HEADERS)
    assert response.status_code == 404
    assert 'not found' in response.json()['detail']


def test_lookup_case_firestore_exception_handled(client, monkeypatch):
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.side_effect = RuntimeError('Firestore transport error')
    mock_db.collection_group.return_value = mock_query
    monkeypatch.setattr(fair_use_router, 'db', mock_db)

    response = client.get('/v1/admin/fair-use/case/FU-A1B2C3D4E5F6', headers=ADMIN_HEADERS)
    assert response.status_code == 500
    assert response.json()['detail'] == 'Failed to lookup case reference'


def test_lookup_case_success(client, monkeypatch):
    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = {'reason': 'test', 'stage': 'warning'}
    mock_doc.reference.path = 'users/user123/fair_use_events/evt456'
    mock_doc.id = 'evt456'

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = [mock_doc]
    mock_db.collection_group.return_value = mock_query
    monkeypatch.setattr(fair_use_router, 'db', mock_db)

    response = client.get('/v1/admin/fair-use/case/FU-A1B2C3D4E5F6', headers=ADMIN_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data['uid'] == 'user123'
    assert data['event_id'] == 'evt456'


def test_public_case_status_invalid_format(client):
    response = client.get('/v1/fair-use/case/bad_format/status')
    assert response.status_code == 400
    assert response.json()['detail'] == 'Invalid case reference format'


def test_public_case_status_not_found(client, monkeypatch):
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = []
    mock_db.collection_group.return_value = mock_query
    monkeypatch.setattr(fair_use_router, 'db', mock_db)

    response = client.get('/v1/fair-use/case/FU-000000000000/status')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Case not found'


def test_public_case_status_firestore_exception_handled(client, monkeypatch):
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.side_effect = RuntimeError('Firestore transport error')
    mock_db.collection_group.return_value = mock_query
    monkeypatch.setattr(fair_use_router, 'db', mock_db)

    response = client.get('/v1/fair-use/case/FU-000000000000/status')
    assert response.status_code == 500
    assert response.json()['detail'] == 'Failed to lookup case reference'


def test_public_case_status_success(client, monkeypatch):
    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = {'created_at': '2026-09-30T00:00:00Z', 'resolved_at': None}
    mock_doc.reference.path = 'users/user123/fair_use_events/evt456'

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = [mock_doc]
    mock_db.collection_group.return_value = mock_query
    monkeypatch.setattr(fair_use_router, 'db', mock_db)
    monkeypatch.setattr(fair_use_router.fair_use_db, 'get_fair_use_state', lambda uid: {'stage': 'warning'})

    response = client.get('/v1/fair-use/case/fu-a1b2c3d4e5f6/status')
    assert response.status_code == 200
    data = response.json()
    assert data['case_ref'] == 'FU-A1B2C3D4E5F6'
    assert data['stage'] == 'warning'
    assert 'FU-A1B2C3D4E5F6' in data['message']


def test_get_flagged_users_invalid_stage(client):
    response = client.get('/v1/admin/fair-use/flagged?stage=invalid_stage', headers=ADMIN_HEADERS)
    assert response.status_code == 400
    assert 'Invalid stage filter' in response.json()['detail']


def test_get_flagged_users_exception_handled(client, monkeypatch):
    monkeypatch.setattr(
        fair_use_router.fair_use_db,
        'get_flagged_users',
        MagicMock(side_effect=RuntimeError('Database unreachable')),
    )

    response = client.get('/v1/admin/fair-use/flagged', headers=ADMIN_HEADERS)
    assert response.status_code == 500
    assert response.json()['detail'] == 'Failed to retrieve flagged users'


def test_set_stage_invalid(client):
    response = client.post('/v1/admin/fair-use/user/u1/set-stage?stage=hacked', headers=ADMIN_HEADERS)
    assert response.status_code == 400
    assert 'Invalid stage' in response.json()['detail']


def test_set_stage_exception_handled(client, monkeypatch):
    monkeypatch.setattr(
        fair_use_router.fair_use_db,
        'update_fair_use_state',
        MagicMock(side_effect=RuntimeError('Write failed')),
    )
    response = client.post('/v1/admin/fair-use/user/u1/set-stage?stage=throttle', headers=ADMIN_HEADERS)
    assert response.status_code == 500
    assert response.json()['detail'] == 'Failed to update user enforcement stage'


def test_get_my_fair_use_status_exception_handled(client, monkeypatch):
    app.dependency_overrides[get_current_user_uid] = lambda: 'test_user_uid'
    try:
        monkeypatch.setattr(
            fair_use_router.fair_use_db,
            'get_fair_use_state',
            MagicMock(side_effect=RuntimeError('Read failure')),
        )
        response = client.get('/v1/fair-use/status')
        assert response.status_code == 500
        assert response.json()['detail'] == 'Failed to retrieve fair use status'
    finally:
        app.dependency_overrides.pop(get_current_user_uid, None)
