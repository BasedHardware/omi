"""The popular-apps listing must drop a record with no id, not 500 the whole surface.

`get_popular_apps` reads `app['id']` unguarded — once to batch the installs and reviews lookups,
and twice more per app inside the loop. It streams the same raw Firestore documents as the two
shared catalog builders (`_typed_doc` in database/apps.py, which returns the stored payload as-is
and injects nothing), so one legacy document without that field raises KeyError the same way.

The surface is separate: its own `get_popular_apps_data` cache key, its own 30-minute Redis TTL,
and its own `/v1/apps/popular` endpoint. That means the catalog guard shipped alongside this one
does not reach it — the builder is Redis- and process-cached and shared across users, so a single
bad document takes out the popular list for everyone.

These tests drive both the DB branch and the Redis-cached branch, since the reported failure mode
is a poisoned cache entry and a guard applied to only one branch would leave it live.
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
        'is_popular': True,
    }


def _no_id_app():
    return {'name': 'No Id App', 'category': 'productivity', 'author': 'Someone', 'is_popular': True}


def _unreachable_db():
    raise AssertionError('the DB branch must not run when the Redis cache is populated')


def _popular(monkeypatch, records, *, from_cache=False):
    """The `/v1/apps/popular` listing: serve `records` from Redis or Firestore, never both."""
    monkeypatch.setattr(apps_utils, 'get_memory_cache', _PassThroughCache)
    monkeypatch.setattr(apps_utils, 'set_generic_cache', lambda *a, **kw: None)
    if from_cache:
        monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda _key: [dict(r) for r in records])
        monkeypatch.setattr(apps_utils, 'get_popular_apps_db', _unreachable_db)
    else:
        monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda _key: None)
        monkeypatch.setattr(apps_utils, 'get_popular_apps_db', lambda: [dict(r) for r in records])
    monkeypatch.setattr(apps_utils, 'get_apps_installs_count', lambda ids: {})
    monkeypatch.setattr(apps_utils, 'get_apps_reviews', lambda ids: {})
    return apps_utils.get_popular_apps()


@pytest.mark.parametrize('from_cache', [False, True], ids=['from_db', 'from_redis_cache'])
def test_popular_apps_drops_a_record_without_an_id(monkeypatch, from_cache):
    apps = _popular(monkeypatch, [_no_id_app(), _valid_app('a1')], from_cache=from_cache)

    assert [app.id for app in apps] == ['a1']


@pytest.mark.parametrize('from_cache', [False, True], ids=['from_db', 'from_redis_cache'])
def test_popular_apps_still_returns_every_well_formed_record(monkeypatch, from_cache):
    apps = _popular(monkeypatch, [_valid_app('a1'), _valid_app('a2')], from_cache=from_cache)

    assert sorted(app.id for app in apps) == ['a1', 'a2']
