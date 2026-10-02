"""Hermetic regression tests: the OAuth callback error page must not reflect the
client-controlled `state` query param raw into HTML.

GET /auth/callback?code=x&state=<value> renders an error page whose "Try again"
link was built as f'<a href="/auth?uid={state}">'. A state such as
"><script>alert(1)</script> closed the attribute and ran as script (reflected
XSS), and an & or # in the value corrupted the query instead of being carried.
The setup page at GET /?uid=<value> built its Connect link the same way.

Run: python3 plugins/omi-twitter-app/test_callback_error_escaping.py
"""

import asyncio
import importlib.util
import sys
import types
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MAIN_PATH = Path(__file__).resolve().parent / "main_simple.py"

XSS_STATE = '"><script>alert(1)</script>'
XSS_STATE_ENCODED = "%22%3E%3Cscript%3Ealert%281%29%3C%2Fscript%3E"


class _Response:
    def __init__(self, content=None, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


class _HTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _identity_decorator(*args, **kwargs):
    def wrap(fn):
        return fn

    return wrap


class _FailingTwitterClient:
    """Stand-in for twitter_client.TwitterClient whose token exchange fails,
    which is the branch that renders the callback error page."""

    def get_access_token(self, authorization_response, state):
        raise Exception("OAuth session not found. Please restart authentication.")


def _install_stubs():
    """Stub FastAPI, dotenv and the sibling modules so main_simple.py imports offline."""
    fastapi = types.ModuleType("fastapi")

    class _FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        get = staticmethod(_identity_decorator)
        post = staticmethod(_identity_decorator)

    fastapi.FastAPI = _FastAPI
    fastapi.Request = object
    fastapi.HTTPException = _HTTPException
    fastapi.Query = lambda default=None, **kwargs: default

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _Response
    responses.RedirectResponse = _Response
    responses.JSONResponse = _Response

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    simple_storage = types.ModuleType("simple_storage")
    simple_storage.SimpleUserStorage = object
    simple_storage.SimpleSessionStorage = object
    simple_storage.OAuthStateStorage = object
    simple_storage.users = {}
    simple_storage.save_users = lambda: None

    twitter_client = types.ModuleType("twitter_client")
    twitter_client.TwitterClient = _FailingTwitterClient

    tweet_detector = types.ModuleType("tweet_detector")
    tweet_detector.TweetDetector = object

    for name, module in {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "dotenv": dotenv,
        "simple_storage": simple_storage,
        "twitter_client": twitter_client,
        "tweet_detector": tweet_detector,
    }.items():
        sys.modules[name] = module


def _load_app():
    spec = importlib.util.spec_from_file_location("twitter_app_main_under_test", MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _PageScan(HTMLParser):
    """Parse the page the way a browser would: collect <a href> values (entity
    decoded) and count every <script> element that actually opens."""

    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.script_tags = 0

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href"))
        if tag == "script":
            self.script_tags += 1


def _scan(body):
    scan = _PageScan()
    scan.feed(body)
    return scan


def _uid_from_href(href):
    return parse_qs(urlsplit(href).query).get("uid", [None])[0]


def _render_error_page(app, state):
    request = types.SimpleNamespace(url="http://testserver/auth/callback?code=x")
    return asyncio.run(app.auth_callback(request, state=state, code="x"))


def test_script_in_state_is_not_reflected_raw(app):
    response = _render_error_page(app, XSS_STATE)
    assert response.status_code == 500, response.status_code
    body = response.content
    assert "<script" not in body.lower(), body
    assert XSS_STATE not in body, body
    scan = _scan(body)
    assert scan.script_tags == 0, body
    assert f'href="/auth?uid={XSS_STATE_ENCODED}"' in body, body


def test_try_again_link_round_trips_state(app):
    for state in (XSS_STATE, "a&b#c", "x=y/z?w"):
        body = _render_error_page(app, state).content
        hrefs = [h for h in _scan(body).hrefs if h and h.startswith("/auth?")]
        assert len(hrefs) == 1, body
        assert _uid_from_href(hrefs[0]) == state, (state, hrefs[0])
        assert "&" not in hrefs[0].split("uid=", 1)[1], hrefs[0]
        assert "#" not in hrefs[0], hrefs[0]


def test_plain_state_link_is_unchanged(app):
    body = _render_error_page(app, "abc123").content
    assert 'href="/auth?uid=abc123"' in body, body


def test_missing_state_falls_back_to_unknown(app):
    response = _render_error_page(app, None)
    assert response.status_code == 500, response.status_code
    assert 'href="/auth?uid=unknown"' in response.content, response.content


def test_setup_page_encodes_uid_in_connect_link(app):
    body = asyncio.run(app.root(uid=XSS_STATE)).content
    scan = _scan(body)
    hrefs = [h for h in scan.hrefs if h and h.startswith("/auth?")]
    assert "<script" not in body.lower(), hrefs
    assert scan.script_tags == 0, hrefs
    assert len(hrefs) == 1, hrefs
    assert _uid_from_href(hrefs[0]) == XSS_STATE, hrefs[0]
    assert f'href="/auth?uid={XSS_STATE_ENCODED}"' in body, hrefs


def main():
    _install_stubs()
    app = _load_app()
    tests = [
        test_script_in_state_is_not_reflected_raw,
        test_try_again_link_round_trips_state,
        test_plain_state_link_is_unchanged,
        test_missing_state_falls_back_to_unknown,
        test_setup_page_encodes_uid_in_connect_link,
    ]
    failures = 0
    for test in tests:
        try:
            test(app)
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        sys.exit(1)
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
