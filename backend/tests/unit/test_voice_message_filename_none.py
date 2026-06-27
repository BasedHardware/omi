"""Regression test: transcribe_voice_message must reject a None filename with 400.

A multipart upload whose UploadFile has filename=None previously hit
`file.filename.lower()` and raised AttributeError -> 500. The endpoint now
guards the missing filename and raises HTTPException(400), consistent with the
other 400s on this endpoint.
"""

import asyncio
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
    'multipart',
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
    from routers import chat as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)

from fastapi import HTTPException


class _StubUploadFile:
    """Minimal UploadFile stand-in: has a .file attr and a None filename."""

    def __init__(self, filename):
        self.filename = filename
        self.file = MagicMock()


class _StubForm:
    def __init__(self, files):
        self._files = files

    def getlist(self, key):
        return self._files if key == 'files' else []

    def get(self, key, default=None):
        return default


class _StubRequest:
    """Drive the multipart branch of transcribe_voice_message."""

    def __init__(self, form):
        self._form = form
        self.headers = {'content-type': 'multipart/form-data; boundary=x'}
        self.query_params = {}

    async def form(self):
        return self._form


def _call(upload_file):
    request = _StubRequest(_StubForm([upload_file]))
    with patch.object(mod, 'is_trial_paywalled', return_value=False):
        return asyncio.run(mod.transcribe_voice_message(request=request, uid='u1', x_app_platform='ios'))


def test_none_filename_raises_400():
    """A multipart upload with filename=None -> HTTPException(400), not AttributeError 500."""
    with pytest.raises(HTTPException) as exc_info:
        _call(_StubUploadFile(filename=None))
    assert exc_info.value.status_code == 400


def test_empty_filename_raises_400():
    """An empty-string filename is also rejected with 400."""
    with pytest.raises(HTTPException) as exc_info:
        _call(_StubUploadFile(filename=''))
    assert exc_info.value.status_code == 400
