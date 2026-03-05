import sys
from datetime import datetime, timezone
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

# Mock llm_mini before importing the router
mock_llm = MagicMock()
mock_llm.invoke.return_value = MagicMock(content='Project Discussion')
sys.modules.setdefault('utils.llm.clients', MagicMock(llm_mini=mock_llm))

from routers.chat import router

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch('routers.chat.auth.get_current_user_uid', return_value='uid-1'):
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


class TestGenerateChatTitle:
    def test_generate_title_success(self, client):
        data = {
            "session_id": "sess-1",
            "messages": [
                {"text": "How do I deploy to production?", "sender": "human"},
                {"text": "You can use the CI/CD pipeline.", "sender": "ai"},
            ],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content='Production Deployment')
            with patch('routers.chat.chat_db.update_chat_session'):
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Production Deployment"

    def test_generate_title_strips_quotes(self, client):
        data = {
            "session_id": "sess-1",
            "messages": [{"text": "Hello", "sender": "human"}],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content='"Greeting Chat"')
            with patch('routers.chat.chat_db.update_chat_session'):
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Greeting Chat"

    def test_generate_title_empty_messages_returns_400(self, client):
        data = {"session_id": "sess-1", "messages": []}
        resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_generate_title_no_messages_field_returns_422(self, client):
        data = {"session_id": "sess-1"}
        resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 422

    def test_generate_title_llm_fallback(self, client):
        data = {
            "session_id": "sess-1",
            "messages": [{"text": "What about the budget proposal?", "sender": "human"}],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.side_effect = Exception("LLM down")
            with patch('routers.chat.chat_db.update_chat_session'):
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["title"] == "What about the budget proposal?"

    def test_generate_title_updates_session(self, client):
        data = {
            "session_id": "sess-1",
            "messages": [{"text": "Hello", "sender": "human"}],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content='Greeting')
            with patch('routers.chat.chat_db.update_chat_session') as mock_update:
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        mock_update.assert_called_once()
        call_args = mock_update.call_args[0]
        assert call_args[1] == 'sess-1'
        assert call_args[2]['title'] == 'Greeting'

    def test_generate_title_session_update_failure_still_returns(self, client):
        data = {
            "session_id": "sess-1",
            "messages": [{"text": "Hello", "sender": "human"}],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content='Greeting')
            with patch('routers.chat.chat_db.update_chat_session', side_effect=Exception("DB err")):
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Greeting"

    def test_generate_title_truncates_long_title(self, client):
        data = {
            "session_id": "sess-1",
            "messages": [{"text": "Hello", "sender": "human"}],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content='A' * 200)
            with patch('routers.chat.chat_db.update_chat_session'):
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.json()["title"]) <= 100

    def test_generate_title_no_auth_returns_401(self, client_no_auth):
        data = {
            "session_id": "sess-1",
            "messages": [{"text": "Hello", "sender": "human"}],
        }
        with patch(
            'routers.chat.auth.get_current_user_uid',
            side_effect=HTTPException(status_code=401, detail='Not authenticated'),
        ):
            resp = client_no_auth.post("/v2/chat/generate-title", json=data)
        assert resp.status_code == 401

    def test_generate_title_limits_messages(self, client):
        """Only first 10 messages should be sent to LLM."""
        data = {
            "session_id": "sess-1",
            "messages": [{"text": f"Message {i}", "sender": "human"} for i in range(20)],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content='Long Chat')
            with patch('routers.chat.chat_db.update_chat_session'):
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        prompt = mock_llm.invoke.call_args[0][0]
        assert 'Message 9' in prompt
        assert 'Message 10' not in prompt

    def test_generate_title_fallback_truncates_to_50_chars(self, client):
        """When LLM fails, fallback title is truncated to 50 chars."""
        long_text = 'A' * 100
        data = {
            "session_id": "sess-1",
            "messages": [{"text": long_text, "sender": "human"}],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.side_effect = Exception("LLM down")
            with patch('routers.chat.chat_db.update_chat_session'):
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.json()["title"]) == 50

    def test_generate_title_truncates_message_text_to_500_chars(self, client):
        """Each message text is truncated to 500 chars in the transcript sent to LLM."""
        long_text = 'B' * 1000
        data = {
            "session_id": "sess-1",
            "messages": [{"text": long_text, "sender": "human"}],
        }
        with patch('routers.chat.llm_mini') as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content='Title')
            with patch('routers.chat.chat_db.update_chat_session'):
                resp = client.post("/v2/chat/generate-title", json=data, headers=AUTH)
        assert resp.status_code == 200
        prompt = mock_llm.invoke.call_args[0][0]
        # The transcript line should contain exactly 500 B's, not 1000
        assert 'B' * 500 in prompt
        assert 'B' * 501 not in prompt
