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
    mod.__path__ = []
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
    "database._client",
    "database.notifications",
    "models",
    "models.memories",
    "utils",
    "utils.memory",
    "utils.memory.memory_service",
    "utils.memory.belief_model",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.chat_scope",
    "utils.retrieval.agentic",
    "utils.retrieval.tools.result_bounds",
    "utils.retrieval.memory_evidence",
    "utils.conversations",
    "utils.conversations.render",
]:
    _register(_name)

# Passthrough @tool decorator so the tool stays a plain callable.
sys.modules["langchain_core.tools"].tool = lambda func=None, **kw: (func if func is not None else (lambda f: f))
sys.modules["langchain_core.runnables"].RunnableConfig = dict

# Stub database._client
sys.modules["database._client"].db = MagicMock()

# Stub models.memories
class DummyMemoryDB:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
sys.modules["models.memories"].MemoryDB = DummyMemoryDB

# Stub utils.memory.memory_service
class DummyMemoryService:
    def __init__(self, *args, **kwargs):
        pass
    def read(self, *args, **kwargs):
        return []
    def search(self, *args, **kwargs):
        return []
sys.modules["utils.memory.memory_service"].MemoryService = DummyMemoryService

# Stub utils.memory.belief_model
belief_mod = sys.modules["utils.memory.belief_model"]
belief_mod.belief_model_enabled = lambda: False
belief_mod.memory_use_suppressed = lambda m: False
belief_mod.normalize_temporal_read_view = lambda v: "released"

# Stub utils.retrieval.chat_scope
chat_scope_mod = sys.modules["utils.retrieval.chat_scope"]
chat_scope_mod.apply_chat_scope_dates = lambda scope, s, e: (s, e, None)
chat_scope_mod.chat_scope_from_config = lambda config: None

# Stub result_bounds
result_bounds_mod = sys.modules["utils.retrieval.tools.result_bounds"]
result_bounds_mod.cap_items_for_llm = lambda items, cap: (items, len(items), False)

# Stub memory_evidence
mem_evidence_mod = sys.modules["utils.retrieval.memory_evidence"]
mem_evidence_mod.MAX_MEMORY_EVIDENCE_CHARS = 10000
mem_evidence_mod.render_memory_evidence = lambda records, **kw: "rendered evidence"
mem_evidence_mod.format_memory_evidence = lambda content, **kw: content

# Stub render
render_mod = sys.modules["utils.conversations.render"]
render_mod.format_local_date = lambda d, tz: str(d)
render_mod.resolve_display_tz = lambda tz: (None, "UTC")


def _load_module_from_file(module_name: str, file_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


memory_tools = _load_module_from_file(
    "utils.retrieval.tools.memory_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "memory_tools.py",
)


def test_get_memories_tool_invalid_date_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    res = memory_tools.get_memories_tool(start_date="invalid-iso-date", config=config)
    assert res.startswith("Error: Invalid start_date format.")
    assert "ValueError" not in res
    assert "ISO format" not in res


def test_get_memories_tool_db_exception_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    with patch.object(memory_tools, "MemoryService", side_effect=RuntimeError("internal_firestore_pool_crash_secret_path")):
        res = memory_tools.get_memories_tool(config=config)
        assert res == "Error retrieving memories."
        assert "internal_firestore_pool_crash_secret_path" not in res


def test_search_memories_tool_exception_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    with patch.object(memory_tools, "MemoryService", side_effect=RuntimeError("vector_db_apiKey_secret_leak")):
        res = memory_tools.search_memories_tool(query="cooking preferences", config=config)
        assert res == "Error searching memories."
        assert "vector_db_apiKey_secret_leak" not in res


if __name__ == "__main__":
    test_get_memories_tool_invalid_date_sanitized()
    test_get_memories_tool_db_exception_sanitized()
    test_search_memories_tool_exception_sanitized()
    print("All memory tools sanitization unit tests passed successfully!")
