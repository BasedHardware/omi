"""Tests verifying defensive parameter guards and exception handling in action_item_tools.py.

Hermetic isolated unit test suite covering:
1. get_action_items_tool bounds limit to [1, 500] and offset to >= 0, handling string inputs.
2. get_action_items_tool safely handles non-string, int, and malformed start/end/due dates without AttributeError.
3. create_action_item_tool rejects empty/None/non-string descriptions cleanly.
4. create_action_item_tool safely handles non-string and malformed due_at without AttributeError.
5. update_action_item_tool rejects empty/None/non-string action_item_id.
6. update_action_item_tool safely handles non-string and malformed due_at without AttributeError.
7. Hierarchical uid extraction from configurable and top-level config keys.

Uses memory_import_isolation snapshot_sys_modules and restore_sys_modules to avoid
leaking stubs across test execution.
"""

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

try:
    from tests.unit.memory_import_isolation import (
        AutoMockModule,
        restore_sys_modules,
        snapshot_sys_modules,
    )
except ImportError:
    class AutoMockModule(types.ModuleType):
        def __getattr__(self, name: str):
            if name.startswith("__") and name.endswith("__"):
                raise AttributeError(name)
            mock = MagicMock()
            setattr(self, name, mock)
            return mock

    def snapshot_sys_modules(names):
        return {name: sys.modules.get(name) for name in names}

    def restore_sys_modules(saved):
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


_SYS_MODULE_NAMES = [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database",
    "database.action_items",
    "database.chat_edits",
    "database.notifications",
    "utils",
    "utils.messaging",
    "utils.messaging.undo",
    "utils.messaging.projection",
    "utils.messaging.turn_context",
    "config",
    "config.action_item_reminder_triggers",
    "utils.notifications",
    "utils.model_text",
    "utils.user_clock",
    "utils.retrieval",
    "utils.retrieval.chat_scope",
    "utils.retrieval.turn_refs",
    "utils.retrieval.agentic",
    "utils.retrieval.tools",
    "utils.retrieval.tools._action_item_tools_guards_test",
]

_SYS_MODULES_SNAPSHOT = snapshot_sys_modules(_SYS_MODULE_NAMES)


def _pkg(name: str):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if isinstance(parent, types.ModuleType):
            setattr(parent, attr_name, mod)
    return mod


def _mod(name: str):
    mod = AutoMockModule(name)
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if isinstance(parent, types.ModuleType):
            setattr(parent, attr_name, mod)
    return mod


def _load(module_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


# Install hermetic stubs
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")
_lc_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

_pkg("database")
_db_ai = _mod("database.action_items")
_db_ai.get_action_items.return_value = []
_db_ai.create_action_item.return_value = "item-123"
_db_ai.get_action_item.return_value = {
    "id": "item-123",
    "description": "Existing task",
    "completed": False,
    "due_at": datetime.now(timezone.utc),
}
_db_ai.update_action_item.return_value = True

_pkg("utils")
_pkg("utils.messaging")
_undo = _mod("utils.messaging.undo")
_undo.record_write.return_value = "\nUndo registered."
_mod("utils.messaging.projection")
_mod("utils.messaging.turn_context")

_pkg("config")
_mod("config.action_item_reminder_triggers")

_notif = _mod("utils.notifications")
_model_text = _mod("utils.model_text")
_model_text.count_header = lambda count, word, prefix="": f"{prefix}{count} {word}"
_model_text.format_date = lambda d: str(d)
_model_text.format_instant = lambda d, user_clock=None: str(d)
_model_text.truncation_note = lambda *a, **k: ""

_uclock = _mod("utils.user_clock")
_uclock.clock_for_config = lambda *a, **k: None

_pkg("utils.retrieval")
_chat_scope = _mod("utils.retrieval.chat_scope")
_chat_scope.apply_chat_scope_dates = lambda scope, start, end: (start, end, None)
_chat_scope.chat_scope_from_config = lambda cfg: None

_turn_refs = _mod("utils.retrieval.turn_refs")
_turn_refs.resolve_edit_ref.side_effect = lambda cfg, kind, ref, **kwargs: (ref, None)
_turn_refs.register_record_ref = lambda *a, **k: None

_agentic = _mod("utils.retrieval.agentic")

_pkg("utils.retrieval.tools")

# Load module under test
ait = _load(
    "utils.retrieval.tools._action_item_tools_guards_test",
    "utils/retrieval/tools/action_item_tools.py",
)


def tearDownModule():
    restore_sys_modules(_SYS_MODULES_SNAPSHOT)


class TestActionItemToolsGuards(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_user_42"}}

    # 1. get_action_items_tool bounds limit and offset
    def test_get_action_items_limit_and_offset_coercion(self):
        # String limit and offset
        res = ait.get_action_items_tool.func(limit="25", offset="10", config=self.config)
        self.assertNotIn("Error", res)

        # Out-of-bounds limit capped to 500
        res_capped = ait.get_action_items_tool.func(limit=1000, config=self.config)
        self.assertNotIn("Error", res_capped)

        # Invalid string falls back to default 50
        res_invalid = ait.get_action_items_tool.func(limit="not_a_number", offset="invalid", config=self.config)
        self.assertNotIn("Error", res_invalid)

    # 2. get_action_items_tool non-string or malformed dates
    def test_get_action_items_invalid_dates_handled(self):
        # Non-string dates should not raise AttributeError
        res_int_start = ait.get_action_items_tool.func(start_date=1705672800, config=self.config)
        self.assertIn("Error: Invalid start_date format", res_int_start)

        res_bool_end = ait.get_action_items_tool.func(end_date=True, config=self.config)
        self.assertIn("Error: Invalid end_date format", res_bool_end)

        res_malformed_due_start = ait.get_action_items_tool.func(due_start_date="not-iso", config=self.config)
        self.assertIn("Error: Invalid due_start_date format", res_malformed_due_start)

        res_int_due_end = ait.get_action_items_tool.func(due_end_date=12345, config=self.config)
        self.assertIn("Error: Invalid due_end_date format", res_int_due_end)

    # 3. create_action_item_tool rejects empty/None/non-string description
    def test_create_action_item_description_validation(self):
        res_none = ait.create_action_item_tool.func(description=None, config=self.config)
        self.assertIn("Error: Description is required", res_none)

        res_empty = ait.create_action_item_tool.func(description="", config=self.config)
        self.assertIn("Error: Description is required", res_empty)

        res_whitespace = ait.create_action_item_tool.func(description="   ", config=self.config)
        self.assertIn("Error: Description is required", res_whitespace)

        res_int = ait.create_action_item_tool.func(description=12345, config=self.config)
        self.assertIn("Error: Description is required", res_int)

    # 4. create_action_item_tool non-string or malformed due_at
    def test_create_action_item_invalid_due_at(self):
        res_int = ait.create_action_item_tool.func(description="Buy groceries", due_at=1705672800, config=self.config)
        self.assertIn("Error: Invalid due_at format", res_int)

        res_malformed = ait.create_action_item_tool.func(description="Buy groceries", due_at="invalid-date", config=self.config)
        self.assertIn("Error: Invalid due_at format", res_malformed)

    # 5. update_action_item_tool rejects invalid action_item_id
    def test_update_action_item_id_validation(self):
        res_none = ait.update_action_item_tool.func(action_item_id=None, config=self.config)
        self.assertIn("Error: action_item_id is required", res_none)

        res_empty = ait.update_action_item_tool.func(action_item_id="", config=self.config)
        self.assertIn("Error: action_item_id is required", res_empty)

        res_int = ait.update_action_item_tool.func(action_item_id=12345, config=self.config)
        self.assertIn("Error: action_item_id is required", res_int)

    # 6. update_action_item_tool non-string or malformed due_at
    def test_update_action_item_invalid_due_at(self):
        res_int = ait.update_action_item_tool.func(action_item_id="item-123", due_at=1705672800, config=self.config)
        self.assertIn("Error: Invalid due_at format", res_int)

        res_malformed = ait.update_action_item_tool.func(action_item_id="item-123", due_at="bad-date", config=self.config)
        self.assertIn("Error: Invalid due_at format", res_malformed)

    # 7. Config hierarchical UID resolution
    def test_hierarchical_uid_resolution(self):
        # Nested configurable uid
        res_nested_uid = ait.get_action_items_tool.func(config={"configurable": {"uid": "user_nested"}})
        self.assertNotIn("User ID not found", res_nested_uid)

        # Top-level user_id
        res_top_user_id = ait.get_action_items_tool.func(config={"user_id": "user_top"})
        self.assertNotIn("User ID not found", res_top_user_id)

        # Top-level uid
        res_top_uid = ait.get_action_items_tool.func(config={"uid": "user_top_uid"})
        self.assertNotIn("User ID not found", res_top_uid)


if __name__ == "__main__":
    unittest.main()
