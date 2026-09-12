"""Hermetic regression tests for plugins/hume-ai/main.py audio path safety.

Standard library only: dotenv, fastapi, uvicorn, and the hume client chain
are replaced with minimal stubs before importing the module under test so
the suite runs without site-packages (the manifest lane runs plain
python3). sys.modules is restored after import.

Covers the uid path traversal: /audio interpolated the uid query parameter
into the WAV filename unsanitized, so uid="../../x" wrote the file outside
the audio_files directory. The fix sanitizes uid before filename use.
"""

import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = (
    "dotenv",
    "fastapi",
    "fastapi.responses",
    "fastapi.templating",
    "uvicorn",
    "hume",
    "hume.expression_measurement",
    "hume.expression_measurement.stream",
    "hume.expression_measurement.stream.stream",
    "hume.expression_measurement.stream.stream.types",
)


def _install_module_stubs():
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

        def on_event(self, *args, **kwargs):
            return lambda f: f

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class Request:
        pass

    def Query(default=None, **kwargs):
        return default

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.Query = Query
    fastapi.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class JSONResponse:
        def __init__(self, status_code=200, content=None, **kwargs):
            self.status_code = status_code
            self.content = content

    class HTMLResponse:
        def __init__(self, *args, **kwargs):
            pass

    responses.JSONResponse = JSONResponse
    responses.HTMLResponse = HTMLResponse
    sys.modules["fastapi.responses"] = responses

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *a, **k: types.SimpleNamespace(TemplateResponse=lambda *a, **k: None)
    sys.modules["fastapi.templating"] = templating

    uvicorn = types.ModuleType("uvicorn")
    uvicorn.run = lambda *a, **k: None
    sys.modules["uvicorn"] = uvicorn

    hume = types.ModuleType("hume")
    hume.AsyncHumeClient = type("AsyncHumeClient", (), {"__init__": lambda self, *a, **k: None})
    sys.modules["hume"] = hume

    em = types.ModuleType("hume.expression_measurement")
    sys.modules["hume.expression_measurement"] = em

    stream = types.ModuleType("hume.expression_measurement.stream")
    stream.StreamLanguage = type("StreamLanguage", (), {"__init__": lambda self, *a, **k: None})
    em.stream = stream
    sys.modules["hume.expression_measurement.stream"] = stream

    stream_stream = types.ModuleType("hume.expression_measurement.stream.stream")
    stream.stream = stream_stream
    sys.modules["hume.expression_measurement.stream.stream"] = stream_stream

    stream_types = types.ModuleType("hume.expression_measurement.stream.stream.types")
    stream_types.Config = type("Config", (), {"__init__": lambda self, *a, **k: None})
    stream_stream.types = stream_types
    sys.modules["hume.expression_measurement.stream.stream.types"] = stream_types


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


def _post_audio(uid, body=b"\x00\x01" * 64):
    return asyncio.run(
        main.handle_audio_stream(_FakeRequest(body), sample_rate=16000, uid=uid, analyze_emotion=False)
    )


class AudioPathSafetyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self.addCleanup(os.chdir, self._cwd)
        self.audio_dir = Path(self._tmp.name) / "audio_files"

    def _written_files(self):
        return list(self.audio_dir.glob("*.wav"))

    def test_normal_uid_writes_inside_audio_dir(self):
        resp = _post_audio("user_123")
        self.assertEqual(resp.status_code, 200)
        files = self._written_files()
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].name.startswith("user_123_"))
        self.assertEqual(files[0].parent.resolve(), self.audio_dir.resolve())

    def test_traversal_uid_cannot_escape_audio_dir(self):
        resp = _post_audio("../../escaped")
        self.assertEqual(resp.status_code, 200)
        files = self._written_files()
        self.assertEqual(len(files), 1)
        # No file may exist above audio_files, and the returned filename
        # must not contain separators or dot-segments.
        filename = resp.content["filename"]
        self.assertNotIn("/", filename)
        self.assertNotIn("..", filename)
        escaped = list(Path(self._tmp.name).glob("*.wav"))
        self.assertEqual(escaped, [])

    def test_dot_dot_segments_are_flattened(self):
        resp = _post_audio("../..")
        filename = resp.content["filename"]
        self.assertNotIn("..", filename)
        self.assertTrue(filename.endswith(".wav"))

    def test_special_chars_replaced(self):
        resp = _post_audio("a/b\\c:d e")
        filename = resp.content["filename"]
        # filename is "<safe_uid>_<YYYYMMDD>_<HHMMSS>_<microseconds>.wav"
        uid_part = filename.rsplit("_", 3)[0]
        self.assertEqual(uid_part, "a_b_c_d_e")

    def test_dots_only_uid_sanitizes_to_underscores(self):
        resp = _post_audio("...")
        self.assertEqual(resp.status_code, 200)
        uid_part = resp.content["filename"].rsplit("_", 3)[0]
        self.assertEqual(uid_part, "___")

    def test_empty_stem_uid_still_writes(self):
        resp = _post_audio("")
        self.assertEqual(resp.status_code, 200)
        files = self._written_files()
        self.assertEqual(len(files), 1)
        filename = resp.content["filename"]
        # empty uid sanitizes to "" so the name is "_{timestamp}.wav"
        self.assertTrue(filename.startswith("_"))
        self.assertTrue(filename.endswith(".wav"))
        self.assertNotIn("..", filename)
        self.assertEqual(files[0].parent.resolve(), self.audio_dir.resolve())


if __name__ == "__main__":
    unittest.main()
