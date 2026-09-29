import pytest
from unittest.mock import MagicMock, patch, call
from google.cloud import firestore
from google.api_core import retry

from backend.database.recording_sessions import (
    RecordingSessionsManager,
    _validate_id,
    _clamp_lifecycle_sequence,
    _clamp_lifecycle_version,
    run_with_transaction_contention_retry,
    LIFECYCLE_ENVELOPE_VERSION,
    MAX_TRANSACTION_RETRIES
)


@pytest.fixture
def mock_db():
    return MagicMock(spec=firestore.Client)


@pytest.fixture
def manager(mock_db):
    return RecordingSessionsManager(mock_db)


# --- Identifier Validation Tests ---

class TestIdentifierValidation:
    def test_valid_identifier(self):
        _validate_id("valid_id_123", "test_field")  # Should not raise

    def test_empty_identifier(self):
        with pytest.raises(ValueError, match="test_field must be a non-empty string"):
            _validate_id("", "test_field")

    def test_none_identifier(self):
        with pytest.raises(ValueError, match="test_field must be a non-empty string"):
            _validate_id(None, "test_field")

    def test_path_traversal_chars(self):
        invalid_ids = ["/path", "..", "dir\\file", "valid/../id"]
        for invalid_id in invalid_ids:
            with pytest.raises(ValueError, match="test_field contains invalid characters"):
                _validate_id(invalid_id, "test_field")

    def test_non_string_identifier(self):
        with pytest.raises(ValueError, match="test_field must be a non-empty string"):
            _validate_id(123, "test_field")


# --- Boundary Clamping Tests ---

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


# --- Transaction Retry Tests ---

class TestTransactionRetry:
    @patch('backend.database.recording_sessions.retry.Retry')
    def test_run_with_transaction_contention_retry(self, mock_retry, mock_db):
        mock_callback = MagicMock(return_value="success")
        mock_db.run_in_transaction = MagicMock(return_value="success")

        result = run_with_transaction_contention_retry(mock_db, mock_callback)

        assert result == "success"
        mock_db.run_in_transaction.assert_called_once()


# --- RecordingSessionsManager Tests ---

class TestRecordingSessionsManager:
    def test_create_or_get_recording_session_new(self, manager, mock_db):
        mock_db.run_in_transaction = MagicMock(
            side_effect=lambda f: f(MagicMock())
        )
        mock_doc = MagicMock()
        mock_snapshot = MagicMock(exists=False)
        mock_doc.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc

        result = manager.create_or_get_recording_session("user1", "session1", "conv1")

        assert result["uid"] == "user1"
        assert result["recording_session_id"] == "session1"
        assert result["conversation_id"] == "conv1"
        assert result["lifecycle_sequence"] == 0
        assert result["lifecycle_version"] == LIFECYCLE_ENVELOPE_VERSION

    def test_create_or_get_recording_session_existing(self, manager, mock_db):
        mock_db.run_in_transaction = MagicMock(
            side_effect=lambda f: f(MagicMock())
        )
        mock_doc = MagicMock()
        mock_snapshot = MagicMock(exists=True)
        mock_snapshot.to_dict.return_value = {"uid": "user1", "recording_session_id": "session1"}
        mock_doc.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc

        result = manager.create_or_get_recording_session("user1", "session1")
        assert result == {"uid": "user1", "recording_session_id": "session1"}

    def test_create_or_get_recording_session_invalid_id(self, manager):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            manager.create_or_get_recording_session("", "session1")

    def test_renew_recording_session_lease(self, manager, mock_db):
        mock_db.run_in_transaction = MagicMock(
            side_effect=lambda f: f(MagicMock())
        )
        mock_doc = MagicMock()
        mock_snapshot = MagicMock(exists=True)
        mock_snapshot.to_dict.return_value = {"uid": "user1"}
        mock_doc.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc

        result = manager.renew_recording_session_lease("user1", "session1", 3600)
        assert result["lease_duration_seconds"] == 3600

    def test_renew_recording_session_lease_not_found(self, manager, mock_db):
        mock_db.run_in_transaction = MagicMock(
            side_effect=lambda f: f(MagicMock())
        )
        mock_doc = MagicMock()
        mock_snapshot = MagicMock(exists=False)
        mock_doc.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc

        with pytest.raises(ValueError, match="Recording session session1 not found"):
            manager.renew_recording_session_lease("user1", "session1", 3600)

    def test_get_recording_session(self, manager, mock_db):
        mock_doc = MagicMock()
        mock_snapshot = MagicMock(exists=True)
        mock_snapshot.to_dict.return_value = {"uid": "user1"}
        mock_doc.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc

        result = manager.get_recording_session("session1")
        assert result == {"uid": "user1"}

    def test_get_recording_session_not_found(self, manager, mock_db):
        mock_doc = MagicMock()
        mock_snapshot = MagicMock(exists=False)
        mock_doc.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc

        result = manager.get_recording_session("session1")
        assert result is None

    def test_tombstone_and_delete_empty_conversation(self, manager, mock_db):
        mock_db.run_in_transaction = MagicMock(
            side_effect=lambda f: f(MagicMock())
        )
        mock_conv_doc = MagicMock()
        mock_conv_snapshot = MagicMock(exists=True)
        mock_conv_snapshot.to_dict.return_value = {
            "is_empty": True,
            "lifecycle_sequence": -1,  # Malformed
            "lifecycle_version": 0      # Malformed
        }
        mock_conv_doc.get.return_value = mock_conv_snapshot

        mock_session_doc = MagicMock()
        mock_session_snapshot = MagicMock(exists=True)
        mock_session_snapshot.to_dict.return_value = {"conversation_id": "conv1"}
        mock_session_doc.get.return_value = mock_session_snapshot

        mock_db.collection.return_value.document.side_effect = [mock_conv_doc, mock_session_doc]

        manager.tombstone_and_delete_empty_conversation("conv1", "session1")

        # Verify transaction calls
        assert mock_db.run_in_transaction.call_count == 1

    def test_record_lifecycle_event_valid(self, manager, mock_db):
        mock_db.run_in_transaction = MagicMock(
            side_effect=lambda f: f(MagicMock())
        )
        mock_doc = MagicMock()
        mock_snapshot = MagicMock(exists=True)
        mock_snapshot.to_dict.return_value = {
            "lifecycle_sequence": 5,
            "lifecycle_version": 2
        }
        mock_doc.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc

        result = manager.record_lifecycle_event(
            "session1", "conv1", "start", {"key": "value"}
        )
        assert result["status"] == "accepted"
        assert result["lifecycle_sequence"] == 6
        assert result["lifecycle_version"] == 2

    def test_record_lifecycle_event_invalid_id(self, manager):
        result = manager.record_lifecycle_event(
            "", "conv1", "start", {}
        )
        assert result["status"] == "rejected"
        assert result["discard_reason"] == "invalid_identifier"

    def test_record_lifecycle_event_session_not_found(self, manager, mock_db):
        mock_db.run_in_transaction = MagicMock(
            side_effect=lambda f: f(MagicMock())
        )
        mock_doc = MagicMock()
        mock_snapshot = MagicMock(exists=False)
        mock_doc.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc

        result = manager.record_lifecycle_event(
            "session1", "conv1", "start", {}
        )
        assert result["status"] == "rejected"
        assert result["discard_reason"] == "session_not_found"
