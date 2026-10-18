"""Unit tests for database.budget_choice — uid/period sanitization, read
resilience, strict validation, and transactional conflict behavior.

The fake models just enough Firestore to exercise the module's contract:
nested collection/document paths, snapshot get/set, and a transaction
object compatible with ``@firestore.transactional``'s retry/commit dance.
"""

import pytest

from database import budget_choice


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocument:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def get(self, transaction=None):
        return _FakeSnapshot(self._store.docs.get(self._path))

    def set(self, data, merge=False):
        if merge:
            self._store.docs.setdefault(self._path, {}).update(data)
        else:
            self._store.docs[self._path] = dict(data)

    def collection(self, name):
        return _FakeCollection(self._store, f'{self._path}/{name}')


class _FakeCollection:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def document(self, doc_id):
        return _FakeDocument(self._store, f'{self._name}/{doc_id}')


class _FakeTransaction:
    """The smallest interface ``@firestore.transactional`` drives:
    _clean_up/_begin/retry_id in _pre_commit, _commit after the wrapped
    call, _rollback on failure, _read_only + _max_attempts for the
    retry boundary."""

    _max_attempts = 1
    _read_only = False

    def __init__(self, store):
        self._store = store
        self._id = 'tx-test'
        self._staged = []
        self.in_progress = False

    def set(self, ref, data):
        self._staged.append((ref, data))

    def _begin(self, retry_id=None):
        self.in_progress = True

    def _commit(self):
        for ref, data in self._staged:
            self._store.docs[ref._path] = dict(data)
        self._staged.clear()
        self.in_progress = False

    def _rollback(self):
        self._staged.clear()
        self.in_progress = False

    def _clean_up(self):
        self.in_progress = False


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def collection(self, name):
        return _FakeCollection(self._store_root(), name)

    def _store_root(self):
        return self

    def document(self, doc_id):
        return _FakeDocument(self, doc_id)

    def transaction(self):
        return _FakeTransaction(self)


@pytest.fixture
def store():
    return _FakeDb()


class TestUidSanitization:
    def test_set_choice_strips_uid_whitespace(self, store):
        budget_choice.set_choice('  u1  ', '2026-01', 'on_device', False, firestore_client=store)
        assert 'users/u1/budget_choice/current' in store.docs
        assert 'users/  u1  /budget_choice/current' not in store.docs

    def test_set_choice_rejects_blank_uid(self, store):
        with pytest.raises(ValueError, match='invalid_uid'):
            budget_choice.set_choice('   ', '2026-01', 'on_device', False, firestore_client=store)

    def test_set_choice_rejects_nonstring_uid(self, store):
        with pytest.raises(ValueError, match='invalid_uid'):
            budget_choice.set_choice(None, '2026-01', 'on_device', False, firestore_client=store)

    def test_get_choice_blank_uid_returns_none(self, store):
        assert budget_choice.get_choice('  ', '2026-01', firestore_client=store) is None

    def test_get_choice_strips_uid(self, store):
        budget_choice.set_choice('u2', '2026-01', 'upgrade', True, firestore_client=store)
        got = budget_choice.get_choice('   u2\t', '2026-01', firestore_client=store)
        assert got['choice'] == 'upgrade'
        assert got['dont_ask_again'] is True


class TestPeriodValidation:
    def test_set_choice_strips_period(self, store):
        budget_choice.set_choice('u3', '  2026-02  ', 'on_device', False, firestore_client=store)
        assert store.docs['users/u3/budget_choice/current']['period'] == '2026-02'

    def test_set_choice_rejects_blank_period(self, store):
        with pytest.raises(ValueError, match='invalid_budget_period'):
            budget_choice.set_choice('u3', '   ', 'on_device', False, firestore_client=store)

    def test_get_choice_blank_period_returns_none(self, store):
        budget_choice.set_choice('u3', '2026-03', 'on_device', False, firestore_client=store)
        assert budget_choice.get_choice('u3', '  ', firestore_client=store) is None


class TestReadResilience:
    def test_get_choice_returns_none_when_doc_missing(self, store):
        assert budget_choice.get_choice('ghost', '2026-01', firestore_client=store) is None

    def test_get_choice_swallows_store_failure(self, store):
        class _Boom:
            def collection(self, name):
                raise TimeoutError('data plane degraded')

        assert budget_choice.get_choice('u', '2026-01', firestore_client=_Boom()) is None

    def test_get_choice_swallows_client_construction_failure(self, monkeypatch):
        def _boom():
            raise OSError('metadata server unreachable')

        monkeypatch.setattr(budget_choice, 'get_firestore_client', _boom)
        assert budget_choice.get_choice('u', '2026-01') is None


class TestStrictValidation:
    def test_rejects_unknown_choice(self, store):
        with pytest.raises(ValueError, match='invalid_budget_choice'):
            budget_choice.set_choice('u4', '2026-01', 'sideways', False, firestore_client=store)

    def test_rejects_nonbool_dont_ask(self, store):
        with pytest.raises(ValueError, match='invalid_budget_choice'):
            budget_choice.set_choice('u4', '2026-01', 'on_device', 'yes', firestore_client=store)


class TestTransactionBehavior:
    def test_set_then_get_round_trips(self, store):
        created = budget_choice.set_choice('u5', '2026-01', 'on_device', True, firestore_client=store)
        assert created == {'period': '2026-01', 'choice': 'on_device', 'dont_ask_again': True}
        assert budget_choice.get_choice('u5', '2026-01', firestore_client=store) == created

    def test_idempotent_repeat(self, store):
        budget_choice.set_choice('u5', '2026-01', 'on_device', False, firestore_client=store)
        again = budget_choice.set_choice('u5', '2026-01', 'on_device', False, firestore_client=store)
        assert again['choice'] == 'on_device'

    def test_conflicting_choice_raises_conflict(self, store):
        budget_choice.set_choice('u5', '2026-01', 'on_device', False, firestore_client=store)
        with pytest.raises(budget_choice.BudgetChoiceConflict):
            budget_choice.set_choice('u5', '2026-01', 'upgrade', False, firestore_client=store)

    def test_newer_period_replaces_older(self, store):
        budget_choice.set_choice('u5', '2026-01', 'on_device', False, firestore_client=store)
        created = budget_choice.set_choice('u5', '2026-02', 'upgrade', False, firestore_client=store)
        assert created['period'] == '2026-02'
        assert created['choice'] == 'upgrade'
