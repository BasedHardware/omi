"""Test tombstone and authorization guards for POST /v1/conversations/merge.

The merge endpoint must use `_get_valid_conversation_by_id` rather than raw
`conversations_db.get_conversation`.

Invariants:
1. Soft-deleted tombstones (`deleted: True`) must be rejected with 404 Not Found
   (same as GET, DELETE, and REPROCESS endpoints) to prevent oracle disclosure
   and ensure deleted conversations are treated as non-existent.
2. Locked conversations (`is_locked: True`) must be rejected with 402 Payment Required
   per the standard platform paywall contract.
3. Neither `lifecycle_service.begin_merge` nor background tasks may be scheduled
   when any source conversation is invalid or tombstoned.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from models.conversation import MergeConversationsRequest
import routers.conversations as conv_router


@pytest.fixture
def background_tasks():
    return BackgroundTasks()


def test_merge_conversations_rejects_soft_deleted_tombstone_with_404(background_tasks):
    """A soft-deleted conversation tombstone must return 404, not 400."""
    tombstone = {'id': 'c1', 'deleted': True, 'status': 'completed'}
    live = {'id': 'c2', 'status': 'completed', 'started_at': None, 'finished_at': None}

    def mock_get(uid, cid, **kwargs):
        if cid == 'c1':
            return tombstone
        if cid == 'c2':
            return live
        return None

    with patch.object(conv_router.conversations_db, 'get_conversation', side_effect=mock_get):
        with patch.object(conv_router.lifecycle_service, 'begin_merge') as begin_merge:
            request = MergeConversationsRequest(conversation_ids=['c1', 'c2'])
            with pytest.raises(HTTPException) as exc_info:
                conv_router.merge_conversations(
                    request=request,
                    background_tasks=background_tasks,
                    uid='test-uid',
                )

            assert exc_info.value.status_code == 404, (
                f"Expected 404 Not Found for tombstone conversation, got {exc_info.value.status_code} "
                f"with detail: {exc_info.value.detail}"
            )
            begin_merge.assert_not_called()
            assert len(background_tasks.tasks) == 0


def test_merge_conversations_rejects_locked_conversation_with_402(background_tasks):
    """A locked conversation must return 402 Payment Required, not 400."""
    locked = {'id': 'c1', 'is_locked': True, 'status': 'completed'}
    live = {'id': 'c2', 'status': 'completed', 'started_at': None, 'finished_at': None}

    def mock_get(uid, cid, **kwargs):
        if cid == 'c1':
            return locked
        if cid == 'c2':
            return live
        return None

    with patch.object(conv_router.conversations_db, 'get_conversation', side_effect=mock_get):
        with patch.object(conv_router.lifecycle_service, 'begin_merge') as begin_merge:
            request = MergeConversationsRequest(conversation_ids=['c1', 'c2'])
            with pytest.raises(HTTPException) as exc_info:
                conv_router.merge_conversations(
                    request=request,
                    background_tasks=background_tasks,
                    uid='test-uid',
                )

            assert exc_info.value.status_code == 402, (
                f"Expected 402 Payment Required for locked conversation, got {exc_info.value.status_code} "
                f"with detail: {exc_info.value.detail}"
            )
            begin_merge.assert_not_called()
            assert len(background_tasks.tasks) == 0


def test_merge_conversations_succeeds_for_valid_live_conversations(background_tasks):
    """Two valid completed conversations proceed to begin_merge and queue background task."""
    live1 = {'id': 'c1', 'status': 'completed', 'started_at': None, 'finished_at': None}
    live2 = {'id': 'c2', 'status': 'completed', 'started_at': None, 'finished_at': None}

    def mock_get(uid, cid, **kwargs):
        if cid == 'c1':
            return live1
        if cid == 'c2':
            return live2
        return None

    with patch.object(conv_router.conversations_db, 'get_conversation', side_effect=mock_get):
        with patch.object(conv_router.lifecycle_service, 'begin_merge') as begin_merge:
            request = MergeConversationsRequest(conversation_ids=['c1', 'c2'])
            response = conv_router.merge_conversations(
                request=request,
                background_tasks=background_tasks,
                uid='test-uid',
            )

            assert response.status == "merging"
            assert response.conversation_ids == ['c1', 'c2']
            assert begin_merge.call_count == 2
            assert len(background_tasks.tasks) == 1
