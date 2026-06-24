"""create_app must return 422 (not 500) when external_integration sets triggers_on but omits webhook_url.

routers/apps.py has a very heavy import graph (langchain, utils.llm, stripe, ...), so we import it
under a stub finder that auto-mocks those namespaces (keeping models/fastapi/pydantic real), then
call create_app directly. The triggers_on branch used to subscript external_integration['webhook_url']
directly, which raises KeyError -> 500 when the key is missing; it now raises a clean HTTPException 422.
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
    """Call create_app with an app payload carrying the given external_integration block."""
    app_data = json.dumps(
        {
            'name': 'Test App',
            'author': 'someone',
            'email': 'someone@example.com',
            'external_integration': external_integration,
        }
    )
    # get_user_from_uid is patched defensively; the triggers_on/webhook_url check runs before
    # any DB/file work, so a missing webhook_url must raise before we ever reach the lookup/upload.
    with patch.object(apps_mod, 'get_user_from_uid', return_value={'email': 'someone@example.com'}):
        return apps_mod.create_app(app_data=app_data, file=MagicMock(), uid='u1')


def test_triggers_on_missing_webhook_url_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({'triggers_on': 'memory_creation'})
    assert e.value.status_code == 422


def test_triggers_on_empty_webhook_url_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({'triggers_on': 'memory_creation', 'webhook_url': ''})
    assert e.value.status_code == 422


def test_triggers_on_whitespace_webhook_url_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({'triggers_on': 'memory_creation', 'webhook_url': '   '})
    assert e.value.status_code == 422


def test_triggers_on_non_string_webhook_url_returns_422():
    for bad in (123, ['http://x'], {'u': 'http://x'}, True):
        with pytest.raises(HTTPException) as e:
            _call({'triggers_on': 'memory_creation', 'webhook_url': bad})
        assert e.value.status_code == 422
