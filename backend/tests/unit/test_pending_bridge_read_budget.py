"""Pending visibility adds a bounded probe and bounded offset-page refills."""

from database import conversation_visibility_counts as counts
from database import conversations as db
from tests.unit.test_sync_donor_tombstone_visibility import _ListingCollection, _ListingDoc, _ListingQuery
from utils.sync import bridge_pending


def test_count_without_pending_reads_only_limit_one_probe(monkeypatch):
    calls = []
    stream = _ListingQuery.stream

    def observe(query, **kw):
        calls.append(([(f.field_path, f.op_string) for f in query._filters], query._limit))
        return stream(query, **kw)

    monkeypatch.setattr(_ListingQuery, 'stream', observe)
    collection = _ListingCollection([_ListingDoc(str(i), {'status': 'completed'}) for i in range(1000)])
    assert counts.count_hidden(collection, include_discarded=False) == 0
    assert [limit for filters, limit in calls if any('sync_bridge_pending' in field for field, _ in filters)] == [1]
    calls.clear()
    assert counts.count_hidden(collection, include_discarded=True) == 0
    assert not any('sync_bridge_pending' in str(filters) for filters, _ in calls)


def test_offset_page_refills_at_most_64_raw_rows(monkeypatch):
    monkeypatch.setattr(db, '_conversation_list_cursor_enabled', lambda _: False)
    monkeypatch.setattr(bridge_pending, 'current_time', lambda: 100)
    calls = []
    stream = _ListingQuery.stream

    def observe(query, **kw):
        rows = list(stream(query, **kw))
        calls.append((query._limit, len(rows)))
        return iter(rows)

    monkeypatch.setattr(_ListingQuery, 'stream', observe)
    docs = [_ListingDoc(str(i), {'created_at': i, 'sync_bridge_pending': {'expires_at': 200}}) for i in range(1000)]
    query = _ListingQuery(docs, order_field='created_at', descending=True)
    assert db._collect_visible_conversation_page(query, uid='u', limit=100, offset=0, include_discarded=False) == []
    assert sum(reads for _, reads in calls) <= 100 + 64
    # One hidden row in a large page needs only one additional read.
    for doc in docs:
        doc._data.pop('sync_bridge_pending', None)
    docs[-1]._data['sync_bridge_pending'] = {'expires_at': 200}
    calls.clear()
    assert (
        len(db._collect_visible_conversation_page(query, uid='u', limit=100, offset=0, include_discarded=False)) == 100
    )
    assert calls == [(100, 100), (1, 1)]
