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


if __name__ == "__main__":
    tests = [test_uid_cannot_break_out_of_href, test_normal_uid_still_links]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)}/{len(tests)} tests passed")
