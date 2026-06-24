"""GET /v1/focus-sessions must return 400 (not 500) for a well-formed but invalid date.

The Query regex ^\\d{4}-\\d{2}-\\d{2}$ accepts 2024-99-99, which then reaches datetime.strptime in the db
layer and raises ValueError -> 500. The endpoint now validates the date and returns 400. routers/
focus_sessions.py has a heavy import graph, so we import it under a stub finder.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

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
        pass


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from routers import focus_sessions as fs_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)

from fastapi import HTTPException  # noqa: E402


def test_invalid_date_returns_400():
    with pytest.raises(HTTPException) as e:
        fs_mod.get_focus_sessions(limit=100, offset=0, date='2024-99-99', uid='u1')
    assert e.value.status_code == 400


def test_valid_date_passes_through():
    with patch.object(fs_mod.focus_sessions_db, 'get_focus_sessions', return_value=[]) as db:
        result = fs_mod.get_focus_sessions(limit=100, offset=0, date='2024-01-15', uid='u1')
    assert result == []
    db.assert_called_once()


def test_none_date_passes_through():
    with patch.object(fs_mod.focus_sessions_db, 'get_focus_sessions', return_value=[]) as db:
        fs_mod.get_focus_sessions(limit=100, offset=0, date=None, uid='u1')
    db.assert_called_once()
