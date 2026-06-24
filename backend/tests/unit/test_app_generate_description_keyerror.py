"""generate_description_endpoint must return 422 (not 500) when 'name'/'description' is missing.

Previously the handler read data['name'] / data['description'] directly, so a payload that
omits a key raised KeyError -> 500 instead of the intended 422 (the sibling
generate_description_and_emoji_endpoint already uses data.get(...)).

routers/apps.py has a very heavy import graph (langchain, utils.llm, stripe, ...), so we import it
under a stub finder that auto-mocks those namespaces (keeping models/fastapi/pydantic real), then
call generate_description_endpoint directly with track_usage patched.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from contextlib import contextmanager
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


@contextmanager
def _no_op_track_usage():
    """track_usage is a context manager used to wrap the LLM call; make it a no-op."""
    yield


def _call(data):
    # generate_description must never be reached for a missing-field payload; if the guard is
    # broken and we fall through, the MagicMock keeps the test from doing real work.
    with patch.object(apps_mod, 'track_usage', return_value=_no_op_track_usage()), patch.object(
        apps_mod, 'generate_description', return_value='desc'
    ):
        return apps_mod.generate_description_endpoint(data=data, uid='u1')


def test_missing_both_fields_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({})
    assert e.value.status_code == 422


def test_missing_description_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({'name': 'x'})
    assert e.value.status_code == 422


def test_empty_name_returns_422():
    with pytest.raises(HTTPException) as e:
        _call({'name': '', 'description': 'd'})
    assert e.value.status_code == 422


def test_valid_payload_succeeds():
    result = _call({'name': 'x', 'description': 'd'})
    assert result == {'description': 'desc'}
