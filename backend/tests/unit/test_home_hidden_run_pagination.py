"""Home pagination across long runs of hidden rows (v3 smell audit F1/F2, 2026-11-18).

Synthetic data only. A v3 owner's indexed Home query (``discarded == False``)
still matches ``home_hidden`` windows and recordings; readers hide them. The
page fill must count only hidden rows against its cap, and report the storage
advance so released apps (which add ``X-Omi-Conversation-Page-Size`` to their
offset and stop below the page size) page past a hidden run.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request, Response

from database import conversations as db
from database import home_visibility_index
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
    assert info == {'storage_rows': 200, 'has_more': True, 'hidden_rows': 150}
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
    assert info == {'storage_rows': 10 + 64, 'has_more': True, 'hidden_rows': 64}
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
    assert info == {'storage_rows': 30, 'has_more': False, 'hidden_rows': 20}


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
    assert info == {'storage_rows': 0, 'has_more': False, 'hidden_rows': 0}


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
    assert info == {'storage_rows': 0, 'has_more': False, 'hidden_rows': 0}


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


# -- Lean refills: a hidden run is scanned by its visibility fields, not downloaded (2026-11-24) --


def test_hidden_run_is_scanned_lean_and_only_visible_rows_are_read_in_full(monkeypatch):
    data, visible = owner()
    ids, info, counts = page(monkeypatch, data, offset=0)
    assert ids == visible[:PAGE]
    # The first window (50 rows: 30 visible, 20 hidden) is a full read, as for an owner with no
    # hidden rows. Everything after it is scouted: 130 hidden + 20 visible rows by projection.
    assert counts['lean'] == 150
    # Only the 20 visible candidates are then read in full.
    assert counts['hydrated'] == 20
    assert counts['reads'] == 200 + 20
    assert info == {'storage_rows': 200, 'has_more': True, 'hidden_rows': 150}


def test_owner_with_no_hidden_rows_pays_no_extra_read(monkeypatch):
    data, visible = owner(before=120, hidden=0, after=0)
    ids, _, counts = page(monkeypatch, data, offset=0)
    assert ids == visible[:PAGE]
    assert counts['reads'] == PAGE and 'lean' not in counts and 'hydrated' not in counts


def test_scout_projection_carries_only_visibility_fields(monkeypatch):
    data, _ = owner()
    seen = []
    original = db._Scout.hidden
    monkeypatch.setattr(db._Scout, 'hidden', lambda self, row: seen.append(set(row)) or original(self, row))
    page(monkeypatch, data, offset=0)
    # The first window is a full read (its hidden rows are also shown to the scout, to decide whether
    # lean refills fit this page); every row after it reaches the scout as a projection.
    scouted = [fields for fields in seen if 'discarded' not in fields]
    assert len(scouted) == 150
    assert all(fields <= {'created_at', 'recording', 'home_hidden', 'deleted'} for fields in scouted)


def test_row_only_the_full_predicate_hides_is_dropped_after_the_full_read(monkeypatch):
    """The scout knows three flags. A dream duplicate passes it and is hidden by the full predicate."""
    data, visible = owner(before=10, hidden=80, after=100)
    duplicate = data[95]
    duplicate['dream_duplicate_of'] = 'x'
    visible.remove(duplicate['id'])
    seen, _ = released_app_walk(monkeypatch, data)
    assert seen == visible


def test_budget_cut_mid_refill_never_skips_a_candidate(monkeypatch):
    """Rows scouted as candidates but not yet read in full are not counted as consumed."""
    data, visible = owner(before=10, hidden=40, after=200)
    seen, offset = [], 0
    for _ in range(200):
        # 70 documents: the first window (50) and a scout batch cut before its candidates hydrate.
        ids, info, _ = page(monkeypatch, data, offset=offset, budget=budget(offset + 70))
        seen.extend(i for i in ids if i not in seen)
        offset += info['storage_rows']
        if not info['has_more']:
            break
    assert seen == visible


def test_kill_switch_restores_full_document_refills(monkeypatch):
    monkeypatch.setenv('OMI_LIST_LEAN_SKIP_ENABLED', 'false')
    data, visible = owner()
    ids, info, counts = page(monkeypatch, data, offset=0)
    assert ids == visible[:PAGE]
    assert counts['reads'] == 200 and 'lean' not in counts and 'hydrated' not in counts
    assert info['storage_rows'] == 200


def test_cursor_pages_refill_lean_and_reach_every_row(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_list_cursor":100}')
    data, visible = owner(before=10, hidden=300, after=120)
    seen, cursor, lean = [], None, 0
    for _ in range(50):
        ids, info, counts = page(monkeypatch, data, cursor=cursor) if cursor else page(monkeypatch, data, offset=0)
        lean += counts.get('lean', 0)
        seen.extend(i for i in ids if i not in seen)
        if not info['has_more']:
            break
        cursor = info['next_cursor']
        assert cursor
    assert seen == visible
    assert lean >= 300


def test_run_the_scout_cannot_explain_keeps_full_document_refills(monkeypatch):
    """Rows hidden for a reason only the full predicate sees would each cost a second read if scouted."""
    data, visible = owner(before=10, hidden=150, after=100, reason='recording')
    for row in data[10:160]:
        del row['recording']
        row['dream_duplicate_of'] = 'x'
    ids, info, counts = page(monkeypatch, data, offset=0)
    assert ids == visible[:PAGE]
    assert 'lean' not in counts and 'hydrated' not in counts
    assert counts['reads'] == info['storage_rows'] == 200


def home_request(mode):
    return Request({'type': 'http', 'query_string': b'', 'headers': [(b'x-omi-home-page-mode', mode.encode())]})


def test_indexed_home_reads_fifty_candidates_across_equal_timestamp_pages(monkeypatch, routes):
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setenv('OMI_HOME_VISIBILITY_INDEX_OWNERS', 'u')
    hidden = 1200
    data, _ = owner(before=10, hidden=hidden)
    # The last document on page one and the first on page two share a sort key.
    data[PAGE + hidden]['created_at'] = data[PAGE + hidden - 1]['created_at']
    for i, row in enumerate(data):
        if row.get('home_hidden') and i % 2:
            row.pop('home_hidden')
            row['recording'] = True
        home_visibility_index.stamp(row)
    visible = [
        row['id']
        for row in sorted(data, key=lambda row: (row['created_at'], row['id']), reverse=True)
        if db.is_visible_conversation(row, hide_home=True)
    ]

    query = CountingQuery(data)
    monkeypatch.setattr(db, 'db', query)
    first, response = call_route(routes, request=home_request('auto'))
    assert [row['id'] for row in first] == visible[:PAGE]
    assert response.headers['X-Omi-Home-Page-Mode'] == 'indexed'
    assert query.counts['reads'] == PAGE

    second, response = call_route(
        routes, request=home_request('indexed'), cursor=response.headers['X-Omi-Next-Cursor'], offset=PAGE
    )
    assert [row['id'] for row in second] == visible[PAGE : 2 * PAGE]
    assert response.headers['X-Omi-Home-Page-Mode'] == 'indexed'
    assert query.counts['reads'] == 2 * PAGE

    # Offset-only clients that opted in use offsets from the same candidate set.
    second, response = call_route(routes, request=home_request('indexed'), offset=PAGE)
    assert [row['id'] for row in second] == visible[PAGE : 2 * PAGE]


def test_home_index_leaves_other_queries_and_released_clients_on_legacy(monkeypatch, routes):
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setenv('OMI_HOME_VISIBILITY_INDEX_OWNERS', 'u')
    data, visible = owner()
    monkeypatch.setattr(db, 'db', CountingQuery(data))

    for kwargs in (
        {},
        {'request': home_request('auto'), 'start_date': data[-1]['created_at']},
        {'request': home_request('legacy')},
    ):
        body, response = call_route(routes, **kwargs)
        assert [row['id'] for row in body] == visible[:PAGE]
        assert response.headers.get('X-Omi-Home-Page-Mode') != 'indexed'


def test_home_gate_rollback_restarts_indexed_continuations(monkeypatch, routes):
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.delenv('OMI_HOME_VISIBILITY_INDEX_OWNERS', raising=False)
    data, visible = owner()
    monkeypatch.setattr(db, 'db', CountingQuery(data))
    body, response = call_route(routes, request=home_request('indexed'), offset=1000, cursor='old-cursor')
    assert [row['id'] for row in body] == visible[:PAGE]
    assert response.headers['X-Omi-Home-Page-Mode'] == 'legacy'


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
