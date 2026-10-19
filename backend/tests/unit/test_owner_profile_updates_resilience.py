"""Hermetic unit tests for backend/database/owner_profile_updates.py resilience."""

from datetime import datetime, timezone

import pytest

from database import owner_profile_updates as recovery_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

STAMP = datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc)


def test_get_recovery_state_trims_uid_and_returns_state():
    store = StrictFirestore()
    store.rows[('users', 'user_1')] = {
        'speaker_embedding_updated_at': STAMP,
        'speaker_embedding': [0.5, -0.5],
    }
    state = recovery_db.get_user_speaker_embedding_recovery_state('  user_1  ', firestore_client=store)
    assert state == (STAMP, [0.5, -0.5])


@pytest.mark.parametrize(
    'bad_uid',
    ['', '   ', 'user/sub', 'user\\sub', 'user..1', 'a' * 129, None, 123],
)
def test_get_recovery_state_returns_none_for_invalid_uid(bad_uid):
    store = StrictFirestore()
    assert recovery_db.get_user_speaker_embedding_recovery_state(bad_uid, firestore_client=store) is None


def test_get_recovery_state_returns_none_when_missing_or_read_fails():
    store = StrictFirestore()
    assert recovery_db.get_user_speaker_embedding_recovery_state('user_1', firestore_client=store) is None

    class _FailingClient:
        def collection(self, name):
            raise RuntimeError('transient firestore error')

    assert recovery_db.get_user_speaker_embedding_recovery_state('user_1', firestore_client=_FailingClient()) is None


def test_get_recovery_state_handles_non_dict_snapshot():
    class _CorruptSnap:
        exists = True

        def to_dict(self):
            return ['not', 'a', 'dict']

    class _Client:
        def collection(self, name):
            return self

        def document(self, doc_id):
            return self

        def get(self):
            return _CorruptSnap()

    assert recovery_db.get_user_speaker_embedding_recovery_state('user_1', firestore_client=_Client()) == (None, None)


@pytest.mark.parametrize(
    'bad_uid',
    ['', '   ', 'user/sub', 'user\\sub', 'user..1', 'a' * 129, None, 123],
)
def test_recover_user_speaker_embedding_rejects_invalid_uid(bad_uid):
    store = StrictFirestore()
    with pytest.raises(ValueError, match='uid'):
        recovery_db.recover_user_speaker_embedding(
            bad_uid,
            [1.0, 0.0],
            expected_updated_at=STAMP,
            firestore_client=store,
        )


@pytest.mark.parametrize(
    'bad_embedding',
    [
        [],
        None,
        'not-a-list',
        [True, 0.5],
        [float('nan'), 1.0],
        [float('inf'), 1.0],
        [float('-inf'), 1.0],
        ['1.0', 0.0],
    ],
)
def test_recover_user_speaker_embedding_rejects_invalid_embedding(bad_embedding):
    store = StrictFirestore()
    with pytest.raises(ValueError, match='embedding'):
        recovery_db.recover_user_speaker_embedding(
            'user_1',
            bad_embedding,
            expected_updated_at=STAMP,
            firestore_client=store,
        )


def test_recover_user_speaker_embedding_trims_uid_coerces_floats_and_respects_cas_and_deletion():
    store = StrictFirestore()
    path = ('users', 'user_1')
    store.rows[path] = {'speaker_embedding_updated_at': STAMP}

    assert recovery_db.recover_user_speaker_embedding(
        '  user_1  ',
        [1, -2.5],
        expected_updated_at=STAMP,
        firestore_client=store,
    )
    assert store.rows[path]['speaker_embedding'] == [1.0, -2.5]
    assert isinstance(store.rows[path]['speaker_embedding'][0], float)

    # Second attempt fails because speaker_embedding is now populated
    assert not recovery_db.recover_user_speaker_embedding(
        'user_1',
        [0.0, 1.0],
        expected_updated_at=STAMP,
        firestore_client=store,
    )

    # Account deletion marker blocks recovery
    store.rows[path] = {'speaker_embedding_updated_at': STAMP}
    store.rows[('account_deletions', 'user_1')] = {'wipe_status': 'pending'}
    assert not recovery_db.recover_user_speaker_embedding(
        'user_1',
        [0.0, 1.0],
        expected_updated_at=STAMP,
        firestore_client=store,
    )
    assert 'speaker_embedding' not in store.rows[path]


def test_recover_user_speaker_embedding_handles_non_dict_snapshot():
    class _CorruptSnap:
        def __init__(self, exists, payload):
            self.exists = exists
            self._payload = payload

        def to_dict(self):
            return self._payload

    class _Ref:
        def __init__(self, snap):
            self._snap = snap
            self.updated = None

        def get(self, transaction=None):
            return self._snap

        def update(self, data):
            self.updated = data

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

        def update(self, ref, data):
            ref.update(data)

    user_ref = _Ref(_CorruptSnap(True, 'corrupt-string-payload'))
    del_ref = _Ref(_CorruptSnap(False, None))

    class _Client:
        def __init__(self):
            self._col = None

        def collection(self, name):
            self._col = name
            return self

        def document(self, doc_id):
            return del_ref if self._col == 'account_deletions' else user_ref

        def transaction(self):
            return _Tx()

    # Does not raise AttributeError when to_dict() returns a non-dict string
    res = recovery_db.recover_user_speaker_embedding(
        'user_1',
        [1.0, 0.0],
        expected_updated_at=None,
        firestore_client=_Client(),
    )
    assert res is True
    assert user_ref.updated['speaker_embedding'] == [1.0, 0.0]
