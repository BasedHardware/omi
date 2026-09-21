"""Hermetic unit tests: prevent sensitive exception details and stack traces
from leaking into client HTTP responses and JSON payloads in hume-ai plugin.

Run: python plugins/hume-ai/test_hume_hardening.py
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import asyncio
import importlib.util
import types
from pathlib import Path
from unittest import mock, TestCase

PLUGIN_DIR = Path(__file__).resolve().parent
APP_PATH = PLUGIN_DIR / "app.py"
MAIN_PATH = PLUGIN_DIR / "main.py"


def _install_stubs():
    """Install minimal stubs so hume-ai app.py and main.py can be tested offline."""
    # Stub hume
    hume = types.ModuleType("hume")
    hume.AsyncHumeClient = mock.Mock()
    expression = types.ModuleType("hume.expression_measurement")
    stream = types.ModuleType("hume.expression_measurement.stream")
    stream.StreamLanguage = mock.Mock()
    stream_stream = types.ModuleType("hume.expression_measurement.stream.stream")
    stream_types = types.ModuleType("hume.expression_measurement.stream.stream.types")
    stream_types.Config = mock.Mock()
    hume.expression_measurement = expression
    expression.stream = stream
    stream.stream = stream_stream
    stream_stream.types = stream_types

    # Stub httpx
    httpx = types.ModuleType("httpx")

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("Database connection string leaked: postgresql://admin:secret@db.internal:5432/omi")

    httpx.AsyncClient = _AsyncClient

    # Stub dotenv
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = mock.Mock()

    # Stub uvicorn
    uvicorn = types.ModuleType("uvicorn")

    # Stub fastapi
    fastapi = types.ModuleType("fastapi")
    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"{status_code}: {detail}")

    fastapi.HTTPException = HTTPException

    def _passthrough_decorator(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    class FakeFastAPI:
        def __init__(self, *args, **kwargs):
            pass
        def post(self, *args, **kwargs):
            return _passthrough_decorator(*args, **kwargs)
        def get(self, *args, **kwargs):
            return _passthrough_decorator(*args, **kwargs)
        def on_event(self, *args, **kwargs):
            return _passthrough_decorator(*args, **kwargs)

    fastapi.FastAPI = FakeFastAPI
    fastapi.Request = mock.Mock()
    fastapi.Query = lambda default=None, **kwargs: default
    fastapi_resp = types.ModuleType("fastapi.responses")
    fastapi_resp.JSONResponse = mock.Mock()
    fastapi_resp.HTMLResponse = mock.Mock()
    fastapi_tpl = types.ModuleType("fastapi.templating")
    fastapi_tpl.Jinja2Templates = mock.Mock()

    modules = {
        "hume": hume,
        "hume.expression_measurement": expression,
        "hume.expression_measurement.stream": stream,
        "hume.expression_measurement.stream.stream": stream_stream,
        "hume.expression_measurement.stream.stream.types": stream_types,
        "httpx": httpx,
        "dotenv": dotenv,
        "uvicorn": uvicorn,
        "fastapi": fastapi,
        "fastapi.responses": fastapi_resp,
        "fastapi.templating": fastapi_tpl,
    }
    for name, mod in modules.items():
        sys.modules[name] = mod


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestHumeExceptionSanitization(TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stubs()
        cls.app_mod = _load_module("hume_app_mod", APP_PATH)
        cls.main_mod = _load_module("hume_main_mod", MAIN_PATH)

    def test_send_omi_notification_does_not_leak_exception(self):
        result = asyncio.run(self.app_mod.send_omi_notification(
            uid="user-123",
            message="Test message",
            app_id="app-1",
            api_key="secret-key"
        ))
        self.assertFalse(result["success"])
        self.assertNotIn("Database connection string leaked", result["error"])
        self.assertNotIn("secret@", result["error"])
        self.assertEqual(result["error"], "Failed to send Omi notification")

    def test_create_omi_memory_does_not_leak_exception(self):
        result = asyncio.run(self.app_mod.create_omi_memory(
            uid="user-123",
            text="Calm day",
            app_id="app-1",
            api_key="secret-key"
        ))
        self.assertFalse(result["success"])
        self.assertNotIn("Database connection string leaked", result["error"])
        self.assertNotIn("secret@", result["error"])
        self.assertEqual(result["error"], "Failed to create Omi memory")

    def test_analyze_text_with_hume_does_not_leak_exception(self):
        with mock.patch.dict("os.environ", {"HUME_API_KEY": "dummy_key"}), \
             mock.patch.object(self.app_mod, "AsyncHumeClient", side_effect=Exception("API key secret-xyz invalid")):
            result = asyncio.run(self.app_mod.analyze_text_with_hume("test text"))
            self.assertFalse(result["success"])
            self.assertNotIn("secret-xyz", result["error"])
            self.assertEqual(result["error"], "Hume text analysis failed.")
            self.assertEqual(result["predictions"], [])

    def test_analyze_audio_with_hume_does_not_leak_exception(self):
        with mock.patch.dict("os.environ", {"HUME_API_KEY": "dummy_key"}), \
             mock.patch("wave.open", side_effect=Exception("Internal filesystem failure")):
            result = asyncio.run(self.app_mod.analyze_audio_with_hume("dummy.wav"))
            self.assertFalse(result["success"])
            self.assertNotIn("filesystem failure", result["error"])
            self.assertEqual(result["error"], "Audio chunking failed.")
            self.assertEqual(result["predictions"], [])

    def test_analyze_single_audio_does_not_leak_exception(self):
        with mock.patch.object(self.app_mod, "AsyncHumeClient", side_effect=Exception("Hume server socket timeout")):
            result = asyncio.run(self.app_mod._analyze_single_audio("dummy.wav", "key"))
            self.assertFalse(result["success"])
            self.assertNotIn("socket timeout", result["error"])
            self.assertEqual(result["error"], "Audio analysis failed.")
            self.assertEqual(result["predictions"], [])

    def test_main_analyze_text_emotion_does_not_leak_exception(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(return_value={"text": "hello", "uid": "user1"})

        with mock.patch.object(self.main_mod, "analyze_text_with_hume", side_effect=Exception("Sensitive DB error")):
            with self.assertRaises(self.main_mod.HTTPException) as ctx:
                asyncio.run(self.main_mod.analyze_text_emotion(req))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertNotIn("Sensitive DB error", ctx.exception.detail)
            self.assertEqual(ctx.exception.detail, "Internal server error occurred while analyzing text.")

    def test_main_handle_audio_stream_does_not_leak_exception(self):
        req = mock.Mock()
        req.body = mock.AsyncMock(side_effect=Exception("File buffer read failed /root/secret"))

        with self.assertRaises(self.main_mod.HTTPException) as ctx:
            asyncio.run(self.main_mod.handle_audio_stream(request=req, sample_rate=16000, uid="user1"))
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertNotIn("secret", ctx.exception.detail)
        self.assertEqual(ctx.exception.detail, "Internal server error occurred while processing audio.")

    def test_main_update_emotion_config_does_not_leak_exception(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=Exception("Invalid JSON payload memory dump"))

        with self.assertRaises(self.main_mod.HTTPException) as ctx:
            asyncio.run(self.main_mod.update_emotion_config(req))
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertNotIn("memory dump", ctx.exception.detail)
        self.assertEqual(ctx.exception.detail, "Failed to update configuration.")

    def test_main_reset_stats_does_not_leak_exception(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=Exception("State lock failure"))

        with self.assertRaises(self.main_mod.HTTPException) as ctx:
            asyncio.run(self.main_mod.reset_stats(req))
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertNotIn("State lock failure", ctx.exception.detail)
        self.assertEqual(ctx.exception.detail, "Failed to reset statistics.")


if __name__ == "__main__":
    import unittest
    unittest.main()
