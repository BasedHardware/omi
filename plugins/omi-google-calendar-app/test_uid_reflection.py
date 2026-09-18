"""Hermetic tests: setup and OAuth-callback pages must not reflect input raw.

Two unauthenticated routes on this plugin render client-controlled values into
HTML with no encoding:

* `GET /auth/google/callback?error=...` puts `error` straight into `<p>{error}</p>`.
* `GET /?uid=...` puts `uid` into href attributes and a hidden input `value=`.

Framework-only stubs (fastapi, dotenv, requests, db, models); the real async
handlers are driven. No network, no third-party packages.
"""

import asyncio
import html
import sys
import types
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent

BREAKOUT = '"><script>alert(1)</script>'
QUERY_BREAKER = 'a&b#c'


class _Captured:
    """Stands in for fastapi.responses.*; keeps the rendered body."""

    def __init__(self, content=None, status_code=200, url=None, **kwargs):
        self.body = content if content is not None else (url or "")
        self.status_code = status_code
        self.url = url


def _load_main():
    saved = {
        name: sys.modules.get(name)
        for name in ("requests", "dotenv", "fastapi", "fastapi.responses", "db", "models", "main")
    }

    sys.modules["requests"] = types.ModuleType("requests")

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    fastapi = types.ModuleType("fastapi")

    class _App:
        def __init__(self, *a, **k):
            pass

        def _decorator(self, *a, **k):
            def wrap(fn):
                return fn
            return wrap

        get = post = put = delete = on_event = middleware = _decorator

    fastapi.FastAPI = _App
    fastapi.Query = lambda default=None, **k: default
    fastapi.Request = object
    fastapi.HTTPException = type("HTTPException", (Exception,), {})
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _Captured
    responses.RedirectResponse = _Captured
    responses.JSONResponse = _Captured
    fastapi.responses = responses
    sys.modules["fastapi.responses"] = responses

    db = types.ModuleType("db")
    for name in (
        "store_google_tokens", "update_google_tokens", "delete_google_tokens",
        "store_oauth_state", "get_oauth_state", "delete_oauth_state",
        "store_user_setting",
    ):
        setattr(db, name, lambda *a, **k: None)
    db.get_google_tokens = lambda uid: None   # drives the disconnected branch
    db.get_user_setting = lambda *a, **k: None
    sys.modules["db"] = db

    models = types.ModuleType("models")
    models.ChatToolResponse = type("ChatToolResponse", (), {"__init__": lambda self, **k: None})
    sys.modules["models"] = models

    sys.path.insert(0, str(APP_ROOT))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("main", APP_ROOT / "main.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["main"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(APP_ROOT))
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


MAIN = _load_main()


def _body(coro):
    result = asyncio.run(coro)
    return getattr(result, "body", result)


class CallbackErrorReflectionTest(unittest.TestCase):
    """GET /auth/google/callback?error=... — unauthenticated, no state needed."""

    def test_error_is_not_reflected_raw(self) -> None:
        body = _body(MAIN.google_callback(code=None, state=None, error=BREAKOUT))
        self.assertNotIn(BREAKOUT, body)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn(html.escape(BREAKOUT), body)

    def test_ordinary_error_still_shown(self) -> None:
        body = _body(MAIN.google_callback(code=None, state=None, error="access_denied"))
        self.assertIn("access_denied", body)


class UidReflectionTest(unittest.TestCase):
    """GET /?uid=... — the disconnected branch renders for any uid."""

    def test_uid_is_not_reflected_raw(self) -> None:
        body = _body(MAIN.root(uid=BREAKOUT))
        self.assertNotIn(BREAKOUT, body)
        self.assertNotIn("<script>alert(1)</script>", body)

    def test_uid_query_separators_do_not_corrupt_the_link(self) -> None:
        body = _body(MAIN.root(uid=QUERY_BREAKER))
        self.assertNotIn("uid=a&b#c", body)
        self.assertIn("uid=a%26b%23c", body)

    def test_ordinary_uid_still_renders(self) -> None:
        body = _body(MAIN.root(uid="abc123"))
        self.assertIn("/auth/google?uid=abc123", body)


if __name__ == "__main__":
    unittest.main()
