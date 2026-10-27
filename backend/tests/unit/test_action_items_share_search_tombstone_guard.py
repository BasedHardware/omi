"""Unit tests for soft-deleted tombstone guard across task sharing and semantic search."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from routers.action_items import (
    AcceptSharedTasksRequest,
    ShareTasksRequest,
    accept_shared_action_items,
    get_shared_action_items,
    search_action_items,
    share_action_items,
)

# ============================================================================
# 1. search_action_items: filter out soft-deleted action items
# ============================================================================


@patch("routers.action_items.search_action_items_by_vector")
@patch("routers.action_items.action_items_db")
def test_search_action_items_filters_soft_deleted(mock_db, mock_vector):
    mock_vector.return_value = ["task-1", "task-2", "task-3"]
    mock_db.get_action_items_by_ids.return_value = [
        {"id": "task-1", "description": "Active task", "completed": False, "deleted": False, "is_locked": False},
        {"id": "task-2", "description": "Soft-deleted task", "completed": False, "deleted": True, "is_locked": False},
        {"id": "task-3", "description": "Locked task", "completed": False, "deleted": False, "is_locked": True},
    ]

    result = search_action_items(query="test", limit=10, uid="user-123")

    mock_vector.assert_called_once_with("user-123", "test", limit=10)
    mock_db.get_action_items_by_ids.assert_called_once_with("user-123", ["task-1", "task-2", "task-3"])
    assert len(result["action_items"]) == 1
    assert result["action_items"][0].id == "task-1"
    assert result["action_items"][0].description == "Active task"


# ============================================================================
# 2. share_action_items: reject soft-deleted action items with 404
# ============================================================================


@patch("routers.action_items.get_user_display_name", return_value="Test User")
@patch("routers.action_items.redis_db")
@patch("routers.action_items.action_items_db")
def test_share_action_items_rejects_soft_deleted_task_with_404(mock_db, mock_redis, mock_display_name):
    mock_db.get_action_item.side_effect = lambda uid, task_id: {
        "task-1": {"id": "task-1", "description": "Live task", "deleted": False, "is_locked": False},
        "task-2": {"id": "task-2", "description": "Deleted task", "deleted": True, "is_locked": False},
    }.get(task_id)

    request = ShareTasksRequest(task_ids=["task-1", "task-2"])

    with pytest.raises(HTTPException) as exc_info:
        share_action_items(request=request, uid="user-123")

    assert exc_info.value.status_code == 404
    assert "Action item task-2 not found" in exc_info.value.detail
    mock_redis.store_task_share.assert_not_called()


@patch("routers.action_items.get_user_display_name", return_value="Test User")
@patch("routers.action_items.redis_db")
@patch("routers.action_items.action_items_db")
def test_share_action_items_success_with_active_tasks(mock_db, mock_redis, mock_display_name):
    mock_db.get_action_item.return_value = {
        "id": "task-1",
        "description": "Live task",
        "deleted": False,
        "is_locked": False,
    }
    mock_redis.store_task_share.return_value = True

    request = ShareTasksRequest(task_ids=["task-1"])
    result = share_action_items(request=request, uid="user-123")

    assert "url" in result
    assert "token" in result
    mock_redis.store_task_share.assert_called_once()


# ============================================================================
# 3. get_shared_action_items: omit soft-deleted tasks in public preview
# ============================================================================


@patch("routers.action_items.redis_db")
@patch("routers.action_items.action_items_db")
def test_get_shared_action_items_omits_soft_deleted_tasks(mock_db, mock_redis):
    mock_redis.get_task_share.return_value = {
        "uid": "sender-123",
        "display_name": "Alice",
        "task_ids": ["task-1", "task-2", "task-3"],
    }
    mock_db.get_action_item.side_effect = lambda uid, task_id: {
        "task-1": {
            "id": "task-1",
            "description": "Visible task",
            "deleted": False,
            "is_locked": False,
            "due_at": "2026-10-30T00:00:00Z",
        },
        "task-2": {"id": "task-2", "description": "Deleted task", "deleted": True, "is_locked": False},
        "task-3": {"id": "task-3", "description": "Locked task", "deleted": False, "is_locked": True},
    }.get(task_id)

    result = get_shared_action_items(token="valid-token")

    assert result["sender_name"] == "Alice"
    assert result["count"] == 1
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["description"] == "Visible task"
    assert result["tasks"][0]["due_at"] == "2026-10-30T00:00:00Z"


# ============================================================================
# 4. accept_shared_action_items: reject all soft-deleted with 404
# ============================================================================


@patch("routers.action_items.redis_db")
@patch("routers.action_items.action_items_db")
def test_accept_shared_tasks_all_soft_deleted_returns_404(mock_db, mock_redis):
    mock_redis.get_task_share.return_value = {
        "uid": "sender-123",
        "display_name": "Alice",
        "task_ids": ["task-1", "task-2"],
    }
    mock_db.get_action_item.return_value = {"id": "task-1", "deleted": True, "is_locked": False}

    request = AcceptSharedTasksRequest(token="valid-token")

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=request, uid="recipient-456")

    assert exc_info.value.status_code == 404
    assert "Shared tasks were deleted or not found" in exc_info.value.detail
    mock_redis.try_accept_task_share.assert_not_called()
    mock_db.create_action_items_batch.assert_not_called()


# ============================================================================
# 5. accept_shared_action_items: skip soft-deleted in mixed payload during clone
# ============================================================================


@patch("routers.action_items.redis_db")
@patch("routers.action_items.action_items_db")
def test_accept_shared_tasks_skips_soft_deleted_in_mixed_payload(mock_db, mock_redis):
    mock_redis.get_task_share.return_value = {
        "uid": "sender-123",
        "display_name": "Alice",
        "task_ids": ["task-live", "task-del"],
    }
    mock_db.get_action_item.side_effect = lambda uid, task_id: {
        "task-live": {
            "id": "task-live",
            "description": "Keep this",
            "deleted": False,
            "is_locked": False,
            "due_at": None,
        },
        "task-del": {"id": "task-del", "description": "Skip this", "deleted": True, "is_locked": False, "due_at": None},
    }.get(task_id)

    mock_redis.try_accept_task_share.return_value = True
    mock_db.create_action_items_batch.return_value = ["new-task-1"]

    request = AcceptSharedTasksRequest(token="valid-token")
    result = accept_shared_action_items(request=request, uid="recipient-456")

    assert result["count"] == 1
    assert result["created"] == ["new-task-1"]

    mock_db.create_action_items_batch.assert_called_once()
    args, _ = mock_db.create_action_items_batch.call_args
    recipient_uid, items_to_create = args
    assert recipient_uid == "recipient-456"
    assert len(items_to_create) == 1
    assert items_to_create[0]["description"] == "Keep this"
    assert items_to_create[0]["shared_from"]["original_task_id"] == "task-live"
