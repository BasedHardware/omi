"""Hermetic regression: omi-twitter-app reflects client-controlled params
into HTML `href` attributes unencoded:

  - GET /            -> auth_url = f"/auth?uid={uid}" inside <a href="{auth_url}">
  - GET /auth/callback -> error_uid = state (raw) inside <a href="/auth?uid={error_uid}">

A uid/state containing a double quote breaks out of the attribute
(HTML/XSS injection); a bare `&` or `#` corrupts the query.

The suite loads the plugin's main_simple.py with stubbed framework/db
imports and drives the real handlers: root() down the personalized-setup
branch, and auth_callback() down the exception branch (token exchange
raises, as it does for any state without a stored OAuth handler).

Run: python3 plugins/test_uid_reflection_twitter.py
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

PLUGINS_DIR = Path(__file__).resolve().parent

HOSTILE_UID = 'x" onmouseover="alert(1)&admin=1'
HOSTILE_STATE = '"><script>alert(1)</script>&x=1#frag'


def _decorator(*args, **kwargs):
    return lambda fn: fn


def _permissive(name):
    module = types.ModuleType(name)

    def _missing(attr):
        return mock.MagicMock(name=f"{name}.{attr}")

    module.__getattr__ = _missing
    return module


def _load_plugin():
    fastapi = types.ModuleType("fastapi")

    class _FastAPI:
        def __init__(self, *a, **k):
            pass

        get = staticmethod(_decorator)
        post = staticmethod(_decorator)
        on_event = staticmethod(_decorator)
        websocket = staticmethod(_decorator)
        mount = staticmethod(lambda *a, **k: None)

    fastapi.FastAPI = _FastAPI
    fastapi.Request = object
    fastapi.Query = lambda default=None, **kw: default
    fastapi.HTTPException = type("HTTPException", (Exception,), {})

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = lambda content=None, **kw: content
    responses.JSONResponse = lambda content=None, **kw: content
    responses.RedirectResponse = lambda url=None, **kw: types.SimpleNamespace(url=url)
    fastapi.responses = responses

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None

    stubs = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "dotenv": dotenv,
    }
    for name in ("simple_storage", "twitter_client", "tweet_detector", "uvicorn"):
        stubs[name] = _permissive(name)

    main_path = PLUGINS_DIR / "omi-twitter-app" / "main_simple.py"
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(
            "omi_twitter_app_under_test", main_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def test_setup_page_uid_cannot_break_out_of_href():
    module = _load_plugin()
    html = asyncio.run(module.root(uid=HOSTILE_UID))
    assert isinstance(html, str), "setup page is not HTML"
    assert '" onmouseover=' not in html, "attribute injection survived on setup page"
    assert "%22" in html, "uid not percent-encoded on setup page"
    assert "/auth?uid=" in html, "auth link missing on setup page"
    assert "%26" in html, "ampersand left raw in uid on setup page"
    assert "&admin=1" not in html, "query param injection survived on setup page"


def test_setup_page_normal_uid_still_links():
    module = _load_plugin()
    html = asyncio.run(module.root(uid="user_123"))
    assert "uid=user_123" in html, "normal uid missing on setup page"


def _callback_error_page(module, state):
    request = types.SimpleNamespace(
        url="https://plugin.example/auth/callback?code=x&state=whatever"
    )

    def _raise(*a, **k):
        raise Exception("OAuth session not found")

    with mock.patch.object(module.twitter_client, "get_access_token", _raise):
        return asyncio.run(module.auth_callback(request=request, state=state, code="x"))


def test_callback_state_cannot_break_out_of_href():
    module = _load_plugin()
    html = _callback_error_page(module, HOSTILE_STATE)
    assert isinstance(html, str), "callback error page is not HTML"
    assert "<script>alert(1)</script>" not in html, "script tag reflected raw in error page"
    assert "%22%3E%3Cscript%3E" in html, "state not percent-encoded in error page"
    assert "/auth?uid=" in html, "retry link missing in error page"
    assert "&x=1" not in html, "query param injection survived in error page"
    assert "#frag" not in html, "fragment injection survived in error page"


def test_callback_state_with_ampersand_still_links():
    module = _load_plugin()
    html = _callback_error_page(module, "abc&x=1")
    assert "uid=abc%26x%3D1" in html, "benign & should be encoded, link must stay intact"


def test_callback_missing_state_falls_back_to_unknown():
    module = _load_plugin()
    html = _callback_error_page(module, None)
    assert "uid=unknown" in html, "missing state should fall back to 'unknown'"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
