"""Hermetic regression tests for plugins/omi-dropbox-app/main.py audio bounds.

Standard library only: requests, dotenv, fastapi, tenacity, and
omi_plugin_sdk are replaced with minimal stubs before importing the module
under test so the suite runs without site-packages (the manifest lane runs
plain python3). db.py is importable as-is (redis import is optional).

Covers the unbounded audio buffer: /audio accumulated request bodies into a
defaultdict(bytes) with no per-uid byte cap and no bound on uid-key growth,
so a long conversation or a spray of unknown uids grew process memory
without limit. The fix caps each buffer at MAX_AUDIO_BUFFER_BYTES and the
uid set at MAX_AUDIO_BUFFERS.
"""

import asyncio
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = (
    "requests",
    "requests.exceptions",
    "dotenv",
    "fastapi",
    "fastapi.responses",
    "tenacity",
    "pydantic",
    "omi_plugin_sdk",
    "omi_plugin_sdk.models",
)


def _install_module_stubs():
    requests = types.ModuleType("requests")

    class _RequestException(Exception):
        pass

    exceptions = types.ModuleType("requests.exceptions")
    exceptions.RequestException = _RequestException
    exceptions.Timeout = type("Timeout", (_RequestException,), {})
    exceptions.ConnectionError = type("ConnectionError", (_RequestException,), {})
    requests.exceptions = exceptions
    requests.post = lambda *a, **k: None
    requests.get = lambda *a, **k: None
    sys.modules["requests"] = requests
    sys.modules["requests.exceptions"] = exceptions

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    class Request:
        pass

    def Query(default=None, **kwargs):
        return default

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.Query = Query
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class _Resp:
        def __init__(self, *args, **kwargs):
            pass

    responses.HTMLResponse = _Resp
    responses.RedirectResponse = _Resp
    responses.JSONResponse = _Resp
    sys.modules["fastapi.responses"] = responses

    tenacity = types.ModuleType("tenacity")
    tenacity.retry = lambda *a, **k: (lambda f: f)
    tenacity.stop_after_attempt = lambda *a, **k: None
    tenacity.wait_exponential = lambda *a, **k: None
    tenacity.retry_if_exception_type = lambda *a, **k: None
    sys.modules["tenacity"] = tenacity

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda *a, **k: (k["default_factory"]() if "default_factory" in k else k.get("default"))
    sys.modules["pydantic"] = pydantic

    sdk_pkg = types.ModuleType("omi_plugin_sdk")
    sdk_models = types.ModuleType("omi_plugin_sdk.models")

    class _Model:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    for name in (
        "ActionItem",
        "Conversation",
        "EndpointResponse",
        "Structured",
        "TranscriptSegment",
    ):
        setattr(sdk_models, name, type(name, (_Model,), {}))
    sdk_pkg.models = sdk_models
    sys.modules["omi_plugin_sdk"] = sdk_pkg
    sys.modules["omi_plugin_sdk.models"] = sdk_models


_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original
    del _name, _original, _saved_modules


class _FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self):
        return self._body


def _feed(uid, chunk, sample_rate=16000):
    return asyncio.run(main.receive_audio(_FakeRequest(chunk), uid=uid, sample_rate=sample_rate))


class AudioBufferBoundsTests(unittest.TestCase):
    def setUp(self):
        main.audio_buffers.clear()
        main.audio_sample_rates.clear()
        self._saved_bytes_cap = main.MAX_AUDIO_BUFFER_BYTES
        self._saved_uid_cap = main.MAX_AUDIO_BUFFERS

    def tearDown(self):
        main.MAX_AUDIO_BUFFER_BYTES = self._saved_bytes_cap
        main.MAX_AUDIO_BUFFERS = self._saved_uid_cap
        main.audio_buffers.clear()
        main.audio_sample_rates.clear()

    def test_accumulates_normally_under_cap(self):
        result = _feed("u1", b"chunk1")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(main.audio_buffers["u1"], b"chunk1")
        self.assertEqual(main.audio_sample_rates["u1"], 16000)
        _feed("u1", b"chunk2")
        self.assertEqual(main.audio_buffers["u1"], b"chunk1chunk2")

    def test_per_uid_byte_cap_truncates_tail(self):
        main.MAX_AUDIO_BUFFER_BYTES = 10
        _feed("u1", b"0123456789")
        result = _feed("u1", b"abcdef")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(main.audio_buffers["u1"]), 10)

    def test_full_buffer_drops_bytes_without_error(self):
        main.MAX_AUDIO_BUFFER_BYTES = 4
        _feed("u1", b"aaaa")
        result = _feed("u1", b"bbbb")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(main.audio_buffers["u1"], b"aaaa")

    def test_partial_chunk_fits_up_to_cap(self):
        main.MAX_AUDIO_BUFFER_BYTES = 8
        _feed("u1", b"aaaa")
        _feed("u1", b"bbbbbb")
        self.assertEqual(main.audio_buffers["u1"], b"aaaabbbb")

    def test_unknown_uid_spray_bounded(self):
        main.MAX_AUDIO_BUFFERS = 2
        _feed("u1", b"x")
        _feed("u2", b"x")
        result = _feed("u3", b"x")
        self.assertEqual(result["status"], "error")
        self.assertNotIn("u3", main.audio_buffers)
        self.assertEqual(len(main.audio_buffers), 2)

    def test_existing_uid_still_accepted_at_uid_cap(self):
        main.MAX_AUDIO_BUFFERS = 2
        _feed("u1", b"x")
        _feed("u2", b"x")
        result = _feed("u1", b"y")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(main.audio_buffers["u1"], b"xy")

    def test_get_and_clear_audio_returns_wav_and_clears(self):
        _feed("u1", b"\x00\x01" * 100)
        wav = main.get_and_clear_audio("u1")
        self.assertIsNotNone(wav)
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertNotIn("u1", main.audio_buffers)
        self.assertNotIn("u1", main.audio_sample_rates)


if __name__ == "__main__":
    unittest.main()
