"""Unit tests for speaker_learning database resilience, input sanitization, and snapshot guards."""

from datetime import datetime, timezone
import pytest

import database.speaker_learning as speaker_learning_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

STAMP = datetime(2026, 2, 1, tzinfo=timezone.utc)


@pytest.fixture
def store():
    return StrictFirestore()


def test_update_person_voice_learning_trims_identifiers_and_writes(store):
    store.rows[('users', 'user_1')] = {'save_other_voice_profiles': True}
    store.rows[('users', 'user_1', 'people', 'person_1')] = {'id': 'person_1', 'updated_at': STAMP}

    result = speaker_learning_db.update_person_voice_learning(
        '  user_1  ',
        '  person_1  ',
        STAMP,
        outcome='  insufficient_speech  ',
        state='  pending  ',
        speech_seconds=4.5,
        needed_seconds=10.5,
        firestore_client=store,
    )
    assert result is True
    saved = store.rows[('users', 'user_1', 'people', 'person_1')]
    assert saved['voice_learning_state'] == 'pending'
    assert saved['voice_learning_outcome'] == 'insufficient_speech'
    assert saved['voice_speech_seconds'] == 4.5
    assert saved['voice_needed_seconds'] == 10.5


@pytest.mark.parametrize('bad_uid', ['', '   ', 'user/sub', 'user\\sub', 'user..1', 'a' * 129, None, 123])
def test_update_person_voice_learning_rejects_invalid_uid(store, bad_uid):
    with pytest.raises(ValueError, match='uid'):
        speaker_learning_db.update_person_voice_learning(
            bad_uid,  # type: ignore[arg-type]
            'person_1',
            STAMP,
            outcome='ok',
            state='pending',
            speech_seconds=1.0,
            needed_seconds=2.0,
            firestore_client=store,
        )


@pytest.mark.parametrize('bad_person_id', ['', '   ', 'p/sub', 'p\\sub', 'p..1', 'a' * 129, None, 123])
def test_update_person_voice_learning_rejects_invalid_person_id(store, bad_person_id):
    with pytest.raises(ValueError, match='person_id'):
        speaker_learning_db.update_person_voice_learning(
            'user_1',
            bad_person_id,  # type: ignore[arg-type]
            STAMP,
            outcome='ok',
            state='pending',
            speech_seconds=1.0,
            needed_seconds=2.0,
            firestore_client=store,
        )


@pytest.mark.parametrize('bad_label', ['', '   ', None, 123])
def test_update_person_voice_learning_rejects_blank_outcome_or_state(store, bad_label):
    with pytest.raises(ValueError, match='outcome'):
        speaker_learning_db.update_person_voice_learning(
            'user_1',
            'person_1',
            STAMP,
            outcome=bad_label,  # type: ignore[arg-type]
            state='pending',
            speech_seconds=1.0,
            needed_seconds=2.0,
            firestore_client=store,
        )
    with pytest.raises(ValueError, match='state'):
        speaker_learning_db.update_person_voice_learning(
            'user_1',
            'person_1',
            STAMP,
            outcome='ok',
            state=bad_label,  # type: ignore[arg-type]
            speech_seconds=1.0,
            needed_seconds=2.0,
            firestore_client=store,
        )


def test_update_person_voice_learning_returns_none_when_person_missing(store):
    res = speaker_learning_db.update_person_voice_learning(
        'user_1',
        'missing_person',
        STAMP,
        outcome='ok',
        state='pending',
        speech_seconds=2.0,
        needed_seconds=5.0,
        firestore_client=store,
    )
    assert res is None


def test_update_person_voice_learning_returns_false_on_stale_updated_at(store):
    store.rows[('users', 'user_1', 'people', 'person_1')] = {
        'id': 'person_1',
        'updated_at': datetime(2026, 3, 1, tzinfo=timezone.utc),
    }
    res = speaker_learning_db.update_person_voice_learning(
        'user_1',
        'person_1',
        STAMP,
        outcome='ok',
        state='pending',
        speech_seconds=2.0,
        needed_seconds=5.0,
        firestore_client=store,
    )
    assert res is False


def test_update_person_voice_learning_handles_none_or_non_dict_person_and_user_snapshots():
    class _CorruptSnap:
        exists = True

        def __init__(self, payload):
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

        def collection(self, name):
            return self

        def document(self, doc_id):
            return person_ref

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

    person_ref = _Ref(_CorruptSnap(None))
    user_ref = _Ref(_CorruptSnap('corrupt-user-settings'))

    class _Client:
        def collection(self, name):
            return self

        def document(self, doc_id):
            return user_ref if doc_id == 'user_1' else person_ref

        def transaction(self):
            return _Tx()

    # When expected_updated_at is None and person snapshot is empty (None dict), it does not raise AttributeError
    res = speaker_learning_db.update_person_voice_learning(
        'user_1',
        'person_1',
        None,
        outcome='ok',
        state='pending',
        speech_seconds=3.0,
        needed_seconds=7.0,
        firestore_client=_Client(),
    )
    assert res is True
    assert person_ref.updated['voice_learning_state'] == 'pending'


def test_update_person_voice_learning_normalizes_invalid_float_bounds(store):
    store.rows[('users', 'user_1')] = {'save_other_voice_profiles': True}
    store.rows[('users', 'user_1', 'people', 'person_1')] = {'id': 'person_1', 'updated_at': STAMP}

    res = speaker_learning_db.update_person_voice_learning(
        'user_1',
        'person_1',
        STAMP,
        outcome='ok',
        state='pending',
        speech_seconds=-5.0,
        needed_seconds=float('nan'),
        firestore_client=store,
    )
    assert res is True
    saved = store.rows[('users', 'user_1', 'people', 'person_1')]
    assert saved['voice_speech_seconds'] == 0.0
    assert saved['voice_needed_seconds'] is None


def test_update_person_voice_learning_respects_disabled_consent_and_ready_profile(store):
    store.rows[('users', 'user_1')] = {'save_other_voice_profiles': False}
    store.rows[('users', 'user_1', 'people', 'person_1')] = {
        'id': 'person_1',
        'updated_at': STAMP,
        'voice_speech_seconds': 14.0,
    }
    res = speaker_learning_db.update_person_voice_learning(
        'user_1',
        'person_1',
        STAMP,
        outcome='queued',
        state='pending',
        speech_seconds=2.0,
        needed_seconds=8.0,
        firestore_client=store,
    )
    assert res is True
    saved = store.rows[('users', 'user_1', 'people', 'person_1')]
    assert saved['voice_learning_state'] == 'disabled'
    assert saved['voice_needed_seconds'] is None
    assert saved['voice_speech_seconds'] == 14.0
