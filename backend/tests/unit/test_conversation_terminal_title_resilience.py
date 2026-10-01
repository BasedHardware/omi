"""Hermetic unit tests for resilience and input validation in conversation_terminal_title."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if not (BACKEND_DIR / "database").is_dir():
    for parent in Path(__file__).resolve().parents:
        if (parent / "database").is_dir():
            BACKEND_DIR = parent
            break
        if (parent / "backend" / "database").is_dir():
            BACKEND_DIR = parent / "backend"
            break
        if (parent / "omi_prep" / "backend" / "database").is_dir():
            BACKEND_DIR = parent / "omi_prep" / "backend"
            break

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Established test helpers from tests/unit/conftest.py / memory_import_isolation.py
try:
    from tests.unit.conftest import (
        _AutoMockModule as AutoMockModule,
        install_database_client_stub,
        restore_sys_modules,
        snapshot_sys_modules,
    )
except ImportError:
    try:
        from tests.unit.memory_import_isolation import (
            AutoMockModule,
            install_database_client_stub,
            restore_sys_modules,
            snapshot_sys_modules,
        )
    except ImportError:
        class AutoMockModule(types.ModuleType):
            def __getattr__(self, name: str):
                if name.startswith("__") and name.endswith("__"):
                    raise AttributeError(name)
                mock = MagicMock()
                setattr(self, name, mock)
                return mock

        def snapshot_sys_modules(names):
            return {name: sys.modules.get(name) for name in names}

        def restore_sys_modules(saved):
            for name, original in saved.items():
                if original is None:
                    sys.modules.pop(name, None)
                    if "." in name:
                        p, c = name.rsplit(".", 1)
                        pm = sys.modules.get(p)
                        if isinstance(pm, types.ModuleType) and hasattr(pm, c):
                            delattr(pm, c)
                else:
                    sys.modules[name] = original
                    if "." in name:
                        p, c = name.rsplit(".", 1)
                        pm = sys.modules.get(p)
                        if isinstance(pm, types.ModuleType):
                            setattr(pm, c, original)

        def install_database_client_stub():
            client_mod = types.ModuleType("database._client")
            client_mod.db = MagicMock()
            client_mod.get_firestore_client = lambda: client_mod.db
            client_mod.get_customer_firestore_client = lambda: client_mod.db
            sys.modules["database._client"] = client_mod
            database_pkg = sys.modules.get("database")
            if isinstance(database_pkg, types.ModuleType):
                setattr(database_pkg, "_client", client_mod)
            return client_mod


_saved_modules = {}


def setUpModule():
    global _saved_modules
    tracked_names = [
        "database._client",
        "database.conversations",
        "utils.conversations.deterministic_minimum",
        "utils.conversations.recovery",
        "database.conversation_terminal_title",
    ]
    _saved_modules = snapshot_sys_modules(tracked_names)

    # 1. Ensure database package is imported as the real package
    import database

    # 2. Install database._client stub
    install_database_client_stub()

    # 3. Stub database.conversations only if real dependency cannot be imported
    try:
        import database.conversations
    except Exception:
        conv_mod = AutoMockModule("database.conversations")
        conv_mod.effective_user_title = lambda title: title.strip() if isinstance(title, str) and title.strip() else None
        conv_mod.decode_transcript_segments_verified = MagicMock(return_value=[])
        sys.modules["database.conversations"] = conv_mod
        setattr(database, "conversations", conv_mod)

    # 4. Stub utils.conversations helpers if real dependencies are unavailable
    import utils
    try:
        import utils.conversations.deterministic_minimum
    except Exception:
        if not hasattr(utils, "conversations"):
            utils_conv = types.ModuleType("utils.conversations")
            utils_conv.__path__ = []
            utils.conversations = utils_conv
            sys.modules["utils.conversations"] = utils_conv
        det_min = AutoMockModule("utils.conversations.deterministic_minimum")
        det_min.deterministic_minimum_title = lambda conv, tz_name_provider=None: "Deterministic Title"
        sys.modules["utils.conversations.deterministic_minimum"] = det_min
        setattr(utils.conversations, "deterministic_minimum", det_min)

    try:
        import utils.conversations.recovery
    except Exception:
        rec = AutoMockModule("utils.conversations.recovery")
        rec.structured_has_protected_content = lambda struct, user_title: False
        sys.modules["utils.conversations.recovery"] = rec
        setattr(utils.conversations, "recovery", rec)

    # 5. Import target module
    if "database.conversation_terminal_title" in sys.modules:
        del sys.modules["database.conversation_terminal_title"]
    try:
        mod = importlib.import_module("database.conversation_terminal_title")
    except ImportError:
        mod = importlib.import_module("conversation_terminal_title_fixed")

    # 6. Populate symbols into globals for test classes
    for name in getattr(mod, "__all__", []):
        globals()[name] = getattr(mod, name)
    globals()["_has_described_photo"] = getattr(mod, "_has_described_photo", None)
    globals()["_described"] = getattr(mod, "_described", None)
    globals()["_value_bytes"] = getattr(mod, "_value_bytes", None)
    globals()["_title_update"] = getattr(mod, "_title_update", None)


def tearDownModule():
    restore_sys_modules(_saved_modules)


class TestCleanId(unittest.TestCase):
    def test_valid_ids(self):
        self.assertEqual(_clean_id("user_123"), "user_123")
        self.assertEqual(_clean_id("  user-abc_456  "), "user-abc_456")
        self.assertEqual(_clean_id("a" * MAX_ID_LENGTH), "a" * MAX_ID_LENGTH)

    def test_non_string_raises(self):
        with self.assertRaises(ValueError):
            _clean_id(None, "uid")
        with self.assertRaises(ValueError):
            _clean_id(12345, "uid")

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            _clean_id("", "uid")
        with self.assertRaises(ValueError):
            _clean_id("   \t\n  ", "uid")

    def test_length_overrun_raises(self):
        with self.assertRaises(ValueError):
            _clean_id("a" * (MAX_ID_LENGTH + 1), "uid")

    def test_path_traversal_and_null_bytes_raises(self):
        with self.assertRaises(ValueError):
            _clean_id("../bad_uid", "uid")
        with self.assertRaises(ValueError):
            _clean_id("users/123", "uid")
        with self.assertRaises(ValueError):
            _clean_id("users\\123", "uid")
        with self.assertRaises(ValueError):
            _clean_id("user\0admin", "uid")


class TestEstimateFirestoreDocumentBytes(unittest.TestCase):
    def test_scalars_and_primitives(self):
        self.assertEqual(_value_bytes(None), 1)
        self.assertEqual(_value_bytes(True), 1)
        self.assertEqual(_value_bytes(False), 1)
        self.assertEqual(_value_bytes(42), 8)
        self.assertEqual(_value_bytes(3.14), 8)
        self.assertEqual(_value_bytes(datetime.now(timezone.utc)), 8)
        self.assertEqual(_value_bytes("hello"), 6)
        self.assertEqual(_value_bytes(b"raw_bytes"), 9)

    def test_nested_map_and_array(self):
        data = {
            "title": "Test Title",
            "count": 5,
            "items": ["a", "b", "c"],
            "meta": {"nested": True},
        }
        size = estimate_firestore_document_bytes(data, "users/u1/conversations/c1")
        self.assertGreater(size, 0)
        self.assertIsInstance(size, int)

    def test_deep_recursion_guard(self):
        # Nest 1200 levels past Python's default recursion limit (1000).
        # Without depth guard, this raises RecursionError.
        # With depth guard, recursion halts cleanly at depth 32 and caps size at exactly 1286 bytes.
        curr: dict = {"key": "leaf"}
        for _ in range(1200):
            curr = {"child": curr}
        size = _value_bytes(curr)
        self.assertEqual(size, 1286)

    def test_document_path_handling(self):
        data = {"field": "val"}
        size_with_path = estimate_firestore_document_bytes(data, "users/u1/conversations/c1")
        size_fallback = estimate_firestore_document_bytes(data, None)
        self.assertGreater(size_with_path, 0)
        self.assertGreater(size_fallback, 0)
        size_slashes = estimate_firestore_document_bytes(data, "//users///u1//conversations//c1//")
        self.assertGreater(size_slashes, 0)


class TestFitDocumentLimit(unittest.TestCase):
    def test_merges_extras_when_within_limit(self):
        conv = {"status": "processing"}
        conv_ref = MagicMock()
        conv_ref.path = "users/u1/conversations/c1"
        base_update = {"status": "completed"}
        extras = {"structured": {"title": "A Title"}}

        result = fit_document_limit(conv, conv_ref, base_update, extras)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["structured"]["title"], "A Title")

    def test_drops_extras_when_exceeding_ceiling(self):
        huge_text = "x" * (FIRESTORE_MAX_DOCUMENT_BYTES - 1000)
        conv = {"huge_blob": huge_text}
        conv_ref = MagicMock()
        conv_ref.path = "users/u1/conversations/c1"
        base_update = {"status": "completed"}
        extras = {"structured": {"title": "Dropped Title"}, "summary_retryable": True}

        result = fit_document_limit(conv, conv_ref, base_update, extras)
        self.assertEqual(result, base_update)
        self.assertNotIn("structured", result)

    def test_empty_extras_returns_base(self):
        conv = {"status": "processing"}
        conv_ref = MagicMock()
        base_update = {"status": "completed"}
        self.assertEqual(fit_document_limit(conv, conv_ref, base_update, {}), base_update)


class TestUserTimeZone(unittest.TestCase):
    def test_valid_time_zone(self):
        client = MagicMock()
        snap = MagicMock()
        snap.exists = True
        snap.to_dict.return_value = {"time_zone": "America/New_York"}
        client.collection.return_value.document.return_value.get.return_value = snap

        self.assertEqual(user_time_zone(client, "valid_uid"), "America/New_York")

    def test_missing_or_invalid_uid_returns_none(self):
        client = MagicMock()
        self.assertIsNone(user_time_zone(client, ""))
        self.assertIsNone(user_time_zone(client, "   "))
        self.assertIsNone(user_time_zone(client, "../bad/path"))

    def test_client_error_returns_none(self):
        client = MagicMock()
        client.collection.side_effect = RuntimeError("Firestore unavailable")
        self.assertIsNone(user_time_zone(client, "user_123"))


class TestTranscriptTexts(unittest.TestCase):
    def test_invalid_uid_returns_empty_false(self):
        self.assertEqual(transcript_texts("", {}), ([], False))
        self.assertEqual(transcript_texts("   ", {}), ([], False))
        self.assertEqual(transcript_texts("../bad_id", {}), ([], False))

    def test_invalid_conversation_type(self):
        self.assertEqual(transcript_texts("user_123", None), ([], False))
        self.assertEqual(transcript_texts("user_123", "not_a_map"), ([], False))

    def test_empty_transcript_segments(self):
        self.assertEqual(transcript_texts("user_123", {"transcript_segments": []}), ([], True))
        self.assertEqual(transcript_texts("user_123", {}), ([], True))


class TestRetryableFailureCodes(unittest.TestCase):
    def test_production_codes_included(self):
        self.assertIn("final_attempt_failed", SUMMARY_RETRYABLE_FAILURE_CODES)
        self.assertIn("processing_failed", SUMMARY_RETRYABLE_FAILURE_CODES)
        self.assertNotIn("recovery_structure_unavailable", SUMMARY_RETRYABLE_FAILURE_CODES)
        self.assertNotIn("timeout", SUMMARY_RETRYABLE_FAILURE_CODES)
        self.assertEqual(len(SUMMARY_RETRYABLE_FAILURE_CODES), 2)

    def test_photo_probe_limit_bound(self):
        self.assertEqual(PHOTO_DESCRIPTION_PROBE_LIMIT, 64)


if __name__ == "__main__":
    unittest.main()
