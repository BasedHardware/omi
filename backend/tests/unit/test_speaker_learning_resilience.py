"""Unit tests for the speaker-learning input and snapshot hardening.

Verifies:
- ``update_person_voice_learning`` rejects unusable document ids and labels
  before touching Firestore.
- Snapshot payloads that are missing, ``None`` or not mappings can no longer
  raise ``AttributeError`` inside the transaction.
- Non-finite, boolean and negative durations are dropped instead of being
  written into the person document.
- A failing client lookup degrades to ``None`` and an injected client is used.
"""

from unittest.mock import MagicMock

import pytest

import database.speaker_learning as speaker_learning


class _FakeSnapshot:
    def __init__(self, payload, exists=True):
        self._payload = payload
        self.exists = exists

    def to_dict(self):
        return self._payload


class _FakeDocRef:
    def __init__(self, path, snapshot=None, children=None):
        self.path = path
        self._snapshot = snapshot
        self._children = children or {}

    def collection(self, name):
        return _FakeCollection(f'{self.path}/{name}', self._children.get(name, {}))

    def get(self, transaction=None):
        if callable(self._snapshot):
            return self._snapshot()
        return self._snapshot


class _FakeCollection:
    def __init__(self, path, documents):
        self.path = path
        self._documents = documents

    def document(self, doc_id):
        if doc_id not in self._documents:
            raise AssertionError(f'unexpected document {self.path}/{doc_id}')
        return self._documents[doc_id]


class _FakeTransaction:
    def __init__(self):
        self.updates = []

    def update(self, ref, data):
        self.updates.append((ref.path, data))


def _client(person_payload, user_payload=None, *, person_exists=True, user_exists=True):
    person_ref = _FakeDocRef('users/u1/people/p1', _FakeSnapshot(person_payload, person_exists))
    user_ref = _FakeDocRef('users/u1', _FakeSnapshot(user_payload, user_exists), {'people': {'p1': person_ref}})
    client = MagicMock()
    client.collection.return_value.document.return_value = user_ref
    return client, person_ref, user_ref


@pytest.fixture(autouse=True)
def _passthrough(monkeypatch):
    def run_transactional(client, fn, *args):
        return fn(_FakeTransaction(), *args)

    monkeypatch.setattr(speaker_learning, 'run_transactional', run_transactional)


def _call(client, **overrides):
    kwargs = dict(
        uid='u1',
        person_id='p1',
        expected_updated_at='ts-1',
        outcome='card_confirms',
        state='learning',
        speech_seconds=12.5,
        needed_seconds=40.0,
        firestore_client=client,
    )
    kwargs.update(overrides)
    return speaker_learning.update_person_voice_learning(**kwargs)



def test_update_payload_carries_the_cleaned_values():
    client, person_ref, _ = _client({'updated_at': 'ts-1', 'voice_readiness': 'cold'})
    transaction = _FakeTransaction()
    result = speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, _user_ref(client), 'ts-1', 'card_confirms', 'learning', 12.5, 40.0
    )
    assert result is True
    assert transaction.updates[0][1] == {
        'voice_learning_state': 'learning',
        'voice_learning_outcome': 'card_confirms',
        'voice_speech_seconds': 12.5,
        'voice_needed_seconds': 40.0,
    }


def _user_ref(client):
    return client.collection.return_value.document.return_value


def test_stale_snapshot_returns_false():
    client, person_ref, user_ref = _client({'updated_at': 'ts-2'})
    transaction = _FakeTransaction()
    assert speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, user_ref, 'ts-1', 'o', 'learning', 1.0, 2.0
    ) is False
    assert transaction.updates == []


def test_missing_person_returns_none():
    client, person_ref, user_ref = _client(None, person_exists=False)
    transaction = _FakeTransaction()
    assert speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, user_ref, 'ts-1', 'o', 'learning', 1.0, 2.0
    ) is None


def test_none_payload_does_not_raise():
    client, person_ref, user_ref = _client(None)
    transaction = _FakeTransaction()
    assert speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, user_ref, 'ts-1', 'o', 'learning', 1.0, 2.0
    ) is None
    assert transaction.updates == []


def test_non_mapping_payload_does_not_raise():
    client, person_ref, user_ref = _client(['not', 'a', 'dict'])
    transaction = _FakeTransaction()
    assert speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, user_ref, 'ts-1', 'o', 'learning', 1.0, 2.0
    ) is None


def test_non_mapping_user_settings_fall_back_to_defaults():
    client, person_ref, user_ref = _client({'updated_at': 'ts-1'}, ['bad'])
    transaction = _FakeTransaction()
    assert speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, user_ref, 'ts-1', 'o', 'learning', 1.0, 2.0
    ) is True


def test_disabled_profiles_force_the_disabled_state():
    client, person_ref, user_ref = _client({'updated_at': 'ts-1'}, {'save_other_voice_profiles': False})
    transaction = _FakeTransaction()
    speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, user_ref, 'ts-1', 'o', 'learning', 1.0, 2.0
    )
    assert transaction.updates[0][1]['voice_learning_state'] == 'disabled'
    assert transaction.updates[0][1]['voice_needed_seconds'] is None


def test_learned_state_keeps_the_stored_speech_seconds():
    client, person_ref, user_ref = _client(
        {'updated_at': 'ts-1', 'voice_speech_seconds': 99.0, 'voice_readiness': 'ready'}
    )
    transaction = _FakeTransaction()
    speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, user_ref, 'ts-1', 'o', 'learning', 1.0, 2.0
    )
    payload = transaction.updates[0][1]
    assert payload['voice_learning_state'] == 'learned'
    assert payload['voice_speech_seconds'] == 99.0
    assert payload['voice_needed_seconds'] is None


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), True, False, -1.0, '12', None, [1]])
def test_non_finite_and_non_numeric_durations_are_dropped(value):
    client, person_ref, user_ref = _client({'updated_at': 'ts-1'})
    transaction = _FakeTransaction()
    speaker_learning._update_voice_learning_transaction(
        transaction, person_ref, user_ref, 'ts-1', 'o', 'learning', value, value
    )
    payload = transaction.updates[0][1]
    assert payload['voice_speech_seconds'] is None
    assert payload['voice_needed_seconds'] is None


def test_public_entry_point_writes_through_an_injected_client():
    client, _, _ = _client({'updated_at': 'ts-1'})
    assert _call(client) is True


@pytest.mark.parametrize('uid', ['', '   ', None, True, 'a/b', 'a\\b', '..', 'a..b', 'u' * 129, 'x\x00y', 'x\x7fy'])
def test_unusable_uids_are_rejected_before_firestore(uid):
    client, _, _ = _client({'updated_at': 'ts-1'})
    assert _call(client, uid=uid) is None
    assert client.collection.call_args_list == []


@pytest.mark.parametrize('person_id', ['', '  ', None, True, 'p/1', 'p\\1', '..', 'p' * 129, 'p\x1f1'])
def test_unusable_person_ids_are_rejected(person_id):
    client, _, _ = _client({'updated_at': 'ts-1'})
    assert _call(client, person_id=person_id) is None
    assert client.collection.call_args_list == []


@pytest.mark.parametrize('field', ['outcome', 'state'])
@pytest.mark.parametrize('value', ['', '   ', None, True, 7, 'l' * 65, 'a\x00b'])
def test_unusable_labels_are_rejected(field, value):
    client, _, _ = _client({'updated_at': 'ts-1'})
    assert _call(client, **{field: value}) is None
    assert client.collection.call_args_list == []


def test_whitespace_is_trimmed_from_ids_and_labels():
    client, _, _ = _client({'updated_at': 'ts-1'})
    assert _call(client, uid=' u1 ', person_id=' p1 ', outcome=' card_confirms ', state=' learning ') is True
    assert client.collection.call_args.args == ('users',)
    assert client.collection.return_value.document.call_args.args == ('u1',)


def test_a_failing_client_lookup_degrades_to_none(monkeypatch):
    def boom():
        raise RuntimeError('no credentials')

    monkeypatch.setattr(speaker_learning, 'get_firestore_client', boom)
    assert speaker_learning.update_person_voice_learning(
        'u1', 'p1', 'ts-1', outcome='o', state='learning', speech_seconds=1.0, needed_seconds=2.0
    ) is None
