"""Hermetic tests for ``database.owner_profile_updates`` input and snapshot hardening.

The real module is exercised directly. The only seams are ``firestore.transactional``
(reduced to the identity decorator), ``run_transactional`` (runs the callable with a
recording transaction) and ``account_deletion_document`` (returns a controllable marker
reference), so no Firestore emulator or network access is involved.
"""

import math
from datetime import datetime, timezone

import pytest

from database import owner_profile_updates as owner_updates


class _Snapshot:
    def __init__(self, data, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _Transaction:
    def __init__(self):
        self.committed = []

    def update(self, ref, value):
        self.committed.append((ref, value))
        ref.writes.append(value)


class _Ref:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot if snapshot is not None else _Snapshot(None, exists=False)
        self.writes = []
        self.reads = 0

    def get(self, transaction=None):
        self.reads += 1
        return self.snapshot


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def document(self, doc_id):
        return self._docs[doc_id]


class _Client:
    def __init__(self, users=None):
        self._users = users if users is not None else {}
        self.transactions = 0

    def collection(self, name):
        assert name == 'users', name
        return _Collection(self._users)

    def transaction(self):
        self.transactions += 1
        return _Transaction()


@pytest.fixture
def users():
    return {'u1': _Ref(_Snapshot({}, exists=True))}


@pytest.fixture
def client(users):
    return _Client(users)


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    state = {'marker': _Snapshot(None, exists=False)}

    def transactional(func):
        return func

    def run_transactional(client_, callable_, *args, **kwargs):
        return callable_(client_.transaction(), *args, **kwargs)

    monkeypatch.setattr(owner_updates.firestore, 'transactional', transactional)
    monkeypatch.setattr(owner_updates, 'run_transactional', run_transactional)
    monkeypatch.setattr(
        owner_updates,
        'account_deletion_document',
        lambda uid, firestore_client=None: _Ref(state['marker']),
    )
    return state


# --------------------------------------------------------------------------- _sanitize_uid


def test_sanitize_uid_returns_stripped_value():
    assert owner_updates._sanitize_uid('  u1  ') == 'u1'


def test_sanitize_uid_rejects_non_string():
    with pytest.raises(ValueError, match='must be a string'):
        owner_updates._sanitize_uid(None)


def test_sanitize_uid_rejects_empty():
    with pytest.raises(ValueError, match='must not be empty'):
        owner_updates._sanitize_uid('')


def test_sanitize_uid_rejects_whitespace_only():
    with pytest.raises(ValueError, match='must not be empty'):
        owner_updates._sanitize_uid('   ')


def test_sanitize_uid_rejects_path_separator():
    with pytest.raises(ValueError, match='path separators'):
        owner_updates._sanitize_uid('users/u1')


def test_sanitize_uid_rejects_backslash():
    with pytest.raises(ValueError, match='path separators'):
        owner_updates._sanitize_uid('users\\u1')


def test_sanitize_uid_rejects_traversal():
    with pytest.raises(ValueError, match='path separators'):
        owner_updates._sanitize_uid('..')


def test_sanitize_uid_rejects_control_characters():
    with pytest.raises(ValueError, match='control characters'):
        owner_updates._sanitize_uid('u\x00d')


def test_sanitize_uid_rejects_overlong_id():
    with pytest.raises(ValueError, match='at most 128'):
        owner_updates._sanitize_uid('u' * 129)


def test_sanitize_uid_accepts_max_length_id():
    assert len(owner_updates._sanitize_uid('u' * 128)) == 128


# ---------------------------------------------------------------------- _validate_embedding


def test_validate_embedding_coerces_ints_to_float():
    assert owner_updates._validate_embedding([1, 2, 3]) == [1.0, 2.0, 3.0]


def test_validate_embedding_accepts_tuple():
    assert owner_updates._validate_embedding((0.5, -0.5)) == [0.5, -0.5]


def test_validate_embedding_rejects_empty_list():
    with pytest.raises(ValueError, match='must not be empty'):
        owner_updates._validate_embedding([])


def test_validate_embedding_rejects_empty_tuple():
    with pytest.raises(ValueError, match='must not be empty'):
        owner_updates._validate_embedding(())


def test_validate_embedding_rejects_non_sequence():
    with pytest.raises(ValueError, match='list or tuple'):
        owner_updates._validate_embedding('0.1,0.2')


def test_validate_embedding_rejects_bool_entry():
    with pytest.raises(ValueError, match='must be numbers'):
        owner_updates._validate_embedding([True, 0.5])


def test_validate_embedding_rejects_non_numeric_entry():
    with pytest.raises(ValueError, match='must be numbers'):
        owner_updates._validate_embedding([0.5, 'x'])


def test_validate_embedding_rejects_nan():
    with pytest.raises(ValueError, match='must be finite'):
        owner_updates._validate_embedding([math.nan])


def test_validate_embedding_rejects_inf():
    with pytest.raises(ValueError, match='must be finite'):
        owner_updates._validate_embedding([math.inf])


def test_validate_embedding_rejects_negative_inf():
    with pytest.raises(ValueError, match='must be finite'):
        owner_updates._validate_embedding([-math.inf])


# ---------------------------------------------------------------------------- _as_mapping


def test_as_mapping_passes_dict_through():
    payload = {'a': 1}
    assert owner_updates._as_mapping(payload) is payload


def test_as_mapping_replaces_none():
    assert owner_updates._as_mapping(None) == {}


def test_as_mapping_replaces_list():
    assert owner_updates._as_mapping([1, 2]) == {}


def test_as_mapping_replaces_string():
    assert owner_updates._as_mapping('corrupt') == {}


# -------------------------------------------------- get_user_speaker_embedding_recovery_state


def test_recovery_state_returns_timestamp_and_vector(client, users):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    users['u1'].snapshot = _Snapshot({'speaker_embedding_updated_at': stamp, 'speaker_embedding': [0.1]})
    assert owner_updates.get_user_speaker_embedding_recovery_state('u1', firestore_client=client) == (stamp, [0.1])


def test_recovery_state_returns_none_when_document_missing(client, users):
    users['u1'].snapshot = _Snapshot(None, exists=False)
    assert owner_updates.get_user_speaker_embedding_recovery_state('u1', firestore_client=client) is None


def test_recovery_state_survives_non_dict_snapshot(client, users):
    users['u1'].snapshot = _Snapshot(['not', 'a', 'mapping'])
    assert owner_updates.get_user_speaker_embedding_recovery_state('u1', firestore_client=client) == (None, None)


def test_recovery_state_survives_string_snapshot(client, users):
    users['u1'].snapshot = _Snapshot('corrupt')
    assert owner_updates.get_user_speaker_embedding_recovery_state('u1', firestore_client=client) == (None, None)


def test_recovery_state_swallows_read_error(client, users):
    def explode(transaction=None):
        raise RuntimeError('transient read failure')

    users['u1'].get = explode
    assert owner_updates.get_user_speaker_embedding_recovery_state('u1', firestore_client=client) is None


def test_recovery_state_rejects_invalid_uid(client):
    with pytest.raises(ValueError, match='must not be empty'):
        owner_updates.get_user_speaker_embedding_recovery_state('', firestore_client=client)


# --------------------------------------------------------------- recover_user_speaker_embedding


def test_recover_writes_vector_and_timestamp(client, users):
    users['u1'].snapshot = _Snapshot({}, exists=True)
    assert owner_updates.recover_user_speaker_embedding('u1', [0.1, 0.2], expected_updated_at=None, firestore_client=client) is True
    written = users['u1'].writes[-1]
    assert written['speaker_embedding'] == [0.1, 0.2]
    assert isinstance(written['speaker_embedding_updated_at'], datetime)


def test_recover_skips_when_embedding_already_present(client, users):
    users['u1'].snapshot = _Snapshot({'speaker_embedding': [0.9]}, exists=True)
    assert owner_updates.recover_user_speaker_embedding('u1', [0.1], expected_updated_at=None, firestore_client=client) is False
    assert users['u1'].writes == []


def test_recover_skips_when_deletion_marker_exists(client, users, _stubs):
    _stubs['marker'] = _Snapshot(None, exists=True)
    users['u1'].snapshot = _Snapshot({}, exists=True)
    assert owner_updates.recover_user_speaker_embedding('u1', [0.1], expected_updated_at=None, firestore_client=client) is False


def test_recover_skips_when_version_moved(client, users):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    users['u1'].snapshot = _Snapshot({'speaker_embedding_updated_at': stamp}, exists=True)
    assert (
        owner_updates.recover_user_speaker_embedding(
            'u1', [0.1], expected_updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc), firestore_client=client
        )
        is False
    )


def test_recover_skips_when_document_missing(client, users):
    users['u1'].snapshot = _Snapshot(None, exists=False)
    assert owner_updates.recover_user_speaker_embedding('u1', [0.1], expected_updated_at=None, firestore_client=client) is False


def test_recover_survives_non_dict_snapshot(client, users):
    users['u1'].snapshot = _Snapshot(['corrupt'], exists=True)
    assert owner_updates.recover_user_speaker_embedding('u1', [0.1], expected_updated_at=None, firestore_client=client) is True


def test_recover_rejects_invalid_uid(client):
    with pytest.raises(ValueError, match='path separators'):
        owner_updates.recover_user_speaker_embedding('a/b', [0.1], expected_updated_at=None, firestore_client=client)


def test_recover_rejects_empty_embedding(client):
    with pytest.raises(ValueError, match='must not be empty'):
        owner_updates.recover_user_speaker_embedding('u1', [], expected_updated_at=None, firestore_client=client)


def test_recover_rejects_nan_embedding(client):
    with pytest.raises(ValueError, match='must be finite'):
        owner_updates.recover_user_speaker_embedding('u1', [math.nan], expected_updated_at=None, firestore_client=client)


def test_recover_rejects_bool_embedding(client):
    with pytest.raises(ValueError, match='must be numbers'):
        owner_updates.recover_user_speaker_embedding('u1', [True], expected_updated_at=None, firestore_client=client)


def test_recover_uses_run_transactional_boundary(client, users, monkeypatch):
    calls = []
    original = owner_updates.run_transactional

    def spy(client_, callable_, *args, **kwargs):
        calls.append(callable_)
        return original(client_, callable_, *args, **kwargs)

    monkeypatch.setattr(owner_updates, 'run_transactional', spy)
    users['u1'].snapshot = _Snapshot({}, exists=True)
    assert owner_updates.recover_user_speaker_embedding('u1', [0.1], expected_updated_at=None, firestore_client=client) is True
    assert len(calls) == 1


def test_recover_reads_marker_and_person_inside_one_transaction(client, users):
    users['u1'].snapshot = _Snapshot({}, exists=True)
    owner_updates.recover_user_speaker_embedding('u1', [0.1], expected_updated_at=None, firestore_client=client)
    assert users['u1'].reads == 1
    assert client.transactions == 1
