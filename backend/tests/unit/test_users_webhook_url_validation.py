"""POST /v1/users/developer/webhook/{wtype} must return 400 (not 500) when 'url' is missing.

set_user_webhook_endpoint read data['url'] via direct subscript, so a body without url raised KeyError ->
500. routers/users.py has a heavy import graph, so we import it under a stub finder and call the handler.
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
_rm_mp = _install_python_multipart_stub()
sys.meta_path.insert(0, _finder)
try:
    from routers import users as users_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_snap)
    if _rm_mp:
        sys.modules.pop('python_multipart', None)

from fastapi import HTTPException  # noqa: E402
import pydantic  # noqa: E402

from routers.users import SetUserWebhookUrlRequest  # noqa: E402


def test_missing_url_returns_422():
    # Pydantic rejects missing required field; FastAPI surfaces as 422 at API layer.
    with pytest.raises(pydantic.ValidationError):
        SetUserWebhookUrlRequest()


def test_valid_url_sets():
    with patch.object(users_mod, 'set_user_webhook_db') as setdb, patch.object(users_mod, 'disable_user_webhook_db'):
        result = users_mod.set_user_webhook_endpoint(
            wtype='audio_bytes', data=SetUserWebhookUrlRequest(url='http://x'), uid='u1'
        )
    assert result['status'] == 'ok'
    setdb.assert_called_once()


def test_get_missing_webhook_url_validates_as_nullable_response():
    with patch.object(users_mod, 'get_user_webhook_db', return_value=None):
        result = users_mod.get_user_webhook_endpoint(wtype='audio_bytes', uid='u1')

    assert result == {'url': None}
    assert users_mod.UserWebhookUrlResponse.model_validate(result).url is None
