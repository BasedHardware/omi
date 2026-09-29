import re
from typing import Any, Dict, Optional, Tuple

from google.cloud import firestore
from google.api_core import retry

# Constants
LIFECYCLE_ENVELOPE_VERSION = 1
MAX_TRANSACTION_RETRIES = 3

# Regex for identifier validation (alphanumeric + underscores, no path traversal)
IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')


def _validate_id(identifier: str, field_name: str) -> None:
    """Validate that an identifier is a non-empty string and free of path traversal characters."""
    if not isinstance(identifier, str) or not identifier:
        raise ValueError(f"{field_name} must be a non-empty string")
    if not IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(f"{field_name} contains invalid characters (only alphanumeric and underscore allowed)")


def _clamp_lifecycle_sequence(sequence: Any) -> int:
    """Clamp lifecycle_sequence to >= 0, defaulting to 0 if malformed."""
    try:
        return max(0, int(sequence))
    except (ValueError, TypeError):
        return 0


def _clamp_lifecycle_version(version: Any) -> int:
    """Clamp lifecycle_version to >= 1, defaulting to LIFECYCLE_ENVELOPE_VERSION if malformed."""
    try:
        return max(1, int(version))
    except (ValueError, TypeError):
        return LIFECYCLE_ENVELOPE_VERSION


@retry.Retry(deadline=30.0, maximum=MAX_TRANSACTION_RETRIES)
def run_with_transaction_contention_retry(db: firestore.Client, callback):
    """Execute a Firestore transaction with retry on contention."""
    def _transaction_wrapper(transaction):
        return callback(transaction)
    return db.run_in_transaction(_transaction_wrapper)


class RecordingSessionsManager:
    def __init__(self, db: firestore.Client):
        self.db = db

    def create_or_get_recording_session(
        self, uid: str, recording_session_id: str, conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create or retrieve a recording session with validated identifiers and transaction retry."""
        _validate_id(uid, "uid")
        _validate_id(recording_session_id, "recording_session_id")
        if conversation_id:
            _validate_id(conversation_id, "conversation_id")

        def _txn_callback(transaction):
            sessions_ref = self.db.collection("recording_sessions")
            session_doc = sessions_ref.document(recording_session_id)
            snapshot = session_doc.get(transaction=transaction)

            if snapshot.exists:
                return snapshot.to_dict()

            session_data = {
                "uid": uid,
                "recording_session_id": recording_session_id,
                "conversation_id": conversation_id,
                "lifecycle_sequence": 0,
                "lifecycle_version": LIFECYCLE_ENVELOPE_VERSION,
                "status": "active"
            }
            transaction.set(session_doc, session_data)
            return session_data

        return run_with_transaction_contention_retry(self.db, _txn_callback)

    def renew_recording_session_lease(
        self, uid: str, recording_session_id: str, lease_duration_seconds: int
    ) -> Dict[str, Any]:
        """Renew a recording session lease with validated identifiers and transaction retry."""
        _validate_id(uid, "uid")
        _validate_id(recording_session_id, "recording_session_id")

        def _txn_callback(transaction):
            session_doc = self.db.collection("recording_sessions").document(recording_session_id)
            snapshot = session_doc.get(transaction=transaction)

            if not snapshot.exists:
                raise ValueError(f"Recording session {recording_session_id} not found")

            session_data = snapshot.to_dict()
            session_data["lease_expiry"] = firestore.SERVER_TIMESTAMP
            session_data["lease_duration_seconds"] = lease_duration_seconds
            transaction.set(session_doc, session_data)
            return session_data

        return run_with_transaction_contention_retry(self.db, _txn_callback)

    def get_recording_session(self, recording_session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a recording session with validated identifier."""
        _validate_id(recording_session_id, "recording_session_id")
        session_doc = self.db.collection("recording_sessions").document(recording_session_id)
        snapshot = session_doc.get()
        return snapshot.to_dict() if snapshot.exists else None

    def tombstone_and_delete_empty_conversation(
        self, conversation_id: str, recording_session_id: str
    ) -> None:
        """Tombstone and delete an empty conversation with validated identifiers and transaction retry."""
        _validate_id(conversation_id, "conversation_id")
        _validate_id(recording_session_id, "recording_session_id")

        def _txn_callback(transaction):
            conv_ref = self.db.collection("conversations").document(conversation_id)
            conv_snapshot = conv_ref.get(transaction=transaction)

            if not conv_snapshot.exists:
                return

            conv_data = conv_snapshot.to_dict()
            lifecycle_sequence = _clamp_lifecycle_sequence(conv_data.get("lifecycle_sequence", 0))
            lifecycle_version = _clamp_lifecycle_version(conv_data.get("lifecycle_version", LIFECYCLE_ENVELOPE_VERSION))

            if conv_data.get("is_empty", False):
                transaction.delete(conv_ref)
                # Update recording session to reflect tombstoning
                session_ref = self.db.collection("recording_sessions").document(recording_session_id)
                session_snapshot = session_ref.get(transaction=transaction)
                if session_snapshot.exists:
                    session_data = session_snapshot.to_dict()
                    session_data["conversation_id"] = None
                    session_data["lifecycle_sequence"] = lifecycle_sequence + 1
                    session_data["lifecycle_version"] = lifecycle_version
                    transaction.set(session_ref, session_data)

        run_with_transaction_contention_retry(self.db, _txn_callback)

    def record_lifecycle_event(
        self,
        recording_session_id: str,
        conversation_id: str,
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Record a lifecycle event with validated identifiers, boundary clamping, and transaction retry."""
        try:
            _validate_id(recording_session_id, "recording_session_id")
            _validate_id(conversation_id, "conversation_id")
        except ValueError as e:
            return {
                "status": "rejected",
                "discard_reason": "invalid_identifier",
                "error": str(e)
            }

        def _txn_callback(transaction):
            session_ref = self.db.collection("recording_sessions").document(recording_session_id)
            session_snapshot = session_ref.get(transaction=transaction)

            if not session_snapshot.exists:
                return {
                    "status": "rejected",
                    "discard_reason": "session_not_found"
                }

            session_data = session_snapshot.to_dict()
            lifecycle_sequence = _clamp_lifecycle_sequence(session_data.get("lifecycle_sequence", 0)) + 1
            lifecycle_version = _clamp_lifecycle_version(session_data.get("lifecycle_version", LIFECYCLE_ENVELOPE_VERSION))

            # Update session with new lifecycle event
            session_data["lifecycle_sequence"] = lifecycle_sequence
            session_data["lifecycle_version"] = lifecycle_version
            session_data["last_event"] = {
                "type": event_type,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "metadata": metadata or {}
            }
            transaction.set(session_ref, session_data)

            return {
                "status": "accepted",
                "lifecycle_sequence": lifecycle_sequence,
                "lifecycle_version": lifecycle_version
            }

        return run_with_transaction_contention_retry(self.db, _txn_callback)
