"""Unit tests for soft-deleted action-item tombstone guards in routers/action_items.py.

Verifies that first-party action-item endpoints reject soft-deleted tombstones (`deleted=True`):
- `_get_valid_action_item` (used by GET/PATCH/DELETE /v1/action-items/{id} and PATCH /v1/action-items/{id}/completed)
- `sync_batch_update` (PATCH /v1/action-items/sync-batch)
- `share_action_items`, `get_shared_action_items`, and `accept_shared_action_items`
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from database import action_items as action_items_db
from database import redis_db
from routers import action_items as action_items_router


def _make_item(item_id: str = 'task-1', deleted: bool = False, locked: bool = False) -> dict:
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return {
        'id': item_id,
        'description': f'Description for {item_id}',
        'completed': False,
        'deleted': deleted,
        'is_locked': locked,
        'created_at': now,
        'updated_at': now,
        'due_at': None,
        'completed_at': None,
        'conversation_id': None,
    }


class TestFirstPartyActionItemsTombstoneGuard:
    """First-party action_items router must reject soft-deleted tombstones."""

    def test_get_valid_action_item_rejects_deleted_tombstone(self, monkeypatch):
        """_get_valid_action_item raises 404 when deleted=True."""
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_item(item_id=item_id, deleted=True),
        )
        with pytest.raises(HTTPException) as exc_info:
            action_items_router._get_valid_action_item('uid-1', 'task-1')
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Action item not found'

    def test_get_valid_action_item_returns_active_item(self, monkeypatch):
        """_get_valid_action_item returns an active, unlocked item."""
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_item(item_id=item_id, deleted=False),
        )
        item = action_items_router._get_valid_action_item('uid-1', 'task-1')
        assert item['id'] == 'task-1'

    def test_delete_action_item_does_not_redelete_tombstone(self, monkeypatch):
        """DELETE /v1/action-items/{id} raises 404 on a soft-deleted tombstone without calling delete_action_item."""
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_item(item_id=item_id, deleted=True),
        )
        mock_delete = MagicMock()
        monkeypatch.setattr(action_items_db, 'delete_action_item', mock_delete)

        with pytest.raises(HTTPException) as exc_info:
            action_items_router.delete_action_item(action_item_id='task-1', uid='uid-1')
        assert exc_info.value.status_code == 404
        mock_delete.assert_not_called()

    def test_sync_batch_update_skips_deleted_tombstones(self, monkeypatch):
        """PATCH /v1/action-items/sync-batch skips soft-deleted tombstones."""
        items_by_id = {
            'deleted-task': _make_item('deleted-task', deleted=True),
            'active-task': _make_item('active-task', deleted=False),
        }
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: items_by_id.get(item_id),
        )
        captured_updates = []

        def fake_batch_sync(uid, updates):
            captured_updates.extend(updates)
            return SimpleNamespace(updated_count=len(updates), updated_ids=[u['id'] for u in updates])

        monkeypatch.setattr(action_items_db, 'batch_sync_update_action_items', fake_batch_sync)
        monkeypatch.setattr(action_items_router, 'upsert_action_item_vectors_batch', MagicMock())
        monkeypatch.setattr(action_items_router, 'sync_action_item_reminder', MagicMock())
        monkeypatch.setattr(
            action_items_router,
            '_batch_mutation_response',
            lambda res, *, locked_ids=None: {'updated_count': res.updated_count},
        )

        req = action_items_router.SyncBatchRequest(
            items=[
                action_items_router.SyncBatchItem(id='deleted-task', description='Hijacked'),
                action_items_router.SyncBatchItem(id='active-task', description='Valid update'),
            ]
        )
        res = action_items_router.sync_batch_update(request=req, uid='uid-1')
        assert res == {'updated_count': 1}
        assert len(captured_updates) == 1
        assert captured_updates[0]['id'] == 'active-task'

    def test_share_action_items_rejects_deleted_tombstone(self, monkeypatch):
        """POST /v1/action-items/share raises 404 when any requested task is soft-deleted."""
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_item(item_id=item_id, deleted=True),
        )
        req = action_items_router.ShareTasksRequest(task_ids=['task-1'])
        with pytest.raises(HTTPException) as exc_info:
            action_items_router.share_action_items(request=req, uid='uid-1')
        assert exc_info.value.status_code == 404

    def test_get_and_accept_shared_action_items_skip_deleted_tombstones(self, monkeypatch):
        """Shared preview and accept endpoints exclude soft-deleted tombstones."""
        monkeypatch.setattr(
            redis_db,
            'get_task_share',
            lambda token: {'uid': 'sender-1', 'display_name': 'Alice', 'task_ids': ['deleted-1']},
        )
        monkeypatch.setattr(
            action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_item(item_id=item_id, deleted=True),
        )

        preview = action_items_router.get_shared_action_items('tok-1')
        assert preview['tasks'] == []
        assert preview['count'] == 0

        accept_req = action_items_router.AcceptSharedTasksRequest(token='tok-1')
        with pytest.raises(HTTPException) as exc_info:
            action_items_router.accept_shared_action_items(request=accept_req, uid='recipient-1')
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Shared tasks were deleted or not found'
