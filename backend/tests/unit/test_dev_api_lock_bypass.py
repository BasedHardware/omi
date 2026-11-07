"""Tests for Developer API and Knowledge Graph locked data bypass fixes (#6146).

Verifies that is_locked conversations/memories/action_items are properly guarded
in the Developer API write endpoints and knowledge graph rebuild.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from tests.unit.dev_api_test_support import isolated_developer_api

developer_module = None


@pytest.fixture(autouse=True)
def _isolated_developer_router(monkeypatch):
    global developer_module
    with isolated_developer_api(monkeypatch) as api:
        developer_module = api.developer
        yield


@pytest.fixture(autouse=True)
def _authorized_memory_developer_for_lock_tests(monkeypatch, _isolated_developer_router):
    monkeypatch.setattr(
        developer_module,
        'authorize_memory_external_default_memory_write',
        MagicMock(return_value=SimpleNamespace(allowed=True, status_code=200, observability={'reason': 'test'})),
        raising=False,
    )


def _make_conversation(locked=False, conversation_id='conv-1'):
    return {
        'id': conversation_id,
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


def _make_memory(locked=False, memory_id='mem-1'):
    return {
        'id': memory_id,
        'uid': 'test-uid',
        'is_locked': locked,
        'content': 'Secret memory content',
        'category': 'interesting',
        'created_at': '2024-01-01T00:00:00',
        'updated_at': '2024-01-01T00:00:00',
        'visibility': 'private',
        'tags': [],
        'manually_added': False,
        'scoring': 'none',
        'reviewed': False,
        'user_review': None,
        'edited': False,
    }


def _make_action_item(locked=False, action_item_id='ai-1'):
    return {
        'id': action_item_id,
        'is_locked': locked,
        'description': 'Secret action item',
        'completed': False,
        'created_at': '2024-01-01T00:00:00',
        'updated_at': '2024-01-01T00:00:00',
        'due_at': None,
        'completed_at': None,
        'conversation_id': None,
    }


# =============================================================================
# Developer API — Conversation write endpoints
# =============================================================================


class TestDevApiConversationLockEnforcement:
    """D1-D2: Dev API conversation PATCH/DELETE must return 402 for locked."""

    def test_patch_conversation_rejects_locked(self):
        """D1: PATCH /v1/dev/user/conversations/{id} must raise 402 for locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.developer import update_conversation_endpoint, UpdateConversationRequest
        from fastapi import HTTPException

        request = UpdateConversationRequest(title='New Title')
        with pytest.raises(HTTPException) as exc_info:
            update_conversation_endpoint(conversation_id='conv-1', request=request, uid='test-uid')
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_patch_conversation_allows_unlocked(self):
        """D1: PATCH delegates title mutation to the lifecycle-owned atomic writer."""
        import database.conversations as conversations_db
        from routers import developer as dev_routes

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=False))
        with patch.object(dev_routes.lifecycle_service, 'apply_user_conversation_patch') as patch_user_conversation:
            request = dev_routes.UpdateConversationRequest(title='New Title', discarded=False)
            dev_routes.update_conversation_endpoint(conversation_id='conv-1', request=request, uid='test-uid')

        patch_user_conversation.assert_called_once_with(
            'test-uid',
            'conv-1',
            title='New Title',
            discarded=False,
        )

    def test_patch_rejects_lock_that_wins_after_initial_read(self):
        from fastapi import HTTPException
        from routers import developer as dev_routes

        locked_error = dev_routes.lifecycle_service.ConversationLockedError('conversation locked')
        with (
            patch.object(
                dev_routes.conversations_db,
                'get_conversation',
                return_value=_make_conversation(locked=False),
            ),
            patch.object(
                dev_routes.lifecycle_service,
                'apply_user_conversation_patch',
                side_effect=locked_error,
            ) as patch_user_conversation,
        ):
            with pytest.raises(HTTPException) as exc_info:
                dev_routes.update_conversation_endpoint(
                    conversation_id='conv-1',
                    request=dev_routes.UpdateConversationRequest(title='New Title', discarded=False),
                    uid='test-uid',
                )

        assert exc_info.value.status_code == 402
        patch_user_conversation.assert_called_once_with(
            'test-uid',
            'conv-1',
            title='New Title',
            discarded=False,
        )

    def test_delete_conversation_rejects_locked(self):
        """D2: DELETE /v1/dev/user/conversations/{id} must raise 402 for locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.developer import delete_conversation_endpoint
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            delete_conversation_endpoint(conversation_id='conv-1', uid='test-uid')
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_delete_conversation_allows_unlocked(self):
        """D2: DELETE should proceed for unlocked conversations."""
        from routers import developer as dev_routes
        from services import conversation_frame_evidence
        from utils.screen_frames import store as screen_frame_store

        with (
            patch.object(
                dev_routes.conversations_db,
                'get_conversation',
                return_value=_make_conversation(locked=False),
            ),
            patch.object(dev_routes.conversations_db, 'delete_conversation') as delete,
            patch.object(dev_routes.conversation_tombstones, 'record_deletion') as record_deletion,
            patch.object(screen_frame_store, 'delete_conversation_screen_frames'),
            patch.object(
                conversation_frame_evidence,
                'delete_conversation_and_frame_evidence',
                side_effect=lambda uid, cid: delete(uid, cid),
            ),
        ):
            result = dev_routes.delete_conversation_endpoint(conversation_id='conv-1', uid='test-uid')

        assert result == {"success": True}
        delete.assert_called_once_with('test-uid', 'conv-1')
        record_deletion.assert_called_once_with('test-uid', 'conv-1')


# =============================================================================
# Developer API — Memory write endpoints
# =============================================================================


class TestDevApiActionItemLockEnforcement:
    """D5-D6: Dev API action-item PATCH/DELETE must return 402 for locked."""

    def test_patch_action_item_rejects_locked(self):
        """D5: PATCH /v1/dev/user/action-items/{id} must raise 402 for locked."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=True))

        from routers.developer import update_action_item, UpdateActionItemRequest
        from fastapi import HTTPException

        request = UpdateActionItemRequest(description='New desc')
        with pytest.raises(HTTPException) as exc_info:
            update_action_item(action_item_id='ai-1', request=request, uid='test-uid')
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_patch_action_item_allows_unlocked(self):
        """D5: PATCH should proceed for unlocked action items."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=False))
        action_items_db.update_action_item = MagicMock(return_value=True)

        from routers.developer import update_action_item, UpdateActionItemRequest

        request = UpdateActionItemRequest(description='New desc')
        update_action_item(action_item_id='ai-1', request=request, uid='test-uid')
        action_items_db.update_action_item.assert_called_once()

    def test_delete_action_item_rejects_locked(self):
        """D6: DELETE /v1/dev/user/action-items/{id} must raise 402 for locked."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=True))

        from routers.developer import delete_action_item
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            delete_action_item(action_item_id='ai-1', uid='test-uid')
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_delete_action_item_allows_unlocked(self):
        """D6: DELETE should proceed for unlocked action items."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=False))
        action_items_db.delete_action_item = MagicMock(return_value=True)

        from routers.developer import delete_action_item

        result = delete_action_item(action_item_id='ai-1', uid='test-uid')
        assert result == {"success": True}
        action_items_db.delete_action_item.assert_called_once_with('test-uid', 'ai-1')

    def test_delete_action_item_cancels_scheduled_reminder(self):
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=False))
        action_items_db.delete_action_item = MagicMock(return_value=True)

        import routers.developer as developer

        with patch.object(developer, 'sync_action_item_reminder') as sync:
            developer.delete_action_item(action_item_id='ai-1', uid='test-uid')
        sync.assert_called_once()
        assert sync.call_args.kwargs['action_item_id'] == 'ai-1'
        assert sync.call_args.kwargs['completed'] is True

    def test_delete_action_item_returns_404_when_not_found(self):
        """D6: DELETE should return 404 when action item doesn't exist."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=None)

        from routers.developer import delete_action_item
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            delete_action_item(action_item_id='ai-missing', uid='test-uid')
        assert exc_info.value.status_code == 404


# =============================================================================
# Knowledge Graph — Rebuild must filter locked memories
