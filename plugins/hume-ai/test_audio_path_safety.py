"""Hermetic regression tests: POST /audio must not let a client-controlled
`uid` query param carry path separators or `..` into the on-disk filename.

The real handler writes `audio_files/{uid}_{timestamp}.wav`. Without
sanitization, `uid=../escape` writes outside `audio_files/`.

Run: python3 plugins/hume-ai/test_audio_path_safety.py
"""

import asyncio
import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

MAIN_PATH = Path(__file__).resolve().parent / "main.py"


class _HTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _identity_decorator(*args, **kwargs):
    def wrap(fn):
        return fn

    return wrap


def _install_stubs():
    fastapi = types.ModuleType("fastapi")

    class _FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        on_event = staticmethod(_identity_decorator)
        post = staticmethod(_identity_decorator)
        get = staticmethod(_identity_decorator)
        websocket = staticmethod(_identity_decorator)

    fastapi.FastAPI = _FastAPI
    fastapi.Request = object
    fastapi.Query = lambda default=None, **kw: default
    fastapi.HTTPException = _HTTPException

    responses = types.ModuleType("fastapi.responses")

    class _JSONResponse:
        def __init__(self, status_code=200, content=None, **kw):
            self.status_code = status_code
            self.content = content

    responses.JSONResponse = _JSONResponse
    responses.HTMLResponse = _JSONResponse

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *a, **kw: mock.Mock()

    uvicorn = types.ModuleType("uvicorn")
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **kw: None

    # The sibling helper module pulls in the `hume` SDK; stub it with the
    # real state dict shape plus permissive callables for the rest.
    app_helpers = types.ModuleType("app")
    app_helpers.audio_stats = {
        "total_requests": 0,
        "successful_analyses": 0,
        "failed_analyses": 0,
        "last_request_time": None,
        "last_uid": None,
        "recent_emotions": [],
        "emotion_counts": {},
        "rizz_score": 75,
        "recent_notifications": [],
        "last_notification_time": None,
    }
    app_helpers.EMOTION_CONFIG = {}
    app_helpers.create_wav_header = lambda sample_rate, n: b"RIFF"

    def _any(name):
        return mock.AsyncMock() if name != "load_emotion_config" else mock.Mock()

    app_helpers.__getattr__ = _any

    stubs = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "fastapi.templating": templating,
        "uvicorn": uvicorn,
        "dotenv": dotenv,
        "app": app_helpers,
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    return saved


def _load_main():
    saved = _install_stubs()
    try:
        spec = importlib.util.spec_from_file_location("hume_main_under_test", MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev


class _Request:
    def __init__(self, body=b"pcm-bytes"):
        self._body = body

    async def body(self):
        return self._body


def _post_audio(module, cwd, uid):
    prev = os.getcwd()
    os.chdir(cwd)
    try:
        return asyncio.run(
            module.handle_audio_stream(
                request=_Request(),
                sample_rate=16000,
                uid=uid,
                analyze_emotion=False,
                send_notification=False,
                emotion_filters=None,
            )
        )
    finally:
        os.chdir(prev)


def test_traversal_uid_stays_inside_audio_dir():
    module = _load_main()
    with tempfile.TemporaryDirectory() as tmp:
        resp = _post_audio(module, tmp, "../escape")
        audio_dir = Path(tmp, "audio_files").resolve()
        written = Path(resp.content["local_file_path"]).resolve()
        assert audio_dir in written.parents, f"wrote outside audio_files: {written}"
        assert not list(Path(tmp).glob("escape_*.wav")), "traversal file exists outside audio_files"
        assert Path(resp.content["filename"]).name == resp.content["filename"]


def test_absolute_and_separator_uids_are_sanitized():
    module = _load_main()
    # %2f is URL-decoded to / by the framework before the handler sees uid
    for uid in ["/abs/path", "..", "a/b\\c", "../../"]:
        with tempfile.TemporaryDirectory() as tmp:
            resp = _post_audio(module, tmp, uid)
            filename = resp.content["filename"]
            assert Path(filename).name == filename, f"unsafe filename for uid={uid!r}: {filename}"
            assert ".." not in filename


def test_normal_uid_and_response_shape_unchanged():
    module = _load_main()
    with tempfile.TemporaryDirectory() as tmp:
        resp = _post_audio(module, tmp, "user_123")
        filename = resp.content["filename"]
        assert filename.startswith("user_123_") and filename.endswith(".wav")
        assert (Path(tmp, "audio_files") / filename).is_file()
        assert resp.content["uid"] == "user_123"
        assert resp.content["sample_rate"] == 16000


if __name__ == "__main__":
    tests = [
        test_traversal_uid_stays_inside_audio_dir,
        test_absolute_and_separator_uids_are_sanitized,
        test_normal_uid_and_response_shape_unchanged,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)}/{len(tests)} tests passed")
