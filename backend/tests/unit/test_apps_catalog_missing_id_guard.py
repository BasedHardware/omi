"""The shared marketplace catalog must drop a record with no id, not 500 every listing.

`get_approved_available_apps` reads `app['id']` unguarded — once to build the ids for the installs
and reviews lookups, and again per app inside the loop. One legacy document without that field
therefore raises KeyError out of the shared builder, which is worse than the same record reaching
`search_apps`: this list is Redis- and process-cached and serves the marketplace to every user, so
a single bad document takes out browse for everyone rather than one person's search page.

`search_apps` was already hardened against exactly this (test_apps_search_poison_guard.py); the
shared path it now reads was not.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from utils import apps as apps_utils  # noqa: E402


class _PassThroughCache:
    """Memory cache stand-in that always runs the fetcher, so the builder itself is exercised."""

    def get_or_fetch(self, _key, fetcher, ttl=None):
        return fetcher()

    def delete(self, _key):
        return None


def _valid_app(app_id='a1'):
    return {
        'id': app_id,
        'name': 'Good App',
        'category': 'productivity',
        'author': 'Someone',
        'description': 'Does things',
        'image': 'http://img',
        'capabilities': ['chat'],
        'approved': True,
        'private': False,
    }


def _catalog(monkeypatch, records):
    monkeypatch.setattr(apps_utils, 'get_memory_cache', _PassThroughCache)
    monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda _key: None)
    monkeypatch.setattr(apps_utils, 'set_generic_cache', lambda *a, **kw: None)
    monkeypatch.setattr(apps_utils, 'get_public_approved_apps_db', lambda: [dict(r) for r in records])
    monkeypatch.setattr(apps_utils, 'get_apps_installs_count', lambda ids: {})
    monkeypatch.setattr(apps_utils, 'get_apps_reviews', lambda ids: {})
    return apps_utils.get_approved_available_apps()


def test_catalog_drops_a_record_without_an_id(monkeypatch):
    no_id = {'name': 'No Id App', 'category': 'productivity', 'author': 'Someone'}

    apps = _catalog(monkeypatch, [no_id, _valid_app('a1')])

    assert [app.id for app in apps] == ['a1']


def test_catalog_still_returns_every_well_formed_record(monkeypatch):
    apps = _catalog(monkeypatch, [_valid_app('a1'), _valid_app('a2')])

    assert sorted(app.id for app in apps) == ['a1', 'a2']
