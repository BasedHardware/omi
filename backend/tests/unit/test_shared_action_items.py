"""Unit tests for shared action items acceptance endpoints."""

from datetime import datetime, timezone
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


@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_accept_shared_tasks_unavailable_claim_returns_503(mock_redis, mock_db, mock_wake, sample_request, share_data):
    """try_accept_task_share returns None when Redis is unreachable, False when the
    token was already used. Only the second is the client's fault, so they must not
    collapse to one status."""
    mock_redis.get_task_share.return_value = share_data
    mock_db.get_action_item.side_effect = lambda _uid, task_id: {
        "id": task_id,
        "description": "Buy milk",
        "is_locked": False,
    }
    mock_redis.try_accept_task_share.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    assert exc_info.value.status_code == 503
    mock_db.create_action_item.assert_not_called()
    mock_wake.assert_not_called()


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
    mock_db.create_action_items_batch.return_value = ["new-1", "new-2"]

    result = accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    assert result == {"created": ["new-1", "new-2"], "count": 2}
    mock_db.create_action_items_batch.assert_called_once()
    mock_db.create_action_item.assert_not_called()
    # Every copy -- not just the first -- lands on the recipient in the one batch
    # and carries provenance back to its own original, and every copy is indexed.
    batch_uid, payload = mock_db.create_action_items_batch.call_args.args
    assert batch_uid == "recipient-user-456"
    assert len(payload) == len(share_data["task_ids"])
    for original_task_id, copied in zip(share_data["task_ids"], payload):
        assert copied["shared_from"]["sender_uid"] == share_data["uid"]
        assert copied["shared_from"]["original_task_id"] == original_task_id
        assert copied["shared_from"]["token"] == sample_request.token
        assert copied["completed"] is False
    assert [c.args[:2] for c in mock_vector.call_args_list] == [
        ("recipient-user-456", "new-1"),
        ("recipient-user-456", "new-2"),
    ]
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
    mock_db.create_action_items_batch.side_effect = RuntimeError("Database down")

    with pytest.raises(RuntimeError):
        accept_shared_action_items(request=sample_request, uid="recipient-user-456")

    mock_redis.undo_accept_task_share.assert_called_once_with(sample_request.token, "recipient-user-456")
    mock_wake.assert_not_called()


@patch("routers.action_items.upsert_action_item_vector")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_later_source_read_failure_happens_before_any_copy(
    mock_redis, mock_db, mock_vector, sample_request, share_data
):
    mock_redis.get_task_share.return_value = share_data
    mock_redis.try_accept_task_share.return_value = True
    item = {"description": "Task", "is_locked": False}
    mock_db.get_action_item.side_effect = [item, item, item, RuntimeError("Source unavailable")]

    with pytest.raises(RuntimeError, match="Source unavailable"):
        accept_shared_action_items(request=sample_request, uid="recipient")

    mock_db.create_action_item.assert_not_called()
    mock_db.create_action_items_batch.assert_not_called()
    mock_vector.assert_not_called()
    mock_redis.undo_accept_task_share.assert_called_once_with(sample_request.token, "recipient")


@patch("routers.action_items._schedule_action_item_reminder")
@patch("routers.action_items.upsert_action_item_vector")
@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_delivery_starts_after_all_twenty_tasks_are_saved(
    mock_redis, mock_db, mock_wake, mock_vector, mock_reminder, sample_request
):
    ids = [f"task-{index}" for index in range(20)]
    created = [f"copy-{index}" for index in range(20)]
    due = datetime(2026, 10, 1, tzinfo=timezone.utc)
    mock_redis.get_task_share.return_value = {"uid": "sender", "display_name": "Sender", "task_ids": ids}
    mock_redis.try_accept_task_share.return_value = True
    mock_db.get_action_item.side_effect = lambda _uid, task_id: {"description": task_id, "due_at": due}
    mock_db.create_action_items_batch.return_value = created

    def assert_committed(*_args):
        mock_db.create_action_items_batch.assert_called_once()
        payloads = mock_db.create_action_items_batch.call_args.args[1]
        assert [payload["description"] for payload in payloads] == ids

    mock_vector.side_effect = assert_committed
    mock_reminder.side_effect = assert_committed
    result = accept_shared_action_items(request=sample_request, uid="recipient")

    assert result == {"created": created, "count": 20}
    assert mock_vector.call_count == mock_reminder.call_count == 20
    mock_db.create_action_item.assert_not_called()
    mock_redis.undo_accept_task_share.assert_not_called()
    mock_wake.assert_called_once()


@pytest.mark.parametrize('remaining', [None, {"is_locked": True}])
@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_no_longer_available_tasks_release_acceptance(
    mock_redis, mock_db, mock_wake, remaining, sample_request, share_data
):
    mock_redis.get_task_share.return_value = share_data
    mock_redis.try_accept_task_share.return_value = True
    mock_db.get_action_item.side_effect = [{"description": "Task"}, {"description": "Task"}, remaining, remaining]
    mock_db.create_action_items_batch.return_value = []

    with pytest.raises(HTTPException) as error:
        accept_shared_action_items(request=sample_request, uid="recipient")

    assert error.value.status_code == 402
    mock_redis.undo_accept_task_share.assert_called_once_with(sample_request.token, "recipient")
    mock_wake.assert_not_called()


@patch("routers.action_items.upsert_action_item_vector")
@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_ineligible_source_does_not_shift_copy_metadata(
    mock_redis, mock_db, mock_wake, mock_vector, sample_request, share_data
):
    mock_redis.get_task_share.return_value = share_data
    mock_redis.try_accept_task_share.return_value = True
    kept = {"description": "Keep this task"}
    mock_db.get_action_item.side_effect = [{"description": "Removed"}, kept, None, kept]
    mock_db.create_action_items_batch.return_value = ["copy-2"]

    assert accept_shared_action_items(request=sample_request, uid="recipient") == {"created": ["copy-2"], "count": 1}
    payload = mock_db.create_action_items_batch.call_args.args[1]
    assert len(payload) == 1
    assert payload[0]['shared_from']['original_task_id'] == 'task-2'
    mock_vector.assert_called_once_with("recipient", "copy-2", "Keep this task")


@patch("routers.action_items._schedule_action_item_reminder")
@patch("routers.action_items.upsert_action_item_vector")
@patch("routers.action_items._wake_task_changes")
@patch("routers.action_items.action_items_db")
@patch("routers.action_items.redis_db")
def test_post_commit_failure_does_not_release_duplicate_acceptance(
    mock_redis, mock_db, mock_wake, mock_vector, mock_reminder, sample_request, share_data
):
    mock_redis.get_task_share.return_value = share_data
    mock_redis.try_accept_task_share.return_value = True
    mock_db.get_action_item.return_value = {"description": "Task", "due_at": datetime(2026, 10, 1, tzinfo=timezone.utc)}
    mock_db.create_action_items_batch.return_value = ["copy-1", "copy-2"]
    mock_reminder.side_effect = RuntimeError("Delivery unavailable")

    with pytest.raises(RuntimeError, match="Delivery unavailable"):
        accept_shared_action_items(request=sample_request, uid="recipient")

    mock_db.create_action_items_batch.assert_called_once()
    mock_redis.undo_accept_task_share.assert_not_called()
