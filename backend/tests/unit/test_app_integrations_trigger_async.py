"""Regression test for issue: trigger_external_integrations blocks the event loop.

`trigger_external_integrations` is an `async def` that historically called the
sync, Firestore-backed `get_available_apps(uid)` directly on the event loop. Per
the backend async rules, every blocking DB call inside an `async def` must be
offloaded via `await run_blocking(db_executor, fn, args)`.

This test drives the handler with an `AsyncMock` standing in for `run_blocking`
(returning [] so the function short-circuits before any webhook fan-out) and
asserts that the apps lookup went through `run_blocking(get_available_apps, ...)`
rather than calling `get_available_apps` directly.

Red (before fix): `get_available_apps` is called directly; `run_blocking` is
never invoked for it. Green (after fix): `run_blocking` is called with
`get_available_apps`.
"""

import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

_STUB = (
    'database',
    'utils.apps',
    'utils.notifications',
    'utils.conversations',
    'utils.llm',
    'utils.llms',
    'utils.mentor_notifications',
    'utils.subscription',
    'utils.log_sanitizer',
    'utils.http_client',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
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
)


def _is_stubbed(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        return importlib.machinery.ModuleSpec(name, self, is_package=True) if _is_stubbed(name) else None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_f = _Finder()
_saved = {n: m for n, m in sys.modules.items() if _is_stubbed(n)}
for n in list(sys.modules):
    if _is_stubbed(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from utils import app_integrations as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)


def _make_conversation():
    """A conversation that passes the early discarded/locked guards."""
    conversation = MagicMock()
    conversation.discarded = False
    conversation.is_locked = False
    conversation.id = 'conv-1'
    return conversation


def test_trigger_external_integrations_offloads_get_available_apps():
    """The Firestore-backed apps lookup must go through run_blocking, not a bare call."""
    conversation = _make_conversation()

    # run_blocking is awaited; AsyncMock returns an awaitable. Returning [] means
    # filtered_apps is empty and the function short-circuits before any fan-out,
    # so run_blocking is invoked exactly once: for the apps lookup.
    fake_run_blocking = AsyncMock(return_value=[])
    # Sentinel standing in for get_available_apps. Held in a local so it survives
    # after patch.object reverts mod.get_available_apps, letting us assert exactly
    # which callable was handed to run_blocking.
    sentinel_get_available_apps = MagicMock(return_value=[], name='get_available_apps')

    with patch.object(mod, 'run_blocking', fake_run_blocking), patch.object(
        mod, 'get_available_apps', sentinel_get_available_apps
    ):
        result = asyncio.run(mod.trigger_external_integrations('uid-1', conversation))

    assert result == []
    # The fix routes the apps lookup through run_blocking(db_executor, get_available_apps, uid).
    assert fake_run_blocking.await_count >= 1
    offloaded_fns = [call.args[1] for call in fake_run_blocking.await_args_list if len(call.args) >= 2]
    assert (
        sentinel_get_available_apps in offloaded_fns
    ), 'get_available_apps must be offloaded via run_blocking, not called directly on the event loop'
    # And it must NOT be called directly (bare sync call on the event loop).
    sentinel_get_available_apps.assert_not_called()
