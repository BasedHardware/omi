"""Hermetic regression: six plugins reflect the client-controlled `uid`
query param into HTML `href` attributes and fetch() URLs unencoded, e.g.
auth_url = f"/auth/whoop?uid={uid}" inside <a href="{auth_url}">.
A uid containing a double quote breaks the attribute (HTML injection).

The suite loads each plugin's main.py with stubbed framework/db imports,
drives the real `root` handler down the not-connected branch, and asserts
the uid arrives percent-encoded inside the href.

Run: python3 plugins/test_uid_reflection.py
"""

import asyncio
import contextlib
import inspect
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

PLUGINS_DIR = Path(__file__).resolve().parent

# plugin dir -> (attribute on the loaded module that gates the connect page,
#                patched to a falsy value so root() renders the auth link)
PLUGINS = {
    "omi-whoop-app": ("get_whoop_tokens", None),
    "omi-twitter-chat-tools-app": ("get_twitter_tokens", None),
    "omi-github-app": ("SimpleUserStorage", "get_user"),
    "omi-notion-app": ("get_notion_tokens", None),
    "omi-clickup-app": ("SimpleUserStorage", "get_user"),
    "omi-slack-app": ("SimpleUserStorage", "get_user"),
}

HOSTILE_UID = 'x" onmouseover="alert(1)&admin=1'


def _decorator(*args, **kwargs):
    return lambda fn: fn


def _permissive(name):
    module = types.ModuleType(name)

    def _missing(attr):
        return mock.MagicMock(name=f"{name}.{attr}")

    module.__getattr__ = _missing
    return module


def _load_plugin(plugin_dir):
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

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *a, **k: mock.Mock()
    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = lambda *a, **k: None
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None

    stubs = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "fastapi.templating": templating,
        "fastapi.staticfiles": staticfiles,
        "dotenv": dotenv,
    }
    for name in (
        "db", "models", "requests", "httpx", "simple_storage", "github_client",
        "issue_detector", "agent_providers", "clickup_client", "task_detector",
        "omi_notifications", "slack_client", "message_detector", "uvicorn",
    ):
        stubs[name] = _permissive(name)

    main_path = PLUGINS_DIR / plugin_dir / "main.py"
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(
            f"{plugin_dir.replace('-', '_')}_under_test", main_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _connect_page(module, gate, uid):
    """Run root() with the token gate forced falsy -> connect/auth page."""
    attr, sub = gate
    if sub is None:
        patcher = mock.patch.object(module, attr, lambda *a, **k: None)
    else:
        patcher = mock.patch.object(getattr(module, attr), sub, lambda *a, **k: None)
    with patcher:
        return asyncio.run(module.root(uid=uid))


def test_uid_cannot_break_out_of_href():
    for plugin_dir, gate in PLUGINS.items():
        module = _load_plugin(plugin_dir)
        html = _connect_page(module, gate, HOSTILE_UID)
        assert isinstance(html, str), f"{plugin_dir}: connect page is not HTML"
        assert '" onmouseover=' not in html, f"{plugin_dir}: attribute injection survived"
        assert "%22" in html, f"{plugin_dir}: uid not percent-encoded in page"
        assert "/auth" in html, f"{plugin_dir}: auth link missing"


def test_normal_uid_still_links():
    for plugin_dir, gate in PLUGINS.items():
        module = _load_plugin(plugin_dir)
        html = _connect_page(module, gate, "user_123")
        assert "uid=user_123" in html, f"{plugin_dir}: normal uid missing"


# plugin dir -> OAuth callback handler that also reflects uid into
# success/retry href links.
CALLBACKS = {
    "omi-whoop-app": "whoop_callback",
    "omi-twitter-chat-tools-app": "twitter_callback",
    "omi-github-app": "auth_callback",
    "omi-notion-app": "notion_callback",
    "omi-clickup-app": "auth_callback",
    "omi-slack-app": "auth_callback",
}


class _FakeResp:
    status_code = 200
    text = "ok"

    def json(self):
        return {
            "access_token": "tok123",
            "refresh_token": "ref123",
            "expires_in": 3600,
            "data": {"username": "u", "id": "1"},
        }


def _drive_callback(module, plugin_dir, uid):
    """Run the plugin's OAuth callback with a seeded valid state and a
    successful token exchange, so the uid-bearing success page renders."""
    cb = getattr(module, CALLBACKS[plugin_dir])
    patches = []
    if plugin_dir in ("omi-github-app", "omi-clickup-app", "omi-slack-app"):
        module.oauth_states["st"] = uid
        state = "st"
    else:
        # notion/twitter derive uid as state.split(":")[0]; whoop resolves
        # it via get_uid_from_oauth_state (patched below).
        state = f"{uid}:nonce"
    if plugin_dir == "omi-whoop-app":
        patches.append(mock.patch.object(module, "get_uid_from_oauth_state", lambda s: uid))
    if plugin_dir in ("omi-notion-app", "omi-twitter-chat-tools-app"):
        patches.append(mock.patch.object(module, "get_oauth_state", lambda u: state))
    req = getattr(module, "requests", None)
    if req is not None:
        patches.append(mock.patch.object(req, "post", lambda *a, **k: _FakeResp()))
        patches.append(mock.patch.object(req, "get", lambda *a, **k: _FakeResp()))
    kwargs = {"code": "code123", "state": state}
    if "request" in inspect.signature(cb).parameters:
        kwargs["request"] = None
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return asyncio.run(cb(**kwargs))


def test_callback_encodes_uid_after_state_lookup():
    for plugin_dir in CALLBACKS:
        module = _load_plugin(plugin_dir)
        html = _drive_callback(module, plugin_dir, HOSTILE_UID)
        assert isinstance(html, str), f"{plugin_dir}: callback did not return HTML"
        assert '" onmouseover=' not in html, f"{plugin_dir}: raw uid reflected in callback"
        assert "&admin=1" not in html, f"{plugin_dir}: raw uid reflected in callback"
        assert "%22" in html, f"{plugin_dir}: encoded uid missing from callback page"


def test_callback_rejects_unknown_state():
    """Invalid-state early returns must not reference the unassigned uid_q."""
    for plugin_dir, cb_name in CALLBACKS.items():
        module = _load_plugin(plugin_dir)
        patches = []
        if plugin_dir == "omi-whoop-app":
            patches.append(mock.patch.object(module, "get_uid_from_oauth_state", lambda s: None))
        if plugin_dir in ("omi-notion-app", "omi-twitter-chat-tools-app"):
            patches.append(mock.patch.object(module, "get_oauth_state", lambda u: None))
        cb = getattr(module, cb_name)
        kwargs = {"code": "c", "state": "never-registered"}
        if "request" in inspect.signature(cb).parameters:
            kwargs["request"] = None
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            html = asyncio.run(cb(**kwargs))
        assert isinstance(html, str), f"{plugin_dir}: invalid-state path crashed"


def test_github_uid_js_escapes_script_close():
    module = _load_plugin("omi-github-app")
    uid = '</script><script>alert(1)</script>'
    with mock.patch.object(
        module.SimpleUserStorage, "get_user", lambda *a, **k: {"access_token": "t"}
    ):
        html = asyncio.run(module.root(uid=uid))
    assert isinstance(html, str)
    assert "<script>alert(1)" not in html, "uid broke out of the script block"
    assert "\\u003c" in html, "uid_js not unicode-escaped"


def test_slack_dev_page_encodes_uid_in_fetch_urls():
    """The dev test page builds fetch() URLs from a DOM uid — every one
    must go through encodeURIComponent, never a raw ${uid} interpolation."""
    module = _load_plugin("omi-slack-app")
    html = asyncio.run(module.test_interface(uid="user_123", dev="true"))
    assert isinstance(html, str)
    assert "${encodeURIComponent(uid)}" in html, "encoded uid interpolation missing"
    assert "${uid}" not in html, "raw uid interpolation survived in fetch URL"


if __name__ == "__main__":
    tests = [
        test_uid_cannot_break_out_of_href,
        test_normal_uid_still_links,
        test_callback_encodes_uid_after_state_lookup,
        test_callback_rejects_unknown_state,
        test_github_uid_js_escapes_script_close,
        test_slack_dev_page_encodes_uid_in_fetch_urls,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)}/{len(tests)} tests passed")
