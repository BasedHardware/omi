"""Tests for folders router soft-deleted conversation access guard.

Verifies that soft-deleted conversations (deleted=True / tombstone)
are properly guarded and return 404 Not Found in folder conversation endpoints:
- PATCH /v1/conversations/{conversation_id}/folder
- POST /v1/folders/{folder_id}/conversations/bulk-move
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import conversations as conversations_db
from database import folders as folders_db
from models.folder import MoveConversationRequest, BulkMoveConversationsRequest
from routers import folders as folders_routes


def _make_conversation(deleted: bool = False, locked: bool = False, conversation_id: str = 'conv-1') -> dict:
    return {
        'id': conversation_id,
        'deleted': deleted,
        'is_locked': locked,
        'folder_id': 'f-old',
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
    }


class TestFolderConversationTombstoneGuard:
    """Folders conversation move and bulk-move endpoints must reject soft-deleted conversations with 404."""

    def test_move_conversation_to_folder_rejects_deleted(self, monkeypatch):
        """PATCH /v1/conversations/{id}/folder must return 404 when conversation is soft-deleted."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=True, conversation_id=conv_id),
        )
        monkeypatch.setattr(folders_db, 'get_folder', lambda uid, folder_id: {'id': folder_id, 'name': 'Target'})
        move_mock = MagicMock(return_value=True)
        monkeypatch.setattr(folders_db, 'move_conversation_to_folder', move_mock)

        req = MoveConversationRequest(folder_id='f-target')
        with pytest.raises(HTTPException) as exc_info:
            folders_routes.move_conversation_to_folder('conv-deleted', req, uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'
        move_mock.assert_not_called()

    def test_move_conversation_to_folder_rejects_locked(self, monkeypatch):
        """PATCH /v1/conversations/{id}/folder must return 402 when conversation is locked."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, locked=True, conversation_id=conv_id),
        )
        monkeypatch.setattr(folders_db, 'get_folder', lambda uid, folder_id: {'id': folder_id, 'name': 'Target'})
        move_mock = MagicMock(return_value=True)
        monkeypatch.setattr(folders_db, 'move_conversation_to_folder', move_mock)

        req = MoveConversationRequest(folder_id='f-target')
        with pytest.raises(HTTPException) as exc_info:
            folders_routes.move_conversation_to_folder('conv-locked', req, uid='user-1')

        assert exc_info.value.status_code == 402
        assert 'paid plan is required' in exc_info.value.detail
        move_mock.assert_not_called()

    def test_move_conversation_to_folder_rejects_nonexistent(self, monkeypatch):
        """PATCH /v1/conversations/{id}/folder must return 404 when conversation does not exist."""
        monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, conv_id, **kwargs: None)
        move_mock = MagicMock(return_value=True)
        monkeypatch.setattr(folders_db, 'move_conversation_to_folder', move_mock)

        req = MoveConversationRequest(folder_id='f-target')
        with pytest.raises(HTTPException) as exc_info:
            folders_routes.move_conversation_to_folder('conv-none', req, uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'
        move_mock.assert_not_called()

    def test_move_conversation_to_folder_allows_valid(self, monkeypatch):
        """PATCH /v1/conversations/{id}/folder moves valid conversation successfully."""
        conv_record = _make_conversation(deleted=False, locked=False, conversation_id='conv-valid')
        monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, conv_id, **kwargs: conv_record)
        monkeypatch.setattr(folders_db, 'get_folder', lambda uid, folder_id: {'id': folder_id, 'name': 'Target'})
        move_mock = MagicMock(return_value=True)
        monkeypatch.setattr(folders_db, 'move_conversation_to_folder', move_mock)

        req = MoveConversationRequest(folder_id='f-target')
        res = folders_routes.move_conversation_to_folder('conv-valid', req, uid='user-1')

        assert res['status'] == 'ok'
        assert res['conversation']['id'] == 'conv-valid'
        move_mock.assert_called_once_with('user-1', 'conv-valid', 'f-target')

    def test_bulk_move_conversations_rejects_deleted(self, monkeypatch):
        """POST /v1/folders/{id}/conversations/bulk-move must return 404 when a conversation is soft-deleted."""
        def fake_get_conv(uid, conv_id):
            if conv_id == 'conv-deleted':
                return _make_conversation(deleted=True, conversation_id=conv_id)
            return _make_conversation(deleted=False, conversation_id=conv_id)

        monkeypatch.setattr(conversations_db, 'get_conversation', fake_get_conv)
        monkeypatch.setattr(folders_db, 'get_folder', lambda uid, folder_id: {'id': folder_id, 'name': 'Target'})
        bulk_mock = MagicMock(return_value=2)
        monkeypatch.setattr(folders_db, 'bulk_move_conversations_to_folder', bulk_mock)

        req = BulkMoveConversationsRequest(conversation_ids=['conv-valid', 'conv-deleted'])
        with pytest.raises(HTTPException) as exc_info:
            folders_routes.bulk_move_conversations('f-target', req, uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation conv-deleted not found'
        bulk_mock.assert_not_called()

    def test_bulk_move_conversations_rejects_locked(self, monkeypatch):
        """POST /v1/folders/{id}/conversations/bulk-move must return 402 when a conversation is locked."""
        def fake_get_conv(uid, conv_id):
            if conv_id == 'conv-locked':
                return _make_conversation(deleted=False, locked=True, conversation_id=conv_id)
            return _make_conversation(deleted=False, conversation_id=conv_id)

        monkeypatch.setattr(conversations_db, 'get_conversation', fake_get_conv)
        monkeypatch.setattr(folders_db, 'get_folder', lambda uid, folder_id: {'id': folder_id, 'name': 'Target'})
        bulk_mock = MagicMock(return_value=2)
        monkeypatch.setattr(folders_db, 'bulk_move_conversations_to_folder', bulk_mock)

        req = BulkMoveConversationsRequest(conversation_ids=['conv-valid', 'conv-locked'])
        with pytest.raises(HTTPException) as exc_info:
            folders_routes.bulk_move_conversations('f-target', req, uid='user-1')

        assert exc_info.value.status_code == 402
        assert 'paid plan is required' in exc_info.value.detail
        bulk_mock.assert_not_called()

    def test_bulk_move_conversations_rejects_nonexistent(self, monkeypatch):
        """POST /v1/folders/{id}/conversations/bulk-move must return 404 when a conversation does not exist."""
        def fake_get_conv(uid, conv_id):
            if conv_id == 'conv-none':
                return None
            return _make_conversation(deleted=False, conversation_id=conv_id)

        monkeypatch.setattr(conversations_db, 'get_conversation', fake_get_conv)
        monkeypatch.setattr(folders_db, 'get_folder', lambda uid, folder_id: {'id': folder_id, 'name': 'Target'})
        bulk_mock = MagicMock(return_value=2)
        monkeypatch.setattr(folders_db, 'bulk_move_conversations_to_folder', bulk_mock)

        req = BulkMoveConversationsRequest(conversation_ids=['conv-valid', 'conv-none'])
        with pytest.raises(HTTPException) as exc_info:
            folders_routes.bulk_move_conversations('f-target', req, uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation conv-none not found'
        bulk_mock.assert_not_called()

    def test_bulk_move_conversations_allows_valid(self, monkeypatch):
        """POST /v1/folders/{id}/conversations/bulk-move moves valid conversations successfully."""
        monkeypatch.setattr(
            conversations_db,
            'get_conversation',
            lambda uid, conv_id: _make_conversation(deleted=False, conversation_id=conv_id),
        )
        monkeypatch.setattr(folders_db, 'get_folder', lambda uid, folder_id: {'id': folder_id, 'name': 'Target'})
        bulk_mock = MagicMock(return_value=2)
        monkeypatch.setattr(folders_db, 'bulk_move_conversations_to_folder', bulk_mock)

        req = BulkMoveConversationsRequest(conversation_ids=['conv-1', 'conv-2'])
        res = folders_routes.bulk_move_conversations('f-target', req, uid='user-1')

        assert res['status'] == 'ok'
        assert res['moved_count'] == 2
        bulk_mock.assert_called_once_with('user-1', ['conv-1', 'conv-2'], 'f-target')
