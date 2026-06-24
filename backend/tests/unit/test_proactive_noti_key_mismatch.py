"""Regression test for the proactive-notification in-process rate-limit key mismatch.

`_set_proactive_noti_sent_at` must write the in-process (mem_db) rate-limit key
under `app.id`, the same key `_hit_proactive_notification_rate_limits` reads with.
The original bug passed the whole `App` object as the key to
`mem_db.set_proactive_noti_sent_at`, so the in-process rate-limit layer never
matched on a subsequent read (the write landed under str(App), the read under
app.id) — silently disabling that layer.

Harness: meta-path stub-finder for heavy deps. The module under test
(utils.app_integrations) is explicitly excluded from stubbing so it imports from
disk; mem_db and redis_db are then patched on the imported module so we can
observe the exact key each layer writes under.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Module under test — must import from disk, never get stubbed.
_TARGET = 'utils.app_integrations'

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'httpx',
    'models',
)


def _is(n):
    if n == _TARGET:
        return False
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)

# Give the real `utils` package a filesystem path so the finder can locate the
# real utils.app_integrations on disk (the finder declines to stub _TARGET).
_real_utils = types.ModuleType('utils')
_real_utils.__path__ = [os.path.join(_BACKEND_DIR, 'utils')]
sys.modules['utils'] = _real_utils

sys.meta_path.insert(0, _f)
try:
    from utils import app_integrations as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.pop('utils', None)
    sys.modules.update(_sav)


def _make_app(app_id):
    """Minimal App-like object: only `.id` is used by the function under test."""
    return SimpleNamespace(id=app_id)


def test_set_proactive_noti_sent_at_writes_under_app_id():
    """The in-process (mem_db) write must use app.id so a later read with app.id hits.

    Red (bug): mem_db.set_proactive_noti_sent_at is called with the App object as
    the key, so the captured key != app.id and a read keyed by app.id misses.
    """
    app = _make_app('app-xyz')
    uid = 'user-1'

    # Simulate the real in-process store: key by f'{uid}:{key}', so passing the
    # App object instead of app.id produces a different (never-matching) key.
    store = {}

    def fake_set(u, key, ts, ttl=30):
        store[f'{u}:{key}'] = ts

    def fake_get(u, key):
        return store.get(f'{u}:{key}')

    fake_mem = MagicMock()
    fake_mem.set_proactive_noti_sent_at.side_effect = fake_set
    fake_mem.get_proactive_noti_sent_at.side_effect = fake_get

    fake_redis = MagicMock()

    with patch.object(mod, 'mem_db', fake_mem), patch.object(mod, 'redis_db', fake_redis):
        mod._set_proactive_noti_sent_at(uid, app)

        # The reader keys the in-process lookup by app.id; it must hit what the
        # writer just stored. With the bug, the writer stored under str(App), so
        # this read returns None.
        assert (
            fake_mem.get_proactive_noti_sent_at(uid, app.id) is not None
        ), "in-process rate-limit write did not land under app.id (read keyed by app.id missed)"

    # Also assert the exact positional key handed to mem_db is app.id, not the App.
    call_uid, call_key, call_ts = fake_mem.set_proactive_noti_sent_at.call_args.args
    assert call_key == app.id, f"mem_db write key was {call_key!r}, expected app.id={app.id!r}"
    assert call_key is not app, "mem_db write key was the App object, not app.id (the bug)"


def test_mem_db_and_redis_keys_agree():
    """mem_db and redis_db rate-limit layers must be keyed identically (both app.id)."""
    app = _make_app('app-abc')
    uid = 'user-2'

    fake_mem = MagicMock()
    fake_redis = MagicMock()

    with patch.object(mod, 'mem_db', fake_mem), patch.object(mod, 'redis_db', fake_redis):
        mod._set_proactive_noti_sent_at(uid, app)

    mem_key = fake_mem.set_proactive_noti_sent_at.call_args.args[1]
    redis_key = fake_redis.set_proactive_noti_sent_at.call_args.args[1]
    assert (
        mem_key == redis_key == app.id
    ), f"mem_db key={mem_key!r} and redis_db key={redis_key!r} must both equal app.id={app.id!r}"
