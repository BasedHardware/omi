"""Hermetic unit tests for resilience and input validation in conversation_terminal_title."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@contextmanager
def stub_modules(mod_names: list[str]):
    """Context manager to scope stubs cleanly without module-level AST pollution."""
    saved = {}
    for name in mod_names:
        saved[name] = sys.modules.get(name)
        if name not in sys.modules:
            if name in ("database", "utils", "utils.conversations"):
                pkg = ModuleType(name)
                pkg.__path__ = []
                sys.modules[name] = pkg
            else:
                sys.modules[name] = MagicMock()
    try:
        yield
    finally:
        for name, orig in saved.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig


def load_module_fresh(module_name: str, stub_names: list[str]) -> ModuleType:
    """Import target module under an isolated, hermetic stub set."""
    with stub_modules(stub_names):
        if module_name in sys.modules:
            del sys.modules[module_name]
        return importlib.import_module(module_name)


@pytest.fixture(autouse=True, scope="module")
def setup_target():
    """Scoping fixture that installs stubs and loads target without failing pytest collection."""
    stub_names = [
        "google",
        "google.cloud",
        "google.cloud.firestore",
        "google.cloud.firestore_v1",
        "google.api_core",
        "google.api_core.exceptions",
        "database",
        "database.conversations",
        "utils",
        "utils.conversations",
        "utils.conversations.deterministic_minimum",
        "utils.conversations.recovery",
    ]
    mod = load_module_fresh("database.conversation_terminal_title", stub_names)
    # Populate symbols into module globals for test access
    for name in getattr(mod, "__all__", []):
        globals()[name] = getattr(mod, name)
    globals()["_has_described_photo"] = getattr(mod, "_has_described_photo", None)
    globals()["_described"] = getattr(mod, "_described", None)
    globals()["_value_bytes"] = getattr(mod, "_value_bytes", None)
    globals()["_title_update"] = getattr(mod, "_title_update", None)
    yield


class TestCleanId:
    def test_valid_ids(self):
        assert _clean_id("user_123") == "user_123"
        assert _clean_id("  user-abc_456  ") == "user-abc_456"
        assert _clean_id("a" * MAX_ID_LENGTH) == "a" * MAX_ID_LENGTH

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="uid must be a string"):
            _clean_id(None, "uid")
        with pytest.raises(ValueError, match="uid must be a string"):
            _clean_id(12345, "uid")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="uid cannot be empty"):
            _clean_id("", "uid")
        with pytest.raises(ValueError, match="uid cannot be empty"):
            _clean_id("   \t\n  ", "uid")

    def test_length_overrun_raises(self):
        with pytest.raises(ValueError, match="exceeds maximum length"):
            _clean_id("a" * (MAX_ID_LENGTH + 1), "uid")

    def test_path_traversal_and_null_bytes_raises(self):
        with pytest.raises(ValueError, match="invalid path traversal"):
            _clean_id("../bad_uid", "uid")
        with pytest.raises(ValueError, match="invalid path traversal"):
            _clean_id("users/123", "uid")
        with pytest.raises(ValueError, match="invalid path traversal"):
            _clean_id("users\\123", "uid")
        with pytest.raises(ValueError, match="invalid path traversal"):
            _clean_id("user\0admin", "uid")


class TestEstimateFirestoreDocumentBytes:
    def test_scalars_and_primitives(self):
        assert _value_bytes(None) == 1
        assert _value_bytes(True) == 1
        assert _value_bytes(False) == 1
        assert _value_bytes(42) == 8
        assert _value_bytes(3.14) == 8
        assert _value_bytes(datetime.now(timezone.utc)) == 8
        assert _value_bytes("hello") == 6  # 5 + 1
        assert _value_bytes(b"raw_bytes") == 9

    def test_nested_map_and_array(self):
        data = {
            "title": "Test Title",
            "count": 5,
            "items": ["a", "b", "c"],
            "meta": {"nested": True},
        }
        size = estimate_firestore_document_bytes(data, "users/u1/conversations/c1")
        assert size > 0
        assert isinstance(size, int)

    def test_deep_recursion_guard(self):
        # Nest 1200 levels past Python's default recursion limit (1000).
        # Without depth guard, this raises RecursionError.
        # With depth guard, recursion halts cleanly at depth 32 and caps size at exactly 1286 bytes.
        curr: dict = {"key": "leaf"}
        for _ in range(1200):
            curr = {"child": curr}
        size = _value_bytes(curr)
        assert size == 1286

    def test_document_path_handling(self):
        data = {"field": "val"}
        size_with_path = estimate_firestore_document_bytes(data, "users/u1/conversations/c1")
        size_fallback = estimate_firestore_document_bytes(data, None)
        assert size_with_path > 0
        assert size_fallback > 0
        size_slashes = estimate_firestore_document_bytes(data, "//users///u1//conversations//c1//")
        assert size_slashes > 0


class TestFitDocumentLimit:
    def test_merges_extras_when_within_limit(self):
        conv = {"status": "processing"}
        conv_ref = MagicMock()
        conv_ref.path = "users/u1/conversations/c1"
        base_update = {"status": "completed"}
        extras = {"structured": {"title": "A Title"}}

        result = fit_document_limit(conv, conv_ref, base_update, extras)
        assert result["status"] == "completed"
        assert result["structured"]["title"] == "A Title"

    def test_drops_extras_when_exceeding_ceiling(self):
        huge_text = "x" * (FIRESTORE_MAX_DOCUMENT_BYTES - 1000)
        conv = {"huge_blob": huge_text}
        conv_ref = MagicMock()
        conv_ref.path = "users/u1/conversations/c1"
        base_update = {"status": "completed"}
        extras = {"structured": {"title": "Dropped Title"}, "summary_retryable": True}

        result = fit_document_limit(conv, conv_ref, base_update, extras)
        assert result == base_update
        assert "structured" not in result

    def test_empty_extras_returns_base(self):
        conv = {"status": "processing"}
        conv_ref = MagicMock()
        base_update = {"status": "completed"}
        assert fit_document_limit(conv, conv_ref, base_update, {}) == base_update


class TestUserTimeZone:
    def test_valid_time_zone(self):
        client = MagicMock()
        snap = MagicMock()
        snap.exists = True
        snap.to_dict.return_value = {"time_zone": "America/New_York"}
        client.collection.return_value.document.return_value.get.return_value = snap

        assert user_time_zone(client, "valid_uid") == "America/New_York"

    def test_missing_or_invalid_uid_returns_none(self):
        client = MagicMock()
        assert user_time_zone(client, "") is None
        assert user_time_zone(client, "   ") is None
        assert user_time_zone(client, "../bad/path") is None

    def test_client_error_returns_none(self):
        client = MagicMock()
        client.collection.side_effect = RuntimeError("Firestore unavailable")
        assert user_time_zone(client, "user_123") is None


class TestTranscriptTexts:
    def test_invalid_uid_returns_empty_false(self):
        assert transcript_texts("", {}) == ([], False)
        assert transcript_texts("   ", {}) == ([], False)
        assert transcript_texts("../bad_id", {}) == ([], False)

    def test_invalid_conversation_type(self):
        assert transcript_texts("user_123", None) == ([], False)
        assert transcript_texts("user_123", "not_a_map") == ([], False)

    def test_empty_transcript_segments(self):
        assert transcript_texts("user_123", {"transcript_segments": []}) == ([], True)
        assert transcript_texts("user_123", {}) == ([], True)


class TestRetryableFailureCodes:
    def test_production_and_transient_codes_included(self):
        assert "final_attempt_failed" in SUMMARY_RETRYABLE_FAILURE_CODES
        assert "processing_failed" in SUMMARY_RETRYABLE_FAILURE_CODES
        assert "timeout" in SUMMARY_RETRYABLE_FAILURE_CODES
        assert "recovery_structure_unavailable" not in SUMMARY_RETRYABLE_FAILURE_CODES

    def test_photo_probe_limit_bound(self):
        assert PHOTO_DESCRIPTION_PROBE_LIMIT == 64
