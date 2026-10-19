"""Hermetic unit tests for backend/database/locked_content.py resilience."""

from types import SimpleNamespace

import pytest

from database import locked_content


class _BatchStore:
    def __init__(self, count=1):
        self.rows = {str(i): {'is_locked': True} for i in range(count)}
        self.commits = 0

    def batch(self):
        updates = []

        def commit():
            self.commits += 1
            for ref, payload in updates:
                self.rows[ref].update(payload)

        return SimpleNamespace(update=lambda ref, payload: updates.append((ref, payload)), commit=commit)


class _Query:
    def __init__(self, store, extra_docs=()):
        self.store = store
        self.bound = None
        self.projection = None
        self.extra_docs = list(extra_docs)

    def select(self, fields):
        self.projection = fields
        return self

    def limit(self, limit):
        self.bound = limit
        return self

    def stream(self):
        rows = [SimpleNamespace(reference=key) for key, value in self.store.rows.items() if value['is_locked']]
        rows.extend(self.extra_docs)
        return iter(rows[: self.bound] if self.bound is not None else rows)


@pytest.mark.parametrize('bad_limit', [True, False, 0, -5, 500, 1.5, '10'])
def test_unlock_query_rows_rejects_boolean_and_invalid_limits(bad_limit):
    store = _BatchStore(1)
    with pytest.raises(ValueError, match='unlock limit'):
        locked_content.unlock_query_rows(store, _Query(store), {'is_locked': False}, limit=bad_limit)
    assert store.commits == 0
    assert store.rows['0']['is_locked'] is True


@pytest.mark.parametrize('bad_update', [{}, None, 'not-a-dict', ['is_locked']])
def test_unlock_query_rows_rejects_empty_or_non_dict_update(bad_update):
    store = _BatchStore(1)
    with pytest.raises(ValueError, match='unlock update'):
        locked_content.unlock_query_rows(store, _Query(store), bad_update)
    assert store.commits == 0


def test_unlock_query_rows_skips_docs_without_reference():
    store = _BatchStore(2)
    query = _Query(store, extra_docs=[SimpleNamespace(reference=None), object()])
    updated = locked_content.unlock_query_rows(store, query, {'is_locked': False})
    assert updated == 2
    assert store.commits == 1
    assert all(not row['is_locked'] for row in store.rows.values())


@pytest.mark.parametrize(
    'bad_uid',
    ['', '   ', 'user/sub', 'user\\sub', 'user..1', 'a' * 129, None, 123],
)
def test_has_recoverable_locked_content_returns_false_for_invalid_uid(bad_uid):
    class _ForbiddenClient:
        def collection(self, name):
            raise AssertionError('Firestore should not be queried for invalid uid')

    assert locked_content.has_recoverable_locked_content(bad_uid, firestore_client=_ForbiddenClient()) is False


def test_has_recoverable_locked_content_trims_uid_and_continues_after_transient_stream_error():
    queried_paths = []

    class _Collection:
        def __init__(self, path):
            self.path = path

        def document(self, doc_id):
            return _Collection(f'{self.path}/{doc_id}')

        def collection(self, name):
            return _Collection(f'{self.path}/{name}')

        def where(self, *, filter=None):
            queried_paths.append((self.path, filter.field_path, filter.op_string, filter.value))
            return self

        def select(self, fields):
            return self

        def limit(self, n):
            return self

        def stream(self):
            if self.path.endswith('/conversations'):
                raise RuntimeError('transient firestore stream error')
            if self.path.endswith('/action_items'):
                return iter([SimpleNamespace(id='task_1')])
            return iter([])

    class _Client:
        def collection(self, name):
            return _Collection(name)

    assert locked_content.has_recoverable_locked_content('  user_1  ', firestore_client=_Client()) is True
    assert queried_paths == [
        ('users/user_1/conversations', 'is_locked', '==', True),
        ('users/user_1/memories', 'is_locked', '==', True),
        ('users/user_1/memory_items', 'promotion.is_locked', '==', True),
        ('users/user_1/action_items', 'is_locked', '==', True),
    ]


def test_has_recoverable_locked_content_returns_false_when_all_collections_empty_or_fail():
    class _Collection:
        def __init__(self, path):
            self.path = path

        def document(self, doc_id):
            return _Collection(f'{self.path}/{doc_id}')

        def collection(self, name):
            return _Collection(f'{self.path}/{name}')

        def where(self, *, filter=None):
            return self

        def select(self, fields):
            return self

        def limit(self, n):
            return self

        def stream(self):
            if self.path.endswith('/memories'):
                raise RuntimeError('transient error')
            return iter([])

    class _Client:
        def collection(self, name):
            return _Collection(name)

    assert locked_content.has_recoverable_locked_content('user_1', firestore_client=_Client()) is False
