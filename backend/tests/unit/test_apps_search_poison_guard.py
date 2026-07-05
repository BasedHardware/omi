"""GET /v2/apps/search must skip a malformed app record, not 500 the whole search page.

search_apps builds App(**app_dict) in a loop over raw Firestore app documents. One legacy or
malformed app document (missing a required field like name/category/author) previously raised
ValidationError and 500'd the entire search result for the user. The guard skips + logs it.

Test isolation: routers.apps imports cleanly, so the test imports it normally, patches the
import-cheap db helpers with monkeypatch.setattr, and calls the handler directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import apps as apps_mod  # noqa: E402


def _valid_app_dict(app_id='a1'):
    return {
        'id': app_id,
        'name': 'Good App',
        'category': 'productivity',
        'author': 'Someone',
        'description': 'Does things',
        'image': 'http://img',
        'capabilities': ['chat'],
    }


def test_search_apps_skips_malformed_record(monkeypatch):
    good = _valid_app_dict('a1')
    bad = {'id': 'a2'}  # missing required fields -> ValidationError -> must be skipped, not 500
    monkeypatch.setattr(apps_mod, 'search_apps_db', lambda **kw: [dict(good), dict(bad)])
    monkeypatch.setattr(apps_mod, 'get_enabled_apps', lambda uid: set())
    monkeypatch.setattr(apps_mod, 'get_apps_installs_count', lambda ids: {})
    monkeypatch.setattr(apps_mod, 'get_apps_reviews', lambda ids: {})

    result = apps_mod.search_apps(
        q=None,
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

    # The malformed record is skipped; the valid app still comes through (no 500).
    assert len(result['data']) == 1


def test_search_apps_skips_record_without_id(monkeypatch):
    # A record missing 'id' would KeyError in the app_ids list / installs / reviews lookups before
    # the per-record ValidationError guard — it must be dropped up front, not 500.
    good = _valid_app_dict('a1')
    no_id = {'name': 'No Id App', 'category': 'productivity', 'author': 'Someone'}  # no 'id'
    monkeypatch.setattr(apps_mod, 'search_apps_db', lambda **kw: [dict(no_id), dict(good)])
    monkeypatch.setattr(apps_mod, 'get_enabled_apps', lambda uid: set())
    monkeypatch.setattr(apps_mod, 'get_apps_installs_count', lambda ids: {})
    monkeypatch.setattr(apps_mod, 'get_apps_reviews', lambda ids: {})

    result = apps_mod.search_apps(
        q=None,
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

    assert len(result['data']) == 1
