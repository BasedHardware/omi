"""GET /v1/x/posts lists the user's synced X posts.

The X connector stores every synced post under the user's account and mines memories
from them, but nothing let a client read the raw posts back. The endpoint returns them
newest-first with an optional kind filter and a bounded limit.

Test isolation: routers.x_connector imports cleanly, so the test imports it normally,
patches the import-cheap x_posts_db helper with monkeypatch.setattr, and calls the
handler directly (no sys.modules mutation, no TestClient).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import inspect  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from routers import x_connector as x_mod  # noqa: E402


def test_list_x_posts_limit_has_documented_bounds_and_default():
    # The limit is declared Query(100, ge=1, le=500); FastAPI rejects out-of-range values
    # (e.g. limit=0 or limit=501) with 422 based on this declaration, and defaults to 100.
    param = inspect.signature(x_mod.list_x_posts).parameters['limit'].default
    assert param.default == 100
    bounds = {type(m).__name__: m for m in param.metadata}
    assert bounds['Ge'].ge == 1
    assert bounds['Le'].le == 500


def test_list_x_posts_returns_posts_wrapped(monkeypatch):
    posts = [{'id': '2', 'text': 'newer', 'kind': 'tweet'}, {'id': '1', 'text': 'older', 'kind': 'tweet'}]
    monkeypatch.setattr(x_mod.x_posts_db, 'get_x_posts', lambda uid, limit=100, kind=None: posts)
    assert x_mod.list_x_posts(kind=None, limit=100, uid='u1') == {'posts': posts}


def test_list_x_posts_passes_kind_and_limit(monkeypatch):
    captured = {}

    def fake_get(uid, limit=100, kind=None):
        captured['args'] = (uid, limit, kind)
        return []

    monkeypatch.setattr(x_mod.x_posts_db, 'get_x_posts', fake_get)
    x_mod.list_x_posts(kind='bookmark', limit=25, uid='u1')
    assert captured['args'] == ('u1', 25, 'bookmark')


def test_list_x_posts_rejects_invalid_kind(monkeypatch):
    called = {'hit': False}

    def fake_get(uid, limit=100, kind=None):
        called['hit'] = True
        return []

    monkeypatch.setattr(x_mod.x_posts_db, 'get_x_posts', fake_get)
    with pytest.raises(HTTPException) as ei:
        x_mod.list_x_posts(kind='retweet', limit=100, uid='u1')
    assert ei.value.status_code == 400
    assert called['hit'] is False  # rejected before touching the db
