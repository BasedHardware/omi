"""Regression test: retrieve_file_paths must reject an oversized timestamp with 400.

A .bin filename like 'recording_99999999999999999999.bin' parses to a valid int,
but datetime.fromtimestamp(timestamp) on that out-of-range value raises
OverflowError / OSError (NOT ValueError). That call used to sit OUTSIDE the
`try/except ValueError` guard, so the error propagated uncaught -> 500. The fix
moves the conversion inside the guard and widens it to
(ValueError, OSError, OverflowError), returning a clean 400 like the endpoint's
other invalid-timestamp paths. This covers both retrieve_file_paths and its
job-scoped twin _retrieve_file_paths_v2.
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

# routers/sync.py pulls in Firestore/Redis/GCS/opus/pydub/models and friends.
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
    'models',
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
    from routers import sync as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)

from fastapi import HTTPException  # noqa: E402  (import after the finder block)

# A 20-digit timestamp is a valid int (passes the ValueError-only guard) but is far
# out of range for datetime.fromtimestamp, which raises OverflowError/OSError.
_OVERSIZED_BIN = 'recording_99999999999999999999.bin'


class _StubUploadFile:
    """Minimal UploadFile stand-in with a configurable filename."""

    def __init__(self, filename):
        self.filename = filename
        self.file = MagicMock()


def test_retrieve_file_paths_oversized_timestamp_raises_400(tmp_path, monkeypatch):
    """An out-of-range timestamp must raise HTTPException(400), not an uncaught OSError/OverflowError -> 500."""
    monkeypatch.chdir(tmp_path)

    upload = _StubUploadFile(filename=_OVERSIZED_BIN)

    with pytest.raises(HTTPException) as exc_info:
        mod.retrieve_file_paths([upload], 'u1')

    assert exc_info.value.status_code == 400


def test_retrieve_file_paths_v2_oversized_timestamp_raises_400(tmp_path, monkeypatch):
    """The job-scoped twin must apply the same guard."""
    monkeypatch.chdir(tmp_path)

    upload = _StubUploadFile(filename=_OVERSIZED_BIN)

    with pytest.raises(HTTPException) as exc_info:
        mod._retrieve_file_paths_v2([upload], 'u1', 'job-1')

    assert exc_info.value.status_code == 400
