"""reply_to_review must return 422 (not 500) when the 'response' field is missing/empty.

routers/apps.py has a very heavy import graph (langchain, utils.llm, stripe, ...), so we import it
under a stub finder that auto-mocks those namespaces (keeping models/fastapi/pydantic real), then
call reply_to_review directly with its collaborators patched.
"""

import importlib.abc
import importlib.machinery
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


def _clear_stubbed_modules():
    for name in list(sys.modules):
        if any(name == p or name.startswith(p + '.') for p in _STUB):
            sys.modules.pop(name, None)


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
_clear_stubbed_modules()
sys.meta_path.insert(0, _finder)
try:
    from routers import apps as apps_mod
finally:
    sys.meta_path.remove(_finder)
    _clear_stubbed_modules()

from fastapi import HTTPException  # noqa: E402


def _call(data):
    """Drive reply_to_review past the app/owner/reviewer gates so we reach the response check."""
    with patch.object(apps_mod, 'get_available_app_by_id', return_value={'id': 'app-1', 'uid': 'uid1'}), patch.object(
        apps_mod, 'App', return_value=MagicMock(uid='uid1', private=False, name='Test App')
    ), patch.object(apps_mod, 'get_specific_user_review', return_value={'uid': 'r1', 'score': 5}), patch.object(
        apps_mod, 'set_app_review'
    ), patch.object(
        apps_mod, 'send_app_review_reply_notification'
    ):
        return apps_mod.reply_to_review('app-1', data, uid='uid1')


def test_missing_response_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({'reviewer_uid': 'r1'})
    assert e.value.status_code == 422


def test_empty_or_blank_response_returns_422():
    for bad in ('', '   '):
        with pytest.raises(HTTPException) as e:
            _call({'reviewer_uid': 'r1', 'response': bad})
        assert e.value.status_code == 422


def test_non_string_response_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({'reviewer_uid': 'r1', 'response': 123})
    assert e.value.status_code == 422


def test_valid_response_succeeds():
    result = _call({'reviewer_uid': 'r1', 'response': 'Thanks for the feedback'})
    assert result['status'] == 'ok'
