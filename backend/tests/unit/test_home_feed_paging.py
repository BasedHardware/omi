from datetime import datetime, timedelta, timezone

import pytest

from utils.home_feed.paging import decode_cursor, encode_cursor, merge_page

AT = datetime(2026, 11, 15, tzinfo=timezone.utc)
SECRET = b'test-secret'


def initial():
    return decode_cursor('u', None, 'policy', SECRET)


def fetcher(streams):
    def fetch(kind, after, limit):
        rows = sorted(streams[kind], key=lambda r: (r['home_sort_at'], r['id']), reverse=True)
        if after:
            rows = [r for r in rows if (r['home_sort_at'], r['id']) < (datetime.fromisoformat(after[0]), after[1])]
        return rows[:limit]

    return fetch


def project(kind, row):
    return {'id': f'{kind}:{row["id"]}'} if not row.get('hidden') else None


def row(cid, at=AT, **kwargs):
    return dict(id=cid, home_sort_at=at, **kwargs)


def test_ties_merge_with_unconsumed_frontiers_and_deleted_anchor():
    streams = {'episode': [row('a'), row('b')], 'conversation': [row('a'), row('b')]}
    state = initial()
    page, more, partial = merge_page(state, fetcher(streams), project, limit=1)
    assert page == [{'id': 'episode:b'}] and more and not partial
    assert state['conversation']['after'] is None
    cursor = encode_cursor('u', state, 'policy', SECRET)
    streams['episode'].pop()
    state = decode_cursor('u', cursor, 'policy', SECRET)
    remaining = []
    while more:
        page, more, _ = merge_page(state, fetcher(streams), project, limit=1)
        remaining.extend(r['id'] for r in page)
    assert remaining == ['episode:a', 'conversation:b', 'conversation:a']


def test_hidden_dense_history_returns_resumable_empty_partial():
    streams = {
        'episode': [],
        'conversation': [row(str(i), AT - timedelta(seconds=i), hidden=i < 20) for i in range(22)],
    }
    state = initial()
    page, more, partial = merge_page(state, fetcher(streams), project, limit=2, scan_limit=10, batch_size=4)
    assert page == [] and more and partial
    page, more, partial = merge_page(state, fetcher(streams), project, limit=2, scan_limit=10, batch_size=4)
    assert page == [] and more and partial
    page, more, partial = merge_page(state, fetcher(streams), project, limit=2, scan_limit=10, batch_size=4)
    assert [r['id'] for r in page] == ['conversation:20', 'conversation:21'] and not more and not partial


def test_byte_budget_retains_unconsumed_value():
    streams = {'episode': [row('a'), row('b')], 'conversation': []}
    state = initial()
    page, more, partial = merge_page(state, fetcher(streams), project, limit=10, byte_limit=1)
    assert page == [{'id': 'episode:b'}] and more and partial
    page, more, _ = merge_page(state, fetcher(streams), project, limit=10)
    assert page == [{'id': 'episode:a'}] and not more


@pytest.mark.parametrize('changed', ['account', 'policy', 'tamper', 'frontier'])
def test_cursor_rejects_scope_tampering_and_malformed_values(changed):
    state = initial()
    if changed == 'frontier':
        state['episode']['after'] = ['not-a-time', 'id']
    cursor = encode_cursor('u', state, 'policy', SECRET)
    if changed == 'tamper':
        cursor = cursor[:-4] + 'AAAA'
    with pytest.raises(ValueError, match='Invalid Home feed cursor'):
        decode_cursor(
            'other' if changed == 'account' else 'u', cursor, 'other' if changed == 'policy' else 'policy', SECRET
        )


def test_late_import_is_ordered_by_recorded_clock_not_created_clock():
    streams = {
        'episode': [row('recent')],
        'conversation': [row('late-import', AT - timedelta(days=7), created_at=AT + timedelta(days=1))],
    }
    state = initial()
    page, more, _ = merge_page(state, fetcher(streams), project, limit=10)
    assert page == [{'id': 'episode:recent'}, {'id': 'conversation:late-import'}]
    assert not more


def test_scan_budget_counts_prefetched_rows_not_only_consumed():
    streams = {'episode': [row(str(i)) for i in range(100)], 'conversation': [row(str(i)) for i in range(100)]}
    actual = fetcher(streams)
    fetched = []

    def fetch(kind, after, limit):
        rows = actual(kind, after, limit)
        fetched.extend(rows)
        return rows

    state = initial()
    page, more, partial = merge_page(state, fetch, project, limit=50, scan_limit=33)
    assert len(fetched) <= 33
    assert more and partial
    # The unconsumed other stream can still advance in a subsequent request.
    assert state['conversation']['after'] is None or state['episode']['after'] is None
