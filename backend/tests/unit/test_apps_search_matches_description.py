"""GET /v2/apps/search must match the query against name OR description, not name alone.

The `q` parameter is documented as 'Search query for app name or description', and every client
falls back to a local rank over name/description/category/author when the endpoint is unreachable
(desktop `appRanking.ts`). The endpoint itself filtered on `search_query in app.name.lower()`, so
an app whose description was about the query but whose name did not contain the string was
unreachable — searching 'adhd' returned "No apps found" online but found the app offline.

Ordering matters too: results are paginated, so a name match must outrank a description-only match
regardless of installs, or the app the user typed the name of falls off page 1.

Test isolation follows test_apps_search_poison_guard.py: import routers.apps normally, patch the
import-cheap db helpers, and call the handler directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import apps as apps_mod  # noqa: E402


def _app_dict(app_id, name, description):
    return {
        'id': app_id,
        'name': name,
        'category': 'productivity',
        'author': 'Someone',
        'description': description,
        'image': 'http://img',
        'capabilities': ['chat'],
    }


def _search(monkeypatch, records, q, installs=None):
    monkeypatch.setattr(apps_mod, 'search_apps_db', lambda **kw: [dict(r) for r in records])
    monkeypatch.setattr(apps_mod, 'get_enabled_apps', lambda uid: set())
    monkeypatch.setattr(apps_mod, 'get_apps_installs_count', lambda ids: installs or {})
    monkeypatch.setattr(apps_mod, 'get_apps_reviews', lambda ids: {})

    return apps_mod.search_apps(
        q=q,
        category=None,
        rating=None,
        capability=None,
        sort=None,
        my_apps=None,
        installed_apps=None,
        offset=0,
        limit=20,
        uid='u1',
    )


def test_search_matches_description_not_only_name(monkeypatch):
    # The reported case: the query appears only in the description.
    focus = _app_dict('a1', 'Focus Coach', 'Helps people with ADHD stay on task')
    unrelated = _app_dict('a2', 'Recipe Finder', 'Finds recipes')

    result = _search(monkeypatch, [focus, unrelated], q='adhd')

    assert [a['id'] for a in result['data']] == ['a1']


def test_search_still_matches_name(monkeypatch):
    named = _app_dict('a1', 'ADHD Buddy', 'Unrelated description')
    unrelated = _app_dict('a2', 'Recipe Finder', 'Finds recipes')

    result = _search(monkeypatch, [named, unrelated], q='adhd')

    assert [a['id'] for a in result['data']] == ['a1']


def test_name_match_outranks_more_installed_description_match(monkeypatch):
    # Default sort when searching is installs-desc; the name match must still come first, or it
    # falls off the first page of a large catalog.
    description_match = _app_dict('popular', 'Focus Coach', 'Great for ADHD')
    name_match = _app_dict('exact', 'ADHD', 'Unrelated description')

    result = _search(
        monkeypatch,
        [description_match, name_match],
        q='adhd',
        installs={'popular': 10_000, 'exact': 1},
    )

    assert [a['id'] for a in result['data']] == ['exact', 'popular']


def test_search_is_case_insensitive_over_description(monkeypatch):
    app = _app_dict('a1', 'Focus Coach', 'Built for ADHD routines')

    result = _search(monkeypatch, [app], q='  AdHd ')

    assert [a['id'] for a in result['data']] == ['a1']
