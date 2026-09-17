"""Hermetic regression tests: the manual import app must post extracted
memories to the Integration Import API route the backend actually serves,
`POST /v2/integrations/{app_id}/user/memories?uid=...`
(backend/routers/integration.py). It posted to `/user/facts`, which is not a
route (404 in production), so every import failed.

Run: python3 plugins/import/manual-import/test_submit_memories_route.py
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

APP_PATH = Path(__file__).resolve().parent / "app.py"


def _identity_route(*args, **kwargs):
    def wrap(fn):
        return fn

    return wrap


class _Request:
    json = None


def _install_stubs():
    """Stub flask/requests/openai/httpx/dotenv so app.py imports offline."""
    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *args, **kwargs):
            pass

        route = staticmethod(_identity_route)

    flask.Flask = _Flask
    flask.request = _Request
    flask.jsonify = lambda payload: payload
    flask.send_from_directory = lambda *a, **kw: None

    posts = []
    requests_mod = types.ModuleType("requests")

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {}

    def _post(url, headers=None, data=None, **kwargs):
        posts.append({"url": url, "headers": headers, "data": data})
        return _Response()

    requests_mod.post = _post

    openai = types.ModuleType("openai")
    openai.api_key = None
    openai.OpenAI = lambda *a, **kw: mock.Mock()

    httpx = types.ModuleType("httpx")
    httpx.Client = lambda *a, **kw: None
    httpx.Limits = lambda *a, **kw: None
    httpx.Timeout = lambda *a, **kw: None

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **kw: None

    for name, module in {
        "flask": flask,
        "requests": requests_mod,
        "openai": openai,
        "httpx": httpx,
        "dotenv": dotenv,
    }.items():
        sys.modules[name] = module
    return posts


def _load_app():
    spec = importlib.util.spec_from_file_location("manual_import_app_under_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARAGRAPH = (
    "Notes from the onboarding call: the customer prefers async updates over "
    "meetings and wants a weekly written summary every Friday."
)


def test_api_url_is_the_v2_user_memories_route(app, posts):
    expected = f"https://api.omi.me/v2/integrations/{app.APP_ID}/user/memories"
    assert app.API_URL == expected, app.API_URL
    assert "/user/facts" not in app.API_URL


def test_submit_posts_each_memory_to_the_memories_route(app, posts):
    posts.clear()
    _Request.json = {"uid": "user-42", "memories": [PARAGRAPH], "use_ai": False}
    with mock.patch.object(app.time, "sleep", lambda *_: None):
        response = app.submit_memories()
    body = response[0] if isinstance(response, tuple) else response
    assert len(posts) == 1, posts
    expected = f"https://api.omi.me/v2/integrations/{app.APP_ID}/user/memories?uid=user-42"
    assert posts[0]["url"] == expected, posts[0]["url"]
    assert posts[0]["headers"]["Authorization"].startswith("Bearer "), posts[0]["headers"]
    assert '"text"' in posts[0]["data"], posts[0]["data"]
    assert body.get("success") is True, body


def test_submit_without_uid_makes_no_request(app, posts):
    posts.clear()
    _Request.json = {"memories": [PARAGRAPH]}
    response = app.submit_memories()
    assert isinstance(response, tuple) and response[1] == 400, response
    assert posts == [], posts


def main():
    posts = _install_stubs()
    app = _load_app()
    tests = [
        test_api_url_is_the_v2_user_memories_route,
        test_submit_posts_each_memory_to_the_memories_route,
        test_submit_without_uid_makes_no_request,
    ]
    failures = 0
    for test in tests:
        try:
            test(app, posts)
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        sys.exit(1)
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
