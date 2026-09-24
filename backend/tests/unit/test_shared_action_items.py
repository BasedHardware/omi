"""Unit tests for shared action items acceptance endpoints."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from routers.action_items import (
    AcceptSharedTasksRequest,
    accept_shared_action_items,
)

RECIPIENT_UID = "recipient-user-456"
SENDER_UID = "sender-user-123"
TOKEN = "test-token-uuid"


@pytest.fixture
def sample_request():
    return AcceptSharedTasksRequest(token=TOKEN)


def _share(task_ids):
    """What redis_db.get_task_share returns for a live share link."""
    return {"uid": SENDER_UID, "task_ids": task_ids, "display_name": "Sender"}


def _items(*items):
    """action_items_db.get_action_item is called once per task id, in order."""
    return lambda _uid, task_id: items[int(task_id.split("-")[1]) - 1]


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_all_deleted_returns_404(mock_redis, mock_db, mock_wake, sample_request):
    mock_redis.get_task_share.return_value = _share(["task-1", "task-2"])
    mock_db.get_action_item.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid=RECIPIENT_UID)

    assert exc_info.value.status_code == 404
    assert "deleted or not found" in exc_info.value.detail
    # The token is never consumed, so the sender can re-share.
    mock_redis.try_accept_task_share.assert_not_called()
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_not_called()


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_all_locked_returns_402(mock_redis, mock_db, mock_wake, sample_request):
    mock_redis.get_task_share.return_value = _share(["task-1", "task-2"])
    mock_db.get_action_item.side_effect = _items(
        {"id": "task-1", "is_locked": True},
        {"id": "task-2", "is_locked": True},
    )

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid=RECIPIENT_UID)

    # Locked is distinct from deleted: the items exist, so this is a paywall.
    assert exc_info.value.status_code == 402
    assert "locked" in exc_info.value.detail
    mock_redis.try_accept_task_share.assert_not_called()
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_not_called()


@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_self_accept_forbidden(mock_redis, mock_db, sample_request):
    mock_redis.get_task_share.return_value = _share(["task-1"])

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid=SENDER_UID)

    assert exc_info.value.status_code == 400
    assert "Cannot accept your own shared tasks" in exc_info.value.detail
    mock_db.get_action_item.assert_not_called()


@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_expired_token_returns_404(mock_redis, mock_db, sample_request):
    mock_redis.get_task_share.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid=RECIPIENT_UID)

    assert exc_info.value.status_code == 404
    assert "Share link expired or not found" in exc_info.value.detail


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_already_accepted_returns_409(mock_redis, mock_db, mock_wake, sample_request):
    mock_redis.get_task_share.return_value = _share(["task-1"])
    mock_db.get_action_item.side_effect = _items({"id": "task-1", "description": "Buy milk", "is_locked": False})
    mock_redis.try_accept_task_share.return_value = False

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid=RECIPIENT_UID)

    assert exc_info.value.status_code == 409
    mock_db.create_action_item.assert_not_called()
    mock_wake.assert_not_called()


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_unavailable_claim_returns_503(mock_redis, mock_db, mock_wake, sample_request):
    mock_redis.get_task_share.return_value = _share(["task-1"])
    mock_db.get_action_item.side_effect = _items({"id": "task-1", "description": "Buy milk", "is_locked": False})
    # try_accept_task_share returns None (not False) when Redis itself is unreachable.
    mock_redis.try_accept_task_share.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid=RECIPIENT_UID)

    assert exc_info.value.status_code == 503
    mock_db.create_action_item.assert_not_called()
    mock_wake.assert_not_called()


@patch("routers.action_items._schedule_action_item_reminder")
@patch("routers.action_items.upsert_action_item_vector")
@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_success_creates_and_wakes(
    mock_redis, mock_db, mock_wake, mock_vector, mock_reminder, sample_request
):
    mock_redis.get_task_share.return_value = _share(["task-1", "task-2"])
    mock_db.get_action_item.side_effect = lambda _uid, task_id: {
        "task-1": {"id": "task-1", "description": "Buy milk", "is_locked": False},
        "task-2": {"id": "task-2", "description": "Review PR", "is_locked": False},
    }[task_id]
    mock_redis.try_accept_task_share.return_value = True
    mock_db.create_action_item.side_effect = ["new-1", "new-2"]

    result = accept_shared_action_items(request=sample_request, uid=RECIPIENT_UID)

    assert result == {"created": ["new-1", "new-2"], "count": 2}
    # Each copy carries its provenance back to the sender's original.
    copied = mock_db.create_action_item.call_args_list[0].args[1]
    assert copied["shared_from"]["sender_uid"] == SENDER_UID
    assert copied["shared_from"]["original_task_id"] == "task-1"
    assert mock_vector.call_count == 2
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_called_once()
    assert mock_wake.call_args.args[0] == RECIPIENT_UID
    assert mock_wake.call_args.args[1] == ["new-1", "new-2"]


@patch("routers.action_items.upsert_action_item_vector")
@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_creation_failure_rolls_back_token(
    mock_redis, mock_db, mock_wake, mock_vector, sample_request
):
    mock_redis.get_task_share.return_value = _share(["task-1"])
    mock_db.get_action_item.side_effect = _items({"id": "task-1", "description": "Do homework", "is_locked": False})
    mock_redis.try_accept_task_share.return_value = True
    mock_db.create_action_item.side_effect = RuntimeError("Database down")

    with pytest.raises(RuntimeError):
        accept_shared_action_items(request=sample_request, uid=RECIPIENT_UID)

    # Nothing was created, so the token is released for a retry.
    mock_redis.undo_accept_task_share.assert_called_once_with(TOKEN, RECIPIENT_UID)
    mock_wake.assert_not_called()
