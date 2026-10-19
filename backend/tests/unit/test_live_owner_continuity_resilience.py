"""Hermetic unit tests for backend/database/live_owner_continuity.py resilience."""

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import live_owner_continuity as continuity
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.mark.parametrize(
    ('bad_uid', 'bad_device', 'bad_token'),
    [
        ('', 'dev1', 'tok1'),
        ('   ', 'dev1', 'tok1'),
        ('user/1', 'dev1', 'tok1'),
        ('user..1', 'dev1', 'tok1'),
        (None, 'dev1', 'tok1'),
        ('user_1', '', 'tok1'),
        ('user_1', '   ', 'tok1'),
        ('user_1', 'dev\n1', 'tok1'),
        ('user_1', 'dev1', ''),
        ('user_1', 'dev1', '   '),
        ('user_1', 'dev1', None),
    ],
)
def test_begin_returns_absent_without_redis_call_on_invalid_inputs(monkeypatch, bad_uid, bad_device, bad_token):
    monkeypatch.setattr(
        continuity,
        '_client',
        lambda: (_ for _ in ()).throw(AssertionError('Redis should not be called on invalid input')),
    )
    assert continuity.begin(bad_uid, bad_device, bad_token) == (None, 'absent')


@pytest.mark.parametrize(
    ('bad_uid', 'bad_conv'),
    [
        ('', 'conv_1'),
        ('   ', 'conv_1'),
        ('user/1', 'conv_1'),
        ('user\\1', 'conv_1'),
        ('user..1', 'conv_1'),
        ('a' * 129, 'conv_1'),
        (None, 'conv_1'),
        ('user_1', ''),
        ('user_1', '   '),
        ('user_1', 'conv/1'),
        ('user_1', 'conv..1'),
        ('user_1', None),
    ],
)
def test_donor_authority_returns_none_for_invalid_uid_or_conversation(bad_uid, bad_conv):
    store = StrictFirestore()
    assert continuity.donor_authority(bad_uid, bad_conv, firestore_client=store) is None


def test_donor_authority_handles_non_dict_snapshot_and_privacy_flags():
    class _CorruptClient:
        def collection(self, name):
            return self

        def document(self, doc_id):
            return self

        def get(self, field_paths=None):
            return SimpleNamespace(exists=True, to_dict=lambda: ['corrupt-non-dict'])

    assert continuity.donor_authority('user_1', 'conv_1', firestore_client=_CorruptClient()) is None

    store = StrictFirestore()
    store.rows[('users', 'user_1', 'conversations', 'conv_1')] = {'is_locked': True}
    assert continuity.donor_authority('  user_1  ', '  conv_1  ', firestore_client=store) is None

    store.rows[('users', 'user_1', 'conversations', 'conv_1')] = {'deleted': False, 'is_locked': False}
    assert continuity.donor_authority('  user_1  ', '  conv_1  ', firestore_client=store) == {}


@pytest.mark.parametrize(
    'bad_conversations',
    [
        (),
        [],
        ('c1', 'c2', 'c3', 'c4'),
        'abc',
        'c1',
        None,
        123,
    ],
)
def test_authority_snapshot_rejects_invalid_conversations_container(bad_conversations):
    store = StrictFirestore()
    with pytest.raises(ValueError, match='owner authority requires one to three conversations'):
        continuity.authority_snapshot('user_1', bad_conversations, firestore_client=store)


@pytest.mark.parametrize(
    ('bad_uid', 'convs'),
    [
        ('', ('c1',)),
        ('   ', ('c1',)),
        ('user/1', ('c1',)),
        ('user..1', ('c1',)),
        ('user_1', ('',)),
        ('user_1', ('   ',)),
        ('user_1', ('conv/1',)),
        ('user_1', ('conv..1',)),
        ('user_1', (None,)),
    ],
)
def test_authority_snapshot_rejects_unsafe_uid_or_conversation_ids(bad_uid, convs):
    store = StrictFirestore()
    with pytest.raises(ValueError):
        continuity.authority_snapshot(bad_uid, convs, firestore_client=store)


def test_authority_snapshot_trims_ids_and_handles_non_dict_snapshot():
    store = StrictFirestore()
    store.rows[('users', 'user_1', 'conversations', 'c1')] = {'deleted': False}
    store.rows[('users', 'user_1', 'conversations', 'c2')] = {'discarded': True}
    res = continuity.authority_snapshot('  user_1  ', ('  c1  ', '  c2  '), firestore_client=store)
    assert res == {'c1': {}, 'c2': None}

    class _Tx:
        _read_only = False
        _max_attempts = 1
        _id = b'tx1'

        def _begin(self, *args, **kwargs):
            pass

        def _commit(self):
            return []

        def _rollback(self):
            pass

        def _clean_up(self):
            pass

    class _CorruptClient:
        def collection(self, name):
            return self

        def document(self, doc_id):
            return self

        def get(self, transaction=None, field_paths=None):
            return SimpleNamespace(exists=True, to_dict=lambda: 'corrupt-string')

        def transaction(self):
            return _Tx()

    assert continuity.authority_snapshot('user_1', ('c1',), firestore_client=_CorruptClient()) == {'c1': None}


@pytest.mark.parametrize(
    ('uid', 'device', 'token', 'payload', 'revision'),
    [
        ('', 'dev1', 'tok1', None, 1),
        ('user/1', 'dev1', 'tok1', None, 1),
        ('user_1', '', 'tok1', None, 1),
        ('user_1', 'dev1', '', None, 1),
        ('user_1', 'dev1', 'tok1', None, True),
        ('user_1', 'dev1', 'tok1', None, False),
        ('user_1', 'dev1', 'tok1', None, 0),
        ('user_1', 'dev1', 'tok1', None, -1),
        ('user_1', 'dev1', 'tok1', None, '1'),
        ('user_1', 'dev1', 'tok1', 'not-a-dict', 1),
    ],
)
def test_publish_skips_redis_call_on_invalid_arguments(monkeypatch, uid, device, token, payload, revision):
    monkeypatch.setattr(
        continuity,
        '_client',
        lambda: (_ for _ in ()).throw(AssertionError('Redis should not be called on invalid input')),
    )
    continuity.publish(uid, device, token, payload, revision)
