"""Unit tests for shared action items acceptance endpoints."""

from unittest.mock import patch
import pytest
from fastapi import HTTPException

from routers.action_items import (
    AcceptSharedTasksRequest,
    accept_shared_action_items,
)


@pytest.fixture
def sample_request():
    return AcceptSharedTasksRequest(token="test-token-uuid")


@pytest.fixture
def share_data():
    return {
        "uid": "sender-user-123",
        "display_name": "Sender",
        "task_ids": ["task-1", "task-2"],
    }


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_all_deleted_returns_404(mock_redis, mock_db, mock_wake, sample_request, share_data):
    mock_redis.get_task_share.return_value = share_data
    mock_db.get_action_item.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    assert exc_info.value.status_code == 404
    assert "deleted or not found" in exc_info.value.detail
    mock_redis.try_accept_task_share.assert_not_called()
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_not_called()


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_all_locked_returns_402(mock_redis, mock_db, mock_wake, sample_request, share_data):
    mock_redis.get_task_share.return_value = share_data
    mock_db.get_action_item.return_value = {"id": "task-1", "is_locked": True}

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    assert exc_info.value.status_code == 402
    assert "locked" in exc_info.value.detail
    mock_redis.try_accept_task_share.assert_not_called()
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_not_called()


@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_self_accept_forbidden(mock_redis, mock_db, sample_request, share_data):
    mock_redis.get_task_share.return_value = share_data

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid="sender-user-123")

    assert exc_info.value.status_code == 400
    assert "your own shared tasks" in exc_info.value.detail
    mock_db.get_action_item.assert_not_called()


@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_absent_link_returns_404(mock_redis, mock_db, sample_request):
    mock_redis.get_task_share.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    assert exc_info.value.status_code == 404
    assert "expired or not found" in exc_info.value.detail
    mock_redis.try_accept_task_share.assert_not_called()


@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_used_token_conflict(mock_redis, mock_db, sample_request, share_data):
    mock_redis.get_task_share.return_value = share_data
    mock_db.get_action_item.return_value = {
        "id": "task-1",
        "description": "Task",
        "is_locked": False,
    }
    mock_redis.try_accept_task_share.return_value = False

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    assert exc_info.value.status_code == 409
    assert "already accepted" in exc_info.value.detail


@patch("routers.action_items.upsert_action_item_vector")
@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_success_creates_and_wakes(
    mock_redis, mock_db, mock_wake, mock_vector, sample_request, share_data
):
    mock_redis.get_task_share.return_value = share_data
    mock_redis.try_accept_task_share.return_value = True
    items = {
        "task-1": {"id": "task-1", "description": "Buy milk", "is_locked": False},
        "task-2": {"id": "task-2", "description": "Review PR", "is_locked": False},
    }
    mock_db.get_action_item.side_effect = lambda _uid, task_id: items[task_id]
    mock_db.create_action_item.side_effect = ["new-1", "new-2"]

    result = accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    assert result == {"created": ["new-1", "new-2"], "count": 2}
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_called_once()
    assert mock_wake.call_args.args[:2] == ("recipient-user-456", ["new-1", "new-2"])


@patch("routers.action_items.upsert_action_item_vector")
@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_creation_failure_rolls_back_token(
    mock_redis, mock_db, mock_wake, mock_vector, sample_request, share_data
):
    mock_redis.get_task_share.return_value = share_data
    mock_redis.try_accept_task_share.return_value = True
    mock_db.get_action_item.return_value = {
        "id": "task-1",
        "description": "Do homework",
        "is_locked": False,
    }
    mock_db.create_action_item.side_effect = RuntimeError("Database down")

    with pytest.raises(RuntimeError):
        accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    mock_redis.undo_accept_task_share.assert_called_once_with(sample_request.token, "recipient-user-456")
    mock_wake.assert_not_called()
