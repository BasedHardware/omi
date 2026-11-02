"""Deferred optimization: pin current lifecycle/offset semantics and its cost.

A remembered startAfter cursor cannot replace numeric offsets transparently:
an insertion ahead of it moves the numeric page boundary. S5 leaves this lever
inert until the client explicitly selects a cursor contract.
"""

import copy
from types import SimpleNamespace

import pytest

from database import conversations as db


class Query:
    def __init__(self, rows, reads, size=None, skip=0, cursor=None):
        self.rows, self.reads, self.size, self.skip, self.cursor = rows, reads, size, skip, cursor

    def limit(self, n):
        return Query(self.rows, self.reads, n, self.skip, self.cursor)

    def offset(self, n):
        return Query(self.rows, self.reads, self.size, n, self.cursor)

    def start_after(self, snapshot):
        return Query(self.rows, self.reads, self.size, 0, snapshot.id)

    def stream(self, **kwargs):
        start = next((i + 1 for i, r in enumerate(self.rows) if r['id'] == self.cursor), 0)
        self.reads[0] += self.skip
        rows = self.rows[start + self.skip :]
        if self.size is not None:
            rows = rows[: self.size]
        for row in rows:
            self.reads[0] += 1
            yield SimpleNamespace(id=row['id'], to_dict=lambda row=row: copy.deepcopy(row))


def collect(rows, include_discarded, offset, limit):
    # Match the caller's already-indexed discarded=False predicate.
    filtered = rows if include_discarded else [r for r in rows if r.get('discarded') is False]
    reads = [0]
    result = db._collect_visible_conversation_page(
        Query(filtered, reads), limit=limit, offset=offset, include_discarded=include_discarded
    )
    return result, reads[0]


@pytest.mark.parametrize('include_discarded', [False, True])
@pytest.mark.parametrize('offset', [0, 2, 7, 100])
def test_untouched_lever_preserves_pages_and_lifecycle(monkeypatch, include_discarded, offset):
    rows = [
        dict(id=str(i), discarded=i == 2, deleted=i == 3, dream_duplicate_of='other' if i == 4 else None)
        for i in range(9)
    ]
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    off, off_reads = collect(rows, include_discarded, offset, 2)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_page":100}')
    on, on_reads = collect(rows, include_discarded, offset, 2)
    assert on == off and on_reads == off_reads
    assert all(row['id'] != '3' for row in on)
    if not include_discarded:
        assert all(row['id'] not in {'2', '4'} for row in on)


@pytest.mark.parametrize('include_discarded', [False, True])
def test_five_numeric_pages_still_bill_thirty_reads(include_discarded):
    rows = [dict(id=str(i), discarded=False) for i in range(10)]
    assert sum(collect(rows, include_discarded, offset, 2)[1] for offset in range(0, 10, 2)) == 30


def test_cached_cursor_changes_numeric_offset_after_insertion():
    before = [dict(id=str(i), discarded=False) for i in range(5)]
    first, _ = collect(before, False, 0, 2)
    after = [dict(id='new', discarded=False), *before]
    numeric, _ = collect(after, False, 2, 2)
    query = Query(after, [0]).start_after(SimpleNamespace(id=first[-1]['id'])).limit(2)
    cursor_items = [doc.to_dict() for doc in query.stream()]
    assert [r['id'] for r in numeric] == ['1', '2']
    assert [r['id'] for r in cursor_items] == ['2', '3']
