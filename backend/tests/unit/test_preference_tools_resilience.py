"""Comprehensive hermetic unit tests for preference_tools hardening (Issue #23328).

Validates:
1. Deterministic boolean coercion for user_stated (_coerce_user_stated).
2. Defensive normalization of replace_memory_id (_normalize_replace_memory_id).
3. Resilient user ID extraction (_get_uid) across configurable/top-level user_id and uid, and context var.
4. Non-dict and non-sequence hit resilience in preference_duplicate_message.
5. Early rejection of empty / whitespace / non-string preferences in save_user_preference_tool without touching Firestore.
6. Provenance resilience against non-string preference inputs.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from types import ModuleType
from unittest.mock import MagicMock


def _setup_stubs():
    class AutoMockModule(ModuleType):
        def __getattr__(self, name: str):
            if name.startswith("__") and name.endswith("__"):
                raise AttributeError(name)
            mock = MagicMock()
            setattr(self, name, mock)
            return mock

    stub_names = [
        "langchain_core",
        "langchain_core.tools",
        "langchain_core.runnables",
        "utils.messaging",
        "utils.messaging.undo",
        "utils.messaging.projection",
        "database",
        "database._client",
        "models",
        "models.knowledge_ledger_policy",
        "models.memory_contracts",
        "models.memory_apply",
        "models.memories",
        "models.product_memory",
        "utils.log_sanitizer",
        "utils.memory",
        "utils.memory.canonical_memory_adapter",
        "utils.memory.knowledge_ledger",
        "utils.memory.memory_service",
        "utils.memory.memory_system",
        "testing",
        "testing.parity_pack_v0",
        "testing.parity_pack_v0.live_capture",
    ]
    for name in stub_names:
        if name not in sys.modules:
            sys.modules[name] = AutoMockModule(name)

    # Tool decorator returns original function
    sys.modules["langchain_core.tools"].tool = lambda fn=None, **_kw: (fn if fn else lambda f: f)


_setup_stubs()

# Load the hardened preference_tools module
_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.path.join(_DIR, "../../utils/retrieval/tools/preference_tools.py"),
    os.path.join(_DIR, "../utils/retrieval/tools/preference_tools.py"),
    os.path.join(_DIR, "../backend/utils/retrieval/tools/preference_tools.py"),
    os.path.join(_DIR, "backend/utils/retrieval/tools/preference_tools.py"),
    os.path.join(_DIR, "preference_tools.py"),
]
MODULE_PATH = next((p for p in _CANDIDATES if os.path.exists(p)), _CANDIDATES[0])
spec = importlib.util.spec_from_file_location("utils.retrieval.tools.preference_tools", MODULE_PATH)
pref_mod = importlib.util.module_from_spec(spec)
sys.modules["utils.retrieval.tools.preference_tools"] = pref_mod
spec.loader.exec_module(pref_mod)


class TestCoerceUserStated(unittest.TestCase):
    """Test truth table for _coerce_user_stated."""

    def test_booleans(self):
        self.assertIs(pref_mod._coerce_user_stated(True), True)
        self.assertIs(pref_mod._coerce_user_stated(False), False)

    def test_numbers(self):
        self.assertIs(pref_mod._coerce_user_stated(1), True)
        self.assertIs(pref_mod._coerce_user_stated(0), False)
        self.assertIs(pref_mod._coerce_user_stated(1.0), True)
        self.assertIs(pref_mod._coerce_user_stated(0.0), False)
        self.assertIs(pref_mod._coerce_user_stated(42), True)

    def test_truthy_strings(self):
        for val in ["true", "TRUE", "True", " 1 ", "1", "yes", "YES", "on", "ON", "y", "Y"]:
            with self.subTest(val=val):
                self.assertIs(pref_mod._coerce_user_stated(val), True)

    def test_falsy_strings(self):
        for val in ["false", "FALSE", "False", " 0 ", "0", "no", "NO", "off", "OFF", "n", "N", "", "   "]:
            with self.subTest(val=val):
                self.assertIs(pref_mod._coerce_user_stated(val), False)

    def test_unrecognized_strings_fail_closed(self):
        for val in ["maybe", "unrecognized", "unknown", "2", "null", "none"]:
            with self.subTest(val=val):
                self.assertIs(pref_mod._coerce_user_stated(val), False)

    def test_none_and_collections_fail_closed(self):
        self.assertIs(pref_mod._coerce_user_stated(None), False)
        self.assertIs(pref_mod._coerce_user_stated(["true"]), False)
        self.assertIs(pref_mod._coerce_user_stated({"user_stated": True}), False)


class TestNormalizeReplaceMemoryId(unittest.TestCase):
    """Test defensive normalization for replace_memory_id."""

    def test_strings(self):
        self.assertEqual(pref_mod._normalize_replace_memory_id("  mem-123  "), "mem-123")
        self.assertEqual(pref_mod._normalize_replace_memory_id("mem-abc"), "mem-abc")
        self.assertEqual(pref_mod._normalize_replace_memory_id(""), "")
        self.assertEqual(pref_mod._normalize_replace_memory_id("   "), "")

    def test_integers(self):
        self.assertEqual(pref_mod._normalize_replace_memory_id(42), "42")
        self.assertEqual(pref_mod._normalize_replace_memory_id(0), "0")

    def test_booleans_rejected(self):
        self.assertEqual(pref_mod._normalize_replace_memory_id(True), "")
        self.assertEqual(pref_mod._normalize_replace_memory_id(False), "")

    def test_none_and_other_types(self):
        self.assertEqual(pref_mod._normalize_replace_memory_id(None), "")
        self.assertEqual(pref_mod._normalize_replace_memory_id(["mem-1"]), "")
        self.assertEqual(pref_mod._normalize_replace_memory_id({"id": "1"}), "")


class TestGetUidResilience(unittest.TestCase):
    """Test user ID extraction across configurations."""

    def setUp(self):
        self.orig_agent_config = pref_mod._agent_config

    def tearDown(self):
        pref_mod._agent_config = self.orig_agent_config

    def test_nested_configurable_user_id(self):
        config = {"configurable": {"user_id": "  user-nested  "}}
        self.assertEqual(pref_mod._get_uid(config), "user-nested")

    def test_nested_configurable_uid(self):
        config = {"configurable": {"uid": "  uid-nested  "}}
        self.assertEqual(pref_mod._get_uid(config), "uid-nested")

    def test_top_level_user_id(self):
        config = {"user_id": "  top-user  "}
        self.assertEqual(pref_mod._get_uid(config), "top-user")

    def test_top_level_uid(self):
        config = {"uid": "  top-uid  "}
        self.assertEqual(pref_mod._get_uid(config), "top-uid")

    def test_precedence_nested_over_top_level(self):
        config = {"configurable": {"user_id": "nested-id"}, "user_id": "top-id"}
        self.assertEqual(pref_mod._get_uid(config), "nested-id")

    def test_non_dict_and_none_configs_without_agent_context(self):
        pref_mod._agent_config = lambda: None
        self.assertEqual(pref_mod._get_uid(None), "")
        self.assertEqual(pref_mod._get_uid("invalid-config"), "")
        self.assertEqual(pref_mod._get_uid({"configurable": None}), "")
        self.assertEqual(pref_mod._get_uid({"configurable": "string"}), "")

    def test_fallback_to_agent_config(self):
        pref_mod._agent_config = lambda: {"configurable": {"user_id": "ctx-user"}}
        self.assertEqual(pref_mod._get_uid(None), "ctx-user")
        self.assertEqual(pref_mod._get_uid({}), "ctx-user")
        self.assertEqual(pref_mod._get_uid({"configurable": None}), "ctx-user")

        pref_mod._agent_config = lambda: {"uid": "ctx-top-uid"}
        self.assertEqual(pref_mod._get_uid(None), "ctx-top-uid")


class TestPreferenceDuplicateMessage(unittest.TestCase):
    """Test preference_duplicate_message against corrupt or malformed inputs."""

    def test_non_sequence_hits_return_none(self):
        self.assertIsNone(pref_mod.preference_duplicate_message("Prefers tea", None))
        self.assertIsNone(pref_mod.preference_duplicate_message("Prefers tea", "not-a-list"))
        self.assertIsNone(pref_mod.preference_duplicate_message("Prefers tea", 123))

    def test_non_dict_hits_skipped(self):
        hits = [None, "bad-string", 456, ["nested"], {"content": "Prefers coffee", "score": 0.1}]
        self.assertIsNone(pref_mod.preference_duplicate_message("Prefers tea", hits))

    def test_valid_hit_after_corrupted_hits(self):
        hits = [
            None,
            "corrupt",
            {"memory_id": "m-42", "content": "Prefers tea"},
        ]
        msg = pref_mod.preference_duplicate_message("Prefers tea", hits)
        self.assertEqual(msg, "Similar preference already exists (memory_id=m-42): Prefers tea")

    def test_score_threshold_matching(self):
        hits = [{"memory_id": "m-99", "content": "Prefers green tea", "score": 0.95}]
        msg = pref_mod.preference_duplicate_message("Prefers tea", hits)
        self.assertEqual(msg, "Similar preference already exists (memory_id=m-99): Prefers green tea")


class TestSaveUserPreferenceToolValidation(unittest.TestCase):
    """Test validation and early exits in save_user_preference_tool."""

    def setUp(self):
        self.orig_firestore = pref_mod.get_data_plane_firestore_client
        # Ensure Firestore is never called when inputs are invalid
        pref_mod.get_data_plane_firestore_client = MagicMock(
            side_effect=AssertionError("Firestore client was touched on invalid input!")
        )

    def tearDown(self):
        pref_mod.get_data_plane_firestore_client = self.orig_firestore

    def test_empty_or_whitespace_preferences_rejected(self):
        for bad_pref in ["", "   ", "\t\n ", None, 123, False, ["Prefers tea"], {"pref": "tea"}]:
            with self.subTest(bad_pref=bad_pref):
                res = pref_mod.save_user_preference_tool(
                    bad_pref,
                    config={"configurable": {"user_id": "user-1"}},
                )
                self.assertEqual(res, "Error: Preference must be a non-empty string")

    def test_missing_user_id_rejected_before_firestore(self):
        # Save orig agent_config
        orig_ctx = pref_mod._agent_config
        pref_mod._agent_config = lambda: None
        try:
            res = pref_mod.save_user_preference_tool("Prefers dark mode", config={})
            self.assertEqual(res, "Error: Could not determine user ID")
        finally:
            pref_mod._agent_config = orig_ctx


class TestProvenanceDefensive(unittest.TestCase):
    """Test _write_provenance robustness."""

    def test_write_provenance_handles_non_string_preference(self):
        class Provenance:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        orig_prov = pref_mod.LedgerProvenance
        pref_mod.LedgerProvenance = Provenance
        try:
            prov = pref_mod._write_provenance("u1", None, {"configurable": {"chat_session_id": "s1"}})
            self.assertEqual(prov.source_id, "s1")
            self.assertEqual(prov.source_type, "agent_chat")
        finally:
            pref_mod.LedgerProvenance = orig_prov


if __name__ == "__main__":
    unittest.main()
