"""Tests verifying edit_tools.py validation, configurable resilience, and error handling.

Ensures that chat edit tools safely handle None configurable dictionaries,
null string parameters, and invalid references without raising unhandled exceptions.
"""

import os
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


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
def _edit_tools_module():
    """Load edit_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    mock_conversations = _module(
        "database.conversations",
        get_conversation=MagicMock(return_value={"id": "conv_1", "deleted": False}),
        prepare_conversation_for_read=MagicMock(return_value={"structured": {}, "user_corrections": []}),
        update_conversation_chat=MagicMock(return_value={"id": "conv_1"}),
    )
    mock_users = _module("database.users", get_person=MagicMock(return_value={"id": "p_1"}))
    mock_firestore = _module("database._client", get_data_plane_firestore_client=MagicMock())
    mock_mem_svc = _module("utils.memory.memory_service", MemoryService=MagicMock())
    mock_mem_sys = _module("utils.memory.memory_system", MemorySystem=MagicMock(CANONICAL="canonical"))
    mock_canon = _module(
        "utils.memory.canonical_memory_adapter",
        read_canonical_memory_item=MagicMock(return_value=MagicMock(uid="test_uid", promotion={})),
    )
    mock_chat_edits = _module(
        "database.chat_edits",
        envelope=lambda data, desc: data,
        snapshot=MagicMock(return_value={}),
        decode=MagicMock(return_value={}),
    )
    mock_undo = _module("utils.messaging.undo", record_write=MagicMock(return_value=""))
    mock_mcp = _module("utils.mcp_server.handlers.other", rename_person=MagicMock(return_value={"person": {"name": "Alice"}}))

    def fake_resolve(conf, cat, entity_id, parameter="id", default_to_attachment=False):
        return entity_id or "resolved_id", None

    def fake_tool_error(code, msg):
        return f"Error [{code}]: {msg}"

    mock_refs = _module("utils.retrieval.turn_refs", resolve_edit_ref=fake_resolve, tool_error=fake_tool_error)

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database.conversations": mock_conversations,
        "database.users": mock_users,
        "database._client": mock_firestore,
        "database.chat_edits": mock_chat_edits,
        "utils": _package("utils"),
        "utils.memory": _package("utils.memory"),
        "utils.memory.memory_service": mock_mem_svc,
        "utils.memory.memory_system": mock_mem_sys,
        "utils.memory.canonical_memory_adapter": mock_canon,
        "utils.messaging": _package("utils.messaging"),
        "utils.messaging.undo": mock_undo,
        "utils.mcp_server": _package("utils.mcp_server"),
        "utils.mcp_server.handlers": _package("utils.mcp_server.handlers"),
        "utils.mcp_server.handlers.other": mock_mcp,
        "utils.retrieval": _package("utils.retrieval"),
        "utils.retrieval.turn_refs": mock_refs,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._edit_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "edit_tools.py"),
        )
        globals()["edit_mod"] = module
        yield
        globals().pop("edit_mod", None)


class TestEditTools(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid"}}

    def test_owner_handles_configurable_none(self):
        with self.assertRaises(PermissionError):
            edit_mod.owner({"configurable": None})

    def test_owner_handles_top_level_uid(self):
        self.assertEqual(edit_mod.owner({"user_id": "top_uid"}), "top_uid")

    def test_update_conversation_guards_none_correction(self):
        res = edit_mod.update_conversation.func(
            conversation_id="conv_1",
            correction=None,
            title="New Title",
            config=self.config,
        )
        self.assertIn("Error [invalid_correction]", res)

    def test_rename_person_guards_none_name(self):
        res = edit_mod.rename_person.func(
            person_id="p_1",
            name=None,
            config=self.config,
        )
        self.assertEqual(res, "Error: person name must not be empty.")

    def test_edit_memory_guards_none_content(self):
        res = edit_mod.edit_memory.func(
            memory_id="m_1",
            content=None,
            config=self.config,
        )
        self.assertEqual(res, "Error: memory content must contain 1 to 20000 characters.")


if __name__ == "__main__":
    unittest.main()
