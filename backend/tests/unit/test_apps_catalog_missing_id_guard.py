"""The shared marketplace catalogs must drop a record with no id, not 500 every listing.

`get_approved_available_apps` and `get_available_apps` both read `app['id']` unguarded — once to
batch the installs and reviews lookups, and again per app inside the loop. One legacy document
without that field therefore raises KeyError out of a shared builder. Both builders are Redis- and
process-cached off the same key and serve `/v1/apps` and the browse endpoints, so a single bad
document takes out the app list for everyone rather than one person's search page.

`search_apps` was already hardened against exactly this (test_apps_search_poison_guard.py), and
`_safe_build_app` skips a record the App model rejects. Neither helps here: the KeyError is raised
before any model is built, on the reduced dicts the cache hands back. These tests therefore drive
both the DB branch and the Redis-cached branch, since the reported failure is a poisoned cache
entry and a guard applied to only one branch would leave it live.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402

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


def _no_id_app():
    return {'name': 'No Id App', 'category': 'productivity', 'author': 'Someone'}


def _unreachable_db():
    raise AssertionError('the DB branch must not run when the Redis cache is populated')


def _patch_public_set(monkeypatch, records, *, from_cache):
    """Serve `records` from Redis or from Firestore, never both, so each branch is proven alone."""
    monkeypatch.setattr(apps_utils, 'get_memory_cache', _PassThroughCache)
    monkeypatch.setattr(apps_utils, 'set_generic_cache', lambda *a, **kw: None)
    if from_cache:
        monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda _key: [dict(r) for r in records])
        monkeypatch.setattr(apps_utils, 'get_public_approved_apps_db', _unreachable_db)
    else:
        monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda _key: None)
        monkeypatch.setattr(apps_utils, 'get_public_approved_apps_db', lambda: [dict(r) for r in records])
    monkeypatch.setattr(apps_utils, 'get_apps_installs_count', lambda ids: {})
    monkeypatch.setattr(apps_utils, 'get_apps_reviews', lambda ids: {})


def _catalog(monkeypatch, records, *, from_cache=False):
    """The browse listing: `get_approved_available_apps`."""
    _patch_public_set(monkeypatch, records, from_cache=from_cache)
    return apps_utils.get_approved_available_apps()


def _available(monkeypatch, records, *, from_cache=False):
    """The `/v1/apps` listing: `get_available_apps`, which reads the same cache key."""
    _patch_public_set(monkeypatch, records, from_cache=from_cache)
    monkeypatch.setattr(apps_utils, 'is_tester', lambda uid: False)
    monkeypatch.setattr(apps_utils, 'get_private_apps', lambda uid: [])
    monkeypatch.setattr(apps_utils, 'get_public_unapproved_apps', lambda uid: [])
    monkeypatch.setattr(apps_utils, 'get_apps_for_tester_db', lambda uid: [])
    monkeypatch.setattr(apps_utils, 'get_enabled_apps', lambda uid: [])
    return apps_utils.get_available_apps('uid-1')


@pytest.mark.parametrize('from_cache', [False, True], ids=['from_db', 'from_redis_cache'])
def test_catalog_drops_a_record_without_an_id(monkeypatch, from_cache):
    apps = _catalog(monkeypatch, [_no_id_app(), _valid_app('a1')], from_cache=from_cache)

    assert [app.id for app in apps] == ['a1']


@pytest.mark.parametrize('from_cache', [False, True], ids=['from_db', 'from_redis_cache'])
def test_available_apps_drops_a_record_without_an_id(monkeypatch, from_cache):
    apps = _available(monkeypatch, [_no_id_app(), _valid_app('a1')], from_cache=from_cache)

    assert [app.id for app in apps] == ['a1']


@pytest.mark.parametrize('from_cache', [False, True], ids=['from_db', 'from_redis_cache'])
def test_catalog_still_returns_every_well_formed_record(monkeypatch, from_cache):
    apps = _catalog(monkeypatch, [_valid_app('a1'), _valid_app('a2')], from_cache=from_cache)

    assert sorted(app.id for app in apps) == ['a1', 'a2']


@pytest.mark.parametrize('from_cache', [False, True], ids=['from_db', 'from_redis_cache'])
def test_available_apps_still_returns_every_well_formed_record(monkeypatch, from_cache):
    apps = _available(monkeypatch, [_valid_app('a1'), _valid_app('a2')], from_cache=from_cache)

    assert sorted(app.id for app in apps) == ['a1', 'a2']
