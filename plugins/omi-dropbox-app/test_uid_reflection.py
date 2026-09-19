"""Hermetic tests: the Dropbox setup page must not reflect input into HTML raw.

AGET /` takes `uid` straight off the query string on an unauthenticated route
and renders it into href/action attributes. `folder_name` is attacker-supplied
via `POST /settings` and is rendered back into a jvalue="..."` attribute, so it
is a stored sink, not just a reflected one.

Framework-only stubs (fastapi, dotenv, requests, db, models, dropbox_client);
the real `get_home_page_html` is exercised. No network, no third-party packages.
"""

import html
import sys
import types
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent

BREAKOUT = '"><script>alert(1)</script>'
QUERY_BREAKER = 'a&b#c'


def _load_main():
    """Import main.py with its framework and sibling dependencies stubbed."""
    saved = {
        name: sys.modules.get(name)
        for name in (
            "requests", "dotenv", "fastapi", "fastapi.responses",
            "db", "models", "dropbox_client", "main",
        )
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
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    for name in ("HTMLResponse", "RedirectResponse", "JSONResponse"):
        setattr(responses, name, type(name, (), {"__init__": lambda self, *a, **k: None}))
    fastapi.responses = responses
    sys.modules["fastapi.responses"] = responses

    db = types.ModuleType("db")
    for name in (
        "store_dropbox_tokens", "get_dropbox_tokens", "update_dropbox_tokens",
        "delete_dropbox_tokens", "store_oauth_state", "get_oauth_state",
        "delete_oauth_state", "store_user_settings",
    ):
        setattr(db, name, lambda *a, **k: None)
    db.get_user_settings = lambda uid: {}
    sys.modules["db"] = db

    models = types.ModuleType("models")
    models.Conversation = type("Conversation", (), {})
    models.EndpointResponse = type("EndpointResponse", (), {})
    sys.modules["models"] = models

    client = types.ModuleType("dropbox_client")
    client.DropboxClient = type("DropboxClient", (), {})
    sys.modules["dropbox_client"] = client

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


class UidReflectionTest(unittest.TestCase):
    def test_disconnected_page_does_not_reflect_uid_raw(self) -> None:
        """The unauthenticated branch is the one any visitor can reach."""
        page = MAIN.get_home_page_html(uid=BREAKOUT, connected=False)
        self.assertNotIn(BREAKOUT, page)
        self.assertNotIn("<script>alert(1)</script>", page)
        # The retry link must still carry the uid, percent-encoded.
        self.assertIn("%3E%3Cscript%3E", page)

    def test_connected_page_does_not_reflect_uid_raw(self) -> None:
        page = MAIN.get_home_page_html(
            uid=BREAKOUT, connected=True, display_name="d", email="e", settings={}
        )
        self.assertNotIn(BREAKOUT, page)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_uid_query_separators_do_not_corrupt_the_link(self) -> None:
        """A bare & or # silently truncates or rewrites the query."""
        page = MAIN.get_home_page_html(uid=QUERY_BREAKER, connected=False)
        self.assertNotIn("uid=a&b#c", page)
        self.assertIn("uid=a%26b%23c", page)

    def test_stored_folder_name_is_escaped(self) -> None:
        """folder_name is set by the user via POST /settings — a stored sink."""
        page = MAIN.get_home_page_html(
            uid="u", connected=True, display_name="d", email="e",
            settings={"folder_name": BREAKOUT},
        )
        self.assertNotIn(BREAKOUT, page)
        self.assertIn(html.escape(BREAKOUT), page)

    def test_dropbox_supplied_identity_is_escaped(self) -> None:
        page = MAIN.get_home_page_html(
            uid="u", connected=True,
            display_name=BREAKOUT, email=BREAKOUT, settings={},
        )
        self.assertNotIn(BREAKOUT, page)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_ordinary_uid_still_renders(self) -> None:
        page = MAIN.get_home_page_html(uid="abc123", connected=False)
        self.assertIn("/auth/dropbox?uid=abc123", page)


if __name__ == "__main__":
    unittest.main()
