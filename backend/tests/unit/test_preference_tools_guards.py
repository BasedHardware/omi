"""Unit tests for preference_tools input validation, guards, and UID resolution."""

from dataclasses import dataclass, field
from enum import Enum
from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import AutoMockModule, stub_modules

@dataclass
class FakeLedgerProvenance:
    source_id: str
    source_type: str
    source_version: str
    action_id: str
    artifact_ref: dict = field(default_factory=dict)

class FakeWriterMode(str, Enum):
    compatibility = "compatibility"
    ledger = "ledger"

fake_knowledge_ledger = AutoMockModule("utils.memory.knowledge_ledger")
fake_knowledge_ledger.LedgerProvenance = FakeLedgerProvenance

fake_memory_apply = AutoMockModule("models.memory_apply")
fake_memory_apply.WriterMode = FakeWriterMode

# Ensure dependencies are stubbed before importing preference_tools
with stub_modules({
    "utils.messaging.undo": AutoMockModule("utils.messaging.undo"),
    "utils.messaging.projection": AutoMockModule("utils.messaging.projection"),
    "models.knowledge_ledger_policy": AutoMockModule("models.knowledge_ledger_policy"),
    "models.memory_contracts": AutoMockModule("models.memory_contracts"),
    "models.memory_apply": fake_memory_apply,
    "models.memories": AutoMockModule("models.memories"),
    "models.product_memory": AutoMockModule("models.product_memory"),
    "utils.memory.canonical_memory_adapter": AutoMockModule("utils.memory.canonical_memory_adapter"),
    "utils.memory.knowledge_ledger": fake_knowledge_ledger,
    "utils.memory.memory_service": AutoMockModule("utils.memory.memory_service"),
    "utils.memory.memory_system": AutoMockModule("utils.memory.memory_system"),
    "testing.parity_pack_v0.live_capture": AutoMockModule("testing.parity_pack_v0.live_capture"),
}):
    import utils.retrieval.tools.preference_tools as pref_module
    from utils.retrieval.tools.preference_tools import (
        save_user_preference_tool,
        _get_uid,
        _write_provenance,
        preference_duplicate_message,
        PREFERENCE_DUPLICATE_THRESHOLD,
    )


class TestPreferenceToolsGuards:
    """Hermetic tests verifying input validation, guards, and UID resolution."""

    def test_preference_empty_or_whitespace_returns_error(self):
        """Empty, whitespace-only, None, or non-string preferences must return error."""
        config = {"configurable": {"user_id": "user_123"}}

        # None preference via invoke
        res_none = save_user_preference_tool.invoke({
            "preference": None,
        }, config=config)
        assert res_none == "Error: Preference content cannot be empty"

        # Direct func call with None
        assert save_user_preference_tool.func(preference=None, config=config) == "Error: Preference content cannot be empty"

        # Empty string via invoke
        res_empty = save_user_preference_tool.invoke({
            "preference": "",
        }, config=config)
        assert res_empty == "Error: Preference content cannot be empty"

        # Whitespace only via invoke
        res_ws = save_user_preference_tool.invoke({
            "preference": "   \n\t  ",
        }, config=config)
        assert res_ws == "Error: Preference content cannot be empty"

        # Non-string via direct call
        assert save_user_preference_tool.func(preference=12345, config=config) == "Error: Preference content cannot be empty"

    def test_get_uid_top_level_resolution(self):
        """_get_uid must resolve user_id from top-level or configurable keys."""
        # Top-level user_id
        assert _get_uid({"user_id": "usr_top"}) == "usr_top"

        # Top-level uid
        assert _get_uid({"uid": "uid_top"}) == "uid_top"

        # Nested configurable user_id
        assert _get_uid({"configurable": {"user_id": "usr_nested"}}) == "usr_nested"

        # Configurable takes precedence if present
        assert _get_uid({
            "user_id": "usr_top",
            "configurable": {"user_id": "usr_nested"},
        }) == "usr_nested"

        # Empty config
        assert _get_uid({}) == ""
        assert _get_uid(None) == ""

    def test_replace_memory_id_safe_none_and_non_string(self):
        """None or non-string replace_memory_id must not crash with AttributeError."""
        config = {"configurable": {"user_id": "user_123"}}

        with patch.object(pref_module, "get_data_plane_firestore_client") as mock_db, \
             patch.object(pref_module, "search_canonical_memories", return_value=[]), \
             patch.object(pref_module, "ensure_canonical_apply_control_state") as mock_ctrl, \
             patch.object(pref_module, "_save_compatibility_preference", return_value="mem_123"), \
             patch.object(pref_module, "record_write", return_value=""):

            mock_ctrl.return_value.writer_mode = "compatibility"

            # Passing replace_memory_id=None should not crash .strip()
            res = save_user_preference_tool.invoke({
                "preference": "Likes dark mode",
                "replace_memory_id": None,
            }, config=config)
            assert "Preference saved (memory_id=mem_123)" in res

            # Passing replace_memory_id as int to func should not crash .strip()
            res2 = save_user_preference_tool.func(
                preference="Prefers morning meetings",
                replace_memory_id=9999,
                config=config,
            )
            assert "Preference saved (memory_id=mem_123)" in res2

    def test_preference_duplicate_message_handles_non_dict_hits(self):
        """Duplicate detection must tolerate non-dict hits without raising AttributeError."""
        hits = [
            None,
            "string_hit",
            123,
            {"memory_id": "mem_dup", "content": "Likes dark mode", "score": 0.95},
        ]
        msg = preference_duplicate_message("likes dark mode", hits)
        assert msg is not None
        assert "Similar preference already exists" in msg
        assert "mem_dup" in msg

        # When no duplicates match, non-dict hits are safely skipped
        hits_no_match = [None, {"content": "Likes pizza", "score": 0.2}]
        assert preference_duplicate_message("Likes dark mode", hits_no_match) is None

    def test_write_provenance_top_level_session_id(self):
        """_write_provenance must extract session_id from top-level config if present."""
        uid = "user_abc"
        pref = "Prefers coffee"

        with patch.object(pref_module, "deterministic_contract_id", return_value="contract_hash_123"):
            # Top-level chat_session_id
            prov1 = _write_provenance(uid, pref, {"chat_session_id": "session_top_1"})
            assert prov1.source_id == "session_top_1"
            assert prov1.artifact_ref == {"chat_session_id": "session_top_1"}

            # Top-level session_id fallback
            prov2 = _write_provenance(uid, pref, {"session_id": "session_top_2"})
            assert prov2.source_id == "session_top_2"
            assert prov2.artifact_ref == {"chat_session_id": "session_top_2"}

            # None preference passed to _write_provenance does not crash
            prov3 = _write_provenance(uid, None, {"configurable": {"chat_session_id": "cfg_sess"}})
            assert prov3.source_id == "cfg_sess"

    def test_save_user_preference_missing_uid(self):
        """Missing user ID must return clear error message."""
        res = save_user_preference_tool.invoke({
            "preference": "Prefers dark mode",
        }, config={})
        assert res == "Error: Could not determine user ID"
