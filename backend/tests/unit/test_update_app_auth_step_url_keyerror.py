"""update_app must return 422 (not 500) when an external_integration auth step omits its 'url'.

routers/apps.py has a very heavy import graph (langchain, utils.llm, stripe, ...), so we import it
under a stub finder that auto-mocks those namespaces (keeping models/fastapi/pydantic real), then
call update_app directly with its collaborators patched.

The backward-compat block in update_app subscripts ext_int['auth_steps'][0]['url'] directly; a stored
auth step without a 'url' key raised KeyError -> 500. This mirrors the create_app webhook_url KeyError.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import json
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


def _install_python_multipart_stub():
    if 'python_multipart' in sys.modules:
        return False
    if importlib.util.find_spec('python_multipart') is not None:
        return False

    mod = types.ModuleType('python_multipart')
    mod.__version__ = '0.0.20'
    sys.modules['python_multipart'] = mod
    return True


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
        if any(name == p or name.startswith(p + '.') for p in _STUB):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_stubbed_modules_snapshot = _snapshot_stubbed_modules()
_clear_stubbed_modules()
_remove_python_multipart_stub = _install_python_multipart_stub()
sys.meta_path.insert(0, _finder)
try:
    from routers import apps as apps_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)

from fastapi import HTTPException  # noqa: E402


def _call(external_integration):
    """Drive update_app past the app/owner gates so we reach the auth_steps backward-compat block."""
    app_data = json.dumps({'id': 'app-1', 'external_integration': external_integration})
    with patch.object(
        apps_mod,
        'get_available_app_by_id',
        return_value={'id': 'app-1', 'uid': 'u1', 'approved': False, 'private': True},
    ), patch.object(apps_mod, 'update_app_in_db'), patch.object(apps_mod, 'upsert_app_payment_link'), patch.object(
        apps_mod, '_process_chat_tools_manifest', side_effect=lambda ei, d: d
    ), patch.object(
        apps_mod, 'delete_app_cache_by_id'
    ), patch.object(
        apps_mod, 'invalidate_approved_apps_cache'
    ):
        return apps_mod.update_app('app-1', app_data=app_data, file=None, uid='u1')


def test_auth_step_missing_url_returns_422():
    # One auth step, no 'url' key, and no app_home_url -> backward-compat block subscripts ['url'].
    with pytest.raises(HTTPException) as e:
        _call({'auth_steps': [{'name': 'Login'}]})
    assert e.value.status_code == 422


def test_auth_step_blank_url_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({'auth_steps': [{'name': 'Login', 'url': ''}]})
    assert e.value.status_code == 422


def test_auth_step_with_url_succeeds():
    # A valid single auth step should populate app_home_url and return ok (no 422/500).
    result = _call({'auth_steps': [{'name': 'Login', 'url': 'https://example.com/auth'}]})
    assert result['status'] == 'ok'
