"""get_google_maps_location must not 500 when the Google Maps response is missing the 'status' field.

The geocoding helper (used by POST /v1/conversations when a geolocation is provided) read data['status']
via direct subscript, so a malformed Maps response raised KeyError -> 500. It now uses .get(). The module
has a heavy import graph, so we import it under a stub finder and patch the HTTP call.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = (
    'database',
    'utils.http_client',
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
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot_stubbed_modules():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear_stubbed_modules():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore_stubbed_modules(snapshot):
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
_snap = _snapshot_stubbed_modules()
_clear_stubbed_modules()
sys.meta_path.insert(0, _finder)
try:
    from utils.conversations import location as loc_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_snap)


def test_missing_status_returns_none_not_keyerror():
    resp = MagicMock()
    resp.json.return_value = {'results': [{'place_id': 'p1'}]}  # no 'status' key
    with patch.object(loc_mod.r, 'get', return_value=None), patch.object(loc_mod.httpx, 'get', return_value=resp):
        result = loc_mod.get_google_maps_location(1.0, 2.0)
    assert result is None


def test_error_status_returns_none():
    resp = MagicMock()
    resp.json.return_value = {'status': 'REQUEST_DENIED'}
    with patch.object(loc_mod.r, 'get', return_value=None), patch.object(loc_mod.httpx, 'get', return_value=resp):
        result = loc_mod.get_google_maps_location(1.0, 2.0)
    assert result is None
