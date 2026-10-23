"""Hermetic unit tests for ``save_user_preference_tool``.

The module under test pulls in Firestore, the knowledge ledger and LangChain.
None of those are needed to exercise the input guards, so the heavy
dependencies are stubbed at import time and every store interaction is recorded
by a fake. No network, no emulator, no credentials.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "utils" / "retrieval" / "tools" / "preference_tools.py"

CONFIG = {"configurable": {"user_id": "user-1"}}


class _State:
    """Mutable recorder shared by the stub implementations."""

    def reset(self) -> None:
        self.memory_service_calls = []
        self.ledger_saves = []
        self.amend_calls = []
        self.read_calls = []
        self.search_calls = []
        self.capture_calls = []
        self.record_writes = []
        self.prior = None
        self.search_hits = []
        self.writer_mode = "compatibility"


STATE = _State()


class _Control:
    def __init__(self, writer_mode: str):
        self.writer_mode = writer_mode


class _Provenance:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_copy(self, *, update):
        data = dict(self.__dict__)
        data.update(update)
        return _Provenance(**data)


class _MemoryDB:
    @classmethod
    def model_validate(cls, data):
        return dict(data)

    @staticmethod
    def calculate_score(_data):
        return 0.5


class _MemoryService:
    def __init__(self, db_client=None):
        self.db_client = db_client

    def create_external_memory(self, uid, memory, **kwargs):
        STATE.memory_service_calls.append({"uid": uid, "memory": memory, "kwargs": kwargs})
        return memory["id"]

    def update_external_memory_content(self, uid, memory_id, content, **kwargs):
        STATE.memory_service_calls.append(
            {"uid": uid, "memory_id": memory_id, "content": content, "kwargs": kwargs}
        )


class _WriterMode(str):
    """String-valued stand-in for ``WriterMode`` so ``mode == WriterMode.x`` works."""

    compatibility = "compatibility"
    ledger = "ledger"

    @property
    def value(self):
        return str(self)


class _SurfaceRuntime:
    def get(self):
        return None


def _passthrough_tool(func=None, **_kwargs):
    return func if func is not None else (lambda wrapped: wrapped)


def _record_write(uid, kind, memory_id, before, after):
    STATE.record_writes.append({"uid": uid, "kind": kind, "memory_id": memory_id})
    return ""


def _read_canonical_memory_item(uid, memory_id, db_client=None):
    STATE.read_calls.append((uid, memory_id))
    return STATE.prior


def _search_canonical_memories(uid, query, limit=3, db_client=None):
    STATE.search_calls.append({"uid": uid, "query": query, "limit": limit})
    return list(STATE.search_hits)


def _save_fact(uid, content, **kwargs):
    STATE.ledger_saves.append({"uid": uid, "content": content, **kwargs})
    return "ledger-memory-id"


def _amend_fact(uid, memory_id, content, **kwargs):
    STATE.amend_calls.append({"uid": uid, "memory_id": memory_id, "content": content, **kwargs})
    return memory_id


def _stub_modules():
    return {
        "langchain_core": {},
        "langchain_core.tools": {"tool": _passthrough_tool},
        "langchain_core.runnables": {"RunnableConfig": dict},
        "utils.messaging.undo": {"record_write": _record_write},
        "utils.messaging.projection": {"surface_runtime": _SurfaceRuntime()},
        "database._client": {"get_data_plane_firestore_client": lambda: object()},
        "models.knowledge_ledger_policy": {
            "canonicalize_ledger_slot": lambda slot, strict=False: (slot or None)
        },
        "models.memory_contracts": {"deterministic_contract_id": lambda *args, **kwargs: "c" * 32},
        "models.memory_apply": {"WriterMode": _WriterMode},
        "models.memories": {"MemoryDB": _MemoryDB},
        "models.product_memory": {
            "LedgerWriteReason": types.SimpleNamespace(
                agent_reusable_conclusion=types.SimpleNamespace(value="agent_reusable_conclusion")
            )
        },
        "utils.log_sanitizer": {"sanitize_pii": lambda value: value},
        "utils.memory.canonical_memory_adapter": {
            "read_canonical_memory_item": _read_canonical_memory_item,
            "search_canonical_memories": _search_canonical_memories,
        },
        "utils.memory.knowledge_ledger": {
            "LedgerProvenance": _Provenance,
            "amend_fact": _amend_fact,
            "save_fact": _save_fact,
        },
        "utils.memory.memory_service": {"MemoryService": _MemoryService},
        "utils.memory.memory_system": {
            "MemorySystem": types.SimpleNamespace(CANONICAL="canonical"),
            "ensure_canonical_apply_control_state": lambda uid, db_client=None: _Control(STATE.writer_mode),
        },
        "testing.parity_pack_v0.live_capture": {
            "capture_memory_write": lambda **kwargs: STATE.capture_calls.append(kwargs)
        },
    }


def _load_preference_tools():
    """Load the module against stub dependencies, then drop the stubs."""
    inserted = []
    for name, attrs in _stub_modules().items():
        if name in sys.modules:
            continue
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
        inserted.append(name)
    try:
        spec = importlib.util.spec_from_file_location("preference_tools_under_test", MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name in inserted:
            sys.modules.pop(name, None)


preference_tools = _load_preference_tools()


@pytest.fixture(autouse=True)
def _reset_state():
    STATE.reset()
    yield
    STATE.reset()


def _call(**kwargs):
    kwargs.setdefault("config", CONFIG)
    return preference_tools.save_user_preference_tool(**kwargs)


# --- crash regressions -----------------------------------------------------


def test_none_replace_memory_id_does_not_crash():
    """A ``None`` optional argument must not raise AttributeError."""
    result = _call(preference="Prefers metric units", replace_memory_id=None)

    assert "Error" not in result
    assert result.startswith("Preference saved (memory_id=")
    assert len(STATE.memory_service_calls) == 1
    assert STATE.memory_service_calls[0]["memory"]["content"] == "Prefers metric units"


def test_none_replace_memory_id_creates_instead_of_correcting():
    _call(preference="Prefers metric units", replace_memory_id=None)

    assert STATE.read_calls == []
    assert STATE.amend_calls == []


def test_blank_replace_memory_id_is_treated_as_absent():
    _call(preference="Prefers metric units", replace_memory_id="   ")

    assert STATE.read_calls == []
    assert len(STATE.memory_service_calls) == 1


def test_non_string_replace_memory_id_is_coerced():
    result = _call(preference="Prefers metric units", replace_memory_id=12345)

    assert STATE.read_calls == [("user-1", "12345")]
    assert result == "Error updating preference: memory is unavailable or historical"


def test_replacement_id_is_stripped_before_lookup():
    _call(preference="Prefers metric units", replace_memory_id="  mem-1  ")

    assert STATE.read_calls == [("user-1", "mem-1")]


def test_write_provenance_tolerates_none_preference():
    """``preference.split()`` must not blow up on ``None``."""
    provenance = preference_tools._write_provenance("user-1", None, None)

    assert provenance.source_type == "agent_chat"
    assert provenance.action_id.startswith("agent-preference:")


def test_write_provenance_is_stable_for_equivalent_whitespace():
    first = preference_tools._write_provenance("user-1", "Prefers  metric   units", None)
    second = preference_tools._write_provenance("user-1", "Prefers metric units", None)

    assert first.action_id == second.action_id


# --- empty preference validation ------------------------------------------


@pytest.mark.parametrize("bad_preference", [None, "", "   ", "\n\t ", 0, [], 42])
def test_empty_preference_is_rejected_before_any_write(bad_preference):
    result = _call(preference=bad_preference)

    assert result == "Error: Preference content cannot be empty"
    assert STATE.memory_service_calls == []
    assert STATE.ledger_saves == []
    assert STATE.amend_calls == []
    assert STATE.search_calls == []


def test_empty_preference_does_not_touch_storage_lookup():
    _call(preference="  ")

    assert STATE.read_calls == []


# --- happy paths -----------------------------------------------------------


def test_preference_saved_through_compatibility_writer():
    result = _call(preference="Prefers Google Calendar over Outlook")

    assert result.startswith("Preference saved (memory_id=")
    assert STATE.memory_service_calls[0]["kwargs"]["consumer"] == "agent_preference"
    assert STATE.record_writes[0]["memory_id"] == STATE.memory_service_calls[0]["memory"]["id"]


def test_preference_saved_through_ledger_writer():
    STATE.writer_mode = "ledger"

    result = _call(preference="Prefers metric units", slot="units", user_stated=True)

    assert result.startswith("Preference saved (memory_id=ledger-memory-id)")
    assert STATE.ledger_saves[0]["content"] == "Prefers metric units"
    assert STATE.ledger_saves[0]["slot"] == "units"
    assert STATE.ledger_saves[0]["user_asserted"] is True


def test_duplicate_preference_is_skipped():
    STATE.search_hits = [{"content": "Prefers metric units", "memory_id": "m-1"}]

    result = _call(preference="  prefers   METRIC units ")

    assert result.startswith("Similar preference already exists (memory_id=m-1)")
    assert STATE.memory_service_calls == []


def test_missing_user_id_is_reported():
    result = preference_tools.save_user_preference_tool(preference="Prefers metric units", config=None)

    assert result == "Error: Could not determine user ID"
