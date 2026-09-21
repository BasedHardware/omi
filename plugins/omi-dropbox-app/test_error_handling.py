"""Hermetic error handling and exception sanitization tests for Dropbox App.

Verifies that internal exceptions, system paths, network addresses, and raw
tracebacks never leak into chat tool responses, OAuth responses, or audio handlers.
Runs under standard library unittest without external network dependencies.
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
    def __init__(self, content="", status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.kwargs = kwargs

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class HTTPExceptionStub(Exception):
    def __init__(self, status_code=None, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def make_module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def load_dropbox_module():
    req_exceptions = make_module(
        "requests.exceptions",
        Timeout=Exception,
        ConnectionError=Exception,
        RequestException=OSError,
    )
    stubs = {
        "requests": make_module(
            "requests",
            post=lambda *args, **kwargs: None,
            get=lambda *args, **kwargs: None,
            Response=object,
            RequestException=OSError,
            exceptions=req_exceptions,
        ),
        "requests.exceptions": req_exceptions,
        "tenacity": make_module(
            "tenacity",
            retry=lambda *a, **kw: lambda f: f,
            stop_after_attempt=lambda *a, **kw: None,
            wait_exponential=lambda *a, **kw: None,
            retry_if_exception_type=lambda *a, **kw: None,
        ),
        "dotenv": make_module("dotenv", load_dotenv=lambda *args, **kwargs: None),
        "fastapi": make_module(
            "fastapi",
            FastAPI=Framework,
            Request=Framework,
            Query=lambda default=None, **kw: default,
            HTTPException=HTTPExceptionStub,
        ),
        "fastapi.responses": make_module(
            "fastapi.responses",
            HTMLResponse=Framework,
            RedirectResponse=Framework,
            JSONResponse=Framework,
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
        "models": make_module(
            "models",
            Conversation=dict,
            EndpointResponse=lambda message="": {"message": message},
        ),
    }

    spec = importlib.util.spec_from_file_location(
        "dropbox_main_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_dropbox_module()


class FakeChatRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body

    async def body(self):
        return b"fake_audio_bytes"


class DropboxErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/dropbox_token.json: connection reset by 192.168.1.55:443"

    async def test_auth_dropbox_sanitizes_exception(self):
        with patch.object(app, "store_oauth_state", side_effect=RuntimeError(self.sensitive_leak)):
            with self.assertRaises(app.HTTPException) as ctx:
                await app.auth_dropbox(uid="user123")
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "OAuth initialization failed")
            self.assertNotIn(self.sensitive_leak, ctx.exception.detail)
            self.assertNotIn("192.168.1.55", ctx.exception.detail)

    async def test_auth_callback_sanitizes_failed_token_exchange(self):
        with patch.object(app, "get_oauth_state", return_value="user123:state123"):
            mock_resp = Mock()
            mock_resp.status_code = 400
            mock_resp.text = f"Internal Upstream Error: {self.sensitive_leak}"
            with patch.object(app.requests, "post", return_value=mock_resp):
                resp = await app.auth_callback(code="bad_code", state="user123:state123")
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.content, "Token exchange failed")
                self.assertNotIn(self.sensitive_leak, str(resp.content))

    async def test_auth_callback_sanitizes_unexpected_exception(self):
        with patch.object(app, "get_oauth_state", return_value="user123:state123"):
            with patch.object(app.requests, "post", side_effect=RuntimeError(self.sensitive_leak)):
                resp = await app.auth_callback(code="auth_code", state="user123:state123")
                self.assertEqual(resp.status_code, 500)
                self.assertEqual(resp.content, "Error during authorization")
                self.assertNotIn(self.sensitive_leak, str(resp.content))

    async def test_tool_search_dropbox_sanitizes_client_error(self):
        req = FakeChatRequest({"uid": "user123", "query": "notes"})
        with patch.object(app, "get_valid_access_token", return_value="fake_tok"):
            with patch.object(app.DropboxClient, "search_files", return_value=(None, self.sensitive_leak)):
                res = await app.tool_search_dropbox(req)
                self.assertEqual(res, {"error": "Failed to search files."})
                self.assertNotIn(self.sensitive_leak, str(res))

    async def test_tool_search_dropbox_sanitizes_unexpected_exception(self):
        req = FakeChatRequest({"uid": "user123", "query": "notes"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            res = await app.tool_search_dropbox(req)
            self.assertEqual(res, {"error": "Failed to search files due to an internal error."})
            self.assertNotIn(self.sensitive_leak, str(res))

    async def test_tool_list_dropbox_sanitizes_client_error(self):
        req = FakeChatRequest({"uid": "user123", "folder": "/docs"})
        with patch.object(app, "get_valid_access_token", return_value="fake_tok"):
            with patch.object(app.DropboxClient, "list_folder", return_value=(None, self.sensitive_leak)):
                res = await app.tool_list_dropbox(req)
                self.assertEqual(res, {"error": "Failed to list folder contents."})
                self.assertNotIn(self.sensitive_leak, str(res))

    async def test_tool_list_dropbox_sanitizes_unexpected_exception(self):
        req = FakeChatRequest({"uid": "user123", "folder": "/docs"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            res = await app.tool_list_dropbox(req)
            self.assertEqual(res, {"error": "Failed to list folder contents due to an internal error."})
            self.assertNotIn(self.sensitive_leak, str(res))

    async def test_tool_read_dropbox_file_sanitizes_client_error(self):
        req = FakeChatRequest({"uid": "user123", "path": "/docs/file.txt"})
        with patch.object(app, "get_valid_access_token", return_value="fake_tok"):
            with patch.object(app.DropboxClient, "download_file", return_value=(None, self.sensitive_leak)):
                res = await app.tool_read_dropbox_file(req)
                self.assertEqual(res, {"error": "Failed to download file."})
                self.assertNotIn(self.sensitive_leak, str(res))

    async def test_tool_read_dropbox_file_sanitizes_unexpected_exception(self):
        req = FakeChatRequest({"uid": "user123", "path": "/docs/file.txt"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            res = await app.tool_read_dropbox_file(req)
            self.assertEqual(res, {"error": "Failed to read file due to an internal error."})
            self.assertNotIn(self.sensitive_leak, str(res))

    async def test_tool_read_dropbox_pdf_sanitizes_extraction_exception(self):
        req = FakeChatRequest({"uid": "user123", "path": "/docs/document.pdf"})
        with patch.object(app, "get_valid_access_token", return_value="fake_tok"):
            with patch.object(app.DropboxClient, "download_file", return_value=(b"%PDF-fake-header", None)):
                fake_pypdf = make_module("pypdf", PdfReader=Mock(side_effect=RuntimeError(self.sensitive_leak)))
                with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
                    res = await app.tool_read_dropbox_file(req)
                    self.assertEqual(res, {"error": "Failed to extract text from PDF."})
                    self.assertNotIn(self.sensitive_leak, str(res))

    async def test_receive_audio_sanitizes_exception(self):
        req = FakeChatRequest({})
        with patch.object(req, "body", side_effect=RuntimeError(self.sensitive_leak)):
            res = await app.receive_audio(req, uid="user123", sample_rate=16000)
            self.assertEqual(res, {"status": "error", "message": "Failed to process audio"})
            self.assertNotIn(self.sensitive_leak, str(res))


if __name__ == "__main__":
    unittest.main()
