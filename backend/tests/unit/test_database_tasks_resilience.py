from unittest.mock import MagicMock
import pytest

from database.tasks import (
    _clean_task_id,
    create,
    get_task_by_action_request,
    update,
)


def test_clean_task_id_valid():
    assert _clean_task_id("task_123") == "task_123"
    assert _clean_task_id("  task_abc_456  ") == "task_abc_456"


@pytest.mark.parametrize("invalid_id", ["", "   ", None, 12345, [], {}])
def test_clean_task_id_empty_or_wrong_type(invalid_id):
    assert _clean_task_id(invalid_id) is None


@pytest.mark.parametrize(
    "traversal_id",
    [
        "../etc/passwd",
        "tasks/../../root",
        "task/123",
        "task\\123",
        "..",
        "t" * 129,
    ],
)
def test_clean_task_id_path_traversal_and_bounds(traversal_id):
    assert _clean_task_id(traversal_id) is None


def test_create_valid_task():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    payload = {"id": "task_valid_1", "action": "send_email", "status": "pending"}
    success = create(payload, db_client=mock_client)

    assert success is True
    mock_client.collection.assert_called_once_with("tasks")
    mock_client.collection.return_value.document.assert_called_once_with("task_valid_1")
    mock_doc.set.assert_called_once_with(payload)


@pytest.mark.parametrize(
    "invalid_payload",
    [
        None,
        "not_a_dict",
        [],
        {},
        {"id": ""},
        {"id": "   "},
        {"id": None},
        {"id": "../bad_path"},
        {"id": "bad/id"},
        {"id": "x" * 130},
    ],
)
def test_create_invalid_payload_rejected(invalid_payload):
    mock_client = MagicMock()
    success = create(invalid_payload, db_client=mock_client)
    assert success is False
    mock_client.collection.assert_not_called()


def test_update_valid_task():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    update_payload = {"status": "completed"}
    success = update("task_valid_1", update_payload, db_client=mock_client)

    assert success is True
    mock_client.collection.assert_called_once_with("tasks")
    mock_client.collection.return_value.document.assert_called_once_with("task_valid_1")
    mock_doc.update.assert_called_once_with(update_payload)


@pytest.mark.parametrize(
    "invalid_input",
    [
        ("", {"status": "ok"}),
        ("   ", {"status": "ok"}),
        (None, {"status": "ok"}),
        ("../bad", {"status": "ok"}),
        ("task/1", {"status": "ok"}),
        ("t" * 130, {"status": "ok"}),
        ("task_1", None),
        ("task_1", {}),
        ("task_1", "not_a_dict"),
    ],
)
def test_update_invalid_input_rejected(invalid_input):
    task_id, payload = invalid_input
    mock_client = MagicMock()
    success = update(task_id, payload, db_client=mock_client)
    assert success is False
    mock_client.collection.assert_not_called()


def test_get_task_by_action_request_valid():
    mock_client = MagicMock()
    mock_item = MagicMock()
    mock_item.to_dict.return_value = {"id": "task_42", "action": "sync", "request_id": "req_1"}
    mock_client.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = [
        mock_item
    ]

    result = get_task_by_action_request("  sync  ", "  req_1  ", db_client=mock_client)
    assert result == {"id": "task_42", "action": "sync", "request_id": "req_1"}


@pytest.mark.parametrize(
    "invalid_args",
    [
        ("", "req_1"),
        ("   ", "req_1"),
        (None, "req_1"),
        (123, "req_1"),
        ("sync", ""),
        ("sync", "   "),
        ("sync", None),
        ("sync", 456),
    ],
)
def test_get_task_by_action_request_invalid_fast_return(invalid_args):
    action, request_id = invalid_args
    mock_client = MagicMock()
    result = get_task_by_action_request(action, request_id, db_client=mock_client)
    assert result is None
    mock_client.collection.assert_not_called()


def test_create_catches_firestore_exception():
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.set.side_effect = RuntimeError("Firestore down")

    success = create({"id": "task_err"}, db_client=mock_client)
    assert success is False


def test_update_catches_firestore_exception():
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.update.side_effect = RuntimeError("Document not found")

    success = update("task_err", {"status": "failed"}, db_client=mock_client)
    assert success is False
