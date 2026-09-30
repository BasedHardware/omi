import uuid
from unittest.mock import MagicMock

import pytest

from database.recording_sessions import (
    LIFECYCLE_ENVELOPE_VERSION,
    MAX_TRANSACTION_RETRIES,
    RECORDING_SESSIONS_COLLECTION,
    _binding,
    _clamp_lifecycle_sequence,
    _clamp_lifecycle_version,
    _session_ref,
    _validate_id,
    record_lifecycle_event,
    renew_recording_session_lease,
    run_with_transaction_contention_retry,
)


class TestIdentifierValidation:
    def test_valid_identifier_alphanumeric(self):
        assert _validate_id("valid_id_123", "test_field") == "valid_id_123"

    def test_valid_uuid_with_hyphens(self):
        test_uuid = str(uuid.uuid4())
        assert _validate_id(test_uuid, "session_id") == test_uuid

    def test_empty_identifier_raises(self):
        with pytest.raises(ValueError, match="test_field must be a non-empty string"):
            _validate_id("", "test_field")
        with pytest.raises(ValueError, match="test_field must be a non-empty string"):
            _validate_id("   ", "test_field")

    def test_none_identifier_raises(self):
        with pytest.raises(ValueError, match="test_field must be a non-empty string"):
            _validate_id(None, "test_field")

    def test_path_traversal_chars_raises(self):
        invalid_ids = ["/path", "..", "dir\\file", "valid/../id", "foo/bar"]
        for invalid_id in invalid_ids:
            with pytest.raises(ValueError, match="test_field contains invalid characters"):
                _validate_id(invalid_id, "test_field")

    def test_null_bytes_raises(self):
        with pytest.raises(ValueError, match="test_field contains invalid characters"):
            _validate_id("id\x00bad", "test_field")

    def test_non_string_identifier_raises(self):
        with pytest.raises(ValueError, match="test_field must be a non-empty string"):
            _validate_id(123, "test_field")

    def test_length_exceeds_raises(self):
        with pytest.raises(ValueError, match="test_field exceeds maximum length"):
            _validate_id("a" * 129, "test_field")


class TestBoundaryClamping:
    def test_clamp_lifecycle_sequence_positive(self):
        assert _clamp_lifecycle_sequence(5) == 5

    def test_clamp_lifecycle_sequence_negative(self):
        assert _clamp_lifecycle_sequence(-1) == 0

    def test_clamp_lifecycle_sequence_zero(self):
        assert _clamp_lifecycle_sequence(0) == 0

    def test_clamp_lifecycle_sequence_non_integer(self):
        assert _clamp_lifecycle_sequence("invalid") == 0
        assert _clamp_lifecycle_sequence(None) == 0
        assert _clamp_lifecycle_sequence(3.14) == 3

    def test_clamp_lifecycle_version_positive(self):
        assert _clamp_lifecycle_version(2) == 2

    def test_clamp_lifecycle_version_negative(self):
        assert _clamp_lifecycle_version(-5) == 1

    def test_clamp_lifecycle_version_zero(self):
        assert _clamp_lifecycle_version(0) == 1

    def test_clamp_lifecycle_version_non_integer(self):
        assert _clamp_lifecycle_version("invalid") == LIFECYCLE_ENVELOPE_VERSION
        assert _clamp_lifecycle_version(None) == LIFECYCLE_ENVELOPE_VERSION


class TestSessionRefAndScoping:
    def test_session_ref_scopes_under_users(self):
        mock_client = MagicMock()
        uid = "user-123"
        session_id = str(uuid.uuid4())
        ref = _session_ref(mock_client, uid, session_id)
        mock_client.collection.assert_called_once_with("users")
        mock_client.collection.return_value.document.assert_called_once_with(uid)
        mock_client.collection.return_value.document.return_value.collection.assert_called_once_with(
            RECORDING_SESSIONS_COLLECTION
        )
        mock_client.collection.return_value.document.return_value.collection.return_value.document.assert_called_once_with(
            session_id
        )

    def test_session_ref_rejects_path_traversal(self):
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="uid contains invalid characters"):
            _session_ref(mock_client, "../evil_uid", "session-1")

        with pytest.raises(ValueError, match="recording_session_id contains invalid characters"):
            _session_ref(mock_client, "user-1", "../../evil_session")


class TestBindingClamping:
    def test_binding_clamps_data(self):
        data = {
            "conversation_id": "conv-1",
            "lifecycle_version": -3,
            "lifecycle_sequence": -10,
            "lifecycle_phase": "in_progress",
        }
        b = _binding(data, "session-1", mapping_conflict=False)
        assert b["recording_session_id"] == "session-1"
        assert b["conversation_id"] == "conv-1"
        assert b["lifecycle_version"] == 1
        assert b["lifecycle_sequence"] == 0
        assert b["mapping_conflict"] is False


class TestPublicApiValidation:
    def test_renew_lease_rejects_empty_identifiers_gracefully(self):
        mock_client = MagicMock()
        assert renew_recording_session_lease("", "session-1", "conv-1", firestore_client=mock_client) is False
        assert renew_recording_session_lease("uid-1", "", "conv-1", firestore_client=mock_client) is False
        assert renew_recording_session_lease("uid-1", "session-1", "../bad_conv", firestore_client=mock_client) is False

    def test_record_lifecycle_event_rejects_invalid_phase(self):
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="unsupported recording lifecycle phase"):
            record_lifecycle_event("uid-1", "session-1", "conv-1", "non_existent_phase", firestore_client=mock_client)

    def test_run_with_transaction_contention_retry(self):
        mock_client = MagicMock()
        mock_callback = MagicMock(return_value="executed")
        # Ensure firestore.transactional pattern is invoked
        mock_tx = MagicMock()
        mock_client.transaction.return_value = mock_tx
        res = run_with_transaction_contention_retry(mock_client, mock_callback)
        mock_callback.assert_called_once()
