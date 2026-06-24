"""Regression test: _retrieve_file_paths_v2 must reject an oversized timestamp with 400.

get_timestamp_from_path() uses an unbounded int(), so a filename whose timestamp
segment is enormous (e.g. 'audio_99999999999999999999.bin') parses past the
`except ValueError` guard, then datetime.fromtimestamp() raises OverflowError/OSError
OUTSIDE that guard -> an uncaught error (HTTP 500). The fix moves the
datetime.fromtimestamp() call inside the try and broadens the caught types to
(ValueError, OverflowError, OSError) so a malformed timestamp becomes the same
clean HTTP 400 as every other bad-filename branch.

Red (pre-fix): OverflowError/OSError escapes as a non-HTTPException -> 500.
Green (post-fix): HTTPException(400).
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


class _StubUploadFile:
    """Minimal UploadFile stand-in with a configurable filename."""

    def __init__(self, filename):
        self.filename = filename
        self.file = MagicMock()


def test_retrieve_file_paths_v2_oversized_timestamp_raises_400(tmp_path, monkeypatch):
    """An oversized timestamp must surface as HTTPException(400), not an uncaught 500.

    'audio_99999999999999999999.bin' parses through int() fine (no ValueError) but
    datetime.fromtimestamp() of the resulting value raises OverflowError/OSError.
    Pre-fix that escapes the `except ValueError`; post-fix it is caught -> 400.
    """
    # Run inside a temp cwd so the 'syncing/<uid>/<job_id>/' makedirs is harmless.
    monkeypatch.chdir(tmp_path)

    upload = _StubUploadFile(filename='audio_99999999999999999999.bin')

    with pytest.raises(HTTPException) as exc_info:
        mod._retrieve_file_paths_v2([upload], 'u1', 'job-1')

    assert exc_info.value.status_code == 400


def test_retrieve_file_paths_v2_valid_timestamp_not_rejected(tmp_path, monkeypatch):
    """Sanity: a well-formed in-range timestamp does NOT hit the invalid-timestamp 400.

    Guards against the fix over-rejecting valid input. A 2024 timestamp passes the
    timestamp checks; the only failure path left is the file-write branch (the stub
    UploadFile.file is a MagicMock), which raises a 500, never the 'invalid timestamp'
    400. So: no HTTPException at all, or a non-400 -> the timestamp guard let it through.
    """
    monkeypatch.chdir(tmp_path)

    # 1719230400 = 2024-06-24, comfortably within [2024-01-01, now) in any local timezone.
    upload = _StubUploadFile(filename='audio_1719230400.bin')

    try:
        mod._retrieve_file_paths_v2([upload], 'u1', 'job-1')
    except HTTPException as exc:
        # A 500 from the file-copy step is fine; a 400 would mean the timestamp guard rejected it.
        assert exc.status_code != 400, 'valid timestamp must not be rejected as invalid'
