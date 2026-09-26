"""Hermetic error-handling regression suite for hume-ai.

Verifies that internal exceptions, unhandled errors, and sensitive system traces
never leak into client HTTP responses or error payloads across Hume AI endpoints.
Uses Python standard library unittest only.

Run: python3 plugins/hume-ai/test_error_handling.py
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

SENTINEL_ERROR = "INTERNAL_DB_DISCONNECTED_AT_10.240.0.1_PASSWORD_LEAK"


def _install_hume_stubs():
    """Stub Hume SDK, httpx, fastapi, and uvicorn so app.py and main.py load offline."""
    hume = types.ModuleType("hume")
    hume.AsyncHumeClient = Mock()
    expression = types.ModuleType("hume.expression_measurement")
    stream = types.ModuleType("hume.expression_measurement.stream")
    stream.StreamLanguage = Mock()
    stream_stream = types.ModuleType("hume.expression_measurement.stream.stream")
    stream_types = types.ModuleType("hume.expression_measurement.stream.stream.types")
    stream_types.Config = Mock()
    hume.expression_measurement = expression
    expression.stream = stream
    stream.stream = stream_stream
    stream_stream.types = stream_types

    httpx = types.ModuleType("httpx")

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            return Mock(status_code=200, text="")

    httpx.AsyncClient = _AsyncClient

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None

    class Framework:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        post = get
        on_event = get

    class _HTTPException(Exception):
        def __init__(self, status_code=500, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _JSONResponse:
        def __init__(self, content=None, status_code=200):
            self.content = content
            self.status_code = status_code

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = Framework
    fastapi.Request = Framework
    fastapi.Query = Framework
    fastapi.HTTPException = _HTTPException

    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.JSONResponse = _JSONResponse
    fastapi_responses.HTMLResponse = Framework

    fastapi_templating = types.ModuleType("fastapi.templating")
    fastapi_templating.Jinja2Templates = Framework

    uvicorn = types.ModuleType("uvicorn")
    uvicorn.run = Mock()

    return {
        "hume": hume,
        "hume.expression_measurement": expression,
        "hume.expression_measurement.stream": stream,
        "hume.expression_measurement.stream.stream": stream_stream,
        "hume.expression_measurement.stream.stream.types": stream_types,
        "httpx": httpx,
        "dotenv": dotenv,
        "fastapi": fastapi,
        "fastapi.responses": fastapi_responses,
        "fastapi.templating": fastapi_templating,
        "uvicorn": uvicorn,
    }


def load_hume_modules():
    """Load plugins/hume-ai/app.py and main.py hermetically."""
    app_path = Path(__file__).resolve().parent / "app.py"
    main_path = Path(__file__).resolve().parent / "main.py"

    stubs = _install_hume_stubs()
    with patch.dict(sys.modules, stubs), patch("builtins.print"):
        # 1. Load app.py
        spec_app = importlib.util.spec_from_file_location("app", app_path)
        app_mod = importlib.util.module_from_spec(spec_app)
        sys.modules["app"] = app_mod
        spec_app.loader.exec_module(app_mod)

        # 2. Load main.py
        spec_main = importlib.util.spec_from_file_location("main", main_path)
        main_mod = importlib.util.module_from_spec(spec_main)
        sys.modules["main"] = main_mod
        spec_main.loader.exec_module(main_mod)

    return app_mod, main_mod


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


class TestHumeErrorHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_mod, cls.main_mod = load_hume_modules()

    def setUp(self):
        patcher = patch("builtins.print")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_text_analysis_error_masks_exception(self):
        """analyze_text_with_hume masks unexpected exceptions."""
        with patch("os.getenv", return_value="fake_key"):
            with patch.object(self.app_mod, "AsyncHumeClient", side_effect=Exception(SENTINEL_ERROR)):
                res = asyncio.run(self.app_mod.analyze_text_with_hume("hello"))
                self.assertFalse(res.get("success"))
                self.assertIn("error", res)
                self.assertNotIn(SENTINEL_ERROR, res["error"])
                self.assertEqual(res["error"], "Hume text analysis failed")

    def test_audio_analysis_error_masks_exception(self):
        """analyze_audio_with_hume masks unexpected exceptions."""
        with patch("os.getenv", return_value="fake_key"):
            with patch("wave.open", side_effect=Exception(SENTINEL_ERROR)):
                res = asyncio.run(self.app_mod.analyze_audio_with_hume("fake.wav"))
                self.assertFalse(res.get("success"))
                self.assertIn("error", res)
                self.assertNotIn(SENTINEL_ERROR, res["error"])
                self.assertEqual(res["error"], "Hume audio analysis failed")

    def test_single_audio_analysis_error_masks_exception(self):
        """_analyze_single_audio masks unexpected exceptions."""
        with patch.object(self.app_mod, "AsyncHumeClient", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app_mod._analyze_single_audio("fake.wav", "fake_key"))
            self.assertFalse(res.get("success"))
            self.assertIn("error", res)
            self.assertNotIn(SENTINEL_ERROR, res["error"])
            self.assertEqual(res["error"], "Hume audio analysis failed")

    def test_endpoint_analyze_text_error_masks_exception(self):
        """POST /analyze-text masks unexpected internal exceptions."""
        req = FakeRequest({"text": "test phrase"})
        with patch.object(self.main_mod, "analyze_text_with_hume", side_effect=Exception(SENTINEL_ERROR)):
            with self.assertRaises(self.main_mod.HTTPException) as ctx:
                asyncio.run(self.main_mod.analyze_text_emotion(req))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertNotIn(SENTINEL_ERROR, str(ctx.exception.detail))
            self.assertEqual(ctx.exception.detail, "Internal server error")

    def test_endpoint_emotion_config_error_masks_exception(self):
        """POST /emotion-config masks unexpected internal exceptions."""
        req = FakeRequest({"notification_enabled": True, "emotion_thresholds": {"admiration": 0.5}})
        with patch("builtins.open", side_effect=Exception(SENTINEL_ERROR)):
            with self.assertRaises(self.main_mod.HTTPException) as ctx:
                asyncio.run(self.main_mod.update_emotion_config(req))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertNotIn(SENTINEL_ERROR, str(ctx.exception.detail))
            self.assertEqual(ctx.exception.detail, "Failed to update configuration")

    def test_endpoint_reset_stats_error_masks_exception(self):
        """POST /reset-stats masks unexpected internal exceptions."""
        req = FakeRequest({"confirm": True})
        call_count = 0

        def raise_once(*a, **k):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception(SENTINEL_ERROR)

        with patch("builtins.print", side_effect=raise_once):
            with self.assertRaises(self.main_mod.HTTPException) as ctx:
                asyncio.run(self.main_mod.reset_stats(req))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertNotIn(SENTINEL_ERROR, str(ctx.exception.detail))
            self.assertEqual(ctx.exception.detail, "Failed to reset statistics")


if __name__ == "__main__":
    unittest.main()
