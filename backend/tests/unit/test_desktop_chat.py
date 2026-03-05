"""Tests for desktop chat sessions CRUD + message rating endpoints."""
import sys
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

for mod_name in [
    'firebase_admin', 'firebase_admin.auth', 'firebase_admin.firestore', 'firebase_admin.messaging',
    'google.cloud', 'google.cloud.exceptions', 'google.cloud.firestore', 'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query', 'google.cloud.firestore_v1.query',
    'google.cloud.storage', 'google.cloud.storage.blob', 'google.cloud.storage.bucket',
    'google.auth', 'google.auth.transport', 'google.auth.transport.requests',
    'google.oauth2', 'google.oauth2.service_account',
    'pinecone', 'typesense',
]:
    sys.modules.setdefault(mod_name, MagicMock())

from routers.desktop_chat import (
    CreateChatSessionRequest,
    UpdateChatSessionRequest,
    ChatSessionResponse,
    SaveMessageRequest,
    SaveMessageResponse,
    RateMessageRequest,
    StatusResponse,
    router,
)


class TestChatSessionModels:
    def test_create_request_defaults(self):
        req = CreateChatSessionRequest()
        assert req.title is None
        assert req.app_id is None

    def test_update_request_partial(self):
        req = UpdateChatSessionRequest(title="New Title")
        assert req.title == "New Title"
        assert req.starred is None

    def test_session_response(self):
        now = datetime.now(timezone.utc)
        resp = ChatSessionResponse(id="s1", title="Test", created_at=now, updated_at=now)
        assert resp.message_count == 0
        assert resp.starred is False

    def test_save_message_request(self):
        req = SaveMessageRequest(text="Hello", sender="human")
        assert req.app_id is None
        assert req.session_id is None

    def test_rate_request(self):
        req = RateMessageRequest(rating=1)
        assert req.rating == 1
        req2 = RateMessageRequest()
        assert req2.rating is None


class TestChatSessionEndpoints:
    def _make_app(self):
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        return TestClient(self._make_app())

    def test_create_session(self, client):
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.add_chat_session') as mock_add,
        ):
            mock_add.side_effect = lambda uid, data: data
            response = client.post(
                '/v2/chat-sessions',
                json={'title': 'My Chat', 'app_id': None},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            data = response.json()
            assert data['title'] == 'My Chat'
            assert data['message_count'] == 0
            assert data['starred'] is False
            assert 'id' in data

    def test_create_session_default_title(self, client):
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.add_chat_session') as mock_add,
        ):
            mock_add.side_effect = lambda uid, data: data
            response = client.post(
                '/v2/chat-sessions',
                json={},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            assert response.json()['title'] == 'New Chat'

    def test_list_sessions(self, client):
        now = datetime.now(timezone.utc)
        mock_sessions = [
            {'id': 's1', 'title': 'Chat 1', 'created_at': now, 'updated_at': now, 'message_count': 5, 'starred': False},
            {'id': 's2', 'title': 'Chat 2', 'created_at': now, 'updated_at': now, 'message_count': 3, 'starred': True},
        ]
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.get_chat_sessions', return_value=mock_sessions),
        ):
            response = client.get('/v2/chat-sessions', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]['title'] == 'Chat 1'

    def test_get_session(self, client):
        now = datetime.now(timezone.utc)
        mock_session = {'id': 's1', 'title': 'Chat', 'created_at': now, 'updated_at': now, 'message_count': 0, 'starred': False}
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.get_chat_session_by_id', return_value=mock_session),
        ):
            response = client.get('/v2/chat-sessions/s1', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['id'] == 's1'

    def test_get_session_not_found(self, client):
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.get_chat_session_by_id', return_value=None),
        ):
            response = client.get('/v2/chat-sessions/missing', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 404

    def test_update_session(self, client):
        now = datetime.now(timezone.utc)
        mock_session = {'id': 's1', 'title': 'Old', 'created_at': now, 'updated_at': now}
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.get_chat_session_by_id', return_value=mock_session),
            patch('routers.desktop_chat.chat_db.update_chat_session') as mock_update,
        ):
            response = client.patch(
                '/v2/chat-sessions/s1',
                json={'title': 'Renamed', 'starred': True},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            call_data = mock_update.call_args[0][2]
            assert call_data['title'] == 'Renamed'
            assert call_data['starred'] is True

    def test_delete_session(self, client):
        now = datetime.now(timezone.utc)
        mock_session = {'id': 's1', 'title': 'Del', 'created_at': now, 'updated_at': now}
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.get_chat_session_by_id', return_value=mock_session),
            patch('routers.desktop_chat.chat_db.delete_chat_session') as mock_del,
        ):
            response = client.delete('/v2/chat-sessions/s1', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert mock_del.called
            assert mock_del.call_args[0][1] == 's1'


class TestDesktopMessageEndpoints:
    def _make_app(self):
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        return TestClient(self._make_app())

    def test_save_message(self, client):
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.save_message') as mock_save,
            patch('routers.desktop_chat.chat_db.add_message_to_chat_session'),
        ):
            mock_save.side_effect = lambda uid, data: data
            response = client.post(
                '/v2/desktop/messages',
                json={'text': 'Hello', 'sender': 'human', 'session_id': 's1'},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            data = response.json()
            assert 'id' in data
            assert 'created_at' in data

    def test_save_message_empty_text_422(self, client):
        with patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'):
            response = client.post(
                '/v2/desktop/messages',
                json={'text': '   ', 'sender': 'human'},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 422

    def test_save_message_invalid_sender_422(self, client):
        with patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'):
            response = client.post(
                '/v2/desktop/messages',
                json={'text': 'Hello', 'sender': 'bot'},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 422

    def test_rate_message_thumbs_up(self, client):
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.update_message_rating') as mock_rate,
        ):
            response = client.patch(
                '/v2/messages/msg-1/rating',
                json={'rating': 1},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            assert mock_rate.called
            assert mock_rate.call_args[0][1] == 'msg-1'
            assert mock_rate.call_args[0][2] == 1

    def test_rate_message_clear(self, client):
        with (
            patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.desktop_chat.chat_db.update_message_rating') as mock_rate,
        ):
            response = client.patch(
                '/v2/messages/msg-1/rating',
                json={'rating': None},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            assert mock_rate.called
            assert mock_rate.call_args[0][1] == 'msg-1'
            assert mock_rate.call_args[0][2] is None

    def test_rate_message_invalid_value_422(self, client):
        with patch('routers.desktop_chat.auth.get_current_user_uid', return_value='uid-1'):
            response = client.patch(
                '/v2/messages/msg-1/rating',
                json={'rating': 5},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 422
