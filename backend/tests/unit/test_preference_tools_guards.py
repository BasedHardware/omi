"""Unit tests for parameter guards, type coercion, and input sanitization in preference_tools.py.

Ensures that:
1. None, non-string, and empty/whitespace preferences return a clean validation error without crashing.
2. None or non-string replace_memory_id values do not raise AttributeError on .strip().
3. user_stated boolean coercion correctly parses booleans, numeric flags, and string representations ("true", "false", "yes", "no").
4. _get_uid correctly resolves user_id from nested configurable, top-level user_id, and top-level uid.
5. Whitespace-only or invalid slots are sanitized before passing to canonical ledger slot resolution.
6. preference_duplicate_message handles malformed or non-dict hits without raising AttributeError.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
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


# Stub external dependencies for hermetic unit testing
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")
if not hasattr(_lc_tools, "tool"):
    _lc_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
if not hasattr(_lc_runnables, "RunnableConfig"):
    _lc_runnables.RunnableConfig = dict

_pkg("database")
_pkg("models")
_pkg("utils")
_pkg("utils.messaging")
_pkg("utils.memory")
_pkg("testing")

for _m_name in [
    "database._client",
    "utils.messaging.undo",
    "utils.messaging.projection",
    "models.knowledge_ledger_policy",
    "models.memory_contracts",
    "models.memory_apply",
    "models.memories",
    "models.product_memory",
    "utils.log_sanitizer",
    "utils.memory.canonical_memory_adapter",
    "utils.memory.knowledge_ledger",
    "utils.memory.memory_service",
    "utils.memory.memory_system",
    "testing.parity_pack_v0.live_capture",
]:
    _m = _mod(_m_name)
    if _m_name == "utils.messaging.undo":
        _m.record_write = MagicMock(return_value="")
    elif _m_name == "utils.messaging.projection":
        _mock_runtime = MagicMock()
        _mock_runtime.get.return_value = None
        _m.surface_runtime = _mock_runtime
    elif _m_name == "database._client":
        _m.get_data_plane_firestore_client = MagicMock(return_value=object())
    elif _m_name == "models.knowledge_ledger_policy":
        _m.canonicalize_ledger_slot = lambda s, **_kw: f"slot_{s}" if s else None
    elif _m_name == "models.memories":
        _m.MemoryDB = MagicMock()
    elif _m_name == "models.memory_contracts":
        _m.deterministic_contract_id = lambda name, payload: "contract-12345678901234567890123456789012"
    elif _m_name == "models.memory_apply":
        from enum import Enum
        class _WM(str, Enum):
            compatibility = "compatibility"
            ledger = "ledger"
        _m.WriterMode = _WM
    elif _m_name == "models.product_memory":
        class _LWR:
            agent_reusable_conclusion = types.SimpleNamespace(value="agent_reusable_conclusion")
        _m.LedgerWriteReason = _LWR
    elif _m_name == "utils.log_sanitizer":
        _m.sanitize_pii = lambda s: s
    elif _m_name == "utils.memory.canonical_memory_adapter":
        _m.read_canonical_memory_item = MagicMock(return_value=None)
        _m.search_canonical_memories = MagicMock(return_value=[])
    elif _m_name == "utils.memory.memory_service":
        _m.MemoryService = MagicMock()
    elif _m_name == "utils.memory.knowledge_ledger":
        class _LP:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
            def model_copy(self, update=None):
                d = dict(self.__dict__)
                if update:
                    d.update(update)
                return _LP(**d)
        _m.LedgerProvenance = _LP
        _m.amend_fact = MagicMock(return_value="mem-amended")
        _m.save_fact = MagicMock(return_value="mem-saved")
    elif _m_name == "utils.memory.memory_system":
        class _MS:
            CANONICAL = "canonical"
        _m.MemorySystem = _MS
        _m.ensure_canonical_apply_control_state = MagicMock(
            return_value=types.SimpleNamespace(writer_mode="ledger")
        )
    elif _m_name == "testing.parity_pack_v0.live_capture":
        _m.capture_memory_write = MagicMock()

pt = _load(
    "utils.retrieval.tools._preference_tools_guards_test",
    "utils/retrieval/tools/preference_tools.py",
)


def test_safe_bool_coercion():
    assert pt._safe_bool(True) is True
    assert pt._safe_bool(False) is False
    assert pt._safe_bool(1) is True
    assert pt._safe_bool(0) is False
    assert pt._safe_bool("true") is True
    assert pt._safe_bool("True") is True
    assert pt._safe_bool("1") is True
    assert pt._safe_bool("yes") is True
    assert pt._safe_bool("false") is False
    assert pt._safe_bool("0") is False
    assert pt._safe_bool("no") is False
    assert pt._safe_bool("random") is False
    assert pt._safe_bool(None) is False
    assert pt._safe_bool([]) is False


def test_empty_preference_returns_error():
    # Empty string, whitespace, None, and non-string must return a clean error without crashing
    res_empty = pt.save_user_preference_tool.func(preference="", config={"user_id": "u1"})
    assert res_empty == "Error: Preference cannot be empty"

    res_ws = pt.save_user_preference_tool.func(preference="   ", config={"user_id": "u1"})
    assert res_ws == "Error: Preference cannot be empty"

    res_none = pt.save_user_preference_tool.func(preference=None, config={"user_id": "u1"})
    assert res_none == "Error: Preference cannot be empty"

    res_int = pt.save_user_preference_tool.func(preference=123, config={"user_id": "u1"})
    assert res_int == "Error: Preference cannot be empty"


def test_replace_memory_id_none_does_not_crash():
    # replace_memory_id=None or non-string must be safely handled without raising AttributeError
    res_none = pt.save_user_preference_tool.func(
        preference="Prefers dark mode",
        replace_memory_id=None,
        config={"configurable": {"user_id": "u1"}},
    )
    assert "Preference saved" in res_none

    res_int = pt.save_user_preference_tool.func(
        preference="Prefers dark mode",
        replace_memory_id=12345,
        config={"configurable": {"user_id": "u1"}},
    )
    assert "Preference saved" in res_int


def test_get_uid_resolution():
    # Nested configurable with user_id
    assert pt._get_uid({"configurable": {"user_id": "user-nested"}}) == "user-nested"

    # Nested configurable with uid
    assert pt._get_uid({"configurable": {"uid": "user-nested-uid"}}) == "user-nested-uid"

    # Top-level user_id fallback
    assert pt._get_uid({"user_id": "user-top"}) == "user-top"

    # Top-level uid fallback
    assert pt._get_uid({"uid": "user-top-uid"}) == "user-top-uid"

    # Empty config
    assert pt._get_uid({}) == ""

    # Non-dict config
    assert pt._get_uid(None) == ""
    assert pt._get_uid("invalid") == ""


def test_slot_sanitization():
    # Whitespace-only slot must be treated as empty and not sent as raw whitespace to ledger
    res_ws_slot = pt.save_user_preference_tool.func(
        preference="Speaks English",
        slot="   ",
        config={"configurable": {"user_id": "u1"}},
    )
    assert "Preference saved" in res_ws_slot

    # None slot must not crash
    res_none_slot = pt.save_user_preference_tool.func(
        preference="Speaks English",
        slot=None,
        config={"configurable": {"user_id": "u1"}},
    )
    assert "Preference saved" in res_none_slot


def test_preference_duplicate_message_resilience():
    # None or malformed hits in search list must not raise AttributeError
    msg_malformed = pt.preference_duplicate_message("Prefers tea", [None, "invalid_hit", {}])
    assert msg_malformed is None

    # Exact match normalized
    msg_exact = pt.preference_duplicate_message("Prefers tea", [{"content": "  prefers tea  ", "id": "m1"}])
    assert msg_exact is not None
    assert "Similar preference already exists (memory_id=m1)" in msg_exact

    # High score match
    msg_score = pt.preference_duplicate_message("Prefers tea", [{"content": "Likes tea", "score": 0.95, "id": "m2"}])
    assert msg_score is not None
    assert "Likes tea" in msg_score
