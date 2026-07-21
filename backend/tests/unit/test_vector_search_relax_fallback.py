"""Regression test: the vector-search relax-retry must fire without a date filter.

database.vector_db.query_vectors_by_metadata queries Pinecone with a uid clause plus an
optional structured $or clause (people/topics/entities) plus an optional date-range clause.
When the structured query returns no matches it drops the $or clause and re-queries uid-only.
The guard was `len(and_clauses) == 3`, which only relaxed when a date filter was ALSO present;
the common query with people/topics/entities but no date range has len == 2 and fell through to
`return []`, silently yielding no results. The guard now relaxes whenever the structured $or
clause is present (and never pops a date-only clause).
"""

from datetime import datetime, timezone

import database.vector_db as vdb


class _FakeIndex:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def query(self, **kwargs):
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        return {'matches': []}


def test_relax_retry_fires_without_date_filter(monkeypatch):
    fake = _FakeIndex(
        [
            {'matches': []},  # structured query (uid + $or) -> no hits
            {'matches': [{'id': 'u1-conv1', 'metadata': {'memory_id': 'conv1'}}]},  # uid-only retry -> hit
        ]
    )
    monkeypatch.setattr(vdb, 'index', fake)

    result = vdb.query_vectors_by_metadata('u1', [0.0] * 8, [], ['alice'], [], [], [], limit=5)

    assert fake.calls == 2  # the relax-retry fired
    assert result == ['conv1']


def test_no_retry_when_structured_query_hits(monkeypatch):
    fake = _FakeIndex([{'matches': [{'id': 'u1-conv2', 'metadata': {'memory_id': 'conv2'}}]}])
    monkeypatch.setattr(vdb, 'index', fake)

    result = vdb.query_vectors_by_metadata('u1', [0.0] * 8, [], ['alice'], [], [], [], limit=5)

    assert fake.calls == 1  # no retry needed
    assert result == ['conv2']


def test_no_retry_for_date_only_query(monkeypatch):
    # uid + date range only (no structured $or): a no-match must NOT pop the date clause; returns [].
    fake = _FakeIndex([{'matches': []}])
    monkeypatch.setattr(vdb, 'index', fake)
    d0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    d1 = datetime(2024, 1, 2, tzinfo=timezone.utc)

    result = vdb.query_vectors_by_metadata('u1', [0.0] * 8, [d0, d1], [], [], [], [], limit=5)

    assert fake.calls == 1  # no relax-retry (nothing structured to drop)
    assert result == []
