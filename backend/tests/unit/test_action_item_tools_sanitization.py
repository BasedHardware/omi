import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock, patch

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent.parent


def _register(name: str):
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr = name.rsplit(".", 1)
        setattr(_register(parent_name), attr, mod)
    return mod


for _name in [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database",
    "database.action_items",
    "database.notifications",
    "utils",
    "utils.notifications",
    "utils.conversations",
    "utils.conversations.render",
    "utils.retrieval",
    "utils.retrieval.chat_scope",
    "utils.retrieval.agentic",
    "utils.retrieval.tools",
]:
    _register(_name)

# Passthrough @tool decorator so the tool stays a plain callable.
sys.modules["langchain_core.tools"].tool = lambda func=None, **kw: (func if func is not None else (lambda f: f))
sys.modules["langchain_core.runnables"].RunnableConfig = dict

# Stub utils.notifications functions
notif_mod = sys.modules["utils.notifications"]
notif_mod.send_action_item_completed_notification = MagicMock()
notif_mod.send_action_item_created_notification = MagicMock()
notif_mod.send_action_item_data_message = MagicMock()
notif_mod.sync_action_item_reminder = MagicMock()

# Stub utils.conversations.render
render_mod = sys.modules["utils.conversations.render"]
render_mod.format_local_time = lambda dt, tz: str(dt)
render_mod.resolve_display_tz = lambda tz: (None, "UTC")

# Stub utils.retrieval.chat_scope
chat_scope_mod = sys.modules["utils.retrieval.chat_scope"]
chat_scope_mod.apply_chat_scope_dates = lambda scope, s, e: (s, e, None)
chat_scope_mod.chat_scope_from_config = lambda config: None


def _load_module_from_file(module_name: str, file_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


action_item_tools = _load_module_from_file(
    "utils.retrieval.tools.action_item_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "action_item_tools.py",
)


def test_get_action_items_tool_invalid_date_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    res = action_item_tools.get_action_items_tool(start_date="invalid-iso-date-format", config=config)
    assert res.startswith("Error: Invalid start_date format.")
    assert "ValueError" not in res
    assert "ISO format" not in res


def test_get_action_items_tool_db_exception_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    action_items_db = sys.modules["database.action_items"]
    action_items_db.get_action_items = MagicMock(side_effect=RuntimeError("internal_db_crash_secret_path_0x123"))

    res = action_item_tools.get_action_items_tool(config=config)
    assert res == "Error retrieving action items."
    assert "internal_db_crash_secret_path_0x123" not in res


def test_create_action_item_tool_invalid_due_at_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    res = action_item_tools.create_action_item_tool(
        description="Write code",
        due_at="bad-due-date",
        config=config,
    )
    assert res.startswith("Error: Invalid due_at format.")
    assert "ValueError" not in res


def test_create_action_item_tool_db_exception_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    action_items_db = sys.modules["database.action_items"]
    action_items_db.create_action_item = MagicMock(side_effect=RuntimeError("secret_database_token_leak"))

    res = action_item_tools.create_action_item_tool(
        description="Buy groceries",
        config=config,
    )
    assert res == "Error creating action item."
    assert "secret_database_token_leak" not in res


def test_update_action_item_tool_lookup_db_exception_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    action_items_db = sys.modules["database.action_items"]
    action_items_db.get_action_item = MagicMock(side_effect=RuntimeError("redis_pool_exhausted_at_internal_ip"))

    res = action_item_tools.update_action_item_tool(
        action_item_id="item-123",
        completed=True,
        config=config,
    )
    assert res == "Error updating action item."
    assert "redis_pool_exhausted_at_internal_ip" not in res


def test_update_action_item_tool_update_db_exception_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    action_items_db = sys.modules["database.action_items"]
    action_items_db.get_action_item = MagicMock(return_value={"id": "item-123", "description": "Existing"})
    action_items_db.update_action_item = MagicMock(side_effect=RuntimeError("firestore_write_quorum_failure_details"))

    res = action_item_tools.update_action_item_tool(
        action_item_id="item-123",
        description="New description",
        config=config,
    )
    assert res == "Error updating action item."
    assert "firestore_write_quorum_failure_details" not in res


if __name__ == "__main__":
    test_get_action_items_tool_invalid_date_sanitized()
    test_get_action_items_tool_db_exception_sanitized()
    test_create_action_item_tool_invalid_due_at_sanitized()
    test_create_action_item_tool_db_exception_sanitized()
    test_update_action_item_tool_lookup_db_exception_sanitized()
    test_update_action_item_tool_update_db_exception_sanitized()
    print("All action item tools sanitization unit tests passed successfully!")
