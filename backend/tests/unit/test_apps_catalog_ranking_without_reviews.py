"""Marketplace catalog sections must rank apps by installs when review scores are 0 or not loaded.

`GET /v2/apps` defaults to `include_reviews=False` and calls
`get_approved_available_apps(include_reviews=False)`, which hydrates `installs` on every `App`
while leaving `rating_avg=0`, `rating_count=0`, and `score=None`. Every section and filtered
listing in `/v2/apps` (except `popular`) then orders its apps with `sort_apps_by_installs`.

Previously, `sort_apps_by_installs` computed `app.score = compute_app_score(app)` (which is `0.0`
whenever `rating_avg` or `rating_count` is `0`) and sorted solely by `a.score or 0`. Because
Python's `sorted` is stable and every app had key `0.0`, `sort_apps_by_installs` was a no-op when
`include_reviews=False` — and for all unreviewed apps when `include_reviews=True` — returning
catalog sections in Firestore document-ID order (oldest ULID first) instead of ranking by installs.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402

from models.app import App  # noqa: E402
from routers import apps as apps_router  # noqa: E402
from utils import apps as apps_utils  # noqa: E402


class _PassThroughCache:
    """Memory cache stand-in that always runs the fetcher, so the builder itself is exercised."""

    def get_or_fetch(self, _key, fetcher, ttl=None):
        return fetcher()

    def delete(self, _key):
        return None


def _valid_app(app_id: str, *, category: str = 'productivity-and-organization', capabilities=('chat',)):
    return {
        'id': app_id,
        'name': f'App {app_id}',
        'category': category,
        'author': 'Someone',
        'description': 'Does things',
        'image': 'http://img',
        'capabilities': list(capabilities),
        'approved': True,
        'private': False,
    }


def _unreachable_db():
    raise AssertionError('the DB branch must not run when the Redis cache is populated')


def _patch_public_set(monkeypatch, records, installs, *, reviews=None, from_cache=False):
    """Serve `records` from Redis or from Firestore, never both, so each branch is proven alone."""
    monkeypatch.setattr(apps_utils, 'get_memory_cache', _PassThroughCache)
    monkeypatch.setattr(apps_utils, 'set_generic_cache', lambda *a, **kw: None)
    if from_cache:
        monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda _key: [dict(r) for r in records])
        monkeypatch.setattr(apps_utils, 'get_public_approved_apps_db', _unreachable_db)
    else:
        monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda _key: None)
        monkeypatch.setattr(apps_utils, 'get_public_approved_apps_db', lambda: [dict(r) for r in records])
    monkeypatch.setattr(apps_utils, 'get_apps_installs_count', lambda ids: dict(installs))
    monkeypatch.setattr(apps_utils, 'get_apps_reviews', lambda ids: dict(reviews or {}))


@pytest.mark.parametrize('from_cache', [False, True], ids=['from_db', 'from_redis_cache'])
def test_approved_available_apps_without_reviews_ranks_by_installs_in_sort_apps_by_installs(monkeypatch, from_cache):
    records = [
        _valid_app('01OLD_LOW'),
        _valid_app('02MID_HIGH'),
        _valid_app('03NEW_MED'),
    ]
    installs = {'01OLD_LOW': 2, '02MID_HIGH': 500, '03NEW_MED': 40}
    _patch_public_set(monkeypatch, records, installs, from_cache=from_cache)

    apps = apps_utils.get_approved_available_apps(include_reviews=False)
    ranked = apps_utils.sort_apps_by_installs(apps)

    assert [app.score for app in ranked] == [0.0, 0.0, 0.0]
    assert [app.id for app in ranked] == ['02MID_HIGH', '03NEW_MED', '01OLD_LOW']


def test_v2_apps_default_without_reviews_orders_groups_and_filters_by_installs(monkeypatch):
    records = [
        _valid_app('01OLD_LOW', capabilities=('chat',)),
        _valid_app('02MID_HIGH', capabilities=('chat',)),
        _valid_app('03NEW_MED', capabilities=('chat',)),
    ]
    installs = {'01OLD_LOW': 1, '02MID_HIGH': 250, '03NEW_MED': 25}
    _patch_public_set(monkeypatch, records, installs, from_cache=False)
    monkeypatch.setattr(apps_router, 'get_generic_cache', lambda _key: None)
    monkeypatch.setattr(apps_router, 'set_generic_cache', lambda *a, **kw: None)

    grouped_res = apps_router.get_apps_v2(
        capability=None,
        category=None,
        offset=0,
        limit=20,
        include_reviews=False,
    )
    chat_group = next(g for g in grouped_res['groups'] if g['capability']['id'] == 'chat')
    assert [a['id'] for a in chat_group['data']] == ['02MID_HIGH', '03NEW_MED', '01OLD_LOW']

    cap_res = apps_router.get_apps_v2(
        capability='chat',
        category=None,
        offset=0,
        limit=20,
        include_reviews=False,
    )
    assert [a['id'] for a in cap_res['data']] == ['02MID_HIGH', '03NEW_MED', '01OLD_LOW']

    cat_res = apps_router.get_apps_v2(
        capability=None,
        category='productivity-and-organization',
        offset=0,
        limit=20,
        include_reviews=False,
    )
    assert [a['id'] for a in cat_res['data']] == ['02MID_HIGH', '03NEW_MED', '01OLD_LOW']


def test_sort_apps_by_installs_keeps_positive_score_priority_and_breaks_ties_by_installs():
    unreviewed_low = App(**{**_valid_app('unreviewed-low'), 'installs': 10, 'rating_avg': None, 'rating_count': 0})
    unreviewed_high = App(**{**_valid_app('unreviewed-high'), 'installs': 900, 'rating_avg': None, 'rating_count': 0})
    reviewed = App(**{**_valid_app('reviewed'), 'installs': 50, 'rating_avg': 4.8, 'rating_count': 5})
    negative_installs = App(
        **{**_valid_app('negative-installs'), 'installs': -5, 'rating_avg': None, 'rating_count': 0}
    )

    ranked = apps_utils.sort_apps_by_installs([unreviewed_low, negative_installs, unreviewed_high, reviewed])

    assert [app.id for app in ranked] == ['reviewed', 'unreviewed-high', 'unreviewed-low', 'negative-installs']
    assert ranked[0].score > 0
    assert [app.score for app in ranked[1:]] == [0.0, 0.0, 0.0]
