"""Tests verifying memory_tools.py validation, configurable resilience, and boundary handling.

Ensures that get_memories_tool and search_memories_tool safely handle None configurable
dictionaries, top-level user_id, coerce string limit/offset, validate non-empty queries,
and publish memory refs without unhandled exceptions.
"""

import os
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

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
def _memory_tools_module():
    """Load memory_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    mock_firestore = _module("database._client", db=MagicMock())
    mock_mem_models = _module("models.memories", MemoryDB=MagicMock())

    mock_service_instance = MagicMock()
    mock_service_instance.get_memories.return_value = []
    mock_service_instance.search.return_value = []
    mock_service = _module("utils.memory.memory_service", MemoryService=MagicMock(return_value=mock_service_instance))

    mock_model_text = _module(
        "utils.model_text",
        format_date=lambda *a: "2026-01-01",
        format_instant=lambda *a: "2026-01-01 12:00:00",
        lookup_failed=lambda k: f"Failed to look up {k}",
        truncation_note=lambda *a, **k: "Truncated",
    )
    mock_clock = _module("utils.user_clock", clock_for_config=MagicMock(return_value=MagicMock()))
    mock_privacy = _module(
        "utils.messaging.memory_privacy",
        channel_private_filter_active=MagicMock(return_value=False),
        is_channel_private_memory=MagicMock(return_value=False),
        omit_channel_private=lambda mems, conf: mems,
    )
    mock_scope = _module(
        "utils.retrieval.chat_scope",
        apply_chat_scope_dates=lambda scope, start, end: (start, end, None),
        chat_scope_from_config=MagicMock(return_value=None),
    )
    mock_register_ref = MagicMock()
    mock_refs = _module("utils.retrieval.turn_refs", register_record_ref=mock_register_ref)
    mock_evidence = _module(
        "utils.retrieval.memory_evidence",
        MAX_MEMORY_EVIDENCE_CHARS=10000,
        format_memory_evidence=lambda c, **k: f"Evidence: {c}",
        render_memory_evidence=lambda title, recs, **k: f"{title}: " + ", ".join(recs),
    )
    mock_bounds = _module(
        "utils.retrieval.tools.result_bounds",
        cap_items_for_llm=lambda items, cap: (items[:cap], len(items), len(items) > cap),
    )
    mock_projection = _module("utils.messaging.projection", surface_runtime=MagicMock(get=MagicMock(return_value=None)))

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database._client": mock_firestore,
        "models": _package("models"),
        "models.memories": mock_mem_models,
        "utils": _package("utils"),
        "utils.memory": _package("utils.memory"),
        "utils.memory.memory_service": mock_service,
        "utils.model_text": mock_model_text,
        "utils.user_clock": mock_clock,
        "utils.messaging": _package("utils.messaging"),
        "utils.messaging.memory_privacy": mock_privacy,
        "utils.messaging.projection": mock_projection,
        "utils.retrieval": _package("utils.retrieval"),
        "utils.retrieval.chat_scope": mock_scope,
        "utils.retrieval.turn_refs": mock_refs,
        "utils.retrieval.memory_evidence": mock_evidence,
        "utils.retrieval.tools": _package("utils.retrieval.tools"),
        "utils.retrieval.tools.result_bounds": mock_bounds,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._memory_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "memory_tools.py"),
        )
        globals()["memory_mod"] = module
        globals()["mock_service_inst"] = mock_service_instance
        globals()["mock_register_ref"] = mock_register_ref
        yield
        globals().pop("memory_mod", None)
        globals().pop("mock_service_inst", None)
        globals().pop("mock_register_ref", None)


class TestMemoryTools(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid"}}
        mock_service_inst.get_memories.reset_mock()
        mock_service_inst.read.reset_mock()
        mock_service_inst.search.reset_mock()
        mock_register_ref.reset_mock()

    def test_get_memories_handles_top_level_uid(self):
        res = memory_mod.get_memories_tool.func(config={"user_id": "top_uid"})
        self.assertIn("No memories found", res)

    def test_get_memories_handles_configurable_none(self):
        res = memory_mod.get_memories_tool.func(config={"configurable": None})
        self.assertEqual(res, "Error: User ID not found in configuration")

    def test_get_memories_coerces_string_limit_and_offset(self):
        res = memory_mod.get_memories_tool.func(limit="100", offset="5", config=self.config)
        self.assertIn("No memories found", res)
        # Verify coerced integer values reach the service read call
        mock_service_inst.read.assert_called_once()
        _, kwargs = mock_service_inst.read.call_args
        self.assertIsInstance(kwargs.get("limit"), int)
        self.assertIsInstance(kwargs.get("offset"), int)
        self.assertEqual(kwargs.get("limit"), 105)
        self.assertEqual(kwargs.get("offset"), 0)

    def test_search_memories_handles_top_level_uid(self):
        res = memory_mod.search_memories_tool.func(
            query="coffee preference",
            config={"user_id": "top_uid"}
        )
        self.assertIn("No memories found matching 'coffee preference'", res)

    def test_search_memories_guards_empty_query(self):
        res_empty = memory_mod.search_memories_tool.func(query="   ", config=self.config)
        self.assertEqual(res_empty, "Error: Query is required to search memories.")

        res_none = memory_mod.search_memories_tool.func(query=None, config=self.config)
        self.assertEqual(res_none, "Error: Query is required to search memories.")

    def test_search_memories_coerces_string_limit(self):
        res = memory_mod.search_memories_tool.func(
            query="travel goals",
            limit="10",
            config=self.config
        )
        self.assertIn("No memories found matching 'travel goals'", res)
        # Verify coerced integer limit reaches the service search call
        mock_service_inst.search.assert_called_once_with("test_uid", "travel goals", limit=10)

    def test_publish_memory_refs_handles_none_configurable(self):
        # Must gracefully return without error and not register refs when memories list is empty
        memory_mod._publish_memory_refs(None, [])
        mock_register_ref.assert_not_called()

        # Must safely fallback to empty dict for configurable and register memory id
        fake_mem = MagicMock(id="mem_test_123", content="Loves dark roast coffee")
        memory_mod._publish_memory_refs(None, [fake_mem])
        mock_register_ref.assert_called_once_with({}, 'memories', 'mem_test_123')


if __name__ == "__main__":
    unittest.main()
