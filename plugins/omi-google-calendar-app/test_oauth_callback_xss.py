"""Hermetic regression test for reflected XSS in /auth/google/callback.

main.py imports fastapi, pydantic (via models.py), requests, and dotenv at
load time. None of them are used for real I/O by the code path under test —
the callback function just builds an HTML string — so stub all four during
import, the same pattern as the sibling plugin suites, and this file runs on
a stdlib-only interpreter.

Covers two reflected values in google_callback() that were interpolated into
HTML with no escaping:

1. `error` — Google forwards this query param verbatim from the authorize
   request, and this branch returns before any state/session check exists,
   so `?error=<script>...</script>` was a zero-interaction reflected XSS.
2. `uid` — the first segment of `state`, itself minted from the `uid` query
   param on /auth/google; an attacker's own uid survives a real OAuth round
   trip (a victim who approves consent completes it for them) and landed
   inside an unescaped href attribute on the success page.
"""

import asyncio
from pathlib import Path
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch


def _install_stubs():
    fastapi_mod = types.ModuleType("fastapi")

    class _FakeFastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco

        def post(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco

        def exception_handler(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco

    def _Query(default=None, *args, **kwargs):
        return default

    class _HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi_mod.FastAPI = _FakeFastAPI
    fastapi_mod.Request = object
    fastapi_mod.Query = _Query
    fastapi_mod.HTTPException = _HTTPException

    fastapi_responses = types.ModuleType("fastapi.responses")

    class _Response:
        def __init__(self, content=None, status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code

    fastapi_responses.HTMLResponse = _Response
    fastapi_responses.RedirectResponse = _Response
    fastapi_responses.JSONResponse = _Response
    fastapi_mod.responses = fastapi_responses

    pydantic_mod = types.ModuleType("pydantic")

    class _BaseModel:
        pass

    pydantic_mod.BaseModel = _BaseModel

    requests_mod = types.ModuleType("requests")
    requests_mod.get = requests_mod.post = lambda *a, **k: None

    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *args, **kwargs: None

    return {
        "fastapi": fastapi_mod,
        "fastapi.responses": fastapi_responses,
        "pydantic": pydantic_mod,
        "requests": requests_mod,
        "dotenv": dotenv_mod,
    }


MODULE_PATH = Path(__file__).with_name("main.py")
spec = importlib.util.spec_from_file_location("google_calendar_main", MODULE_PATH)
main = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, _install_stubs()):
    spec.loader.exec_module(main)

google_callback = main.google_callback


def run(coro):
    return asyncio.run(coro)


class OAuthCallbackXSSTests(unittest.TestCase):
    def test_error_param_is_escaped_in_error_page(self):
        payload = "<script>alert(1)</script>"
        response = run(google_callback(code=None, state=None, error=payload))
        self.assertNotIn(payload, response.content)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", response.content)

    def test_error_param_without_markup_still_renders(self):
        response = run(google_callback(code=None, state=None, error="access_denied"))
        self.assertIn("access_denied", response.content)
        self.assertEqual(response.status_code, 400)

    def test_uid_is_escaped_on_the_success_page(self):
        payload_uid = '"><script>alert(1)</script>'
        state = f"{payload_uid}:tok123"
        # Stub the oauth-state and token store so the test never touches
        # db.py's Redis-or-file storage — the callback's HTML building is
        # what's under test, not persistence.
        with patch.object(main, "get_oauth_state", return_value=state), \
             patch.object(main, "delete_oauth_state"), \
             patch.object(main, "store_google_tokens"), \
             patch.object(main.requests, "post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
            }
            response = run(google_callback(code="authcode", state=state, error=None))
        self.assertNotIn(payload_uid, response.content)
        self.assertIn("&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;", response.content)


if __name__ == "__main__":
    unittest.main()
