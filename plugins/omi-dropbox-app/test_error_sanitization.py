"""Hermetic regression tests verifying error sanitization in plugins/omi-dropbox-app.
Ensures internal exception details, network errors, and sensitive tokens are not leaked to users.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda f: f

    post = get


class DummyResponse:
    def __init__(self, content=None, status_code=200, *args, **kwargs):
        self.content = content
        self.status_code = status_code


class EndpointResponseStub:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


def make_module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


stubs = {
    "requests": make_module(
        "requests",
        RequestException=OSError,
        Response=DummyResponse,
        post=lambda *a, **kw: None,
        get=lambda *a, **kw: None,
        exceptions=make_module(
            "requests.exceptions",
            RequestException=OSError,
            Timeout=OSError,
            ConnectionError=OSError,
        ),
    ),
    "tenacity": make_module(
        "tenacity",
        retry=lambda *a, **kw: lambda f: f,
        stop_after_attempt=lambda *a, **kw: None,
        wait_exponential=lambda *a, **kw: None,
        retry_if_exception_type=lambda *a, **kw: None,
    ),
    "dotenv": make_module("dotenv", load_dotenv=lambda *a, **kw: None),
    "fastapi": make_module(
        "fastapi",
        FastAPI=Framework,
        Request=object,
        Query=lambda default=None, **kw: default,
        HTTPException=Exception,
    ),
    "fastapi.responses": make_module(
        "fastapi.responses",
        HTMLResponse=DummyResponse,
        RedirectResponse=DummyResponse,
        JSONResponse=DummyResponse,
    ),
    "db": make_module(
        "db",
        store_dropbox_tokens=Mock(),
        get_dropbox_tokens=Mock(),
        update_dropbox_tokens=Mock(),
        delete_dropbox_tokens=Mock(),
        store_oauth_state=Mock(),
        get_oauth_state=Mock(),
        delete_oauth_state=Mock(),
        get_user_settings=Mock(),
        store_user_settings=Mock(),
    ),
    "models": make_module("models", Conversation=dict, EndpointResponse=EndpointResponseStub),
}

active_stubs = {k: v for k, v in stubs.items() if k not in sys.modules}

spec = importlib.util.spec_from_file_location(
    "dropbox_err_test", Path(__file__).with_name("main.py")
)
dropbox_main = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, active_stubs):
    spec.loader.exec_module(dropbox_main)


class FakeRequest:
    def __init__(self, body=None, raw_body=b""):
        self._body = body or {}
        self._raw_body = raw_body

    async def json(self):
        return self._body

    async def body(self):
        return self._raw_body


class DropboxErrorSanitizationTests(unittest.TestCase):
    """Verify that unexpected exceptions return sanitized error strings without leaking internal state."""

    def test_auth_callback_exception_sanitized(self):
        with patch.object(dropbox_main, "get_oauth_state", return_value="u1:secret"):
            with patch.object(dropbox_main.requests, "post", side_effect=RuntimeError("db connection failed: postgresql://secret")):
                res = asyncio.run(dropbox_main.auth_callback(code="test_code", state="u1:secret"))
                self.assertEqual(res.status_code, 500)
                self.assertEqual(res.content, "Error during authorization")
                self.assertNotIn("postgresql", str(res.content))

    def test_tool_search_dropbox_exception_sanitized(self):
        req = FakeRequest({"uid": "u1", "query": "test"})
        with patch.object(dropbox_main, "get_valid_access_token", side_effect=RuntimeError("internal crash in token vault")):
            res = asyncio.run(dropbox_main.tool_search_dropbox(req))
            self.assertEqual(res, {"error": "Search error"})
            self.assertNotIn("token vault", str(res))

    def test_tool_list_dropbox_exception_sanitized(self):
        req = FakeRequest({"uid": "u1", "path": "/test"})
        with patch.object(dropbox_main, "get_valid_access_token", side_effect=RuntimeError("internal crash in token vault")):
            res = asyncio.run(dropbox_main.tool_list_dropbox(req))
            self.assertEqual(res, {"error": "List error"})
            self.assertNotIn("token vault", str(res))

    def test_tool_read_dropbox_file_exception_sanitized(self):
        req = FakeRequest({"uid": "u1", "path": "/test.txt"})
        with patch.object(dropbox_main, "get_valid_access_token", side_effect=RuntimeError("internal crash in token vault")):
            res = asyncio.run(dropbox_main.tool_read_dropbox_file(req))
            self.assertEqual(res, {"error": "Read error"})
            self.assertNotIn("token vault", str(res))

    def test_receive_audio_exception_sanitized(self):
        req = Mock()
        req.body = AsyncMock(side_effect=RuntimeError("internal buffer overflow in audio pipeline"))
        res = asyncio.run(dropbox_main.receive_audio(req, uid="u1"))
        self.assertEqual(res, {"status": "error", "message": "Failed to process audio"})
        self.assertNotIn("buffer overflow", str(res))


if __name__ == "__main__":
    unittest.main(verbosity=2)
