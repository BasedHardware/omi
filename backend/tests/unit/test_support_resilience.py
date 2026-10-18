import hashlib
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock
import pytest
from google.cloud import firestore

from database import support


class FakeSnapshot:
    def __init__(self, exists: bool, data: dict | None = None):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


def test_get_support_access_valid():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = FakeSnapshot(True, {'role': 'support:read', 'user': 'admin'})
    client.collection.return_value.document.return_value = doc_ref

    result = support.get_support_access('admin_123', firestore_client=client)
    assert result == {'role': 'support:read', 'user': 'admin'}
    client.collection.assert_called_once_with('supportData')
    client.collection.return_value.document.assert_called_once_with('admin_123')


def test_get_support_access_not_found():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = FakeSnapshot(False, None)
    client.collection.return_value.document.return_value = doc_ref

    assert support.get_support_access('missing_uid', firestore_client=client) is None


@pytest.mark.parametrize('bad_uid', ['', '   ', None, 123, 'users/traversal/attack', 'nested/id'])
def test_get_support_access_invalid_uid_fast_rejection(bad_uid):
    client = MagicMock()
    assert support.get_support_access(bad_uid, firestore_client=client) is None
    client.collection.assert_not_called()


def test_get_support_access_malformed_snapshot():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = FakeSnapshot(True, 'not-a-dict')
    client.collection.return_value.document.return_value = doc_ref

    assert support.get_support_access('uid_123', firestore_client=client) is None


def test_get_support_activity_valid():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = FakeSnapshot(
        True, {'last_active_at': '2026-10-18T10:00:00Z', 'last_active_platform': 'ios'}
    )
    client.collection.return_value.document.return_value = doc_ref

    result = support.get_support_activity('target_123', firestore_client=client)
    assert result == {'last_active_at': '2026-10-18T10:00:00Z', 'last_active_platform': 'ios'}
    client.collection.assert_called_once_with('users')
    client.collection.return_value.document.assert_called_once_with('target_123')
    doc_ref.get.assert_called_once_with(field_paths=['last_active_at', 'last_active_platform'])


def test_get_support_activity_missing():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = FakeSnapshot(False, None)
    client.collection.return_value.document.return_value = doc_ref

    assert support.get_support_activity('missing_user', firestore_client=client) == {}


@pytest.mark.parametrize('bad_uid', ['', '   ', None, 456, 'users/admin/danger', 'path/to/bad'])
def test_get_support_activity_invalid_uid_fast_rejection(bad_uid):
    client = MagicMock()
    assert support.get_support_activity(bad_uid, firestore_client=client) == {}
    client.collection.assert_not_called()


def test_get_support_activity_malformed_snapshot():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = FakeSnapshot(True, None)
    client.collection.return_value.document.return_value = doc_ref

    assert support.get_support_activity('target_user', firestore_client=client) == {}


def test_write_support_audit_lookup():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    support.write_support_audit(
        actor_uid='agent_007',
        action='lookup',
        target_uid='target_456',
        email='test@example.com',
        firestore_client=client,
    )

    client.collection.assert_called_once_with('support_audit_log')
    client.collection.return_value.document.assert_called_once_with()
    call_args = doc_ref.set.call_args[0][0]

    assert call_args['actor_uid'] == 'agent_007'
    assert call_args['action'] == 'lookup'
    assert call_args['target_uid'] == 'target_456'
    assert call_args['email_sha256'] == hashlib.sha256(b'test@example.com').hexdigest()
    assert call_args['at'] == firestore.SERVER_TIMESTAMP
    assert 'window_from' not in call_args
    assert 'window_to' not in call_args


def test_write_support_audit_trace():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    t_from = datetime(2026, 10, 1, tzinfo=timezone.utc)
    t_to = datetime(2026, 10, 5, tzinfo=timezone.utc)

    support.write_support_audit(
        actor_uid='agent_007',
        action='trace',
        target_uid='target_456',
        email='user@domain.com',
        window_from=t_from,
        window_to=t_to,
        firestore_client=client,
    )

    call_args = doc_ref.set.call_args[0][0]
    assert call_args['action'] == 'trace'
    assert call_args['window_from'] == t_from
    assert call_args['window_to'] == t_to


@pytest.mark.parametrize('bad_actor', ['', '  ', None, 99, 'foo/bar'])
def test_write_support_audit_invalid_actor(bad_actor):
    with pytest.raises(ValueError, match='Invalid actor_uid'):
        support.write_support_audit(
            actor_uid=bad_actor,
            action='lookup',
            target_uid='target_123',
            email='test@example.com',
        )


@pytest.mark.parametrize('bad_target', ['', '  ', None, 99, 'foo/bar'])
def test_write_support_audit_invalid_target(bad_target):
    with pytest.raises(ValueError, match='Invalid target_uid'):
        support.write_support_audit(
            actor_uid='actor_123',
            action='lookup',
            target_uid=bad_target,
            email='test@example.com',
        )


@pytest.mark.parametrize('bad_action', ['delete', 'update', '', 'LOOKUP', None])
def test_write_support_audit_invalid_action(bad_action):
    with pytest.raises(ValueError, match='Invalid support audit action'):
        support.write_support_audit(
            actor_uid='actor_123',
            action=bad_action,
            target_uid='target_123',
            email='test@example.com',
        )


@pytest.mark.parametrize('bad_email', ['', '  ', None, 123])
def test_write_support_audit_invalid_email(bad_email):
    with pytest.raises(ValueError, match='Invalid email'):
        support.write_support_audit(
            actor_uid='actor_123',
            action='lookup',
            target_uid='target_123',
            email=bad_email,
        )


def test_write_support_audit_storage_error_fails_closed():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.set.side_effect = RuntimeError('Firestore write failed')
    client.collection.return_value.document.return_value = doc_ref

    with pytest.raises(RuntimeError, match='Firestore write failed'):
        support.write_support_audit(
            actor_uid='actor_123',
            action='lookup',
            target_uid='target_123',
            email='test@example.com',
            firestore_client=client,
        )
