"""Regression test: _retrieve_file_paths_v2 must reject a None filename with 400.

An UploadFile with filename=None used to crash _retrieve_file_paths_v2 with an
AttributeError ('NoneType' object has no attribute 'endswith') -> 500. The guard
returns a clean 400 (consistent with the endpoint's other 400s) instead.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

# routers/sync.py pulls in Firestore/Redis/GCS/opus/pydub and friends.
# Stub every heavy package so importing the router stays light; fastapi, pydantic,
# numpy and httpx are real (the function under test raises a real HTTPException).
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
    if n == 'utils.sync' or n.startswith('utils.sync.'):
        return False
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
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    utils_pkg = types.ModuleType('utils')
    utils_pkg.__path__ = [os.path.join(backend_dir, 'utils')]
    sys.modules['utils'] = utils_pkg
    sync_pkg = types.ModuleType('utils.sync')
    sync_pkg.__path__ = [os.path.join(backend_dir, 'utils', 'sync')]
    sys.modules['utils.sync'] = sync_pkg
    from utils.sync import pipeline as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)

from fastapi import HTTPException  # noqa: E402  (import after the finder block)


class _StubUploadFile:
    """Minimal UploadFile stand-in with a configurable filename."""

    def __init__(self, filename):
        self.filename = filename
        self.file = MagicMock()


def test_retrieve_file_paths_v2_none_filename_raises_400(tmp_path, monkeypatch):
    """A file with filename=None must raise HTTPException(400), not AttributeError -> 500."""
    # Run inside a temp cwd so the 'syncing/<uid>/<job_id>/' makedirs is harmless.
    monkeypatch.chdir(tmp_path)

    upload = _StubUploadFile(filename=None)

    with pytest.raises(HTTPException) as exc_info:
        mod._retrieve_file_paths_v2([upload], 'u1', 'job-1')

    assert exc_info.value.status_code == 400


def test_retrieve_file_paths_v2_bad_extension_still_400(tmp_path, monkeypatch):
    """Sanity: a present-but-wrong filename keeps the existing 400 behavior."""
    monkeypatch.chdir(tmp_path)

    upload = _StubUploadFile(filename='recording.mp3')

    with pytest.raises(HTTPException) as exc_info:
        mod._retrieve_file_paths_v2([upload], 'u1', 'job-1')

    assert exc_info.value.status_code == 400
