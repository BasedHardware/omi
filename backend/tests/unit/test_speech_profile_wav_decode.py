"""Unit test for the speech-profile upload WAV-decode guard.

POST /v3/upload-audio decodes the uploaded file with AudioSegment.from_wav.
A malformed / non-WAV upload makes pydub raise (e.g. CouldntDecodeError),
which previously escaped the handler and surfaced as a 500. A bad client
upload should be reported as a 400 client error instead.

This test patches AudioSegment.from_wav to raise and asserts upload_profile
raises HTTPException(400). It is red on the unguarded code (raw exception -> 500)
and green once the decode is wrapped in a try/except that returns 400.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import io
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

# Heavy / native packages pulled in (directly or transitively) by routers.speech_profile.
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


class _FakeDecodeError(Exception):
    """Stand-in for pydub.exceptions.CouldntDecodeError (pydub is stubbed here)."""


def _fake_upload_file(content: bytes, filename: str = "speech_profile.wav"):
    f = MagicMock()
    f.filename = filename
    f.file = MagicMock()
    f.file.read.return_value = content
    return f


class TestUploadProfileWavDecodeGuard:
    def test_invalid_wav_returns_400_not_500(self):
        """A failing AudioSegment.from_wav must surface as HTTPException(400), not escape as 500."""
        fake_file = _fake_upload_file(b"not a wav")

        with patch.object(mod, "os") as mock_os, patch("builtins.open", MagicMock()), patch.object(
            mod, "AudioSegment"
        ) as mock_aseg:
            # makedirs is a no-op; everything else on os.* stays usable via the mock.
            mock_os.makedirs.return_value = None
            mock_aseg.from_wav.side_effect = _FakeDecodeError("Decoding failed")

            with pytest.raises(HTTPException) as exc_info:
                mod.upload_profile(fake_file, uid="test-uid")

        assert exc_info.value.status_code == 400

    def test_invalid_wav_does_not_run_vad_or_upload(self):
        """On a decode failure the handler must bail before VAD / storage side effects."""
        fake_file = _fake_upload_file(b"garbage bytes")

        with patch.object(mod, "os") as mock_os, patch("builtins.open", MagicMock()), patch.object(
            mod, "AudioSegment"
        ) as mock_aseg, patch.object(mod, "apply_vad_for_speech_profile") as mock_vad, patch.object(
            mod, "upload_profile_audio"
        ) as mock_upload:
            mock_os.makedirs.return_value = None
            mock_aseg.from_wav.side_effect = _FakeDecodeError("Decoding failed")

            with pytest.raises(HTTPException) as exc_info:
                mod.upload_profile(fake_file, uid="test-uid")

        assert exc_info.value.status_code == 400
        mock_vad.assert_not_called()
        mock_upload.assert_not_called()
