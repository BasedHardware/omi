"""Unit test for the speech-profile matching-prediction file-descriptor leak.

`get_speech_profile_matching_predictions` (utils/stt/speech_profile.py) opened the
audio file inline inside the `files=[...]` list passed to `httpx.post(...)` and never
closed it. Every call leaked a file descriptor (httpx does not close caller-provided
file objects). The fix wraps the open() in a `with open(audio_file_path, 'rb') as f:`
block that encloses the httpx.post call, mirroring the sibling `_read_file` helper.

This test patches `httpx.post` to capture the file object handed to it and asserts the
handle is `.closed` after the call returns. It is RED on the unguarded code (the inline
open is never closed -> handle.closed is False) and GREEN once the `with` block closes
it deterministically.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

# Heavy / native packages pulled in (directly or transitively) by utils.stt.speech_profile.
# httpx is kept REAL so we can patch the real httpx.post attribute on the module.
_STUB = (
    "database",
    "firebase_admin",
    "google",
    "pinecone",
    "opuslib",
    "pydub",
    "redis",
    "utils.executors",
    "utils.http_client",
    "utils.other.storage",
)


def _is(n):
    return any(n == p or n.startswith(p + ".") for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith("__") and n.endswith("__"):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for _n in list(sys.modules):
    if _is(_n):
        sys.modules.pop(_n, None)
sys.meta_path.insert(0, _f)
try:
    from utils.stt import speech_profile as mod
finally:
    sys.meta_path.remove(_f)
    for _n in list(sys.modules):
        if _is(_n) and _n not in _sav:
            sys.modules.pop(_n, None)
    sys.modules.update(_sav)


def _make_wav():
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.write(fd, b"RIFF....WAVEfmt ")
    os.close(fd)
    return path


def _cleanup(path, captured):
    """Best-effort temp-file removal.

    On Windows an un-closed handle (the bug) blocks os.remove, so close the
    captured handle first if it is still open. This keeps the *assertion* (not
    the cleanup) the thing that fails, on both Windows and Linux/CI.
    """
    fh = captured.get("fh")
    if fh is not None and not fh.closed:
        try:
            fh.close()
        except Exception:
            pass
    try:
        os.remove(path)
    except OSError:
        pass


class TestSpeechProfileMatchingPredictionsFdLeak:
    def test_audio_file_handle_closed_after_success(self):
        """The opened audio file handle must be closed once the call returns (no FD leak)."""
        path = _make_wav()
        captured = {}

        def _fake_post(url, data=None, files=None, **kwargs):
            # files = [('audio_file', (basename, <file object>, 'audio/wav'))]
            fh = files[0][1][1]
            captured["fh"] = fh
            captured["closed_at_call_return"] = None
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = [False]
            return resp

        try:
            with patch.dict(os.environ, {"HOSTED_SPEECH_PROFILE_API_URL": "http://stt.test/match"}), patch.object(
                mod.httpx, "post", side_effect=_fake_post
            ):
                mod.get_speech_profile_matching_predictions("uid-1", path, segments=[{"text": "hi"}])
                # Capture closed-state at the moment the function returned, before cleanup.
                captured["closed_at_call_return"] = captured["fh"].closed
        finally:
            _cleanup(path, captured)

        assert "fh" in captured, "httpx.post was not called with a files= payload"
        assert (
            captured["closed_at_call_return"] is True
        ), "audio file handle was left open after the call returned (FD leak)"

    def test_audio_file_handle_closed_even_when_post_raises(self):
        """Even if httpx.post raises mid-request the handle must not be leaked."""
        path = _make_wav()
        captured = {}

        def _raising_post(url, data=None, files=None, **kwargs):
            captured["fh"] = files[0][1][1]
            raise RuntimeError("boom")

        try:
            with patch.dict(os.environ, {"HOSTED_SPEECH_PROFILE_API_URL": "http://stt.test/match"}), patch.object(
                mod.httpx, "post", side_effect=_raising_post
            ):
                try:
                    mod.get_speech_profile_matching_predictions("uid-1", path, segments=[{"text": "hi"}])
                except RuntimeError:
                    pass
                captured["closed_at_call_return"] = captured["fh"].closed
        finally:
            _cleanup(path, captured)

        assert "fh" in captured, "httpx.post was not called with a files= payload"
        assert (
            captured.get("closed_at_call_return") is True
        ), "audio file handle was left open after post raised (FD leak)"
