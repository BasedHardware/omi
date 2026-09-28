import os
from unittest.mock import patch

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from utils.retrieval.tools import action_item_tools

SENSITIVE_FIRESTORE_ERR = "Firestore connection failed: /databases/default/documents/users/secret_uid/action_items"
CONFIG = {"configurable": {"user_id": "test_uid_123"}}


def test_get_action_items_tool_sanitized(caplog):
    with (
        patch.object(
            action_item_tools.action_items_db,
            "get_action_items",
            side_effect=RuntimeError(SENSITIVE_FIRESTORE_ERR),
        ),
        caplog.at_level("ERROR"),
    ):
        res = action_item_tools.get_action_items_tool.func(config=CONFIG)

    assert "/databases/default/documents/users/secret_uid/action_items" not in res
    assert "secret_uid" not in res
    assert (
        res
        == "An error occurred while retrieving action items. Please try again later."
    )
    assert any(
        record.levelname == "ERROR"
        and "Error getting action items:" in record.message
        and "Firestore connection failed" in record.message
        for record in caplog.records
    )


def test_create_action_item_tool_sanitized(caplog):
    with (
        patch.object(
            action_item_tools.action_items_db,
            "create_action_item",
            side_effect=RuntimeError(SENSITIVE_FIRESTORE_ERR),
        ),
        caplog.at_level("ERROR"),
    ):
        res = action_item_tools.create_action_item_tool.func(
            description="Buy groceries",
            config=CONFIG,
        )

    assert "/databases/default/documents/users/secret_uid/action_items" not in res
    assert "secret_uid" not in res
    assert (
        res
        == "An error occurred while creating the action item. Please try again later."
    )
    assert any(
        record.levelname == "ERROR"
        and "Error creating action item:" in record.message
        and "Firestore connection failed" in record.message
        for record in caplog.records
    )


def test_update_action_item_tool_sanitized(caplog):
    with (
        patch.object(
            action_item_tools.action_items_db,
            "get_action_item",
            return_value={"id": "item_456", "description": "Existing task"},
        ),
        patch.object(
            action_item_tools.action_items_db,
            "update_action_item",
            side_effect=RuntimeError(SENSITIVE_FIRESTORE_ERR),
        ),
        caplog.at_level("ERROR"),
    ):
        res = action_item_tools.update_action_item_tool.func(
            action_item_id="item_456",
            completed=True,
            config=CONFIG,
        )

    assert "/databases/default/documents/users/secret_uid/action_items" not in res
    assert "secret_uid" not in res
    assert (
        res
        == "An error occurred while updating the action item. Please try again later."
    )
    assert any(
        record.levelname == "ERROR"
        and "Error updating action item:" in record.message
        and "Firestore connection failed" in record.message
        for record in caplog.records
    )
