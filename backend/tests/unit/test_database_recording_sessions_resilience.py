"""Contract and resilience tests for database.recording_sessions input guards and exceptions."""

from unittest.mock import MagicMock
import pytest
from google.api_core.exceptions import NotFound

import database.recording_sessions as rs


# ============================================================================
# Input Validation & Sanitization Tests
# ============================================================================

@pytest.mark.parametrize(
    'uid,session_id,conv_id',
    [
        ('', 'session-1', 'conv-1'),
        ('   ', 'session-1', 'conv-1'),
        (None, 'session-1', 'conv-1'),
        ('user-1', '', 'conv-1'),
        ('user-1', '   ', 'conv-1'),
        ('user-1', None, 'conv-1'),
        ('user-1', 'session-1', ''),
        ('user-1', 'session-1', '   '),
        ('user-1', 'session-1', None),
    ],
)
def test_create_or_get_recording_session_input_guards(uid, session_id, conv_id):
    with pytest.raises(ValueError, match='uid, recording_session_id, and proposed_conversation_id are required'):
        rs.create_or_get_recording_session(uid, session_id, conv_id)


@pytest.mark.parametrize(
    'uid,session_id',
    [
        ('', 'session-1'),
        ('   ', 'session-1'),
        (None, 'session-1'),
        ('user-1', ''),
        ('user-1', '   '),
        ('user-1', None),
    ],
)
def test_get_recording_session_input_guards(uid, session_id):
    with pytest.raises(ValueError, match='uid and recording_session_id are required'):
        rs.get_recording_session(uid, session_id)


@pytest.mark.parametrize(
    'uid,conv_id',
    [
        ('', 'conv-1'),
        ('   ', 'conv-1'),
        (None, 'conv-1'),
        ('user-1', ''),
        ('user-1', '   '),
        ('user-1', None),
    ],
)
def test_tombstone_and_delete_empty_conversation_input_guards(uid, conv_id):
    with pytest.raises(ValueError, match='uid and conversation_id are required'):
        rs.tombstone_and_delete_empty_conversation(uid, conv_id, 'session-1')


@pytest.mark.parametrize(
    'uid,session_id,conv_id',
    [
        ('', 'session-1', 'conv-1'),
        ('   ', 'session-1', 'conv-1'),
        (None, 'session-1', 'conv-1'),
        ('user-1', '', 'conv-1'),
        ('user-1', '   ', 'conv-1'),
        ('user-1', None, 'conv-1'),
        ('user-1', 'session-1', ''),
        ('user-1', 'session-1', '   '),
        ('user-1', 'session-1', None),
    ],
)
def test_record_lifecycle_event_input_guards(uid, session_id, conv_id):
    with pytest.raises(ValueError, match='uid, recording_session_id, and conversation_id are required'):
        rs.record_lifecycle_event(uid, session_id, conv_id, 'in_progress')


def test_record_lifecycle_event_invalid_phase():
    with pytest.raises(ValueError, match='unsupported recording lifecycle phase'):
        rs.record_lifecycle_event('user-1', 'session-1', 'conv-1', 'invalid_phase')


# ============================================================================
# Resilience & Edge Case Tests
# ============================================================================

def test_binding_missing_conversation_id_safe():
    # Documents missing 'conversation_id' should not trigger KeyError
    data = {
        'lifecycle_version': 1,
        'lifecycle_phase': 'in_progress',
        'lifecycle_sequence': 2,
    }
    binding = rs._binding(data, 'session-1', mapping_conflict=False)
    assert binding['recording_session_id'] == 'session-1'
    assert binding['conversation_id'] == ''
    assert binding['lifecycle_phase'] == 'in_progress'
    assert binding['lifecycle_sequence'] == 2
    assert binding['mapping_conflict'] is False


def test_tombstone_and_delete_whitespace_session_id_coerces_to_none():
    fake_client = MagicMock()
    fake_user_doc = MagicMock()
    fake_conv_coll = MagicMock()
    fake_conv_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_client.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_conv_coll
    fake_conv_coll.document.return_value = fake_conv_doc
    fake_conv_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = False

    # Calling with whitespace session_id '   ' should not attempt to access users/uid/recording_sessions/'   '
    result = rs.tombstone_and_delete_empty_conversation(
        'user-1', 'conv-1', '   ', firestore_client=fake_client
    )
    assert result is False
    # Ensure collection('users').document('user-1').collection('conversations').document('conv-1') was called
    fake_client.collection.assert_called_with('users')
    fake_user_doc.collection.assert_called_with('conversations')
    fake_conv_coll.document.assert_called_with('conv-1')


def test_tombstone_and_delete_not_found_exception_returns_false():
    fake_client = MagicMock()
    # Mock transaction to raise NotFound during execution
    fake_client.transaction.side_effect = NotFound('Document not found concurrently')

    result = rs.tombstone_and_delete_empty_conversation(
        'user-1', 'conv-1', 'session-1', firestore_client=fake_client
    )
    assert result is False


def test_get_recording_session_strips_whitespace():
    fake_client = MagicMock()
    fake_user_doc = MagicMock()
    fake_sess_coll = MagicMock()
    fake_sess_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_client.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_sess_coll
    fake_sess_coll.document.return_value = fake_sess_doc
    fake_sess_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    fake_snapshot.to_dict.return_value = {
        'uid': 'user-1',
        'recording_session_id': 'session-1',
        'conversation_id': 'conv-1',
        'lifecycle_version': 1,
        'lifecycle_phase': 'in_progress',
        'lifecycle_sequence': 0,
    }

    binding = rs.get_recording_session('  user-1  ', '  session-1  ', firestore_client=fake_client)
    assert binding is not None
    assert binding['recording_session_id'] == 'session-1'
    assert binding['conversation_id'] == 'conv-1'
    fake_client.collection.assert_called_with('users')
    fake_user_doc.collection.assert_called_with(rs.RECORDING_SESSIONS_COLLECTION)
    fake_sess_coll.document.assert_called_with('session-1')
