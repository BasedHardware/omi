"""GET /v2/apps/search serves the public catalog from the cache the browse endpoints already share.

The endpoint used to call `search_apps_db` on every request, which streams the whole approved
public catalog out of Firestore before any text filter runs — so typing 's' cost the same as
typing 'sports', and every keystroke was a collection scan. `get_approved_available_apps()` already
holds that same set (`approved == True AND private == False`) behind a 10-minute Redis copy with a
singleflight in front of it, invalidated on approve/publish/unpublish.

Two things must stay true after the switch, and both are asserted here:

- the personal views (`my_apps`, `installed_apps`) still read live, because they are not shareable;
- `enabled` is stamped per request onto a copy, never onto the cached objects themselves. The
  cache hands the same `App` instances to every caller, so mutating them in place would publish one
  user's installed apps to everyone served from that list until it expired.

Test isolation follows test_apps_search_matches_description.py: import routers.apps normally, patch
the import-cheap db helpers, and call the handler directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402

from models.app import App  # noqa: E402
from routers import apps as apps_mod  # noqa: E402


def _app(app_id, name, description='Something', category='productivity', approved=True, private=False):
    return App(
        id=app_id,
        name=name,
        category=category,
        author='Someone',
        description=description,
        image='http://img',
        capabilities={'chat'},
        approved=approved,
        private=private,
    )


def _catalog_search(monkeypatch, catalog, *, uid='u1', enabled=None, **kwargs):
    """Run a search whose public catalog is `catalog`, failing if it falls back to Firestore."""

    def _forbidden(**_):
        raise AssertionError('search_apps_db must not be called for the shared public catalog')

    monkeypatch.setattr(apps_mod, 'get_approved_available_apps', lambda include_reviews=False: catalog)
    monkeypatch.setattr(apps_mod, 'search_apps_db', _forbidden)
    monkeypatch.setattr(apps_mod, 'get_enabled_apps', lambda _uid: set(enabled or []))

    params = dict(q=None, category=None, rating=None, capability=None, sort=None, my_apps=None, installed_apps=None)
    params.update(kwargs)
    return apps_mod.search_apps(offset=0, limit=20, uid=uid, **params)


def test_public_search_reads_the_shared_catalog_not_firestore(monkeypatch):
    # _catalog_search asserts search_apps_db is never reached; results proving the catalog was used.
    result = _catalog_search(monkeypatch, [_app('a1', 'Focus Coach'), _app('a2', 'Recipe Finder')])

    assert [a['id'] for a in result['data']] == ['a1', 'a2']


def test_enabled_is_per_user_and_does_not_persist_into_the_shared_catalog(monkeypatch):
    # The regression this guards: the cache returns the same App objects to every request, so
    # stamping `enabled` in place would carry one user's installs into the next user's results.
    catalog = [_app('a1', 'Focus Coach'), _app('a2', 'Recipe Finder')]

    installed = _catalog_search(monkeypatch, catalog, uid='u1', enabled={'a1'})
    assert {a['id']: a['enabled'] for a in installed['data']} == {'a1': True, 'a2': False}

    fresh = _catalog_search(monkeypatch, catalog, uid='u2', enabled=set())
    assert {a['id']: a['enabled'] for a in fresh['data']} == {'a1': False, 'a2': False}

    # The catalog objects themselves must be untouched by either request.
    assert [app.enabled for app in catalog] == [False, False]


def test_public_search_excludes_an_unapproved_or_private_app_in_the_catalog(monkeypatch):
    # Defence in depth: the shared source is already approved-and-public, but search must not be
    # the endpoint that leaks if that ever widens.
    catalog = [
        _app('ok', 'Focus Coach'),
        _app('unapproved', 'Draft App', approved=False),
        _app('private', 'Secret App', private=True),
    ]

    result = _catalog_search(monkeypatch, catalog)

    assert [a['id'] for a in result['data']] == ['ok']


def test_category_filter_applies_over_the_shared_catalog(monkeypatch):
    catalog = [_app('a1', 'Focus Coach', category='productivity'), _app('a2', 'Chef', category='cooking')]

    result = _catalog_search(monkeypatch, catalog, category='cooking')

    assert [a['id'] for a in result['data']] == ['a2']


@pytest.mark.parametrize('scope', ['my_apps', 'installed_apps'])
def test_personal_scopes_still_read_live(monkeypatch, scope):
    # my_apps and installed_apps are per-user, so they must never be served from the shared catalog.
    called = {}

    def _record(**kwargs):
        called.update(kwargs)
        return [
            {
                'id': 'mine',
                'name': 'My App',
                'category': 'productivity',
                'author': 'Me',
                'description': 'Mine',
                'image': 'http://img',
                'capabilities': ['chat'],
            }
        ]

    def _forbidden(include_reviews=False):
        raise AssertionError('the shared catalog must not serve a per-user scope')

    monkeypatch.setattr(apps_mod, 'search_apps_db', _record)
    monkeypatch.setattr(apps_mod, 'get_approved_available_apps', _forbidden)
    monkeypatch.setattr(apps_mod, 'get_enabled_apps', lambda _uid: {'mine'})
    monkeypatch.setattr(apps_mod, 'get_apps_installs_count', lambda ids: {})
    monkeypatch.setattr(apps_mod, 'get_apps_reviews', lambda ids: {})

    result = apps_mod.search_apps(
        q=None,
        category=None,
        rating=None,
        capability=None,
        sort=None,
        my_apps=True if scope == 'my_apps' else None,
        installed_apps=True if scope == 'installed_apps' else None,
        offset=0,
        limit=20,
        uid='u1',
    )

    assert called[scope] is True
    assert [a['id'] for a in result['data']] == ['mine']
