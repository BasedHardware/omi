"""Tests verifying exception hardening and information disclosure protection in action_item_tools.

Ensures that database errors, malformed dates, and runtime exceptions are sanitized into
generic user-friendly messages and never disclose internal stack traces, DB credentials,
or raw exception representations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest
from database import chat_edits, notifications as notification_db
from utils.retrieval.tool_services import action_items as service
from utils.retrieval.tools import action_item_tools as tools


@pytest.fixture
def action_tools_module(monkeypatch):
    database = SimpleNamespace(
        get_action_items=MagicMock(return_value=[]),
        create_action_item=MagicMock(return_value='test_item_123'),
        get_action_item=MagicMock(
            return_value={
                'id': 'test_item_123',
                'description': 'Test task',
                'completed': False,
                'due_at': datetime.now(timezone.utc),
            }
        ),
        update_action_item=MagicMock(return_value=True),
    )
    monkeypatch.setattr(tools, 'action_items_db', database)
    monkeypatch.setattr(service, 'action_items_db', database)
    monkeypatch.setattr(notification_db, 'get_user_time_zone', lambda *_: 'UTC')
    monkeypatch.setattr(chat_edits, 'snapshot', MagicMock(return_value={'completed': False}))
    monkeypatch.setattr(chat_edits, 'envelope', lambda snapshot, summary: {'_snapshot': snapshot, '_summary': summary})
    monkeypatch.setattr(tools, 'record_write', MagicMock(return_value=''))
    for name in (
        'send_action_item_completed_notification',
        'send_action_item_created_notification',
        'send_action_item_data_message',
        'sync_action_item_reminder',
    ):
        monkeypatch.setattr(tools, name, MagicMock())
    return SimpleNamespace(
        action_items_db=database,
        get_action_items_tool=tools.get_action_items_tool.func,
        create_action_item_tool=tools.create_action_item_tool.func,
        update_action_item_tool=tools.update_action_item_tool.func,
    )


def _valid_config():
    return {"configurable": {"user_id": "test_user_456"}}


class TestGetActionItemsSanitization:
    def test_invalid_start_date_sanitized(self, action_tools_module):
        res = action_tools_module.get_action_items_tool(
            start_date="not-a-valid-date",
            config=_valid_config(),
        )
        assert res.startswith("Error: Invalid start_date format.")
        assert "not-a-valid-date" in res
        assert "ValueError" not in res
        assert "ISO" not in res

    def test_invalid_end_date_sanitized(self, action_tools_module):
        res = action_tools_module.get_action_items_tool(
            end_date="invalid-iso-date",
            config=_valid_config(),
        )
        assert res.startswith("Error: Invalid end_date format.")
        assert "invalid-iso-date" in res
        assert "ValueError" not in res

    def test_invalid_due_start_date_sanitized(self, action_tools_module):
        res = action_tools_module.get_action_items_tool(
            due_start_date="invalid-due-start",
            config=_valid_config(),
        )
        assert res.startswith("Error: Invalid due_start_date format.")
        assert "invalid-due-start" in res
        assert "ValueError" not in res

    def test_invalid_due_end_date_sanitized(self, action_tools_module):
        res = action_tools_module.get_action_items_tool(
            due_end_date="invalid-due-end",
            config=_valid_config(),
        )
        assert res.startswith("Error: Invalid due_end_date format.")
        assert "invalid-due-end" in res
        assert "ValueError" not in res

    def test_config_error_sanitized(self, action_tools_module):
        class BrokenConfig:
            def get(self, key):
                raise RuntimeError("Accessing config key failed with internal db password secret_pass_123")

        res = action_tools_module.get_action_items_tool(
            config=BrokenConfig(),
        )
        assert res == "Error: Configuration error."
        assert "secret_pass_123" not in res
        assert "RuntimeError" not in res

    def test_db_exception_sanitized(self, action_tools_module, monkeypatch):
        monkeypatch.setattr(
            action_tools_module.action_items_db,
            "get_action_items",
            MagicMock(
                side_effect=RuntimeError(
                    "psycopg2.OperationalError: connection to postgres://admin:dbpass@host refused"
                )
            ),
        )
        res = action_tools_module.get_action_items_tool(
            config=_valid_config(),
        )
        assert res == "Error retrieving action items. Please try again."
        assert "postgres://" not in res
        assert "dbpass" not in res
        assert "RuntimeError" not in res


class TestCreateActionItemSanitization:
    def test_invalid_due_at_sanitized(self, action_tools_module):
        res = action_tools_module.create_action_item_tool(
            description="Buy milk",
            due_at="bad-due-date",
            config=_valid_config(),
        )
        assert res.startswith("Error: Invalid due_at format.")
        assert "bad-due-date" in res
        assert "ValueError" not in res

    def test_db_exception_sanitized(self, action_tools_module, monkeypatch):
        monkeypatch.setattr(
            action_tools_module.action_items_db,
            "create_action_item",
            MagicMock(side_effect=RuntimeError("Firestore connection failed: credentials leak key_secret_abc123")),
        )
        res = action_tools_module.create_action_item_tool(
            description="Buy groceries",
            config=_valid_config(),
        )
        assert res == "Error creating action item. Please try again."
        assert "key_secret_abc123" not in res
        assert "Firestore" not in res

    def test_config_error_sanitized(self, action_tools_module):
        class BrokenConfig:
            def get(self, key):
                raise TypeError("Bad config mapping")

        res = action_tools_module.create_action_item_tool(
            description="Buy coffee",
            config=BrokenConfig(),
        )
        assert res == "Error: Configuration not available"


class TestUpdateActionItemSanitization:
    def test_invalid_due_at_sanitized(self, action_tools_module):
        res = action_tools_module.update_action_item_tool(
            action_item_id="item_999",
            due_at="not-a-valid-timestamp",
            config=_valid_config(),
        )
        assert res.startswith("Error: Invalid due_at format.")
        assert "not-a-valid-timestamp" in res
        assert "ValueError" not in res

    def test_db_exception_sanitized(self, action_tools_module, monkeypatch):
        monkeypatch.setattr(
            action_tools_module.action_items_db,
            "update_action_item",
            MagicMock(side_effect=RuntimeError("Firestore transaction deadlock: token secret_update_token")),
        )
        res = action_tools_module.update_action_item_tool(
            action_item_id="item_999",
            completed=True,
            config=_valid_config(),
        )
        assert res == "Error updating action item. Please try again."
        assert "secret_update_token" not in res
        assert "deadlock" not in res

    def test_config_error_sanitized(self, action_tools_module):
        class BrokenConfig:
            def get(self, key):
                raise AttributeError("No configurable")

        res = action_tools_module.update_action_item_tool(
            action_item_id="item_999",
            completed=True,
            config=BrokenConfig(),
        )
        assert res == "Error: Configuration not available"


def test_snapshot_exception_is_sanitized_before_any_update(action_tools_module, monkeypatch):
    from database import chat_edits

    update = MagicMock()
    monkeypatch.setattr(action_tools_module.action_items_db, 'update_action_item', update)
    monkeypatch.setattr(chat_edits, 'snapshot', MagicMock(side_effect=RuntimeError('secret_snapshot_token')))
    result = action_tools_module.update_action_item_tool('item_999', completed=True, config=_valid_config())
    assert result == 'Error updating action item. Please try again.'
    assert 'secret_snapshot_token' not in result
    update.assert_not_called()
