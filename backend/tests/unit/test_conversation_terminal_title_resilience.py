"""Hermetic unit tests for resilience and input validation in conversation_terminal_title."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

class AutoMockModule(types.ModuleType):
    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock

def ensure_module(name: str):
    if name not in sys.modules:
        m = AutoMockModule(name)
        sys.modules[name] = m
        if "." in name:
            parent_name, child_name = name.rsplit(".", 1)
            ensure_module(parent_name)
            setattr(sys.modules[parent_name], child_name, m)
    return sys.modules[name]

for mod_name in [
    "google",
    "google.cloud",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.api_core",
    "google.api_core.exceptions",
]:
    ensure_module(mod_name)

import database
database._client = AutoMockModule("database._client")
sys.modules["database._client"] = database._client

conversations_mock = AutoMockModule("database.conversations")
conversations_mock.effective_user_title = lambda title: title if isinstance(title, str) and title.strip() else None
database.conversations = conversations_mock
sys.modules["database.conversations"] = conversations_mock

deterministic_minimum_mock = AutoMockModule("utils.conversations.deterministic_minimum")
deterministic_minimum_mock.deterministic_minimum_title = lambda conv, tz_name_provider=None: "Deterministic Title"
sys.modules["utils.conversations.deterministic_minimum"] = deterministic_minimum_mock

recovery_mock = AutoMockModule("utils.conversations.recovery")
recovery_mock.structured_has_protected_content = lambda struct, user_title: False
sys.modules["utils.conversations.recovery"] = recovery_mock

import unittest
from datetime import datetime, timezone

import pytest

from database.conversation_terminal_title import (
    FIRESTORE_MAX_DOCUMENT_BYTES,
    MAX_ID_LENGTH,
    PHOTO_DESCRIPTION_PROBE_LIMIT,
    SUMMARY_RETRYABLE_FAILURE_CODES,
    TERMINAL_SIZE_HEADROOM_BYTES,
    _clean_id,
    _described,
    _has_described_photo,
    _value_bytes,
    dead_letter_conversation_updates,
    estimate_firestore_document_bytes,
    fit_document_limit,
    kept_row_terminal_update,
    transcript_texts,
    user_time_zone,
)


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
        # Create a deeply nested map beyond depth 32
        curr: dict = {"key": "leaf"}
        for _ in range(40):
            curr = {"child": curr}
        # Must not raise RecursionError
        size = _value_bytes(curr)
        assert size > 0

    def test_document_path_handling(self):
        data = {"field": "val"}
        size_with_path = estimate_firestore_document_bytes(data, "users/u1/conversations/c1")
        size_fallback = estimate_firestore_document_bytes(data, None)
        assert size_with_path > 0
        assert size_fallback > 0
        # Consecutive slashes handled gracefully
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
        # Create huge conversation that pushes estimate over 1 MiB ceiling
        huge_text = "x" * (FIRESTORE_MAX_DOCUMENT_BYTES - 1000)
        conv = {"huge_blob": huge_text}
        conv_ref = MagicMock()
        conv_ref.path = "users/u1/conversations/c1"
        base_update = {"status": "completed"}
        extras = {"structured": {"title": "Dropped Title"}, "summary_retryable": True}

        result = fit_document_limit(conv, conv_ref, base_update, extras)
        # Extras are dropped to ensure the terminal transaction can commit
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
        client.collection.assert_called_with("users")
        client.collection.return_value.document.assert_called_with("valid_uid")

    def test_invalid_uid_returns_none(self):
        client = MagicMock()
        assert user_time_zone(client, "../bad_uid") is None
        assert user_time_zone(client, "") is None
        assert user_time_zone(client, None) is None

    def test_none_client_returns_none(self):
        assert user_time_zone(None, "valid_uid") is None

    def test_missing_document_returns_none(self):
        client = MagicMock()
        snap = MagicMock()
        snap.exists = False
        client.collection.return_value.document.return_value.get.return_value = snap
        assert user_time_zone(client, "valid_uid") is None

    def test_firestore_exception_handled_gracefully(self):
        client = MagicMock()
        client.collection.side_effect = RuntimeError("Firestore unavailable")
        assert user_time_zone(client, "valid_uid") is None


class TestTranscriptTexts:
    def test_empty_or_invalid_uid_fails_closed(self):
        texts, decoded = transcript_texts("", {})
        assert texts == []
        assert decoded is False

        texts, decoded = transcript_texts("../bad_path", {})
        assert texts == []
        assert decoded is False

        texts, decoded = transcript_texts(None, {})
        assert texts == []
        assert decoded is False

    def test_no_segments_returns_empty_decoded(self):
        texts, decoded = transcript_texts("valid_uid", {})
        assert texts == []
        assert decoded is True


class TestDescribedPhoto:
    def test_described_inline(self):
        assert _described({"description": "a sunset"}) is True
        assert _described({"description": ""}) is False
        assert _described({"description": "   "}) is False
        assert _described({}) is False
        assert _described(None) is False

    def test_has_described_photo_inline(self):
        conv = {"photos": [{"description": "valid photo"}]}
        assert _has_described_photo(conv, MagicMock(), MagicMock()) is True

    def test_has_described_photo_empty(self):
        conv = {"photos": []}
        conv_ref = MagicMock()
        conv_ref.collection.return_value.limit.return_value.stream.return_value = []
        assert _has_described_photo(conv, conv_ref, MagicMock()) is False


class TestDeadLetterConversationUpdates:
    def test_marks_summary_retryable_for_recoverable_failures(self):
        conv = {"photos": [{"description": "a photo"}]}
        conv_ref = MagicMock()
        conv_ref.path = "users/u1/conversations/c1"

        for code in SUMMARY_RETRYABLE_FAILURE_CODES:
            res = dead_letter_conversation_updates(
                uid="u1",
                conversation=conv,
                conversation_ref=conv_ref,
                transaction=MagicMock(),
                failure_code=code,
                time_zone_for_uid=None,
            )
            assert res.get("status") == "completed"
            assert res.get("finalization_status") == "dead_letter"
            assert res.get("summary_retryable") is True

    def test_does_not_mark_retryable_for_unrecoverable_failures(self):
        conv = {"photos": [{"description": "a photo"}]}
        conv_ref = MagicMock()
        conv_ref.path = "users/u1/conversations/c1"

        res = dead_letter_conversation_updates(
            uid="u1",
            conversation=conv,
            conversation_ref=conv_ref,
            transaction=MagicMock(),
            failure_code="recovery_structure_unavailable",
            time_zone_for_uid=None,
        )
        assert res.get("status") == "completed"
        assert res.get("summary_retryable") is None
