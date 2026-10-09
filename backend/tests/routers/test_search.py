"""Global-search support routes: recap search and the overview tile counts.

Hermetic: every Firestore read is patched at the router's module references or
served by a MagicMock client injected into the database helpers.
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.conversations as conversations_db
import database.memories as memories_db
import database.users as users_db
from routers import search as search_router
from routers import users as users_router
from utils.daily_summary_search import DAILY_SUMMARY_SEARCH_WINDOW, filter_daily_summaries


def _client(router_module) -> TestClient:
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.auth.get_current_user_uid] = lambda: 'uid1'
    return TestClient(app)


def _summary(summary_id: str, date: str, **fields) -> dict:
    return {'id': summary_id, 'date': date, 'headline': '', 'overview': '', **fields}


SUMMARIES = [
    _summary('s3', '2026-09-03', headline='Launch Day', overview='Shipped the mobile search screen.'),
    _summary(
        's2',
        '2026-09-02',
        headline='Quiet day',
        highlights=[{'topic': 'Hiking', 'summary': 'Walked the coastal trail with Maya.'}],
    ),
    _summary(
        's1',
        '2026-09-01',
        headline='Planning',
        overview='Roadmap review for SEARCH.',
        decisions_made=[{'decision': 'Ship the mobile build Friday'}],
    ),
]


# --- recap search ---------------------------------------------------------


def test_search_path_is_not_captured_as_summary_id():
    get_one = MagicMock(return_value={'id': 'search'})
    with patch.object(
        users_router.daily_summaries_db, 'get_daily_summaries', MagicMock(return_value=SUMMARIES)
    ) as get_list, patch.object(users_router.daily_summaries_db, 'get_daily_summary', get_one):
        response = _client(users_router).get('/v1/users/daily-summaries/search', params={'query': 'launch'})

    assert response.status_code == 200
    assert [s['id'] for s in response.json()['summaries']] == ['s3']
    get_one.assert_not_called()
    get_list.assert_called_once_with('uid1', limit=DAILY_SUMMARY_SEARCH_WINDOW, offset=0)


def test_summary_id_route_still_serves_other_ids():
    with patch.object(
        users_router.daily_summaries_db, 'get_daily_summary', MagicMock(return_value=_summary('abc', '2026-09-01'))
    ):
        response = _client(users_router).get('/v1/users/daily-summaries/abc')

    assert response.status_code == 200
    assert response.json()['id'] == 'abc'


def test_search_matches_case_insensitively_across_readable_fields_newest_first():
    with patch.object(users_router.daily_summaries_db, 'get_daily_summaries', MagicMock(return_value=SUMMARIES)):
        client = _client(users_router)
        by_overview = client.get('/v1/users/daily-summaries/search', params={'query': 'SeArCh'})
        by_highlight = client.get('/v1/users/daily-summaries/search', params={'query': 'maya'})

    assert [s['id'] for s in by_overview.json()['summaries']] == ['s3', 's1']
    assert [s['id'] for s in by_highlight.json()['summaries']] == ['s2']
    # Items keep the list endpoint's shape.
    assert by_highlight.json()['summaries'][0]['highlights'][0]['topic'] == 'Hiking'


def test_search_requires_every_term():
    with patch.object(users_router.daily_summaries_db, 'get_daily_summaries', MagicMock(return_value=SUMMARIES)):
        response = _client(users_router).get('/v1/users/daily-summaries/search', params={'query': 'mobile friday'})

    # s3 mentions "mobile" but not "friday"; s1 has both (overview + decision).
    assert [s['id'] for s in response.json()['summaries']] == ['s1']


def test_search_respects_limit():
    with patch.object(users_router.daily_summaries_db, 'get_daily_summaries', MagicMock(return_value=SUMMARIES)):
        response = _client(users_router).get('/v1/users/daily-summaries/search', params={'query': 'search', 'limit': 1})

    assert [s['id'] for s in response.json()['summaries']] == ['s3']


def test_search_validates_query_and_limit():
    with patch.object(users_router.daily_summaries_db, 'get_daily_summaries', MagicMock(return_value=SUMMARIES)):
        client = _client(users_router)
        assert client.get('/v1/users/daily-summaries/search', params={'query': ''}).status_code == 422
        assert client.get('/v1/users/daily-summaries/search').status_code == 422
        assert client.get('/v1/users/daily-summaries/search', params={'query': 'x', 'limit': 51}).status_code == 422
        assert client.get('/v1/users/daily-summaries/search', params={'query': 'x', 'limit': 0}).status_code == 422


def test_filter_ignores_blank_query_and_malformed_fields():
    summaries = [_summary('a', '2026-09-01', headline=None, highlights='not-a-list', action_items=[None, {'x': 1}])]
    assert filter_daily_summaries(summaries, '   ', 10) == []
    assert filter_daily_summaries(summaries, 'anything', 10) == []


# --- overview counts ------------------------------------------------------

FOLDERS = [
    {'id': 'f-work', 'name': 'Work', 'icon': '💼', 'color': '#3B82F6', 'order': 0},
    {'id': 'f-personal', 'name': 'Personal', 'icon': '👤', 'color': '#10B981', 'order': 1},
    {'id': None, 'name': 'Broken'},
]


def _patch_overview(**overrides):
    def conversations_count(uid, *, starred=None, folder_id=None):
        assert uid == 'uid1'
        if starred:
            return 4
        return {'f-work': 7, 'f-personal': 2}[folder_id]

    fakes = {
        'get_folders': MagicMock(return_value=FOLDERS),
        'get_conversations_count': MagicMock(side_effect=conversations_count),
        'get_summaries_count': MagicMock(return_value=30),
        'count_default_visible_memories': MagicMock(return_value=120),
        'count_people': MagicMock(return_value=5),
        'count_conversations_with_geolocation': MagicMock(return_value=11),
    }
    fakes.update(overrides)
    return fakes, [
        patch.object(search_router.folders_db, 'get_folders', fakes['get_folders']),
        patch.object(search_router.conversations_db, 'get_conversations_count', fakes['get_conversations_count']),
        patch.object(search_router.daily_summaries_db, 'get_summaries_count', fakes['get_summaries_count']),
        patch.object(
            search_router.memories_db, 'count_default_visible_memories', fakes['count_default_visible_memories']
        ),
        patch.object(search_router.users_db, 'count_people', fakes['count_people']),
        patch.object(
            search_router.conversations_db,
            'count_conversations_with_geolocation',
            fakes['count_conversations_with_geolocation'],
        ),
    ]


def _get_overview(patches):
    for p in patches:
        p.start()
    try:
        return _client(search_router).get('/v1/search/overview')
    finally:
        for p in patches:
            p.stop()


def test_overview_shape_and_counts():
    fakes, patches = _patch_overview()
    response = _get_overview(patches)

    assert response.status_code == 200
    assert response.json() == {
        'starred': 4,
        'folders': [
            {'id': 'f-work', 'name': 'Work', 'icon': '💼', 'color': '#3B82F6', 'count': 7},
            {'id': 'f-personal', 'name': 'Personal', 'icon': '👤', 'color': '#10B981', 'count': 2},
        ],
        'recaps': 30,
        'memories': 120,
        'people': 5,
        'places': 11,
    }
    fakes['get_summaries_count'].assert_called_once_with('uid1')
    fakes['count_people'].assert_called_once_with('uid1')


def test_one_failing_count_does_not_fail_the_others():
    def conversations_count(uid, *, starred=None, folder_id=None):
        if folder_id == 'f-work':
            raise RuntimeError('boom')
        return 4 if starred else 2

    fakes, patches = _patch_overview(
        count_default_visible_memories=MagicMock(side_effect=RuntimeError('aggregation unavailable')),
        get_conversations_count=MagicMock(side_effect=conversations_count),
    )
    response = _get_overview(patches)

    assert response.status_code == 200
    body = response.json()
    # A failed count is null, never a false 0: the app then shows the tile without a number.
    assert body['memories'] is None
    assert body['starred'] == 4
    assert body['people'] == 5
    assert body['places'] == 11
    assert body['recaps'] == 30
    assert [(f['id'], f['count']) for f in body['folders']] == [('f-work', None), ('f-personal', 2)]


def test_folder_read_failure_returns_empty_folders_and_other_counts():
    fakes, patches = _patch_overview(get_folders=MagicMock(side_effect=RuntimeError('folders down')))
    response = _get_overview(patches)

    assert response.status_code == 200
    assert response.json()['folders'] == []
    assert response.json()['starred'] == 4


# --- database count helpers -----------------------------------------------


def _aggregation(value):
    row = MagicMock()
    row.value = value
    return [[row]]


def test_count_people_uses_server_side_aggregation():
    client = MagicMock()
    people_ref = client.collection.return_value.document.return_value.collection.return_value
    people_ref.count.return_value.get.return_value = _aggregation(3)
    people_ref.where.return_value.count.return_value.get.return_value = _aggregation(1)

    assert users_db.count_people('uid1', firestore_client=client) == 2
    client.collection.return_value.document.return_value.collection.assert_called_once_with('people')
    dismissed_filter = people_ref.where.call_args.kwargs['filter']
    assert (dismissed_filter.field_path, dismissed_filter.op_string, dismissed_filter.value) == (
        'is_dismissed',
        '==',
        True,
    )
    people_ref.stream.assert_not_called()


def test_count_conversations_with_geolocation_filters_on_latitude():
    client = MagicMock()
    conversations_ref = client.collection.return_value.document.return_value.collection.return_value
    conversations_ref.where.return_value.count.return_value.get.return_value = _aggregation(9)

    assert conversations_db.count_conversations_with_geolocation('uid1', firestore_client=client) == 9
    field_filter = conversations_ref.where.call_args.kwargs['filter']
    assert field_filter.field_path == 'geolocation.latitude'
    # The client rewrites `!= None` into Firestore's unary IS_NOT_NULL filter.
    assert getattr(field_filter.op_string, 'name', field_filter.op_string) == 'IS_NOT_NULL'


def test_count_default_visible_memories_prefers_active_canonical_items():
    client = MagicMock()
    canonical = MagicMock()
    canonical.where.return_value.count.return_value.get.return_value = _aggregation(42)
    client.collection.side_effect = lambda path: canonical if path == 'users/uid1/memory_items' else MagicMock()

    assert memories_db.count_default_visible_memories('uid1', firestore_client=client) == 42
    field_filter = canonical.where.call_args.kwargs['filter']
    assert (field_filter.field_path, field_filter.op_string, field_filter.value) == ('status', '==', 'active')


def test_count_default_visible_memories_falls_back_to_legacy_store():
    client = MagicMock()
    canonical = MagicMock()
    canonical.where.return_value.count.return_value.get.return_value = _aggregation(0)
    users = MagicMock()
    legacy = users.document.return_value.collection.return_value
    legacy.count.return_value.get.return_value = _aggregation(17)
    client.collection.side_effect = lambda path: canonical if path == 'users/uid1/memory_items' else users

    assert memories_db.count_default_visible_memories('uid1', firestore_client=client) == 17
    users.document.assert_called_once_with('uid1')
    users.document.return_value.collection.assert_called_once_with('memories')
