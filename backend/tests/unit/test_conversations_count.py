import sys
from unittest.mock import patch, MagicMock

import pytest

for mod_name in [
    'firebase_admin',
    'firebase_admin.auth',
    'firebase_admin.firestore',
    'firebase_admin.messaging',
    'google.cloud',
    'google.cloud.exceptions',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
    'google.cloud.firestore_v1.query',
    'google.cloud.storage',
    'google.cloud.storage.blob',
    'google.cloud.storage.bucket',
    'google.auth',
    'google.auth.transport',
    'google.auth.transport.requests',
    'google.oauth2',
    'google.oauth2.service_account',
    'pinecone',
    'typesense',
    'openai',
    'langchain_openai',
]:
    sys.modules.setdefault(mod_name, MagicMock())

from routers.conversations import router

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch('routers.conversations.auth.get_current_user_uid', return_value='uid-1'):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as c:
            yield c


@pytest.fixture
def client_no_auth():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer 123testuser"}


class TestConversationsCount:
    def test_count_default_statuses(self, client):
        with patch('routers.conversations.conversations_db.count_conversations', return_value=42) as mock_count:
            resp = client.get("/v1/conversations/count", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["count"] == 42
        args = mock_count.call_args
        assert args[1]['statuses'] == ['processing', 'completed']

    def test_count_custom_statuses(self, client):
        with patch('routers.conversations.conversations_db.count_conversations', return_value=10) as mock_count:
            resp = client.get("/v1/conversations/count?statuses=completed", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["count"] == 10
        assert mock_count.call_args[1]['statuses'] == ['completed']

    def test_count_empty_statuses(self, client):
        with patch('routers.conversations.conversations_db.count_conversations', return_value=0) as mock_count:
            resp = client.get("/v1/conversations/count?statuses=", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert mock_count.call_args[1]['statuses'] == []

    def test_count_zero(self, client):
        with patch('routers.conversations.conversations_db.count_conversations', return_value=0):
            resp = client.get("/v1/conversations/count", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_count_fallback_on_aggregation_error(self, client):
        """If Firestore count() aggregation fails, falls back to stream_conversations."""
        with patch(
            'routers.conversations.conversations_db.count_conversations', side_effect=Exception("aggregation err")
        ):
            with patch('routers.conversations.conversations_db.stream_conversations', return_value=iter([1, 2, 3])):
                resp = client.get("/v1/conversations/count", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    def test_count_no_auth_returns_401(self, client_no_auth):
        with patch(
            'routers.conversations.auth.get_current_user_uid',
            side_effect=HTTPException(status_code=401, detail='Not authenticated'),
        ):
            resp = client_no_auth.get("/v1/conversations/count")
        assert resp.status_code == 401

    def test_count_multiple_statuses(self, client):
        with patch('routers.conversations.conversations_db.count_conversations', return_value=25) as mock_count:
            resp = client.get("/v1/conversations/count?statuses=processing,completed,in_progress", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["count"] == 25
        assert mock_count.call_args[1]['statuses'] == ['processing', 'completed', 'in_progress']

    def test_count_too_many_statuses_returns_400(self, client):
        statuses = ','.join(f'status{i}' for i in range(11))
        resp = client.get(f"/v1/conversations/count?statuses={statuses}", headers=AUTH)
        assert resp.status_code == 400
        assert 'max 10' in resp.json()['detail']

    def test_count_stream_fallback(self, client):
        """Fallback uses stream_conversations for unbounded counting."""
        with patch(
            'routers.conversations.conversations_db.count_conversations', side_effect=Exception("no aggregation")
        ):
            with patch(
                'routers.conversations.conversations_db.stream_conversations', return_value=iter([1, 2, 3, 4, 5])
            ):
                resp = client.get("/v1/conversations/count", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["count"] == 5
