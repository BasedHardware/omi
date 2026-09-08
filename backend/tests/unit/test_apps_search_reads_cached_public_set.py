"""GET /v2/apps/search must read the approved+public app set through the shared Redis cache.

Prod signature (api.omi.me load-balancer logs, 2026-08-18/19, image c5b0b5d): `?q=<term>` searches
ran p50 13.4s / p90 30.0s and 24 of 29 requests exceeded 5s, most terminating as 504 at the 30s
edge — app search was effectively unusable in the mobile Apps tab. `installed_apps=true` requests
served by the same branch (>30 enabled apps) carried the same tail; the `id in [...]` fast path
sat at p50 0.15s.

Root cause: `search_apps_db` streamed `approved==True AND private==False` from Firestore on every
request. That is 3,247 documents / ~25MB in prod. The marketplace list path
(`utils.apps.get_approved_available_apps`) already serves exactly those documents from a 10-minute
Redis cache under `get_public_approved_apps_data`; search was the one reader that bypassed it.

These tests drive the real route over HTTP with only the Firestore client and the Redis cache
helpers stubbed, so the router, `search_apps_db` and the cache read all execute.
"""

from __future__ import annotations

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from database import apps as apps_db  # noqa: E402
from routers import apps as apps_mod  # noqa: E402

UID = 'uid-apps-search'


def _app_doc(app_id: str, name: str, **overrides):
    doc = {
        'id': app_id,
        'name': name,
        'category': 'productivity',
        'author': 'Someone',
        'description': f'{name} description',
        'image': 'http://img',
        'capabilities': ['chat'],
        'approved': True,
        'private': False,
        'uid': 'author-uid',
        # Excluded by App.reduce_dict — present on the Firestore document, absent from the cache.
        'chat_prompt': 'x' * 128,
        'memory_prompt': 'y' * 128,
    }
    doc.update(overrides)
    return doc


class _FakeDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, collection, docs):
        self._collection = collection
        self._docs = docs

    def stream(self):
        self._collection.streams += 1
        return [_FakeDoc(d) for d in self._docs]


class _FakeCollection:
    """Streams every seeded document; the point of the assertions is *whether* it is streamed."""

    def __init__(self, docs):
        self.docs = docs
        self.streams = 0

    def where(self, filter=None):  # noqa: A002 - matches the firestore kwarg
        return _FakeQuery(self, self.docs)


class _FakeFirestore:
    def __init__(self, docs):
        self.collection_obj = _FakeCollection(docs)

    def collection(self, _name):
        return self.collection_obj


@pytest.fixture
def env(monkeypatch):
    """Real router + real search_apps_db; only Firestore and the Redis cache are stubbed."""
    docs = [_app_doc('a1', 'Todoist'), _app_doc('a2', 'Grok'), _app_doc('a3', 'Calendar Sync')]
    firestore = _FakeFirestore(docs)
    cache: dict[str, object] = {}

    monkeypatch.setattr(apps_db, 'db', firestore)
    # raising=False so the control run against the pre-fix source still executes and fails on the
    # behavioural assertion (a Firestore stream per request) rather than erroring at setup.
    monkeypatch.setattr(apps_db, 'get_generic_cache', lambda key: cache.get(key), raising=False)
    monkeypatch.setattr(
        apps_db, 'set_generic_cache', lambda key, data, ttl=None: cache.__setitem__(key, data), raising=False
    )
    monkeypatch.setattr(apps_mod, 'get_enabled_apps', lambda uid: set())
    monkeypatch.setattr(apps_mod, 'get_apps_installs_count', lambda ids: {})
    monkeypatch.setattr(apps_mod, 'get_apps_reviews', lambda ids: {})

    app = FastAPI()
    app.include_router(apps_mod.router)
    app.dependency_overrides[apps_mod.auth.get_current_user_uid] = lambda: UID

    class Env:
        client = TestClient(app)

    Env.firestore = firestore
    Env.cache = cache
    Env.docs = docs
    return Env


def test_search_populates_the_shared_cache_on_a_cold_read(env):
    response = env.client.get('/v2/apps/search', params={'q': 'todoist', 'limit': 100})

    assert response.status_code == 200
    assert [a['id'] for a in response.json()['data']] == ['a1']
    assert env.firestore.collection_obj.streams == 1

    cached = env.cache['get_public_approved_apps_data']
    assert [a['id'] for a in cached] == ['a1', 'a2', 'a3']
    # Cached as reduced records, matching the marketplace list path.
    assert 'chat_prompt' not in cached[0]
    assert 'description' in cached[0]


def test_warm_cache_serves_search_without_streaming_the_collection(env):
    assert env.client.get('/v2/apps/search', params={'q': 'grok', 'limit': 100}).status_code == 200
    env.firestore.collection_obj.streams = 0

    response = env.client.get('/v2/apps/search', params={'q': 'grok', 'limit': 100})

    assert response.status_code == 200
    assert [a['id'] for a in response.json()['data']] == ['a2']
    # The regression: this is the read that cost 13s+ per request in prod.
    assert env.firestore.collection_obj.streams == 0


def test_default_browse_and_filters_are_served_from_the_cache(env):
    env.client.get('/v2/apps/search', params={'limit': 100})
    env.firestore.collection_obj.streams = 0

    browse = env.client.get('/v2/apps/search', params={'limit': 100})
    assert [a['id'] for a in browse.json()['data']] == ['a3', 'a2', 'a1']  # name_asc default

    matching = env.client.get('/v2/apps/search', params={'category': 'productivity', 'limit': 100})
    assert [a['id'] for a in matching.json()['data']] == ['a3', 'a2', 'a1']
    other = env.client.get('/v2/apps/search', params={'category': 'entertainment', 'limit': 100})
    assert other.json()['data'] == []

    has_cap = env.client.get('/v2/apps/search', params={'capability': 'chat', 'limit': 100})
    assert len(has_cap.json()['data']) == 3
    no_cap = env.client.get('/v2/apps/search', params={'capability': 'persona', 'limit': 100})
    assert no_cap.json()['data'] == []

    assert env.firestore.collection_obj.streams == 0


def test_my_apps_still_reads_firestore(env):
    """Private/unapproved records are not in the public cache — that branch must keep querying."""
    env.client.get('/v2/apps/search', params={'limit': 100})  # warm the cache
    env.firestore.collection_obj.streams = 0

    response = env.client.get('/v2/apps/search', params={'my_apps': 'true', 'limit': 100})

    assert response.status_code == 200
    assert env.firestore.collection_obj.streams == 1


def test_installed_apps_under_the_in_limit_still_reads_firestore(env, monkeypatch):
    monkeypatch.setattr(apps_mod, 'get_enabled_apps', lambda uid: {'a1'})
    env.client.get('/v2/apps/search', params={'limit': 100})  # warm the cache
    env.firestore.collection_obj.streams = 0

    response = env.client.get('/v2/apps/search', params={'installed_apps': 'true', 'limit': 100})

    assert response.status_code == 200
    assert env.firestore.collection_obj.streams == 1


def test_installed_apps_over_the_in_limit_uses_the_cache_for_the_public_set(env, monkeypatch):
    """>30 enabled ids: the public set comes from the cache, the user's own apps still from Firestore."""
    enabled = {'a1', 'a2'} | {f'x{i}' for i in range(30)}
    monkeypatch.setattr(apps_mod, 'get_enabled_apps', lambda uid: enabled)
    env.client.get('/v2/apps/search', params={'limit': 100})  # warm the cache
    env.firestore.collection_obj.streams = 0

    response = env.client.get('/v2/apps/search', params={'installed_apps': 'true', 'limit': 100})

    assert response.status_code == 200
    assert sorted(a['id'] for a in response.json()['data']) == ['a1', 'a2']
    # Exactly one stream: the uid-scoped query for the user's own private/unapproved apps.
    assert env.firestore.collection_obj.streams == 1
