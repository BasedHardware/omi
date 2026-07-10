"""POST /v1/conversations/{id}/calendar-event/auto-link must return 400, not 500, on a bad timestamp.

The handler parses the conversation's stored started_at/finished_at with datetime.fromisoformat when they
are strings. A legacy or imported conversation whose timestamp string is not valid ISO raised ValueError
and surfaced as a 500. The same handler already returns 400 when the timestamp is missing, so a malformed
timestamp should be a 400 too. routers/conversations.py has a heavy import graph, so we import it under a
stub finder, then call the handler directly.
"""

import asyncio
import pytest
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


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
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        if module.__name__ == 'utils.request_validation':
            module.NonNegativeOffset = int
            module.PositiveLimit = int
        elif module.__name__ == 'utils.other':
            endpoints = types.ModuleType('utils.other.endpoints')
            endpoints.get_current_user_uid = lambda: 'uid1'
            endpoints.timeit = lambda fn: fn
            endpoints.with_rate_limit = lambda dependency, _policy: dependency
            module.endpoints = endpoints
            sys.modules['utils.other.endpoints'] = endpoints


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from routers import conversations as conv_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


from fastapi import HTTPException  # noqa: E402


def test_invalid_stored_timestamp_returns_400_not_500():
    async def _run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    convo = {'id': 'c1', 'started_at': 'not-a-real-timestamp', 'finished_at': 'not-a-real-timestamp'}
    with (
        patch.object(conv_mod, '_get_valid_conversation_by_id', return_value=convo),
        patch.object(conv_mod, 'run_blocking', _run_blocking),
    ):
        with pytest.raises(HTTPException) as e:
            asyncio.run(conv_mod.auto_link_calendar_event(conversation_id='c1', uid='uid1'))
    assert e.value.status_code == 400
