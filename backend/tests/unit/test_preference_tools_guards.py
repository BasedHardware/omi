"""Tests verifying parameter guards, coercion, and config handling in preference_tools.py.

Hermetic isolated unit test suite covering:
1. replace_memory_id=None and non-string types do not raise AttributeError.
2. preference=None, empty string "", and whitespace "   " return clean validation errors without crashing.
3. _get_uid extraction resolves user_id/uid from nested configurable and top-level config.
4. user_stated boolean coercion from string ("true"/"false"), int (1/0), and bool.
5. slot whitespace stripping, empty/None handling, and non-string handling.
6. preference_duplicate_message resilience against malformed or non-dict hit objects.
"""

from enum import Enum
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
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


# 1. Langchain core stubs
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")
if not hasattr(_lc_tools, "tool"):
    _lc_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
if not hasattr(_lc_runnables, "RunnableConfig"):
    _lc_runnables.RunnableConfig = dict

# 2. Package hierarchy stubs
for _p in [
    "database",
    "models",
    "utils",
    "utils.messaging",
    "utils.memory",
    "testing",
    "testing.parity_pack_v0",
]:
    _pkg(_p)

# 3. Messaging stubs
_undo = _mod("utils.messaging.undo")
_undo.record_write = MagicMock(return_value="")

_proj = _mod("utils.messaging.projection")
_proj.surface_runtime = MagicMock()
_proj.surface_runtime.get.return_value = None

# 4. Database stubs
_db_client = _mod("database._client")
_db_client.get_data_plane_firestore_client = MagicMock(return_value=MagicMock())

# 5. Model stubs
_kl_policy = _mod("models.knowledge_ledger_policy")


def _canonicalize_ledger_slot(slot, strict=False):
    if not isinstance(slot, str):
        return None
    s = slot.strip().lower()
    valid_slots = {
        "preferred_name",
        "pronouns",
        "primary_language",
        "age_years",
        "timezone",
        "home_city",
        "work_city",
        "occupation",
        "employer",
        "communication_style",
        "dietary_preferences",
        "current_focus",
    }
    return s if s in valid_slots else None


_kl_policy.canonicalize_ledger_slot = _canonicalize_ledger_slot

_mem_contracts = _mod("models.memory_contracts")
_mem_contracts.deterministic_contract_id = (
    lambda prefix, data: hashlib.sha256(f"{prefix}:{data}".encode()).hexdigest()
)

_mem_apply = _mod("models.memory_apply")


class WriterMode(str, Enum):
    compatibility = "compatibility"
    ledger = "ledger"
    direct = "direct"


_mem_apply.WriterMode = WriterMode

_memories = _mod("models.memories")


class MemoryDB:
    @classmethod
    def calculate_score(cls, val):
        return 0.5

    @classmethod
    def model_validate(cls, val):
        return val


_memories.MemoryDB = MemoryDB

_prod_mem = _mod("models.product_memory")


class LedgerWriteReason(str, Enum):
    agent_reusable_conclusion = "agent_reusable_conclusion"
    direct_user_statement = "direct_user_statement"


_prod_mem.LedgerWriteReason = LedgerWriteReason

# 6. Log sanitizer
_sanitizer = _mod("utils.log_sanitizer")
_sanitizer.sanitize_pii = lambda text: str(text)

# 7. Memory adapter and service stubs
_c_adapter = _mod("utils.memory.canonical_memory_adapter")
_mock_read_canonical = MagicMock(return_value=None)
_mock_search_canonical = MagicMock(return_value=[])
_c_adapter.read_canonical_memory_item = _mock_read_canonical
_c_adapter.search_canonical_memories = _mock_search_canonical

_k_ledger = _mod("utils.memory.knowledge_ledger")


class LedgerProvenance:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_copy(self, update=None):
        inst = LedgerProvenance(**self.__dict__)
        if update:
            inst.__dict__.update(update)
        return inst


_k_ledger.LedgerProvenance = LedgerProvenance
_mock_amend_fact = MagicMock(return_value="amended_memory_id")
_mock_save_fact = MagicMock(return_value="saved_memory_id")
_k_ledger.amend_fact = _mock_amend_fact
_k_ledger.save_fact = _mock_save_fact

_m_service = _mod("utils.memory.memory_service")
_mock_memory_service = MagicMock()
_m_service.MemoryService = _mock_memory_service

_m_system = _mod("utils.memory.memory_system")


class MemorySystem(str, Enum):
    CANONICAL = "canonical"


_m_system.MemorySystem = MemorySystem
_m_system.ensure_canonical_apply_control_state = MagicMock(
    return_value=types.SimpleNamespace(writer_mode=WriterMode.ledger)
)

_live_cap = _mod("testing.parity_pack_v0.live_capture")
_live_cap.capture_memory_write = MagicMock()

# Load isolated preference_tools module
pt = _load(
    "utils.retrieval.tools._preference_tools_guards_test",
    "utils/retrieval/tools/preference_tools.py",
)


class TestPreferenceToolsGuards(unittest.TestCase):
    def setUp(self):
        _mock_read_canonical.reset_mock()
        _mock_search_canonical.reset_mock()
        _mock_search_canonical.return_value = []
        _mock_amend_fact.reset_mock()
        _mock_save_fact.reset_mock()
        _mock_save_fact.return_value = "saved_memory_id"

    # -------------------------------------------------------------------------
    # Test 1: replace_memory_id=None and non-string types
    # -------------------------------------------------------------------------
    def test_replace_memory_id_none_or_non_string_does_not_raise(self):
        """Passing replace_memory_id=None or non-string must not raise AttributeError."""
        config = {"configurable": {"user_id": "u1"}}

        # None must not raise AttributeError (e.g. from replace_memory_id.strip())
        res_none = pt.save_user_preference_tool.func(
            preference="Prefers dark mode", replace_memory_id=None, config=config
        )
        self.assertIn("Preference saved (memory_id=saved_memory_id)", res_none)

        # Integer must not raise AttributeError
        res_int = pt.save_user_preference_tool.func(
            preference="Prefers dark mode", replace_memory_id=123, config=config
        )
        self.assertIn("Preference saved (memory_id=saved_memory_id)", res_int)

        # List/dict must not raise AttributeError
        res_list = pt.save_user_preference_tool.func(
            preference="Prefers dark mode", replace_memory_id=[], config=config
        )
        self.assertIn("Preference saved (memory_id=saved_memory_id)", res_list)

        res_dict = pt.save_user_preference_tool.func(
            preference="Prefers dark mode", replace_memory_id={}, config=config
        )
        self.assertIn("Preference saved (memory_id=saved_memory_id)", res_dict)

    # -------------------------------------------------------------------------
    # Test 2: preference=None, empty string "", and whitespace "   "
    # -------------------------------------------------------------------------
    def test_preference_empty_or_whitespace_returns_clean_error(self):
        """preference=None, empty string, and whitespace must return clean validation errors."""
        config = {"configurable": {"user_id": "u1"}}

        # None
        res_none = pt.save_user_preference_tool.func(preference=None, config=config)
        self.assertTrue(res_none.startswith("Error:"), f"Expected Error prefix, got: {res_none}")
        self.assertIn("cannot be empty", res_none.lower())

        # Empty string
        res_empty = pt.save_user_preference_tool.func(preference="", config=config)
        self.assertTrue(res_empty.startswith("Error:"), f"Expected Error prefix, got: {res_empty}")
        self.assertIn("cannot be empty", res_empty.lower())

        # Whitespace
        res_ws = pt.save_user_preference_tool.func(preference="   \t\n  ", config=config)
        self.assertTrue(res_ws.startswith("Error:"), f"Expected Error prefix, got: {res_ws}")
        self.assertIn("cannot be empty", res_ws.lower())

        # Non-string
        res_int = pt.save_user_preference_tool.func(preference=999, config=config)
        self.assertTrue(res_int.startswith("Error:"), f"Expected Error prefix, got: {res_int}")
        self.assertIn("cannot be empty", res_int.lower())

        # Ensure no write was attempted
        _mock_save_fact.assert_not_called()

    # -------------------------------------------------------------------------
    # Test 3: _get_uid extraction with top-level user_id / uid
    # -------------------------------------------------------------------------
    def test_get_uid_nested_and_top_level_resolution(self):
        """_get_uid must resolve user_id and uid from both nested configurable and top-level."""
        # 1. Nested configurable.user_id
        cfg_nested_user_id = {"configurable": {"user_id": "u_nested_user_id"}}
        self.assertEqual("u_nested_user_id", pt._get_uid(cfg_nested_user_id))

        # 2. Nested configurable.uid
        cfg_nested_uid = {"configurable": {"uid": "u_nested_uid"}}
        self.assertEqual("u_nested_uid", pt._get_uid(cfg_nested_uid))

        # 3. Top-level user_id
        cfg_top_user_id = {"user_id": "u_top_user_id"}
        self.assertEqual("u_top_user_id", pt._get_uid(cfg_top_user_id))

        # 4. Top-level uid
        cfg_top_uid = {"uid": "u_top_uid"}
        self.assertEqual("u_top_uid", pt._get_uid(cfg_top_uid))

        # 5. Nested priority over top-level
        cfg_both = {
            "configurable": {"user_id": "u_nested_priority"},
            "user_id": "u_top_ignored",
        }
        self.assertEqual("u_nested_priority", pt._get_uid(cfg_both))

        # 6. Whitespace stripping
        cfg_ws = {"user_id": "  u_padded  "}
        self.assertEqual("u_padded", pt._get_uid(cfg_ws))

        # 7. Empty or missing config
        self.assertEqual("", pt._get_uid({}))
        self.assertEqual("", pt._get_uid(None))

    # -------------------------------------------------------------------------
    # Test 4: user_stated boolean coercion from string/int/bool
    # -------------------------------------------------------------------------
    def test_user_stated_safe_bool_coercion(self):
        """_safe_bool correctly coerces booleans, numeric strings, and ints."""
        # Direct helper verification
        self.assertTrue(pt._safe_bool(True))
        self.assertFalse(pt._safe_bool(False))
        self.assertTrue(pt._safe_bool("true"))
        self.assertTrue(pt._safe_bool("True"))
        self.assertTrue(pt._safe_bool("TRUE"))
        self.assertTrue(pt._safe_bool("1"))
        self.assertTrue(pt._safe_bool("yes"))
        self.assertTrue(pt._safe_bool("t"))
        self.assertTrue(pt._safe_bool(1))
        self.assertFalse(pt._safe_bool(0))
        self.assertFalse(pt._safe_bool("false"))
        self.assertFalse(pt._safe_bool("False"))
        self.assertFalse(pt._safe_bool("0"))
        self.assertFalse(pt._safe_bool("no"))
        self.assertFalse(pt._safe_bool(None))
        self.assertFalse(pt._safe_bool(""))

    def test_user_stated_tool_argument_coercion_flow(self):
        """Calling save_user_preference_tool passes coerced boolean to save_fact."""
        config = {"configurable": {"user_id": "u1"}}

        # String "true" -> user_asserted=True
        _mock_save_fact.reset_mock()
        pt.save_user_preference_tool.func(
            preference="Prefers Linux", user_stated="true", config=config
        )
        self.assertEqual(1, _mock_save_fact.call_count)
        self.assertIs(True, _mock_save_fact.call_args.kwargs.get("user_asserted"))

        # String "false" -> user_asserted=False
        _mock_save_fact.reset_mock()
        pt.save_user_preference_tool.func(
            preference="Prefers Linux", user_stated="false", config=config
        )
        self.assertEqual(1, _mock_save_fact.call_count)
        self.assertIs(False, _mock_save_fact.call_args.kwargs.get("user_asserted"))

        # Int 1 -> user_asserted=True
        _mock_save_fact.reset_mock()
        pt.save_user_preference_tool.func(
            preference="Prefers Linux", user_stated=1, config=config
        )
        self.assertEqual(1, _mock_save_fact.call_count)
        self.assertIs(True, _mock_save_fact.call_args.kwargs.get("user_asserted"))

        # Int 0 -> user_asserted=False
        _mock_save_fact.reset_mock()
        pt.save_user_preference_tool.func(
            preference="Prefers Linux", user_stated=0, config=config
        )
        self.assertEqual(1, _mock_save_fact.call_count)
        self.assertIs(False, _mock_save_fact.call_args.kwargs.get("user_asserted"))

    # -------------------------------------------------------------------------
    # Test 5: slot whitespace stripping and None handling
    # -------------------------------------------------------------------------
    def test_slot_sanitization_and_whitespace_stripping(self):
        """slot values are whitespace-stripped; whitespace-only or non-string resolve to None."""
        config = {"configurable": {"user_id": "u1"}}

        # Valid slot with whitespace -> stripped and canonicalized
        _mock_save_fact.reset_mock()
        pt.save_user_preference_tool.func(
            preference="Lives in Seattle", slot="  home_city  ", config=config
        )
        self.assertEqual(1, _mock_save_fact.call_count)
        self.assertEqual("home_city", _mock_save_fact.call_args.kwargs.get("slot"))

        # Whitespace-only slot -> None
        _mock_save_fact.reset_mock()
        pt.save_user_preference_tool.func(
            preference="Lives in Seattle", slot="    ", config=config
        )
        self.assertEqual(1, _mock_save_fact.call_count)
        self.assertIsNone(_mock_save_fact.call_args.kwargs.get("slot"))

        # Non-string slot -> None
        _mock_save_fact.reset_mock()
        pt.save_user_preference_tool.func(
            preference="Lives in Seattle", slot=123, config=config
        )
        self.assertEqual(1, _mock_save_fact.call_count)
        self.assertIsNone(_mock_save_fact.call_args.kwargs.get("slot"))

        # None slot -> None
        _mock_save_fact.reset_mock()
        pt.save_user_preference_tool.func(
            preference="Lives in Seattle", slot=None, config=config
        )
        self.assertEqual(1, _mock_save_fact.call_count)
        self.assertIsNone(_mock_save_fact.call_args.kwargs.get("slot"))

    # -------------------------------------------------------------------------
    # Test 6: preference_duplicate_message malformed hit resilience
    # -------------------------------------------------------------------------
    def test_preference_duplicate_message_malformed_hits(self):
        """preference_duplicate_message safely ignores non-dict or malformed hits."""
        # Non-dict items in hits list must not raise AttributeError
        res_none_hit = pt.preference_duplicate_message("Prefers tea", [None])
        self.assertIsNone(res_none_hit)

        res_str_hit = pt.preference_duplicate_message("Prefers tea", ["string_hit"])
        self.assertIsNone(res_str_hit)

        res_int_hit = pt.preference_duplicate_message("Prefers tea", [123, 456])
        self.assertIsNone(res_int_hit)

        res_obj_hit = pt.preference_duplicate_message("Prefers tea", [object(), []])
        self.assertIsNone(res_obj_hit)

        # Empty dict or dict with missing keys
        res_empty_dict = pt.preference_duplicate_message("Prefers tea", [{}])
        self.assertIsNone(res_empty_dict)

        # Mixed hits with malformed elements and a valid duplicate
        mixed_hits = [
            None,
            "corrupted_cache",
            123,
            object(),
            {"memory_id": "dup-42", "content": "Prefers tea", "score": 0.95},
        ]
        res_mixed = pt.preference_duplicate_message("Prefers tea", mixed_hits)
        self.assertIsNotNone(res_mixed)
        self.assertIn("Similar preference already exists (memory_id=dup-42): Prefers tea", res_mixed)

        # Unparseable score does not crash
        unparseable_score_hits = [{"memory_id": "m1", "content": "Other", "score": "bad_float"}]
        res_score = pt.preference_duplicate_message("Prefers tea", unparseable_score_hits)
        self.assertIsNone(res_score)


if __name__ == "__main__":
    unittest.main()
