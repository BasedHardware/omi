"""Home pagination across long runs of hidden rows (v3 smell audit F1/F2, 2026-11-18).

Synthetic data only. A v3 owner's indexed Home query (``discarded == False``)
still matches ``home_hidden`` windows and recordings; readers hide them. The
page fill must count only hidden rows against its cap, and report the storage
advance so released apps (which add ``X-Omi-Conversation-Page-Size`` to their
offset and stop below the page size) page past a hidden run.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Response

from database import conversations as db
from tests.unit.test_fsr_wq4_cursor import CountingQuery, budget, rows

PAGE = 50  # app/lib/providers/conversation_provider.dart _conversationPageSize


@pytest.fixture(autouse=True)
def cursor_lever_off(monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)


def owner(before=30, hidden=150, after=100, *, reason='home_hidden'):
    """Newest first: ``before`` visible, a run of ``hidden`` hidden, ``after`` visible."""
    data = rows(before + hidden + after)
    for row in data:
        row['status'] = 'completed'
    for row in data[before : before + hidden]:
        if reason == 'recording':
            row['recording'] = True
        else:
            row['home_hidden'] = True
    visible = [row['id'] for row in data if not (row.get('home_hidden') or row.get('recording'))]
    return data, visible


def page(monkeypatch, data, **kwargs):
    query = CountingQuery(data)
    monkeypatch.setattr(db, 'db', query)
    info = {}
    # The Home route always reads under a request budget; that is what earns the larger cap.
    kwargs.setdefault('budget', budget())
    result = db.get_conversations_without_photos('u', limit=PAGE, hide_home=True, cursor_page=info, **kwargs)
    return [row['id'] for row in result], info, query.counts


def released_app_walk(monkeypatch, data, *, read_header=True):
    """Mirror conversation_provider.dart: offset += storage count; hasMore = storage count >= 50."""
    seen, offset, reads = [], 0, []
    for _ in range(50):
        ids, info, counts = page(monkeypatch, data, offset=offset)
        reads.append(counts['reads'] - offset)
        seen.extend(i for i in ids if i not in seen)
        storage = info['storage_rows'] if read_header else len(ids)
        offset += storage
        if storage < PAGE:
            return seen, reads
    raise AssertionError('pagination did not terminate')


@pytest.mark.parametrize('reason', ['home_hidden', 'recording'])
def test_150_hidden_rows_then_visible_rows_are_all_reachable(monkeypatch, reason):
    data, visible = owner(reason=reason)
    seen, reads = released_app_walk(monkeypatch, data)
    assert seen == visible
    # Every page stays bounded: a page plus the hidden-row cap.
    assert max(reads) <= PAGE + db._HIDDEN_ROW_PAGE_SKIP_CAP


def test_page_after_the_run_is_full_and_advances_past_it(monkeypatch):
    data, visible = owner()
    ids, info, _ = page(monkeypatch, data, offset=0)
    assert ids == visible[:PAGE]
    # 30 visible + 150 hidden + 20 visible rows consumed, not the 64-read cap.
    assert info == {'storage_rows': 200, 'has_more': True}
    ids, info, _ = page(monkeypatch, data, offset=200)
    assert ids == visible[PAGE : 2 * PAGE]
    # No re-served rows: the advance is in storage rows, which the offset counts.
    assert info['storage_rows'] == PAGE


def test_apps_that_ignore_the_header_still_reach_every_row(monkeypatch):
    """The day page counts returned rows; it re-reads some rows but never dead-ends on this run."""
    data, visible = owner()
    seen, _ = released_app_walk(monkeypatch, data, read_header=False)
    assert seen == visible


def test_run_longer_than_the_cap_returns_a_short_page_that_still_pages_on(monkeypatch):
    monkeypatch.setattr(db, '_HIDDEN_ROW_PAGE_SKIP_CAP', 64)
    data, visible = owner(before=10, hidden=150, after=100)
    ids, info, counts = page(monkeypatch, data, offset=0)
    assert ids == visible[:10]
    assert info == {'storage_rows': 10 + 64, 'has_more': True}
    assert counts['reads'] == 10 + 64
    seen, _ = released_app_walk(monkeypatch, data)
    assert seen == visible


def test_unbudgeted_readers_keep_the_old_allowance(monkeypatch):
    """Full-document internal callers have no request budget; their worst case must not grow."""
    data, visible = owner(before=10, hidden=150, after=100)
    ids, info, counts = page(monkeypatch, data, offset=0, budget=None)
    assert ids == visible[:10]
    assert counts['reads'] == 10 + db._UNBUDGETED_HIDDEN_ROW_SKIP_CAP
    assert info['has_more'] is True


def test_end_of_collection_reports_no_more(monkeypatch):
    data, visible = owner(before=5, hidden=20, after=5)
    ids, info, _ = page(monkeypatch, data, offset=0)
    assert ids == visible
    assert info == {'storage_rows': 30, 'has_more': False}


def test_budget_cut_keeps_prefix_and_says_more(monkeypatch):
    data, visible = owner()
    ids, info, _ = page(monkeypatch, data, offset=0, budget=budget(60))
    assert ids == visible[:30]
    assert info['has_more'] is True


def test_budget_spent_before_the_first_row_does_not_say_more(monkeypatch):
    data, _ = owner()
    ids, info, _ = page(monkeypatch, data, offset=0, budget=budget(0))
    assert ids == []
    # A client honoring has-more would repeat the identical request forever.
    assert info == {'storage_rows': 0, 'has_more': False}


def test_discarded_scan_spent_before_a_row_does_not_say_more(monkeypatch):
    data, _ = owner()
    ids, info, _ = page(monkeypatch, data, offset=0, budget=budget(0), include_discarded=True)
    assert ids == []
    assert info['storage_rows'] == 0 and info['has_more'] is False


def test_offset_charge_that_exhausts_the_budget_ends_the_walk(monkeypatch):
    data, _ = owner()
    ids, info, counts = page(monkeypatch, data, offset=100, budget=budget(60))
    assert ids == []
    assert counts['reads'] == 0
    # No storage row was read, so there is no position to resume from.
    assert info == {'storage_rows': 0, 'has_more': False}


def test_cursor_walk_crosses_the_run(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_list_cursor":100}')
    data, visible = owner()
    seen, cursor = [], None
    for _ in range(20):
        ids, info, _ = page(monkeypatch, data, offset=0, cursor=cursor)
        seen.extend(ids)
        if not info['has_more']:
            break
        cursor = info['next_cursor']
    assert seen == visible


# -- route: headers, day view, body shape ------------------------------------


@pytest.fixture
def routes(monkeypatch):
    from routers import conversations as routes

    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    monkeypatch.setattr(routes, 'redact_conversations_for_list', lambda *a: None)
    return routes


def call_route(routes, **kwargs):
    response = Response()
    params = dict(
        request=None,
        response=response,
        uid='u',
        limit=PAGE,
        offset=0,
        statuses='processing,completed',
        include_discarded=False,
        sources=None,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
        cursor=None,
    )
    params.update(kwargs)
    return routes.get_conversations(**params), response


def test_route_sets_storage_advance_and_has_more_headers(monkeypatch, routes):
    data, visible = owner()
    query = CountingQuery(data)
    monkeypatch.setattr(db, 'db', query)
    body, response = call_route(routes)
    assert isinstance(body, list) and [row['id'] for row in body] == visible[:PAGE]
    assert response.headers['X-Omi-Conversation-Page-Size'] == '200'
    assert response.headers['X-Omi-Has-More'] == 'true'
    assert 'X-Omi-Next-Cursor' not in response.headers


def test_route_cursor_header_and_param_round_trip(monkeypatch, routes):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_list_cursor":100}')
    data, visible = owner()
    monkeypatch.setattr(db, 'db', CountingQuery(data))
    body, response = call_route(routes)
    cursor = response.headers['X-Omi-Next-Cursor']
    monkeypatch.setattr(db, 'db', CountingQuery(data))
    body, response = call_route(routes, cursor=cursor, offset=9999)
    # The body stays a plain list; the cursor replaces the offset.
    assert isinstance(body, list) and [row['id'] for row in body] == visible[PAGE : 2 * PAGE]


@pytest.mark.parametrize(
    'filters, hide_home',
    [
        ({}, True),
        # The day view is Home's own drill-in: a date range alone still hides what Home hides.
        ({'start_date': datetime(2026, 11, 18, tzinfo=timezone.utc)}, True),
        (
            {
                'start_date': datetime(2026, 11, 18, tzinfo=timezone.utc),
                'end_date': datetime(2026, 11, 18, tzinfo=timezone.utc) + timedelta(days=1),
            },
            True,
        ),
        # Explicit reveal filters keep showing hidden rows.
        ({'include_discarded': True}, False),
        ({'starred': True}, False),
        ({'folder_id': 'f'}, False),
        ({'statuses': 'in_progress'}, False),
    ],
)
def test_day_view_applies_home_visibility(monkeypatch, routes, filters, hide_home):
    calls = []

    def fetch(uid, limit, offset, **kw):
        calls.append(kw)
        return []

    monkeypatch.setattr(routes.conversations_db, 'get_conversations_without_photos', fetch)
    call_route(routes, **filters)
    assert calls[0]['hide_home'] is hide_home


def test_day_cursor_resume_reads_current_rows_and_has_an_independent_kill_switch(monkeypatch, routes):
    from starlette.requests import Request

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_list_cursor":100,"conversation_day_list_cursor":100}')
    data, expected = owner(before=12, hidden=0, after=0)
    # All rows tie on the date key. Firestore resolves the tie using document ID.
    for row in data:
        row['created_at'] = datetime(2026, 11, 19, tzinfo=timezone.utc)
    request = Request({'type': 'http', 'query_string': b'', 'headers': [(b'x-omi-day-cursor', b'1')]})
    params = dict(request=request, limit=3, start_date=data[0]['created_at'] - timedelta(days=1))
    monkeypatch.setattr(db, 'db', CountingQuery(data))
    first, response = call_route(routes, **params)
    assert [row['id'] for row in first] == expected[:3]
    assert response.headers['X-Omi-Day-Cursor'] == '1'
    cursor = response.headers['X-Omi-Next-Cursor']

    # Delete the cursor anchor and another unseen row, update an unseen row,
    # and insert a row above the bookmark. Pagination must use the old values,
    # and a refresh must see the new head.
    data[3]['structured'] = {'title': 'Edited between pages'}
    data[2]['deleted'] = data[4]['deleted'] = True
    data.insert(0, {**data[0], 'id': '099'})
    query = CountingQuery(data)
    monkeypatch.setattr(db, 'db', query)
    second, _ = call_route(routes, **params, cursor=cursor, offset=3)
    assert [row['id'] for row in second] == [expected[3], expected[5], expected[6]]
    assert second[0]['structured']['title'] == 'Edited between pages'
    assert query.counts['offsets'] == []
    refreshed, _ = call_route(routes, **params)
    assert refreshed[0]['id'] == '099'

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_list_cursor":100}')
    fallback_query = CountingQuery(data)
    monkeypatch.setattr(db, 'db', fallback_query)
    _, response = call_route(routes, **params, cursor=cursor, offset=3)
    assert fallback_query.counts['offsets'] == [3]
    assert 'X-Omi-Day-Cursor' not in response.headers
