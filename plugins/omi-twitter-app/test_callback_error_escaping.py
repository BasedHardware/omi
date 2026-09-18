"""Hermetic regression tests for reflected query values in the Twitter UI."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote


class Response:
    def __init__(self, content="", status_code=200, **_kwargs):
        self.content = content
        self.status_code = status_code


def load_app():
    class FastAPI:
        def __init__(self, **_kwargs):
            pass

        def get(self, *_args, **_kwargs):
            return lambda handler: handler

        post = get

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = type("Request", (), {})
    fastapi.HTTPException = type("HTTPException", (Exception,), {})
    fastapi.Query = lambda default=None, **_kwargs: default
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = Response
    responses.RedirectResponse = Response
    responses.JSONResponse = Response

    storage = ModuleType("simple_storage")
    storage.SimpleUserStorage = type("SimpleUserStorage", (), {"save_user": staticmethod(lambda **_kwargs: None)})
    storage.SimpleSessionStorage = type("SimpleSessionStorage", (), {})
    storage.OAuthStateStorage = type("OAuthStateStorage", (), {})
    storage.users = {}
    storage.save_users = lambda: None

    twitter_client = ModuleType("twitter_client")

    class TwitterClient:
        def get_access_token(self, *_args):
            raise RuntimeError("OAuth session not found")

    twitter_client.TwitterClient = TwitterClient

    detector = ModuleType("tweet_detector")
    detector.TweetDetector = type("TweetDetector", (), {})
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None

    spec = importlib.util.spec_from_file_location("twitter_main", Path(__file__).with_name("main_simple.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "simple_storage": storage,
            "twitter_client": twitter_client,
            "tweet_detector": detector,
            "dotenv": dotenv,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


class CallbackEscapingTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_link_percent_encodes_and_round_trips_uid(self):
        uid = '"><script>alert(1)</script>&'
        response = await app.root(uid=uid)
        self.assertNotIn("<script>alert(1)</script>", response.content)
        self.assertIn("%22%3E%3Cscript%3Ealert%281%29%3C%2Fscript%3E%26", response.content)
        href = response.content.split('href="/auth?uid=', 1)[1].split('"', 1)[0]
        self.assertEqual(unquote(parse_qs("uid=" + href)["uid"][0]), uid)

    async def test_callback_error_link_does_not_reflect_raw_html(self):
        state = '"><script>alert(1)</script>&'
        request = SimpleNamespace(url="https://twitter.example/auth/callback")
        response = await app.auth_callback(request=request, state=state, code="oauth-code")

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("<script>alert(1)</script>", response.content)
        href = response.content.split('href="/auth?uid=', 1)[1].split('"', 1)[0]
        self.assertEqual(unquote(parse_qs("uid=" + href)["uid"][0]), state)


if __name__ == "__main__":
    unittest.main()
