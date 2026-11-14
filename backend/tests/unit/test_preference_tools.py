"""Tests verifying preference_tools.py validation, null-safety, and ledger/memory updates.

Ensures that save_user_preference_tool safely handles None replace_memory_id,
rejects empty preference strings, and correctly writes to the knowledge ledger.
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
def _preference_tools_module():
    """Load preference_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    mock_db_client = MagicMock()
    mock_firestore = _module("database._client", get_data_plane_firestore_client=MagicMock(return_value=mock_db_client))
    mock_undo = _module("utils.messaging.undo", record_write=MagicMock(return_value=""))
    mock_proj = _module("utils.messaging.projection", surface_runtime=MagicMock(get=MagicMock(return_value=None)))
    mock_policy = _module("models.knowledge_ledger_policy", canonicalize_ledger_slot=lambda s, strict=False: s)
    mock_contracts = _module("models.memory_contracts", deterministic_contract_id=lambda name, d: "det_id_12345678901234567890123456789012")

    class FakeWriterMode:
        compatibility = "compatibility"
        ledger = "ledger"
        def __init__(self, val):
            self.value = val
        def __eq__(self, other):
            return self.value == getattr(other, "value", other)

    mock_apply = _module("models.memory_apply", WriterMode=FakeWriterMode)

    class FakeMemoryDB:
        @staticmethod
        def calculate_score(m):
            return 1.0
        @staticmethod
        def model_validate(d):
            return MagicMock()

    mock_memories = _module("models.memories", MemoryDB=FakeMemoryDB)

    class FakeReason:
        agent_reusable_conclusion = MagicMock(value="agent_reusable_conclusion")

    mock_prod_mem = _module("models.product_memory", LedgerWriteReason=FakeReason)
    mock_sanitizer = _module("utils.log_sanitizer", sanitize_pii=lambda x: str(x))

    mock_canon = _module(
        "utils.memory.canonical_memory_adapter",
        read_canonical_memory_item=MagicMock(return_value=None),
        search_canonical_memories=MagicMock(return_value=[]),
    )

    class FakeLedgerProv:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.source_id = kwargs.get("source_id", "src")
        def model_copy(self, update=None):
            return self

    mock_ledger = _module(
        "utils.memory.knowledge_ledger",
        LedgerProvenance=FakeLedgerProv,
        save_fact=MagicMock(return_value="fact_123"),
        amend_fact=MagicMock(return_value="amended_123"),
    )

    class FakeMemoryService:
        def __init__(self, **kwargs):
            pass
        def create_external_memory(self, *args, **kwargs):
            pass
        def update_external_memory_content(self, *args, **kwargs):
            pass

    mock_mem_svc = _module("utils.memory.memory_service", MemoryService=FakeMemoryService)
    mock_mem_sys = _module(
        "utils.memory.memory_system",
        MemorySystem=MagicMock(CANONICAL="canonical"),
        ensure_canonical_apply_control_state=MagicMock(return_value=MagicMock(writer_mode="ledger")),
    )
    mock_live_cap = _module("testing.parity_pack_v0.live_capture", capture_memory_write=MagicMock())

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database._client": mock_firestore,
        "utils": _package("utils"),
        "utils.messaging": _package("utils.messaging"),
        "utils.messaging.undo": mock_undo,
        "utils.messaging.projection": mock_proj,
        "models": _package("models"),
        "models.knowledge_ledger_policy": mock_policy,
        "models.memory_contracts": mock_contracts,
        "models.memory_apply": mock_apply,
        "models.memories": mock_memories,
        "models.product_memory": mock_prod_mem,
        "utils.log_sanitizer": mock_sanitizer,
        "utils.memory": _package("utils.memory"),
        "utils.memory.canonical_memory_adapter": mock_canon,
        "utils.memory.knowledge_ledger": mock_ledger,
        "utils.memory.memory_service": mock_mem_svc,
        "utils.memory.memory_system": mock_mem_sys,
        "testing": _package("testing"),
        "testing.parity_pack_v0": _package("testing.parity_pack_v0"),
        "testing.parity_pack_v0.live_capture": mock_live_cap,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._preference_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "preference_tools.py"),
        )
        globals()["pref_tool"] = module
        globals()["mock_ledger"] = mock_ledger
        globals()["mock_canon"] = mock_canon
        yield
        globals().pop("pref_tool", None)
        globals().pop("mock_ledger", None)
        globals().pop("mock_canon", None)


class TestPreferenceTools(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid_123"}}

    def test_handles_none_replace_memory_id(self):
        mock_canon.search_canonical_memories.return_value = []
        res = pref_tool.save_user_preference_tool.func(
            preference="Prefers metric units",
            replace_memory_id=None,
            config=self.config,
        )
        self.assertIn("Preference saved (memory_id=fact_123): Prefers metric units", res)

    def test_rejects_empty_preference(self):
        res1 = pref_tool.save_user_preference_tool.func(
            preference="",
            config=self.config,
        )
        self.assertEqual(res1, "Error: Preference content cannot be empty")

        res2 = pref_tool.save_user_preference_tool.func(
            preference="   ",
            config=self.config,
        )
        self.assertEqual(res2, "Error: Preference content cannot be empty")

        res3 = pref_tool.save_user_preference_tool.func(
            preference=None,
            config=self.config,
        )
        self.assertEqual(res3, "Error: Preference content cannot be empty")

    def test_missing_user_id(self):
        res = pref_tool.save_user_preference_tool.func(
            preference="Likes dark mode",
            config={},
        )
        self.assertEqual(res, "Error: Could not determine user ID")

    def test_detects_duplicate_preference(self):
        mock_canon.search_canonical_memories.return_value = [
            {"content": "Likes dark mode", "score": 0.99, "memory_id": "mem_existing"}
        ]
        res = pref_tool.save_user_preference_tool.func(
            preference="Likes dark mode",
            config=self.config,
        )
        self.assertIn("Similar preference already exists (memory_id=mem_existing): Likes dark mode", res)


if __name__ == "__main__":
    unittest.main()
