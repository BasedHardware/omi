"""Hermetic regression tests: setup and OAuth-callback pages must not reflect input raw.

Tests:
- /setup/ms365?uid=...: uid must be percent-encoded and attribute-escaped so
  XSS payloads, quote-breakouts, and query delimiters (&, #) cannot corrupt the link.
- /auth/microsoft/callback?error=...&error_description=...: error and
  error_description must be HTML-escaped to prevent reflected XSS.

Run: python plugins/omi-ms365-app/test_ms365_security.py
"""

import asyncio
import html
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

MAIN_PATH = Path(__file__).resolve().parent / "main.py"


def _module(name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    return module


def load_handlers():
    """Load setup_page and auth_callback from main.py with lightweight framework stubs."""
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class HTMLResponse:
        def __init__(self, content="", status_code=200):
            self.body = content
            self.status_code = status_code

    class JSONResponse:
        def __init__(self, content=None, status_code=200):
            self.content = content
            self.status_code = status_code

    class RedirectResponse:
        def __init__(self, url="", status_code=307):
            self.url = url
            self.status_code = status_code

    class HTTPException(Exception):
        def __init__(self, status_code, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class Serializer:
        def __init__(self, *args, **kwargs):
            pass

        def dumps(self, obj):
            return "dummy-state"

        def loads(self, s):
            return {"uid": "test-uid"}

    class AnyHandlers(ModuleType):
        def __getattr__(self, name):
            async def handler(user_id=None, **kwargs):
                return {}
            return handler

    services = _module("services")
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        setattr(services, name, AnyHandlers(f"services.{name}"))

    services.auth.AuthError = Exception
    services.auth.build_auth_url = lambda state: "https://login.microsoft.com"
    services.auth.exchange_code_for_token = lambda code, uid: None

    settings = SimpleNamespace(log_level="INFO", session_secret="secret", app_base_url="http://plugin")

    stubs = {
        "fastapi": _module(
            "fastapi",
            FastAPI=FastAPI,
            HTTPException=HTTPException,
            Query=lambda default=None, **kwargs: default,
            Request=object,
        ),
        "fastapi.responses": _module(
            "fastapi.responses",
            HTMLResponse=HTMLResponse,
            JSONResponse=JSONResponse,
            RedirectResponse=RedirectResponse,
        ),
        "itsdangerous": _module(
            "itsdangerous",
            URLSafeSerializer=Serializer,
            BadSignature=Exception,
        ),
        "config": _module("config", get_settings=lambda: settings),
        "services": services,
    }
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        stubs[f"services.{name}"] = getattr(services, name)

    spec = importlib.util.spec_from_file_location("main_security_test", MAIN_PATH)
    main_mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(main_mod)
    return main_mod.setup_page, main_mod.auth_callback


class TestMS365Security(unittest.TestCase):
    setup_page = None
    auth_callback = None

    @classmethod
    def setUpClass(cls):
        sp, ac = load_handlers()
        cls.setup_page = staticmethod(sp)
        cls.auth_callback = staticmethod(ac)

    def test_setup_page_normal_uid(self):
        body = asyncio.run(self.setup_page(uid="alice123"))
        self.assertIn('/auth/microsoft?uid=alice123', body)
        self.assertIn('Connect with Microsoft', body)

    def test_setup_page_quote_and_script_injection(self):
        payload = '"><script>alert("xss")</script>'
        body = asyncio.run(self.setup_page(uid=payload))
        # Raw unescaped breakout must not appear
        self.assertNotIn(payload, body)
        self.assertNotIn('<script>alert("xss")</script>', body)
        # Percent-encoded form must be present inside href
        self.assertIn('%22%3E%3Cscript%3Ealert%28%22xss%22%29%3C%2Fscript%3E', body)

    def test_setup_page_query_delimiters(self):
        payload = 'user123&admin=true#frag'
        body = asyncio.run(self.setup_page(uid=payload))
        self.assertNotIn('uid=user123&admin=true', body)
        self.assertIn('uid=user123%26admin%3Dtrue%23frag', body)

    def test_auth_callback_normal_error(self):
        res = asyncio.run(self.auth_callback(error="access_denied", error_description="The user declined consent"))
        self.assertEqual(res.status_code, 400)
        self.assertIn('<h3>Authorization failed</h3>', res.body)
        self.assertIn('<pre>access_denied: The user declined consent</pre>', res.body)

    def test_auth_callback_error_without_description(self):
        res = asyncio.run(self.auth_callback(error="invalid_request", error_description=None))
        self.assertEqual(res.status_code, 400)
        self.assertIn('<pre>invalid_request</pre>', res.body)

    def test_auth_callback_xss_in_error(self):
        payload = '<script>alert("error-xss")</script>'
        res = asyncio.run(self.auth_callback(error=payload, error_description="description"))
        self.assertEqual(res.status_code, 400)
        self.assertNotIn(payload, res.body)
        self.assertIn(html.escape(payload), res.body)

    def test_auth_callback_xss_in_error_description(self):
        payload = '<img src=x onerror=alert(1)>'
        res = asyncio.run(self.auth_callback(error="access_denied", error_description=payload))
        self.assertEqual(res.status_code, 400)
        self.assertNotIn(payload, res.body)
        self.assertIn(html.escape(payload), res.body)


if __name__ == "__main__":
    unittest.main()
