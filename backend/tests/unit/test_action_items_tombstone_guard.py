"""Tests for tombstone (soft-deleted) safety in action items endpoints."""

from unittest.mock import patch
import pytest
from fastapi import HTTPException

from routers.action_items import (
    AcceptSharedTasksRequest,
    ActionItemUpdateRequest,
    ShareTasksRequest,
    _get_valid_action_item,
    accept_shared_action_items,
    delete_action_item,
    get_action_item,
    get_shared_action_items,
    share_action_items,
    toggle_action_item_completion,
    update_action_item,
)

UID = "test-user-123"
TASK_ID = "task-tombstone-1"


class TestGetValidActionItemTombstoneGuard:
    @patch("routers.action_items.action_items_db")
    def test_get_valid_action_item_rejects_deleted(self, mock_db):
        mock_db.get_action_item.return_value = {
            "id": TASK_ID,
            "description": "Deleted task",
            "deleted": True,
            "is_locked": False,
        }

        with pytest.raises(HTTPException) as exc_info:
            _get_valid_action_item(UID, TASK_ID)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Action item not found"

    @patch("routers.action_items.action_items_db")
    def test_get_action_item_endpoint_rejects_deleted(self, mock_db):
        mock_db.get_action_item.return_value = {
            "id": TASK_ID,
            "description": "Deleted task",
            "deleted": True,
            "is_locked": False,
        }

        with pytest.raises(HTTPException) as exc_info:
            get_action_item(action_item_id=TASK_ID, uid=UID)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Action item not found"

    @patch("routers.action_items.action_items_db")
    def test_update_action_item_endpoint_rejects_deleted(self, mock_db):
        mock_db.get_action_item.return_value = {
            "id": TASK_ID,
            "description": "Deleted task",
            "deleted": True,
            "is_locked": False,
        }

        with pytest.raises(HTTPException) as exc_info:
            update_action_item(
                action_item_id=TASK_ID,
                request=ActionItemUpdateRequest(description="Updated"),
                uid=UID,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Action item not found"

    @patch("routers.action_items.action_items_db")
    def test_toggle_completion_endpoint_rejects_deleted(self, mock_db):
        mock_db.get_action_item.return_value = {
            "id": TASK_ID,
            "description": "Deleted task",
            "deleted": True,
            "is_locked": False,
        }

        with pytest.raises(HTTPException) as exc_info:
            toggle_action_item_completion(
                action_item_id=TASK_ID,
                completed=True,
                uid=UID,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Action item not found"

    @patch("routers.action_items.action_items_db")
    def test_delete_action_item_endpoint_rejects_deleted(self, mock_db):
        mock_db.get_action_item.return_value = {
            "id": TASK_ID,
            "description": "Deleted task",
            "deleted": True,
            "is_locked": False,
        }

        with pytest.raises(HTTPException) as exc_info:
            delete_action_item(
                action_item_id=TASK_ID,
                uid=UID,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Action item not found"


class TestSharedActionItemsTombstoneGuard:
    @patch("routers.action_items.action_items_db")
    def test_share_action_items_rejects_deleted(self, mock_db):
        mock_db.get_action_item.return_value = {
            "id": TASK_ID,
            "description": "Deleted task",
            "deleted": True,
            "is_locked": False,
        }

        with pytest.raises(HTTPException) as exc_info:
            share_action_items(
                request=ShareTasksRequest(task_ids=[TASK_ID]),
                uid=UID,
            )

        assert exc_info.value.status_code == 404

    @patch("routers.action_items.redis_db")
    @patch("routers.action_items.action_items_db")
    def test_get_shared_action_items_omits_deleted(self, mock_db, mock_redis):
        mock_redis.get_task_share.return_value = {
            "uid": "sender-1",
            "display_name": "Sender",
            "task_ids": ["task-live", "task-deleted"],
        }

        def mock_get(uid, tid):
            if tid == "task-live":
                return {"id": "task-live", "description": "Live task", "deleted": False, "is_locked": False}
            return {"id": "task-deleted", "description": "Deleted task", "deleted": True, "is_locked": False}

        mock_db.get_action_item.side_effect = mock_get

        result = get_shared_action_items(token="test-token")
        assert result["count"] == 1
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["description"] == "Live task"

    @patch("routers.action_items.redis_db")
    @patch("routers.action_items.action_items_db")
    def test_accept_shared_action_items_rejects_all_deleted(self, mock_db, mock_redis):
        mock_redis.get_task_share.return_value = {
            "uid": "sender-1",
            "display_name": "Sender",
            "task_ids": ["task-deleted"],
        }
        mock_db.get_action_item.return_value = {
            "id": "task-deleted",
            "description": "Deleted task",
            "deleted": True,
            "is_locked": False,
        }

        with pytest.raises(HTTPException) as exc_info:
            accept_shared_action_items(
                request=AcceptSharedTasksRequest(token="test-token"),
                uid="recipient-1",
            )

        assert exc_info.value.status_code == 404
        assert "deleted or not found" in exc_info.value.detail
