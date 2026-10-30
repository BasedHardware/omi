"""Tests verifying action_item_tools.py validation, configurable resilience, and boundary handling.

Ensures that get_action_items_tool, create_action_item_tool, and update_action_item_tool
safely handle None configurable dictionaries, top-level user_id, coerce string limit/offset,
validate non-empty descriptions and IDs, and return structured error responses without unhandled exceptions.
"""

import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _module(name, **attrs):
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _package(name):
    mod = _module(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    return mod


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


@pytest.fixture(scope="module", autouse=True)
def _action_item_tools_module():
    """Load action_item_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    def _mock_update(uid, action_item_id, update_data, expected_chat_state=None):
        if expected_chat_state is not None:
            expected_chat_state["after"] = {}
        return True

    mock_db = _module(
        "database.action_items",
        get_action_items=MagicMock(return_value=[]),
        get_action_item=MagicMock(return_value={"id": "task_1", "description": "Buy groceries", "completed": False}),
        create_action_item=MagicMock(return_value="task_1"),
        update_action_item=MagicMock(side_effect=_mock_update),
    )

    mock_notif = _module(
        "utils.notifications",
        send_action_item_completed_notification=MagicMock(),
        send_action_item_created_notification=MagicMock(),
        send_action_item_data_message=MagicMock(),
        sync_action_item_reminder=MagicMock(),
    )

    mock_undo = _module("utils.messaging.undo", record_write=MagicMock(return_value=""))
    mock_projection = _module("utils.messaging.projection", surface_runtime=MagicMock(get=MagicMock(return_value=None)))
    mock_turn = _module("utils.messaging.turn_context", phone_reminder_confirmation=MagicMock(return_value=""))
    mock_triggers = _module(
        "config.action_item_reminder_triggers",
        action_item_write_affects_reminder=MagicMock(return_value=False),
    )

    mock_refs = _module(
        "utils.retrieval.turn_refs",
        register_record_ref=MagicMock(),
        resolve_edit_ref=lambda conf, cat, entity_id, parameter="id": (entity_id or "resolved_id", None),
    )

    mock_scope = _module(
        "utils.retrieval.chat_scope",
        apply_chat_scope_dates=lambda scope, start, end: (start, end, None),
        chat_scope_from_config=MagicMock(return_value=None),
    )

    mock_clock = _module("utils.user_clock", clock_for_config=MagicMock(return_value=MagicMock()))

    mock_chat_edits = _module(
        "database.chat_edits",
        envelope=lambda data, desc: data,
        snapshot=MagicMock(return_value={"before": {}, "after": {}}),
    )

    utils_pkg = _package("utils")
    model_text_mod = load_module_fresh(
        "utils.model_text",
        str(BACKEND_DIR / "utils" / "model_text.py"),
    )
    utils_pkg.model_text = model_text_mod

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database.action_items": mock_db,
        "database.chat_edits": mock_chat_edits,
        "utils": utils_pkg,
        "utils.model_text": model_text_mod,
        "utils.notifications": mock_notif,
        "utils.messaging": _package("utils.messaging"),
        "utils.messaging.undo": mock_undo,
        "utils.messaging.projection": mock_projection,
        "utils.messaging.turn_context": mock_turn,
        "config.action_item_reminder_triggers": mock_triggers,
        "utils.retrieval": _package("utils.retrieval"),
        "utils.retrieval.turn_refs": mock_refs,
        "utils.retrieval.chat_scope": mock_scope,
        "utils.user_clock": mock_clock,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._action_item_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "action_item_tools.py"),
        )
        globals()["action_mod"] = module
        globals()["mock_db"] = mock_db
        yield
        globals().pop("action_mod", None)
        globals().pop("mock_db", None)


class TestActionItemTools(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid"}}
        mock_db.get_action_items.reset_mock()
        mock_db.get_action_item.reset_mock()
        mock_db.create_action_item.reset_mock()
        mock_db.update_action_item.reset_mock()

    def test_get_action_items_handles_top_level_uid(self):
        res = action_mod.get_action_items_tool.func(config={"user_id": "top_uid"})
        self.assertIn("No action items found", res)
        mock_db.get_action_items.assert_called()

    def test_get_action_items_handles_configurable_none(self):
        res = action_mod.get_action_items_tool.func(config={"configurable": None})
        self.assertEqual(res, "Error: User ID not found in configuration")

    def test_get_action_items_coerces_string_limit_and_offset(self):
        res = action_mod.get_action_items_tool.func(limit="100", offset="5", config=self.config)
        self.assertIn("No action items found", res)
        mock_db.get_action_items.assert_called_with(
            uid="test_uid",
            conversation_id=None,
            completed=None,
            start_date=None,
            end_date=None,
            due_start_date=None,
            due_end_date=None,
            limit=100,
            offset=5,
        )

    def test_get_action_items_clamps_large_limit(self):
        res = action_mod.get_action_items_tool.func(limit="999", offset="-10", config=self.config)
        self.assertIn("No action items found", res)
        mock_db.get_action_items.assert_called_with(
            uid="test_uid",
            conversation_id=None,
            completed=None,
            start_date=None,
            end_date=None,
            due_start_date=None,
            due_end_date=None,
            limit=500,
            offset=0,
        )

    def test_create_action_item_handles_top_level_uid(self):
        res = action_mod.create_action_item_tool.func(
            description="Buy groceries",
            config={"user_id": "top_uid"},
        )
        self.assertIn("Added: Buy groceries", res)

    def test_create_action_item_guards_empty_description(self):
        res = action_mod.create_action_item_tool.func(
            description="   ",
            config=self.config,
        )
        self.assertEqual(res, "Error: Description is required to create an action item.")

    def test_update_action_item_handles_top_level_uid(self):
        res = action_mod.update_action_item_tool.func(
            action_item_id="task_1",
            completed=True,
            config={"user_id": "top_uid"},
        )
        self.assertIn("Successfully updated action item", res)

    def test_update_action_item_guards_empty_id(self):
        res = action_mod.update_action_item_tool.func(
            action_item_id="",
            config=self.config,
        )
        self.assertEqual(res, "Error: Action item ID is required.")


if __name__ == "__main__":
    unittest.main()
