import os
import inspect
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import routers.apps as apps_mod


def _sample_app(**kwargs) -> dict:
    base = {
        'id': 'app-1',
        'uid': 'owner-uid',
        'name': 'Sample App',
        'category': 'productivity-and-organization',
        'author': 'Developer',
        'description': 'Test App Description',
        'image': 'https://example.com/icon.png',
        'capabilities': {'memories'},
        'approved': True,
        'private': False,
    }
    base.update(kwargs)
    return base


def _sample_reviews() -> dict:
    return {
        'rev-1': {
            'uid': 'reviewer-1',
            'score': 5,
            'review': 'Excellent app, loved the workflow!',
            'username': 'ReviewerOne',
            'response': 'Thank you!',
        },
        'rev-2': {
            'uid': 'reviewer-2',
            'score': 4,
            'review': '',  # empty review text, should be filtered out
            'username': 'ReviewerTwo',
            'response': '',
        },
    }


def test_app_reviews_signature_enforces_auth_dependency():
    """Verify that app_reviews declares uid: str = Depends(auth.get_current_user_uid)."""
    sig = inspect.signature(apps_mod.app_reviews)
    assert 'uid' in sig.parameters
    param = sig.parameters['uid']
    assert param.default.dependency == apps_mod.auth.get_current_user_uid


def test_unauthenticated_request_rejected_via_testclient():
    """Verify that unauthenticated HTTP requests receive 401 Unauthorized."""
    app = FastAPI()
    app.include_router(apps_mod.router)
    client = TestClient(app)

    response = client.get('/v1/apps/app-1/reviews')
    assert response.status_code == 401


def test_non_existent_app_returns_404(monkeypatch):
    """Verify that requesting reviews for a non-existent app returns 404."""
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: None)

    with pytest.raises(HTTPException) as exc_info:
        apps_mod.app_reviews('non-existent-app', uid='user-1')

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'App not found'


def test_unapproved_app_by_non_owner_returns_404(monkeypatch):
    """Verify that requesting reviews for an unapproved app by a non-owner returns 404."""
    unapproved = _sample_app(id='unapproved-app', uid='owner-uid', approved=False)
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: unapproved)

    with pytest.raises(HTTPException) as exc_info:
        apps_mod.app_reviews('unapproved-app', uid='attacker-uid')

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'App not found'


def test_unapproved_app_by_owner_succeeds(monkeypatch):
    """Verify that the owner of an unapproved app can view its reviews."""
    unapproved = _sample_app(id='unapproved-app', uid='owner-uid', approved=False)
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: unapproved)
    monkeypatch.setattr(apps_mod, 'get_app_reviews', lambda app_id: _sample_reviews())

    reviews = apps_mod.app_reviews('unapproved-app', uid='owner-uid')
    assert len(reviews) == 1
    assert reviews[0]['review'] == 'Excellent app, loved the workflow!'


def test_private_app_by_non_owner_returns_403(monkeypatch):
    """Verify that requesting reviews for a private app by a non-owner returns 403."""
    private_app = _sample_app(id='private-app', uid='owner-uid', approved=True, private=True)
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: private_app)

    with pytest.raises(HTTPException) as exc_info:
        apps_mod.app_reviews('private-app', uid='attacker-uid')

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == 'You are not authorized to view this app'


def test_private_app_by_owner_succeeds(monkeypatch):
    """Verify that the owner of a private app can view its reviews."""
    private_app = _sample_app(id='private-app', uid='owner-uid', approved=True, private=True)
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: private_app)
    monkeypatch.setattr(apps_mod, 'get_app_reviews', lambda app_id: _sample_reviews())

    reviews = apps_mod.app_reviews('private-app', uid='owner-uid')
    assert len(reviews) == 1
    assert reviews[0]['review'] == 'Excellent app, loved the workflow!'


def test_public_approved_app_accessible_by_any_user(monkeypatch):
    """Verify that any authenticated user can view reviews of a public approved app."""
    public_app = _sample_app(id='public-app', uid='owner-uid', approved=True, private=False)
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: public_app)
    monkeypatch.setattr(apps_mod, 'get_app_reviews', lambda app_id: _sample_reviews())

    reviews = apps_mod.app_reviews('public-app', uid='other-user-uid')
    assert len(reviews) == 1
    assert reviews[0]['review'] == 'Excellent app, loved the workflow!'


def test_empty_reviews_filtered_out(monkeypatch):
    """Verify that reviews without review text are filtered out as per existing contract."""
    public_app = _sample_app(id='public-app', uid='owner-uid', approved=True, private=False)
    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: public_app)

    raw_reviews = {
        'rev-empty': {'uid': 'u1', 'score': 5, 'review': None},
        'rev-empty-str': {'uid': 'u2', 'score': 4, 'review': ''},
        'rev-valid': {'uid': 'u3', 'score': 5, 'review': 'Real review'},
    }
    monkeypatch.setattr(apps_mod, 'get_app_reviews', lambda app_id: raw_reviews)

    reviews = apps_mod.app_reviews('public-app', uid='user-1')
    assert len(reviews) == 1
    assert reviews[0]['uid'] == 'u3'
    assert reviews[0]['review'] == 'Real review'
