"""Unit tests for shared action items acceptance endpoints."""

from unittest.mock import patch
import pytest
from fastapi import HTTPException

from routers.action_items import (
    AcceptSharedTasksRequest,
    accept_shared_action_items,
)


@pytest.fixture
def sample_payload():
    return AcceptSharedTasksRequest(
        token="test-token-uuid",
        task_ids=["task-1", "task-2"],
        sender_id="sender-user-123",
    )


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_all_deleted_returns_404(
    mock_redis, mock_db, mock_wake, sample_payload
):
    mock_redis.verify_task_share_token.return_value = True
    mock_db.get_action_items_by_ids.return_value = []

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(payload=sample_payload, uid="recipient-user-456")

    assert exc_info.value.status_code == 404
    assert "deleted or not found" in exc_info.value.detail
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_not_called()


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_all_locked_returns_402(
    mock_redis, mock_db, mock_wake, sample_payload
):
    mock_redis.verify_task_share_token.return_value = True
    mock_db.get_action_items_by_ids.return_value = [
        {"id": "task-1", "is_locked": True},
        {"id": "task-2", "is_locked": True},
    ]

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(payload=sample_payload, uid="recipient-user-456")

    assert exc_info.value.status_code == 402
    assert "locked" in exc_info.value.detail
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_not_called()


@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_self_accept_forbidden(
    mock_redis, mock_db, sample_payload
):
    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(payload=sample_payload, uid="sender-user-123")

    assert exc_info.value.status_code == 400
    assert "cannot accept tasks you shared yourself" in exc_info.value.detail


@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_invalid_or_used_token_conflict(
    mock_redis, mock_db, sample_payload
):
    mock_redis.verify_task_share_token.return_value = False

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(payload=sample_payload, uid="recipient-user-456")

    assert exc_info.value.status_code == 409


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_success_creates_and_wakes(
    mock_redis, mock_db, mock_wake, sample_payload
):
    mock_redis.verify_task_share_token.return_value = True
    mock_db.get_action_items_by_ids.return_value = [
        {"id": "task-1", "description": "Buy milk", "is_locked": False},
        {"id": "task-2", "description": "Review PR", "is_locked": False},
    ]
    mock_db.create_action_item.side_effect = [
        {"id": "new-1", "description": "Buy milk"},
        {"id": "new-2", "description": "Review PR"},
    ]

    result = accept_shared_action_items(payload=sample_payload, uid="recipient-user-456")

    assert result["status"] == "accepted"
    assert result["accepted_count"] == 2
    assert len(result["created_items"]) == 2
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_called_once()


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_creation_failure_rolls_back_token(
    mock_redis, mock_db, mock_wake, sample_payload
):
    mock_redis.verify_task_share_token.return_value = True
    mock_db.get_action_items_by_ids.return_value = [
        {"id": "task-1", "description": "Do homework", "is_locked": False}
    ]
    mock_db.create_action_item.side_effect = RuntimeError("Database down")

    with pytest.raises(RuntimeError):
        accept_shared_action_items(payload=sample_payload, uid="recipient-user-456")

    mock_redis.undo_accept_task_share.assert_called_once_with(
        sample_payload.token, sample_payload.task_ids
    )
    mock_wake.assert_not_called()
