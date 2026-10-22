"""Tests for hardened resilience and validation in preference_tools.py.

Verifies:
- Robust user ID extraction across nested configurable, top-level keys, and context variables.
- Strict input validation rejecting empty, whitespace-only, None, or non-string preferences.
- Safe boolean coercion for user_stated (preventing Python truthy "false" string bug).
- Defensive normalization of replace_memory_id (handling None, int, whitespace).
- Non-dict and missing-field resilience in duplicate preference detection and provenance generation.
- Graceful handling and fail-safe return values for ledger and compatibility flows.
"""

from __future__ import annotations

import os
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from models.memory_apply import WriterMode
from models.product_memory import MemoryItemStatus
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


class DummyLedgerProvenance:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def model_copy(self, update=None):
        data = vars(self).copy()
        if update:
            data.update(update)
        return DummyLedgerProvenance(**data)


def _load_preference_tools_module():
    """Load preference_tools with isolated stubs avoiding external side-effects."""
    tools_pkg = types.ModuleType("utils.retrieval.tools")
    tools_pkg.__path__ = [os.path.join(str(_BACKEND), "utils", "retrieval", "tools")]  # type: ignore[attr-defined]
    fakes = {
        "utils.retrieval.tools": tools_pkg,
        "database._client": AutoMockModule("database._client"),
        "utils.memory.canonical_memory_adapter": AutoMockModule("utils.memory.canonical_memory_adapter"),
        "utils.memory.knowledge_ledger": AutoMockModule("utils.memory.knowledge_ledger"),
        "utils.memory.memory_service": AutoMockModule("utils.memory.memory_service"),
        "utils.memory.memory_system": AutoMockModule("utils.memory.memory_system"),
        "testing.parity_pack_v0.live_capture": AutoMockModule("testing.parity_pack_v0.live_capture"),
        "langchain_core.tools": AutoMockModule("langchain_core.tools"),
        "langchain_core.runnables": AutoMockModule("langchain_core.runnables"),
        "models.memories": AutoMockModule("models.memories"),
    }
    with stub_modules(fakes):
        import langchain_core.tools as lc_tools

        def _tool(fn=None, **_kwargs):
            if fn is None:
                return lambda real_fn: real_fn
            return fn

        lc_tools.tool = _tool
        module = load_module_fresh(
            "utils.retrieval.tools.preference_tools",
            os.path.join(str(_BACKEND), "utils", "retrieval", "tools", "preference_tools.py"),
        )
        module.LedgerProvenance = DummyLedgerProvenance
        return module


@pytest.fixture(scope="module")
def pref_mod():
    return _load_preference_tools_module()


# ---------------------------------------------------------------------------
# 1. _get_uid resilience tests
# ---------------------------------------------------------------------------


def test_get_uid_from_nested_configurable_user_id(pref_mod):
    config = {"configurable": {"user_id": "user-nested-123"}}
    assert pref_mod._get_uid(config) == "user-nested-123"


def test_get_uid_from_nested_configurable_uid(pref_mod):
    config = {"configurable": {"uid": "user-nested-uid"}}
    assert pref_mod._get_uid(config) == "user-nested-uid"


def test_get_uid_from_toplevel_user_id(pref_mod):
    config = {"user_id": "user-top-123"}
    assert pref_mod._get_uid(config) == "user-top-123"


def test_get_uid_from_toplevel_uid(pref_mod):
    config = {"uid": "user-top-uid"}
    assert pref_mod._get_uid(config) == "user-top-uid"


def test_get_uid_strips_surrounding_whitespace(pref_mod):
    config = {"configurable": {"user_id": "   user-whitespace   "}}
    assert pref_mod._get_uid(config) == "user-whitespace"


def test_get_uid_fallback_to_agent_config_context(pref_mod, monkeypatch):
    monkeypatch.setattr(
        pref_mod,
        "_agent_config",
        lambda: {"configurable": {"user_id": "ctx-user-456"}},
    )
    # Empty config should fall back to context var
    assert pref_mod._get_uid({}) == "ctx-user-456"
    assert pref_mod._get_uid(None) == "ctx-user-456"


def test_get_uid_returns_empty_string_when_unresolvable(pref_mod, monkeypatch):
    monkeypatch.setattr(pref_mod, "_agent_config", lambda: None)
    assert pref_mod._get_uid({}) == ""
    assert pref_mod._get_uid(None) == ""
    assert pref_mod._get_uid("not-a-dict") == ""
    assert pref_mod._get_uid({"configurable": {"other": "value"}}) == ""
    assert pref_mod._get_uid({"configurable": {"user_id": ""}}) == ""
    assert pref_mod._get_uid({"configurable": {"user_id": "   "}}) == ""
    assert pref_mod._get_uid({"user_id": 12345}) == ""


# ---------------------------------------------------------------------------
# 2. Preference string validation tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_preference",
    [
        "",
        "   ",
        "\t\n  ",
        None,
        12345,
        {"preference": "dark mode"},
        ["Prefers coffee"],
    ],
)
def test_save_user_preference_rejects_empty_or_non_string_preference(pref_mod, invalid_preference):
    result = pref_mod.save_user_preference_tool(
        invalid_preference,
        config={"configurable": {"user_id": "user-1"}},
    )
    assert result == "Error: Preference must be a non-empty string"


def test_save_user_preference_rejects_missing_uid(pref_mod, monkeypatch):
    monkeypatch.setattr(pref_mod, "_agent_config", lambda: None)
    result = pref_mod.save_user_preference_tool("Prefers tea", config={})
    assert result == "Error: Could not determine user ID"


# ---------------------------------------------------------------------------
# 3. user_stated coercion tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_val,expected_bool",
    [
        (True, True),
        (False, False),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("YES", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("", False),
        (None, False),
    ],
)
def test_save_user_preference_coerces_user_stated_safely(pref_mod, monkeypatch, input_val, expected_bool):
    captured = {}

    def mock_save_compatibility(uid, pref, user_stated, firestore_client):
        captured["user_stated"] = user_stated
        return "mem_compat_1"

    monkeypatch.setattr(pref_mod, "_save_compatibility_preference", mock_save_compatibility)
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=object()))
    monkeypatch.setattr(pref_mod, "search_canonical_memories", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        pref_mod,
        "ensure_canonical_apply_control_state",
        lambda *_args, **_kwargs: types.SimpleNamespace(writer_mode=WriterMode.compatibility),
    )
    monkeypatch.setattr(pref_mod, "record_write", lambda *_args, **_kwargs: "")

    res = pref_mod.save_user_preference_tool(
        "Prefers dark mode",
        user_stated=input_val,
        config={"configurable": {"user_id": "user-1"}},
    )

    assert "Preference saved (memory_id=mem_compat_1)" in res
    assert captured["user_stated"] is expected_bool


# ---------------------------------------------------------------------------
# 4. _write_provenance resilience tests
# ---------------------------------------------------------------------------


def test_write_provenance_handles_non_dict_config_and_none_preference(pref_mod, monkeypatch):
    monkeypatch.setattr(pref_mod, "_agent_config", lambda: None)
    provenance = pref_mod._write_provenance("uid-1", None, config=None)
    assert provenance.source_id == "direct-agent-tool"
    assert provenance.source_type == "agent_chat"
    assert provenance.action_id.startswith("agent-preference:")
    assert provenance.artifact_ref == {}


def test_write_provenance_picks_chat_session_id_or_thread_id(pref_mod):
    prov1 = pref_mod._write_provenance("uid-1", "pref", config={"configurable": {"chat_session_id": "chat-99"}})
    assert prov1.source_id == "chat-99"
    assert prov1.artifact_ref == {"chat_session_id": "chat-99"}

    prov2 = pref_mod._write_provenance("uid-1", "pref", config={"thread_id": "thread-88"})
    assert prov2.source_id == "thread-88"
    assert prov2.artifact_ref == {}


# ---------------------------------------------------------------------------
# 5. preference_duplicate_message resilience tests
# ---------------------------------------------------------------------------


def test_preference_duplicate_message_skips_non_dict_hits(pref_mod):
    # Hits containing None, str, int, empty dict must not cause AttributeError / KeyError
    hits = [None, "invalid_hit", 123, {}, {"content": "Unrelated topic"}]
    msg = pref_mod.preference_duplicate_message("Prefers Vim over Emacs", hits)
    assert msg is None


def test_preference_duplicate_message_detects_exact_match(pref_mod):
    hits = [{"memory_id": "mem_10", "content": "  prefers vim over emacs  "}]
    msg = pref_mod.preference_duplicate_message("Prefers Vim over Emacs", hits)
    assert msg is not None
    assert "memory_id=mem_10" in msg


def test_preference_duplicate_message_safe_with_none_or_empty_preference(pref_mod):
    assert pref_mod.preference_duplicate_message("", []) is None
    assert pref_mod.preference_duplicate_message(None, []) is None


# ---------------------------------------------------------------------------
# 6. replace_memory_id normalization and correction tests
# ---------------------------------------------------------------------------


def test_replace_memory_id_normalized_when_passed_as_int_or_padded_string(pref_mod, monkeypatch):
    """replace_memory_id passed as int or whitespace string must not crash with AttributeError."""
    firestore_client = object()
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))

    # Test int replace_memory_id
    monkeypatch.setattr(
        pref_mod,
        "read_canonical_memory_item",
        MagicMock(return_value=None),
    )

    result = pref_mod.save_user_preference_tool(
        "Prefers dark theme",
        replace_memory_id=12345,
        config={"configurable": {"user_id": "user-1"}},
    )
    assert result == "Error updating preference: memory is unavailable or historical"


def test_replace_memory_id_checks_status_and_superseded(pref_mod, monkeypatch):
    firestore_client = object()
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))

    # Case 1: Memory status is historical
    prior_mock = types.SimpleNamespace(
        status=types.SimpleNamespace(value="historical"),
        superseded_by=None,
        content="Old preference",
    )
    monkeypatch.setattr(pref_mod, "read_canonical_memory_item", MagicMock(return_value=prior_mock))

    res = pref_mod.save_user_preference_tool(
        "Prefers light theme",
        replace_memory_id="mem_old",
        config={"configurable": {"user_id": "user-1"}},
    )
    assert res == "Error updating preference: memory is unavailable or historical"

    # Case 2: Memory already superseded
    prior_mock_superseded = types.SimpleNamespace(
        status=types.SimpleNamespace(value="active"),
        superseded_by="mem_newer",
        content="Old preference",
    )
    monkeypatch.setattr(pref_mod, "read_canonical_memory_item", MagicMock(return_value=prior_mock_superseded))

    res2 = pref_mod.save_user_preference_tool(
        "Prefers light theme",
        replace_memory_id="mem_old",
        config={"configurable": {"user_id": "user-1"}},
    )
    assert res2 == "Error updating preference: memory is unavailable or historical"


def test_replace_memory_id_skips_identical_duplicate(pref_mod, monkeypatch):
    firestore_client = object()
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))

    prior_mock = types.SimpleNamespace(
        status=types.SimpleNamespace(value="active"),
        superseded_by=None,
        content="Prefers dark theme",
    )
    monkeypatch.setattr(pref_mod, "read_canonical_memory_item", MagicMock(return_value=prior_mock))

    res = pref_mod.save_user_preference_tool(
        "   Prefers dark theme   ",
        replace_memory_id="mem_target",
        config={"configurable": {"user_id": "user-1"}},
    )
    assert res == "Preference already saved (memory_id=mem_target)"


def test_replace_memory_id_updates_knowledge_ledger_fact(pref_mod, monkeypatch):
    firestore_client = object()
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))
    amend_fact_mock = MagicMock(return_value="mem_amended_99")
    monkeypatch.setattr(pref_mod, "amend_fact", amend_fact_mock)
    monkeypatch.setattr(pref_mod, "record_write", lambda *_args, **_kwargs: " [write_recorded]")

    prior_mock = types.SimpleNamespace(
        status=types.SimpleNamespace(value="active"),
        superseded_by=None,
        content="Old preference",
        ledger_schema_version="knowledge_ledger.v1",
        slot="user_theme",
        subject_scope=None,
        subject_entity_id=None,
        curation_weight=1.0,
        visibility=None,
    )
    monkeypatch.setattr(pref_mod, "read_canonical_memory_item", MagicMock(return_value=prior_mock))

    res = pref_mod.save_user_preference_tool(
        "Prefers solarized dark theme",
        replace_memory_id="mem_old_fact",
        user_stated=True,
        config={"configurable": {"user_id": "user-1", "chat_session_id": "session-1"}},
    )
    assert res == "Preference updated (memory_id=mem_amended_99): Prefers solarized dark theme [write_recorded]"
    amend_fact_mock.assert_called_once()
    assert amend_fact_mock.call_args.kwargs["user_asserted"] is True


def test_replace_memory_id_catches_unexpected_exception(pref_mod, monkeypatch):
    firestore_client = object()
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))
    monkeypatch.setattr(
        pref_mod,
        "read_canonical_memory_item",
        MagicMock(side_effect=Exception("Database connection failure")),
    )

    res = pref_mod.save_user_preference_tool(
        "Prefers dark theme",
        replace_memory_id="mem_any",
        config={"configurable": {"user_id": "user-1"}},
    )
    assert res == "Error updating preference"


def test_save_user_preference_catches_client_init_failure(pref_mod, monkeypatch):
    monkeypatch.setattr(
        pref_mod,
        "get_data_plane_firestore_client",
        MagicMock(side_effect=Exception("Firestore offline")),
    )

    res = pref_mod.save_user_preference_tool(
        "Prefers dark theme",
        config={"configurable": {"user_id": "user-1"}},
    )
    assert res == "Error saving preference"


def test_replace_memory_id_updates_preledger_memory(pref_mod, monkeypatch):
    firestore_client = object()
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))
    mem_svc_mock = MagicMock()
    monkeypatch.setattr(pref_mod, "MemoryService", MagicMock(return_value=mem_svc_mock))
    monkeypatch.setattr(pref_mod, "record_write", lambda *_args, **_kwargs: " [write_recorded]")

    prior_mock = types.SimpleNamespace(
        status=types.SimpleNamespace(value="active"),
        superseded_by=None,
        content="Old pre-ledger preference",
        ledger_schema_version=None,
    )
    monkeypatch.setattr(pref_mod, "read_canonical_memory_item", MagicMock(return_value=prior_mock))

    res = pref_mod.save_user_preference_tool(
        "New pre-ledger preference",
        replace_memory_id="mem_legacy_77",
        config={"configurable": {"user_id": "user-1"}},
    )
    assert res == "Preference updated (memory_id=mem_legacy_77): New pre-ledger preference [write_recorded]"
    mem_svc_mock.update_external_memory_content.assert_called_once_with(
        "user-1",
        "mem_legacy_77",
        "New pre-ledger preference",
        memory_system=pref_mod.MemorySystem.CANONICAL,
        consumer="agent_preference",
        operation="correct_user_preference",
    )


def test_save_preference_ledger_mode_creates_fact(pref_mod, monkeypatch):
    firestore_client = object()
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))
    monkeypatch.setattr(pref_mod, "search_canonical_memories", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        pref_mod,
        "ensure_canonical_apply_control_state",
        lambda *_args, **_kwargs: types.SimpleNamespace(writer_mode=WriterMode.ledger),
    )
    save_fact_mock = MagicMock(return_value="mem_fact_new_42")
    monkeypatch.setattr(pref_mod, "save_fact", save_fact_mock)
    capture_mock = MagicMock()
    monkeypatch.setattr(pref_mod, "_capture_app_memory_write", capture_mock)
    monkeypatch.setattr(pref_mod, "record_write", lambda *_args, **_kwargs: " [recorded]")

    res = pref_mod.save_user_preference_tool(
        "Prefers monospace font in editor",
        slot="coding_editor_font",
        user_stated="yes",
        config={"configurable": {"user_id": "user-1", "chat_session_id": "session-42"}},
    )
    assert res == "Preference saved (memory_id=mem_fact_new_42): Prefers monospace font in editor [recorded]"
    save_fact_mock.assert_called_once()
    assert save_fact_mock.call_args.kwargs["user_asserted"] is True
    capture_mock.assert_called_once()


def test_save_preference_handles_unsupported_writer_mode(pref_mod, monkeypatch):
    firestore_client = object()
    monkeypatch.setattr(pref_mod, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))
    monkeypatch.setattr(pref_mod, "search_canonical_memories", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        pref_mod,
        "ensure_canonical_apply_control_state",
        lambda *_args, **_kwargs: types.SimpleNamespace(writer_mode="unsupported_mode"),
    )

    res = pref_mod.save_user_preference_tool(
        "Prefers dark theme",
        config={"configurable": {"user_id": "user-1"}},
    )
    assert res == "Error saving preference"

