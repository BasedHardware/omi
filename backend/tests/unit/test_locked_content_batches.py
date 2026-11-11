"""Exercise atomic-batch failures against the shared production unlock primitive."""

from types import SimpleNamespace

import pytest

from database.locked_content import unlock_query_rows


class Store:
    def __init__(self, count):
        self.rows = {str(i): {'is_locked': True} for i in range(count)}
        self.commits = 0
        self.fail_commit = None

    def batch(self):
        updates = []

        def commit():
            self.commits += 1
            if self.commits == self.fail_commit:
                raise RuntimeError('simulated atomic commit failure')
            for ref, payload in updates:
                self.rows[ref].update(payload)

        return SimpleNamespace(update=lambda ref, payload: updates.append((ref, payload)), commit=commit)


class Query:
    def __init__(self, store):
        self.store = store
        self.bound = None
        self.projection = None

    def select(self, fields):
        self.projection = fields
        return self

    def limit(self, limit):
        self.bound = limit
        return self

    def stream(self):
        rows = [SimpleNamespace(reference=key) for key, value in self.store.rows.items() if value['is_locked']]
        return iter(rows[: self.bound])


def test_atomic_batch_failure_resumes_and_is_idempotent():
    store = Store(1000)
    store.fail_commit = 2
    callbacks = []
    with pytest.raises(RuntimeError):
        unlock_query_rows(store, Query(store), {'is_locked': False}, on_commit=lambda: callbacks.append('commit'))
    assert sum(row['is_locked'] for row in store.rows.values()) == 501
    assert callbacks == ['commit']
    store.fail_commit = None
    assert unlock_query_rows(store, Query(store), {'is_locked': False}) == 501
    assert unlock_query_rows(store, Query(store), {'is_locked': False}) == 0


def test_page_only_reads_names_and_never_exceeds_bound():
    store = Store(101)
    query = Query(store)
    assert unlock_query_rows(store, query, {'is_locked': False}, limit=100) == 100
    assert query.projection == [] and query.bound == 100
    assert sum(row['is_locked'] for row in store.rows.values()) == 1
    assert store.commits == 1


def test_cache_failure_after_commit_is_repaired_on_empty_retry():
    store = Store(1)

    def fail():
        raise RuntimeError('cache unavailable')

    with pytest.raises(RuntimeError):
        unlock_query_rows(store, Query(store), {'is_locked': False}, limit=100, on_commit=fail)
    assert store.rows['0']['is_locked'] is False
    repairs = []
    assert (
        unlock_query_rows(store, Query(store), {'is_locked': False}, limit=100, on_commit=lambda: repairs.append(True))
        == 0
    )
    assert repairs == [True]


@pytest.mark.parametrize('limit', [0, 500, -1])
def test_invalid_bound_never_reads_or_writes(limit):
    store = Store(1)
    with pytest.raises(ValueError):
        unlock_query_rows(store, Query(store), {'is_locked': False}, limit=limit)
    assert store.commits == 0 and store.rows['0']['is_locked'] is True
