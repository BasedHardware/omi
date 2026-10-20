"""Tests for action items router soft-deleted conversation access guard.

Verifies that soft-deleted conversations (deleted=True / tombstone)
are properly guarded and return 404 Not Found in conversation action items endpoints:
- GET /v1/conversations/{conversation_id}/action-items
- GET /v1/conversations/{conversation_id}/action-items/count
- DELETE /v1/conversations/{conversation_id}/action-items
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import conversations as conversations_db
from database import action_items as action_items_db
from routers import action_items as action_items_routes


def _make_conversation(deleted: bool = False, locked: bool = False, conversation_id: str = 'conv-1') -> dict:
    return {
        'id': conversation_id,
        'deleted': deleted,
        'is_locked': locked,
        'structured': {
            'title': 'Test Conversation',
            'action_items': [],
        },
        'transcript_segments': [],
        'started_at': '2024-01-01T00:00:00',
        'finished_at': '2024-01-01T01:00:00',
        'created_at': 1704067200,
        'discarded': False,
    }


def _make_action_item(item_id: str = 'ai-1', conv_id: str = 'conv-1') -> dict:
    return {
        'id': item_id,
        'uid': 'user-1',
        'conversation_id': conv_id,
        'description': 'Test action item',
        'completed': False,
        'created_at': '2024-01-01T00:00:00Z',
        'updated_at': '2024-01-01T00:00:00Z',
    }


class TestGetConversationActionItems:
    """GET /v1/conversations/{conversation_id}/action-items access guard tests."""

    def test_get_conversation_action_items_rejects_deleted(self, monkeypatch):
        """GET action-items must return 404 when conversation is soft-deleted."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=True, conversation_id=conv_id),
        )
        get_items_mock = MagicMock(return_value=[_make_action_item()])
        monkeypatch.setattr(action_items_db, 'get_action_items_by_conversation', get_items_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.get_conversation_action_items('conv-deleted', uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'
        get_items_mock.assert_not_called()

    def test_get_conversation_action_items_rejects_locked(self, monkeypatch):
        """GET action-items must return 402 when conversation is locked."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, locked=True, conversation_id=conv_id),
        )
        get_items_mock = MagicMock(return_value=[_make_action_item()])
        monkeypatch.setattr(action_items_db, 'get_action_items_by_conversation', get_items_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.get_conversation_action_items('conv-locked', uid='user-1')

        assert exc_info.value.status_code == 402
        assert 'paid plan is required' in exc_info.value.detail
        get_items_mock.assert_not_called()

    def test_get_conversation_action_items_rejects_nonexistent(self, monkeypatch):
        """GET action-items must return 404 when conversation does not exist."""
        monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, conv_id, **kwargs: None)
        get_items_mock = MagicMock(return_value=[_make_action_item()])
        monkeypatch.setattr(action_items_db, 'get_action_items_by_conversation', get_items_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.get_conversation_action_items('conv-none', uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'
        get_items_mock.assert_not_called()

    def test_get_conversation_action_items_allows_valid(self, monkeypatch):
        """GET action-items succeeds on a valid active conversation."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, locked=False, conversation_id=conv_id),
        )
        item = _make_action_item(item_id='ai-1', conv_id='conv-valid')
        monkeypatch.setattr(action_items_db, 'get_action_items_by_conversation', lambda uid, conv_id: [item])

        res = action_items_routes.get_conversation_action_items('conv-valid', uid='user-1')

        assert res['conversation_id'] == 'conv-valid'
        assert len(res['action_items']) == 1
        assert res['action_items'][0].description == 'Test action item'


class TestGetConversationActionItemsCount:
    """GET /v1/conversations/{conversation_id}/action-items/count access guard tests."""

    def test_get_conversation_action_items_count_rejects_deleted(self, monkeypatch):
        """GET count must return 404 when conversation is soft-deleted."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=True, conversation_id=conv_id),
        )
        count_mock = MagicMock(return_value={'total': 2, 'completed': 1, 'incomplete': 1})
        monkeypatch.setattr(action_items_db, 'get_action_items_count_by_conversation', count_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.get_conversation_action_items_count('conv-deleted', uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'
        count_mock.assert_not_called()

    def test_get_conversation_action_items_count_rejects_locked(self, monkeypatch):
        """GET count must return 402 when conversation is locked."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, locked=True, conversation_id=conv_id),
        )
        count_mock = MagicMock(return_value={'total': 2, 'completed': 1, 'incomplete': 1})
        monkeypatch.setattr(action_items_db, 'get_action_items_count_by_conversation', count_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.get_conversation_action_items_count('conv-locked', uid='user-1')

        assert exc_info.value.status_code == 402
        assert 'paid plan is required' in exc_info.value.detail
        count_mock.assert_not_called()

    def test_get_conversation_action_items_count_rejects_nonexistent(self, monkeypatch):
        """GET count must return 404 when conversation does not exist."""
        monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, conv_id, **kwargs: None)
        count_mock = MagicMock(return_value={'total': 2, 'completed': 1, 'incomplete': 1})
        monkeypatch.setattr(action_items_db, 'get_action_items_count_by_conversation', count_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.get_conversation_action_items_count('conv-none', uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'
        count_mock.assert_not_called()

    def test_get_conversation_action_items_count_allows_valid(self, monkeypatch):
        """GET count returns counts on a valid active conversation."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, locked=False, conversation_id=conv_id),
        )
        monkeypatch.setattr(
            action_items_db,
            'get_action_items_count_by_conversation',
            lambda uid, conv_id: {'total': 3, 'completed': 1, 'incomplete': 2},
        )

        res = action_items_routes.get_conversation_action_items_count('conv-valid', uid='user-1')

        assert res['total'] == 3
        assert res['completed'] == 1
        assert res['incomplete'] == 2


class TestDeleteConversationActionItems:
    """DELETE /v1/conversations/{conversation_id}/action-items access guard tests."""

    def test_delete_conversation_action_items_rejects_deleted(self, monkeypatch):
        """DELETE action-items must return 404 when conversation is soft-deleted."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=True, conversation_id=conv_id),
        )
        del_mock = MagicMock(return_value=1)
        monkeypatch.setattr(action_items_db, 'delete_action_items_for_conversation', del_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.delete_conversation_action_items('conv-deleted', uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'
        del_mock.assert_not_called()

    def test_delete_conversation_action_items_rejects_locked(self, monkeypatch):
        """DELETE action-items must return 402 when conversation is locked."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, locked=True, conversation_id=conv_id),
        )
        del_mock = MagicMock(return_value=1)
        monkeypatch.setattr(action_items_db, 'delete_action_items_for_conversation', del_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.delete_conversation_action_items('conv-locked', uid='user-1')

        assert exc_info.value.status_code == 402
        assert 'paid plan is required' in exc_info.value.detail
        del_mock.assert_not_called()

    def test_delete_conversation_action_items_rejects_nonexistent(self, monkeypatch):
        """DELETE action-items must return 404 when conversation does not exist."""
        monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, conv_id, **kwargs: None)
        del_mock = MagicMock(return_value=1)
        monkeypatch.setattr(action_items_db, 'delete_action_items_for_conversation', del_mock)

        with pytest.raises(HTTPException) as exc_info:
            action_items_routes.delete_conversation_action_items('conv-none', uid='user-1')

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'
        del_mock.assert_not_called()

    def test_delete_conversation_action_items_allows_valid(self, monkeypatch):
        """DELETE action-items deletes items on a valid active conversation."""
        monkeypatch.setattr(
            action_items_routes.conversations_db,
            'get_conversation',
            lambda uid, conv_id, **kwargs: _make_conversation(deleted=False, locked=False, conversation_id=conv_id),
        )
        item = _make_action_item(item_id='ai-1', conv_id='conv-valid')
        monkeypatch.setattr(action_items_db, 'get_action_items_by_conversation', lambda uid, conv_id: [item])
        del_mock = MagicMock(return_value=1)
        monkeypatch.setattr(action_items_db, 'delete_action_items_for_conversation', del_mock)
        vec_mock = MagicMock(return_value=None)
        monkeypatch.setattr(action_items_routes, 'delete_action_item_vectors_batch', vec_mock)

        res = action_items_routes.delete_conversation_action_items('conv-valid', uid='user-1')

        assert res['status'] == 'Ok'
        assert res['deleted_count'] == 1
        del_mock.assert_called_once_with('user-1', 'conv-valid')
        vec_mock.assert_called_once_with('user-1', ['ai-1'])
