"""Tests verifying exception hardening and information disclosure protection in action_item_tools.

Ensures that database errors, malformed dates, and runtime exceptions are sanitized into
generic user-friendly messages and never disclose internal stack traces, DB credentials,
or raw exception representations.
"""

from __future__ import annotations

import contextvars
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def action_tools_module():
    """Load utils.retrieval.tools.action_item_tools with isolated stubs."""
    db_action_items = ModuleType("database.action_items")
    db_action_items.get_action_items = MagicMock(return_value=[])
    db_action_items.create_action_item = MagicMock(return_value="test_item_123")
    db_action_items.get_action_item = MagicMock(
        return_value={
            "id": "test_item_123",
            "description": "Test task",
            "completed": False,
            "due_at": datetime.now(timezone.utc),
        }
    )
    db_action_items.update_action_item = MagicMock(return_value=True)

    db_notifications = ModuleType("database.notifications")
    db_notifications.get_user_time_zone = MagicMock(return_value="UTC")

    utils_notifications = ModuleType("utils.notifications")
    utils_notifications.send_action_item_completed_notification = MagicMock()
    utils_notifications.send_action_item_created_notification = MagicMock()
    utils_notifications.send_action_item_data_message = MagicMock()
    utils_notifications.sync_action_item_reminder = MagicMock()

    utils_conversations_render = ModuleType("utils.conversations.render")
    utils_conversations_render.resolve_display_tz = lambda tz: (ZoneInfo(tz) if tz else timezone.utc, tz or "UTC")
    utils_conversations_render.format_local_time = lambda dt, display_tz, tz_label: f"{dt.isoformat()} {tz_label}"

    utils_retrieval_chat_scope = ModuleType("utils.retrieval.chat_scope")
    utils_retrieval_chat_scope.apply_chat_scope_dates = lambda scope, s, e: (s, e, None)
    utils_retrieval_chat_scope.chat_scope_from_config = lambda c: c.get("chat_scope") if isinstance(c, dict) else None

    utils_retrieval_agentic = ModuleType("utils.retrieval.agentic")
    utils_retrieval_agentic.agent_config_context = contextvars.ContextVar("agent_config", default=None)

    langchain_core_tools = ModuleType("langchain_core.tools")
    langchain_core_tools.tool = lambda f: f

    langchain_core_runnables = ModuleType("langchain_core.runnables")
    langchain_core_runnables.RunnableConfig = dict

    fakes: dict[str, ModuleType | None] = {
        "database.action_items": db_action_items,
        "database.notifications": db_notifications,
        "utils.notifications": utils_notifications,
        "utils.conversations.render": utils_conversations_render,
        "utils.retrieval.chat_scope": utils_retrieval_chat_scope,
        "utils.retrieval.agentic": utils_retrieval_agentic,
        "langchain_core.tools": langchain_core_tools,
        "langchain_core.runnables": langchain_core_runnables,
    }

    tool_path = BACKEND_DIR / "utils" / "retrieval" / "tools" / "action_item_tools.py"
    with stub_modules(fakes):
        mod = load_module_fresh("utils.retrieval.tools.action_item_tools", str(tool_path))
        yield mod


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
