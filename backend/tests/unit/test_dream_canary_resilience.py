"""Hermetic unit tests for backend/database/dream_canary.py resilience."""

import pytest

from database import dream_canary
from tests.support.dream_firestore import DreamFirestore

CANARY_UID = 'dream-canary-synthetic'


@pytest.mark.parametrize(
    'bad_uid',
    ['', '   ', 'wrong-uid', 'dream/canary', 'dream\\canary', 'dream..canary', 'a' * 129, None, 123],
)
def test_ensure_synthetic_owner_rejects_invalid_or_mismatched_uid(monkeypatch, bad_uid):
    monkeypatch.setenv('DREAM_AGENT_CANARY_UID', CANARY_UID)
    store = DreamFirestore()
    with pytest.raises(ValueError, match='dream_canary_configuration'):
        dream_canary.ensure_synthetic_owner(bad_uid, firestore_client=store)


@pytest.mark.parametrize('bad_env_uid', ['', '  padded  ', 'bad/uid', 'bad..uid'])
def test_ensure_synthetic_owner_rejects_unsafe_configured_canary_uid(monkeypatch, bad_env_uid):
    monkeypatch.setenv('DREAM_AGENT_CANARY_UID', bad_env_uid)
    store = DreamFirestore()
    with pytest.raises(ValueError, match='dream_canary_configuration'):
        dream_canary.ensure_synthetic_owner(bad_env_uid, firestore_client=store)


def test_ensure_synthetic_owner_creates_synthetic_user_and_rejects_non_canary_owner(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_CANARY_UID', CANARY_UID)
    store = DreamFirestore()
    dream_canary.ensure_synthetic_owner(CANARY_UID, firestore_client=store)
    assert store.rows[('users', CANARY_UID)] == {'dream_canary': True}

    # Re-running against an already-marked synthetic user is a no-op
    dream_canary.ensure_synthetic_owner(CANARY_UID, firestore_client=store)

    # A real user document without dream_canary=True is rejected
    store.rows[('users', CANARY_UID)] = {'dream_canary': False, 'email': 'real@example.com'}
    with pytest.raises(ValueError, match='dream_canary_existing_owner'):
        dream_canary.ensure_synthetic_owner(CANARY_UID, firestore_client=store)


def test_ensure_synthetic_owner_handles_non_dict_snapshot(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_CANARY_UID', CANARY_UID)

    class _CorruptSnap:
        exists = True

        def to_dict(self):
            return 'corrupt-string-payload'

    class _Ref:
        def get(self, transaction=None):
            return _CorruptSnap()

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

    class _Client:
        def collection(self, name):
            return self

        def document(self, doc_id):
            return _Ref()

        def transaction(self):
            return _Tx()

    with pytest.raises(ValueError, match='dream_canary_existing_owner'):
        dream_canary.ensure_synthetic_owner(CANARY_UID, firestore_client=_Client())


@pytest.mark.parametrize(
    ('raw_value', 'expected'),
    [
        (None, 0),
        (True, 0),
        (False, 0),
        (-10, 0),
        (0, 0),
        (7, 7),
        (250, 100),
        (12.9, 12),
        (float('nan'), 0),
        (float('inf'), 0),
        (' 15 ', 15),
        ('not-an-int', 0),
        (['bad'], 0),
    ],
)
def test_failure_count_coerces_malformed_values_safely(raw_value, expected):
    store = DreamFirestore()
    store.rows[('dream_canary_health', 'current')] = {'canary_failures': raw_value}
    assert dream_canary.failure_count(firestore_client=store) == expected


def test_failure_count_returns_zero_on_read_error_or_non_dict_snapshot():
    class _FailingClient:
        def collection(self, name):
            raise RuntimeError('transient firestore error')

    assert dream_canary.failure_count(firestore_client=_FailingClient()) == 0

    class _CorruptClient:
        def collection(self, name):
            return self

        def document(self, doc_id):
            return self

        def get(self):
            class _Snap:
                exists = True

                def to_dict(self):
                    return ['corrupt']

            return _Snap()

    assert dream_canary.failure_count(firestore_client=_CorruptClient()) == 0


@pytest.mark.parametrize('bad_passed', [None, 1, 0, 'true', []])
def test_record_result_rejects_non_boolean_passed(bad_passed):
    store = DreamFirestore()
    with pytest.raises(ValueError, match='passed must be a boolean'):
        dream_canary.record_result(bad_passed, firestore_client=store)


def test_record_result_and_reset_failures_handle_corrupt_counts_and_cap_at_100():
    store = DreamFirestore()
    store.rows[('dream_canary_health', 'current')] = {'canary_failures': None}
    assert dream_canary.record_result(False, firestore_client=store) == 1
    assert dream_canary.failure_count(firestore_client=store) == 1

    store.rows[('dream_canary_health', 'current')] = {'canary_failures': 100}
    assert dream_canary.record_result(False, firestore_client=store) == 100

    assert dream_canary.reset_failures(firestore_client=store) == 0
    assert dream_canary.failure_count(firestore_client=store) == 0

    store.rows[('dream_canary_health', 'current')] = {'canary_failures': 'corrupt'}
    assert dream_canary.record_result(False, firestore_client=store) == 1
    assert dream_canary.record_result(True, firestore_client=store) == 0
