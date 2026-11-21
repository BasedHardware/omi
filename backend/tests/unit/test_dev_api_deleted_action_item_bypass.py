"""Tests for Developer API soft-deleted action item access guard.

Verifies that soft-deleted action item tombstones (`deleted=True`)
are rejected with 404 Not Found in Developer API mutation endpoints:
- DELETE /v1/dev/user/action-items/{action_item_id}
- PATCH /v1/dev/user/action-items/{action_item_id}
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from database import action_items as action_items_db
from routers import developer as dev_routes
from routers.developer import UpdateActionItemRequest


def _make_action_item(deleted: bool = False, locked: bool = False, item_id: str = 'task-1') -> dict:
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return {
        'id': item_id,
        'description': 'Test action item',
        'completed': False,
        'deleted': deleted,
        'is_locked': locked,
        'created_at': now,
        'updated_at': now,
        'due_at': None,
        'completed_at': None,
        'conversation_id': None,
    }


class TestDevApiDeletedActionItemGuard:
    """Developer API action-item PATCH/DELETE must reject soft-deleted tombstones with 404."""

    def test_delete_action_item_rejects_deleted_tombstone(self, monkeypatch):
        """DELETE /v1/dev/user/action-items/{id} must raise 404 when deleted=True."""
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_action_item(deleted=True, item_id=item_id),
        )
        mock_delete = MagicMock()
        monkeypatch.setattr(action_items_db, 'delete_action_item', mock_delete)

        with pytest.raises(HTTPException) as exc_info:
            dev_routes.delete_action_item(action_item_id='task-1', uid='test-uid')
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Action item not found'
        mock_delete.assert_not_called()

    def test_delete_action_item_allows_active(self, monkeypatch):
        """DELETE /v1/dev/user/action-items/{id} deletes an active action item."""
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_action_item(deleted=False, item_id=item_id),
        )
        mock_delete = MagicMock()
        monkeypatch.setattr(action_items_db, 'delete_action_item', mock_delete)
        mock_sync_reminder = MagicMock()
        monkeypatch.setattr(dev_routes, 'sync_action_item_reminder', mock_sync_reminder)

        res = dev_routes.delete_action_item(action_item_id='task-1', uid='test-uid')
        assert res == {'success': True}
        mock_delete.assert_called_once_with('test-uid', 'task-1')

    def test_patch_action_item_rejects_deleted_tombstone(self, monkeypatch):
        """PATCH /v1/dev/user/action-items/{id} must raise 404 when deleted=True."""
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_action_item(deleted=True, item_id=item_id),
        )
        mock_update = MagicMock()
        monkeypatch.setattr(action_items_db, 'update_action_item', mock_update)

        request = UpdateActionItemRequest(description='Updated description')
        with pytest.raises(HTTPException) as exc_info:
            dev_routes.update_action_item(action_item_id='task-1', request=request, uid='test-uid')
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Action item not found'
        mock_update.assert_not_called()

    def test_patch_action_item_allows_active(self, monkeypatch):
        """PATCH /v1/dev/user/action-items/{id} updates an active action item."""
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_action_item(deleted=False, item_id=item_id),
        )
        mock_update = MagicMock(return_value=True)
        monkeypatch.setattr(action_items_db, 'update_action_item', mock_update)
        monkeypatch.setattr(dev_routes, 'sync_action_item_reminder', MagicMock())

        request = UpdateActionItemRequest(description='Updated description')
        res = dev_routes.update_action_item(action_item_id='task-1', request=request, uid='test-uid')
        mock_update.assert_called_once_with('test-uid', 'task-1', {'description': 'Updated description'})
        assert res['id'] == 'task-1'
