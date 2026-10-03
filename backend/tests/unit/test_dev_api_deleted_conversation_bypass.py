"""Tests for Developer API soft-deleted conversation access guard.

Verifies that soft-deleted conversations (deleted=True / is_soft_deleted)
are properly guarded and return 404 Not Found in Developer API endpoints:
- GET /v1/dev/user/conversations/{conversation_id}
- PATCH /v1/dev/user/conversations/{conversation_id}
- DELETE /v1/dev/user/conversations/{conversation_id}
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import conversations as conversations_db
from routers import developer as dev_routes
from routers.developer import UpdateConversationRequest


def _make_conversation(deleted: bool = False, locked: bool = False, conversation_id: str = 'conv-1') -> dict:
    return {
        'id': conversation_id,
        'deleted': deleted,
        'is_locked': locked,
        'structured': {
            'title': 'Test Conversation',
            'overview': 'Test overview',
            'action_items': [],
            'events': [],
            'category': 'personal',
        },
        'transcript_segments': [],
        'started_at': '2024-01-01T00:00:00',
        'finished_at': '2024-01-01T01:00:00',
        'created_at': 1704067200,
        'discarded': False,
        'visibility': 'private',
        'geolocation': None,
        'language': 'en',
        'status': 'completed',
        'source': 'friend',
    }


class TestDevApiDeletedConversationGuard:
    """Developer API conversation GET/PATCH/DELETE must reject soft-deleted records with 404."""

    def test_get_conversation_rejects_deleted(self, monkeypatch):
        """GET /v1/dev/user/conversations/{id} must raise 404 when deleted=True."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=True, conversation_id=conv_id),
        )

        auth_mock = MagicMock()
        auth_mock.uid = 'test-uid'
        auth_mock.key_id = 'test-key'
        auth_mock.app_id = 'test-app'

        with pytest.raises(HTTPException) as exc_info:
            dev_routes.get_conversation_endpoint(
                conversation_id='conv-1',
                include_transcript=False,
                uid=auth_mock,
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_get_conversation_allows_active(self, monkeypatch):
        """GET /v1/dev/user/conversations/{id} returns active conversation."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, conversation_id=conv_id),
        )
        monkeypatch.setattr(dev_routes, 'populate_folder_names', lambda uid, convs: None)

        auth_mock = MagicMock()
        auth_mock.uid = 'test-uid'
        auth_mock.key_id = 'test-key'
        auth_mock.app_id = 'test-app'

        res = dev_routes.get_conversation_endpoint(
            conversation_id='conv-1',
            include_transcript=False,
            uid=auth_mock,
        )
        assert res['id'] == 'conv-1'
        assert res.get('deleted') is False

    def test_delete_conversation_rejects_deleted(self, monkeypatch):
        """DELETE /v1/dev/user/conversations/{id} must raise 404 when deleted=True."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=True, conversation_id=conv_id),
        )

        with pytest.raises(HTTPException) as exc_info:
            dev_routes.delete_conversation_endpoint(conversation_id='conv-1', uid='test-uid')
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_delete_conversation_allows_active(self, monkeypatch):
        """DELETE /v1/dev/user/conversations/{id} deletes active conversation."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, conversation_id=conv_id),
        )

        mock_delete_sources = MagicMock()
        monkeypatch.setattr(
            'utils.conversations.merge_conversations.delete_conversation_with_sync_sources', mock_delete_sources
        )

        result = dev_routes.delete_conversation_endpoint(conversation_id='conv-1', uid='test-uid')
        assert result == {"success": True}
        mock_delete_sources.assert_called_once_with('test-uid', 'conv-1')

    def test_patch_conversation_rejects_deleted(self, monkeypatch):
        """PATCH /v1/dev/user/conversations/{id} must raise 404 when deleted=True."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=True, conversation_id=conv_id),
        )

        request = UpdateConversationRequest(title='New Title')
        with pytest.raises(HTTPException) as exc_info:
            dev_routes.update_conversation_endpoint(conversation_id='conv-1', request=request, uid='test-uid')
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_patch_conversation_allows_active(self, monkeypatch):
        """PATCH /v1/dev/user/conversations/{id} updates title for active conversation."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, conversation_id=conv_id),
        )
        mock_update_title = MagicMock()
        monkeypatch.setattr(conversations_db, 'update_conversation_title', mock_update_title)
        monkeypatch.setattr(dev_routes, 'populate_folder_names', lambda uid, convs: None)

        request = UpdateConversationRequest(title='New Title')
        result = dev_routes.update_conversation_endpoint(conversation_id='conv-1', request=request, uid='test-uid')
        mock_update_title.assert_called_once_with('test-uid', 'conv-1', 'New Title')
        assert result['id'] == 'conv-1'
