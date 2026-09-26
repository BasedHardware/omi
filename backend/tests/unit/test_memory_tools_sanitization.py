"""Exception-leak guards for memory chat tools.

get_memories_tool and search_memories_tool must never interpolate raw exception
text into LLM-facing strings. Invalid temporal arguments, chat_scope date
failures, and retrieval crashes return fixed messages; details stay in logs.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from tests.unit.memory_import_isolation import (
    AutoMockModule,
    install_database_client_stub,
    restore_sys_modules,
    snapshot_sys_modules,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
MEMORY_TOOLS_PATH = BACKEND_DIR / "utils" / "retrieval" / "tools" / "memory_tools.py"
SENSITIVE = "postgresql://user:super_secret_password@internal-db.prod.local:5432/omi"

STUBBED = (
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database.notifications",
    "models.memories",
    "utils.memory.memory_service",
    "utils.memory.belief_model",
    "utils.conversations.render",
    "utils.retrieval.chat_scope",
    "utils.retrieval.memory_evidence",
    "utils.retrieval.tools.result_bounds",
    "utils.retrieval.agentic",
)

PACKAGES = (
    "database",
    "models",
    "utils",
    "utils.memory",
    "utils.conversations",
    "utils.retrieval",
    "utils.retrieval.tools",
)


def _ensure_pkg(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if not isinstance(mod, types.ModuleType) or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = mod
    if "." in name:
        parent_name, attr = name.rsplit(".", 1)
        parent = _ensure_pkg(parent_name)
        setattr(parent, attr, mod)
    return mod


def _load_memory_tools():
    names = list(STUBBED) + list(PACKAGES) + ["database._client", "utils.retrieval.tools.memory_tools"]
    saved = snapshot_sys_modules(names)
    install_database_client_stub()

    for name in PACKAGES:
        _ensure_pkg(name)
    for name in STUBBED:
        sys.modules[name] = AutoMockModule(name)

    sys.modules["langchain_core.tools"].tool = lambda func=None, **_kw: (func if func is not None else (lambda f: f))
    sys.modules["langchain_core.runnables"].RunnableConfig = dict

    models_memories = sys.modules["models.memories"]
    models_memories.MemoryDB = type("MemoryDB", (), {})

    belief = sys.modules["utils.memory.belief_model"]
    belief.belief_model_enabled = lambda: True
    belief.memory_use_suppressed = lambda *_a, **_k: False
    belief.normalize_temporal_read_view = lambda view: view or "released"

    render = sys.modules["utils.conversations.render"]
    render.format_local_date = lambda value, *a, **k: str(value)
    render.resolve_display_tz = lambda _uid: (None, None)

    chat_scope = sys.modules["utils.retrieval.chat_scope"]
    chat_scope.chat_scope_from_config = lambda _cfg: None
    chat_scope.apply_chat_scope_dates = lambda scope, start, end: (start, end, None)

    evidence = sys.modules["utils.retrieval.memory_evidence"]
    evidence.MAX_MEMORY_EVIDENCE_CHARS = 1000
    evidence.format_memory_evidence = lambda *a, **k: "memory"
    evidence.render_memory_evidence = lambda records, **k: "\n".join(records)

    sys.modules["utils.retrieval.tools.result_bounds"].cap_items_for_llm = lambda items, **k: items
    sys.modules["database.notifications"].get_user_time_zone = lambda uid: None

    sys.modules.pop("utils.retrieval.tools.memory_tools", None)
    spec = importlib.util.spec_from_file_location("utils.retrieval.tools.memory_tools", MEMORY_TOOLS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["utils.retrieval.tools.memory_tools"] = module
    spec.loader.exec_module(module)
    return module, saved


import unittest


class TestMemoryToolsExceptionLeak(unittest.TestCase):
    def setUp(self):
        self.module, self.saved = _load_memory_tools()
        self.config = {"configurable": {"user_id": "uid-1"}}

    def tearDown(self):
        restore_sys_modules(self.saved)

    def test_invalid_temporal_view_does_not_leak(self):
        def boom(_view):
            raise ValueError(f"bad view {SENSITIVE}")

        self.module.normalize_temporal_read_view = boom
        result = self.module.get_memories_tool(view="nope", config=self.config)
        assert result == "Error: Invalid temporal read arguments."
        assert SENSITIVE not in result

    def test_invalid_as_of_does_not_leak(self):
        def bad_parse(_value):
            raise ValueError(f"cannot parse {SENSITIVE}")

        self.module._parse_aware_iso = bad_parse
        result = self.module.get_memories_tool(view="history", as_of="2026-01-01T00:00:00Z", config=self.config)
        assert result == "Error: Invalid temporal read arguments."
        assert SENSITIVE not in result

    def test_search_invalid_as_of_does_not_leak(self):
        def bad_parse(_value):
            raise ValueError(f"cannot parse {SENSITIVE}")

        self.module._parse_aware_iso = bad_parse
        result = self.module.search_memories_tool(
            query="hi", view="history", as_of="2026-01-01T00:00:00Z", config=self.config
        )
        assert result == "Error: Invalid temporal read arguments."
        assert SENSITIVE not in result

    def test_invalid_start_date_does_not_leak_parser_message(self):
        class BoomDateTime:
            @staticmethod
            def fromisoformat(_value):
                raise ValueError(f"unconverted data remains {SENSITIVE}")

        old = self.module.datetime
        self.module.datetime = BoomDateTime
        try:
            result = self.module.get_memories_tool(start_date="not-a-date", config=self.config)
        finally:
            self.module.datetime = old
        assert result.startswith("Error: Invalid start_date format.")
        assert SENSITIVE not in result
        assert "unconverted data remains" not in result

    def test_chat_scope_parse_error_is_generic(self):
        scope = {"start_date": "2026-01-01T00:00:00Z"}

        def bad_parse(value):
            # Leave the tool's own as_of=None path untouched; fail only scope dates.
            if value is None:
                return None
            raise ValueError(f"scope parse {SENSITIVE}")

        self.module._parse_aware_iso = bad_parse
        self.module.chat_scope_from_config = lambda _cfg: scope
        self.module.apply_chat_scope_dates = lambda scope, start, end: (start, end, None)
        result = self.module.search_memories_tool(query="hi", config=self.config)
        assert result == "Error: chat_scope dates invalid."
        assert SENSITIVE not in result

    def test_search_crash_is_generic(self):
        class BoomService:
            def __init__(self, *a, **k):
                raise RuntimeError(f"db down {SENSITIVE}")

        self.module.MemoryService = BoomService
        result = self.module.search_memories_tool(query="hello", config=self.config)
        assert result == "Error searching memories."
        assert SENSITIVE not in result


if __name__ == "__main__":
    unittest.main()
