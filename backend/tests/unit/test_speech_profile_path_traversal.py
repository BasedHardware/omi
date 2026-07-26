"""POST /v3/upload-audio must not honor path-traversal segments in the uploaded filename.

file.filename comes straight from the client-supplied Content-Disposition header and is
not sanitized by Starlette/FastAPI. Before this fix, upload_profile built the on-disk
path as f"_temp/{uid}/{file.filename}" verbatim, so an authenticated caller could upload
with a filename like "../../evil.wav" (or an absolute path) to write bytes outside
_temp/{uid}/ to anywhere this process can write. The handler now reduces the filename to
its basename (os.path.basename) before using it in a path, stripping any directory
components.

Uses the same import-stubbing approach as test_speech_profile_wav_decode.py since
routers.speech_profile pulls in heavy/native deps (av, pydub, firebase_admin, ...).
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

_STUB = (
    "database",
    "utils.other.storage",
    "utils.stt.speaker_embedding",
    "utils.stt.vad",
    "av",
    "pydub",
    "firebase_admin",
    "google",
    "pinecone",
    "opuslib",
    "redis",
    "scipy",
)


def _is_stubbed(n):
    return any(n == p or n.startswith(p + ".") for p in _STUB)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
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
for _n in list(sys.modules):
    if _is_stubbed(_n):
        sys.modules.pop(_n, None)
sys.meta_path.insert(0, _f)
try:
    from routers import speech_profile as mod
finally:
    sys.meta_path.remove(_f)
    for _n in list(sys.modules):
        if _is_stubbed(_n) and _n not in _saved:
            sys.modules.pop(_n, None)
    sys.modules.update(_saved)

from fastapi import HTTPException  # noqa: E402  (import after the finder block)


def _fake_upload_file(content: bytes, filename: str):
    f = MagicMock()
    f.filename = filename
    f.file = MagicMock()
    f.file.read.return_value = content
    return f


class TestUploadProfilePathTraversalGuard:
    def test_traversal_filename_is_reduced_to_basename(self):
        """A filename with '../' segments must never reach open() with those segments intact."""
        fake_file = _fake_upload_file(b"RIFF....WAVEfmt ", filename="../../../etc/evil.wav")

        opened_paths = []
        mock_open = MagicMock(side_effect=lambda path, *a, **k: opened_paths.append(path) or MagicMock())

        with patch.object(mod, "AudioSegment") as mock_aseg, patch.object(
            mod.os, "makedirs"
        ) as mock_makedirs, patch("builtins.open", mock_open):
            mock_makedirs.return_value = None
            mock_aseg.from_wav.side_effect = Exception("stop after path construction")

            with pytest.raises(HTTPException):
                mod.upload_profile(fake_file, uid="test-uid")

        assert len(opened_paths) == 1
        opened_path = opened_paths[0]
        assert ".." not in opened_path, f"path traversal segments leaked into the write path: {opened_path}"
        assert opened_path == "_temp/test-uid/evil.wav"

    def test_absolute_path_filename_is_reduced_to_basename(self):
        fake_file = _fake_upload_file(b"RIFF....WAVEfmt ", filename="/etc/passwd")

        opened_paths = []
        mock_open = MagicMock(side_effect=lambda path, *a, **k: opened_paths.append(path) or MagicMock())

        with patch.object(mod, "AudioSegment") as mock_aseg, patch.object(
            mod.os, "makedirs"
        ) as mock_makedirs, patch("builtins.open", mock_open):
            mock_makedirs.return_value = None
            mock_aseg.from_wav.side_effect = Exception("stop after path construction")

            with pytest.raises(HTTPException):
                mod.upload_profile(fake_file, uid="test-uid")

        assert opened_paths == ["_temp/test-uid/passwd"]

    def test_empty_filename_is_rejected(self):
        fake_file = _fake_upload_file(b"RIFF....WAVEfmt ", filename="")

        with pytest.raises(HTTPException) as exc_info:
            mod.upload_profile(fake_file, uid="test-uid")

        assert exc_info.value.status_code == 400
