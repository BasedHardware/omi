"""Tests for tombstone safety in get_conversation_for_capture_check."""

import pytest
from database import conversations as conversations_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = "test-tombstone-user"
CONV_ID = "c-100"
PATH = ("users", UID, "conversations", CONV_ID)


def sample_conversation(deleted: bool = False, **extra):
    return {
        "id": CONV_ID,
        "deleted": deleted,
        "status": "completed",
        "transcript_segments": [
            {
                "text": "we should ship the pendant firmware before the trade show",
                "speaker": "SPEAKER_00",
                "is_user": False,
                "start": 0.0,
                "end": 10.0,
            }
        ],
        **extra,
    }


def test_get_conversation_for_capture_check_active_conversation():
    store = StrictFirestore()
    store.rows[PATH] = sample_conversation(deleted=False)

    conv, fingerprint = conversations_db.get_conversation_for_capture_check(UID, CONV_ID, firestore_client=store)
    assert conv is not None
    assert fingerprint is not None
    assert conv["id"] == CONV_ID
    assert conv["transcript_segments"][0]["text"] == "we should ship the pendant firmware before the trade show"


def test_get_conversation_for_capture_check_missing_conversation():
    store = StrictFirestore()
    conv, fingerprint = conversations_db.get_conversation_for_capture_check(UID, "nonexistent", firestore_client=store)
    assert conv is None
    assert fingerprint is None


@pytest.mark.parametrize("deleted_val", [True, 1, "true", "yes"])
def test_get_conversation_for_capture_check_rejects_soft_deleted_tombstone(deleted_val):
    store = StrictFirestore()
    store.rows[PATH] = sample_conversation(deleted=deleted_val)

    conv, fingerprint = conversations_db.get_conversation_for_capture_check(UID, CONV_ID, firestore_client=store)
    # Tombstone must be rejected and return (None, None)
    assert conv is None
    assert fingerprint is None


def test_get_conversation_for_capture_check_empty_doc():
    store = StrictFirestore()
    store.rows[PATH] = {}

    conv, fingerprint = conversations_db.get_conversation_for_capture_check(UID, CONV_ID, firestore_client=store)
    assert conv is None
    assert fingerprint is None
