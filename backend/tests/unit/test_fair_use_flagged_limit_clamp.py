"""Regression test for GET /v1/admin/fair-use/flagged limit clamping.

`get_flagged_users` exposes `limit: int = Query(default=50, le=200)`. The Query bound only
constrains the HTTP layer; a direct/non-HTTP caller (or any path that bypasses FastAPI's
validation) could pass a negative or huge limit straight through to the Firestore-backed
`fair_use_db.get_flagged_users(...)`. The handler now clamps in-function to [1, 200]. These
tests call the handler directly and assert the clamped value reaches the DB call.

The fair_use_admin router pulls heavy deps (database.*, firebase_admin, redis, models/utils
chains) at import time, so we import it under a meta-path stub-finder that fakes those packages.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

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
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
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
    from routers import fair_use_admin as fu_mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)


def test_negative_limit_is_clamped_to_one():
    mock_get = MagicMock(return_value=[])
    with patch.object(fu_mod.fair_use_db, 'get_flagged_users', mock_get):
        fu_mod.get_flagged_users(admin_id='a', stage=None, limit=-5)
    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs['limit'] == 1


def test_huge_limit_is_clamped_to_two_hundred():
    mock_get = MagicMock(return_value=[])
    with patch.object(fu_mod.fair_use_db, 'get_flagged_users', mock_get):
        fu_mod.get_flagged_users(admin_id='a', stage=None, limit=100000)
    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs['limit'] == 200


def test_in_range_limit_is_passed_through():
    mock_get = MagicMock(return_value=[])
    with patch.object(fu_mod.fair_use_db, 'get_flagged_users', mock_get):
        fu_mod.get_flagged_users(admin_id='a', stage=None, limit=75)
    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs['limit'] == 75
