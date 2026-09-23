"""Unit tests for shared action items acceptance endpoints."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from routers.action_items import (
    AcceptSharedTasksRequest,
    accept_shared_action_items,
)


def test_accept_shared_action_items_token_not_found():
    with patch("routers.action_items.redis_db.get_task_share", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            accept_shared_action_items(
                AcceptSharedTasksRequest(token="invalid_token"),
                uid="recipient_123",
            )
        assert exc_info.value.status_code == 404
        assert "Share link expired or not found" in exc_info.value.detail


def test_accept_shared_action_items_self_accept_rejected():
    share_data = {
        "uid": "user_same",
        "display_name": "Alice",
        "task_ids": ["task_1"],
    }
    with patch("routers.action_items.redis_db.get_task_share", return_value=share_data):
        with pytest.raises(HTTPException) as exc_info:
            accept_shared_action_items(
                AcceptSharedTasksRequest(token="valid_token"),
                uid="user_same",
            )
        assert exc_info.value.status_code == 400
        assert "Cannot accept your own shared tasks" in exc_info.value.detail


def test_accept_shared_action_items_deleted_tasks_returns_404_not_402():
    """Verify that when tasks were deleted by the sender (not found),
    the endpoint returns 404 instead of a misleading 402 Payment Required."""
    share_data = {
        "uid": "sender_123",
        "display_name": "Sender",
        "task_ids": ["deleted_task_1", "deleted_task_2"],
    }
    with patch("routers.action_items.redis_db.get_task_share", return_value=share_data), \
         patch("routers.action_items.action_items_db.get_action_item", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            accept_shared_action_items(
                AcceptSharedTasksRequest(token="valid_token"),
                uid="recipient_456",
            )
        # MUST be 404, not 402!
        assert exc_info.value.status_code == 404
        assert "Shared tasks were deleted or not found" in exc_info.value.detail


def test_accept_shared_action_items_locked_tasks_returns_402():
    """Verify that when tasks exist but are locked behind a paid plan,
    the endpoint returns 402 Payment Required."""
    share_data = {
        "uid": "sender_123",
        "display_name": "Sender",
        "task_ids": ["locked_task_1"],
    }
    locked_item = {
        "id": "locked_task_1",
        "description": "Locked task",
        "is_locked": True,
    }
    with patch("routers.action_items.redis_db.get_task_share", return_value=share_data), \
         patch("routers.action_items.action_items_db.get_action_item", return_value=locked_item):
        with pytest.raises(HTTPException) as exc_info:
            accept_shared_action_items(
                AcceptSharedTasksRequest(token="valid_token"),
                uid="recipient_456",
            )
        assert exc_info.value.status_code == 402
        assert "All shared tasks are locked. A paid plan is required." in exc_info.value.detail


def test_accept_shared_action_items_already_accepted_returns_409():
    share_data = {
        "uid": "sender_123",
        "display_name": "Sender",
        "task_ids": ["task_1"],
    }
    valid_item = {
        "id": "task_1",
        "description": "Prepare slides",
        "is_locked": False,
    }
    with patch("routers.action_items.redis_db.get_task_share", return_value=share_data), \
         patch("routers.action_items.action_items_db.get_action_item", return_value=valid_item), \
         patch("routers.action_items.redis_db.try_accept_task_share", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            accept_shared_action_items(
                AcceptSharedTasksRequest(token="valid_token"),
                uid="recipient_456",
            )
        assert exc_info.value.status_code == 409
        assert "You have already accepted this share" in exc_info.value.detail


def test_accept_shared_action_items_success_and_wake():
    share_data = {
        "uid": "sender_123",
        "display_name": "Sender Alice",
        "task_ids": ["task_1"],
    }
    valid_item = {
        "id": "task_1",
        "description": "Buy groceries",
        "is_locked": False,
        "due_at": None,
    }
    with patch("routers.action_items.redis_db.get_task_share", return_value=share_data), \
         patch("routers.action_items.action_items_db.get_action_item", return_value=valid_item), \
         patch("routers.action_items.redis_db.try_accept_task_share", return_value=True), \
         patch("routers.action_items.action_items_db.create_action_item", return_value="new_task_999"), \
         patch("routers.action_items.upsert_action_item_vector") as mock_vector, \
         patch("routers.action_items._wake_task_changes") as mock_wake:

        response = accept_shared_action_items(
            AcceptSharedTasksRequest(token="valid_token"),
            uid="recipient_456",
        )

        assert response["created"] == ["new_task_999"]
        assert response["count"] == 1
        mock_vector.assert_called_once_with("recipient_456", "new_task_999", "Buy groceries")
        mock_wake.assert_called_once()
        assert mock_wake.call_args[0][0] == "recipient_456"
        assert mock_wake.call_args[0][1] == ["new_task_999"]
