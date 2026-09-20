"""Hermetic regression: a failed X API call must not surface a Python error.

twitter_api_request returns None when the stored token cannot be refreshed or
the HTTP call itself raises. Every chat tool guarded that with

    if not result or "error" in result:
        return ChatToolResponse(error=f"...: {result.get('error', 'Unknown error')}")

so the None branch called .get on None, raised AttributeError, and the
handler's broad `except Exception` reported it verbatim — users saw
"Failed to get timeline: 'NoneType' object has no attribute 'get'" instead of
being told to reconnect. A dict carrying an "error" key must still surface
that message unchanged.

Import the production module with framework-only stubs and drive the real
handlers. No network, credentials, or third-party packages required.

Run: python3 plugins/omi-twitter-chat-tools-app/test_api_failure_messages.py
"""

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

MAIN_PATH = Path(__file__).resolve().parent / "main.py"


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    def module(name, **attributes):
        value = ModuleType(name)
        value.__dict__.update(attributes)
        return value

    db = module("db")
    for name in (
        "store_twitter_tokens",
        "get_twitter_tokens",
        "update_twitter_tokens",
        "delete_twitter_tokens",
        "store_oauth_state",
        "get_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
        "get_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)

    stubs = {
        "fastapi": module("fastapi", FastAPI=FastAPI, Request=object, Query=lambda *a, **k: None, HTTPException=Exception),
        "fastapi.responses": module("fastapi.responses", HTMLResponse=str, RedirectResponse=str, JSONResponse=dict),
        "dotenv": module("dotenv", load_dotenv=lambda *a, **k: None),
        "requests": module("requests"),
        "db": db,
        "models": module("models", ChatToolResponse=ChatToolResponse),
    }
    spec = importlib.util.spec_from_file_location("twitter_failure_messages_under_test", MAIN_PATH)
    loaded = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(loaded)
    return loaded


app = load_app()


def _request(body):
    class _Request:
        async def json(self):
            return body

    return _Request()


# Handlers that reach twitter_api_request, with a body that clears their own
# argument validation. Each is authenticated: the missing-token case is
# already handled earlier by each handler's own get_twitter_tokens check.
HANDLERS = {
    "tool_post_tweet": {"uid": "u", "text": "hello"},
    "tool_get_timeline": {"uid": "u"},
    "tool_get_my_tweets": {"uid": "u"},
    "tool_get_mentions": {"uid": "u"},
    "tool_search_tweets": {"uid": "u", "query": "omi"},
    "tool_like_tweet": {"uid": "u", "tweet_id": "1"},
    "tool_retweet": {"uid": "u", "tweet_id": "1"},
    "tool_unlike_tweet": {"uid": "u", "tweet_id": "1"},
    "tool_delete_tweet": {"uid": "u", "tweet_id": "1"},
    "tool_get_user_profile": {"uid": "u", "username": "omi"},
}


class ApiFailureMessageTests(unittest.TestCase):
    def drive(self, name, api_result):
        handler = getattr(app, name)
        with patch.object(app, "get_twitter_tokens", lambda uid: {"access_token": "t"}), \
             patch.object(app, "get_valid_access_token", lambda uid: "t"), \
             patch.object(app, "get_user_id", lambda uid: "123"), \
             patch.object(app, "twitter_api_request", lambda *a, **k: api_result):
            return asyncio.run(handler(_request(dict(HANDLERS[name]))))

    def test_none_result_does_not_leak_a_python_error(self):
        # twitter_api_request returns None on a failed token refresh or a
        # request exception; the failure branch must survive it.
        for name in HANDLERS:
            with self.subTest(handler=name):
                response = self.drive(name, None)
                self.assertIsNotNone(response.error, "a failed call must report an error")
                self.assertNotIn("NoneType", response.error)
                self.assertNotIn("has no attribute", response.error)
                self.assertNotIn("Traceback", response.error)

    def test_none_result_tells_the_user_what_to_do(self):
        response = self.drive("tool_get_timeline", None)
        self.assertIn("reconnect", response.error.lower())

    def test_api_supplied_error_message_is_preserved(self):
        response = self.drive("tool_get_timeline", {"error": "Rate limit exceeded"})
        self.assertIn("Rate limit exceeded", response.error)

    def test_error_payload_without_a_message_falls_back(self):
        for payload in ({"error": None}, {"error": ""}):
            with self.subTest(payload=payload):
                response = self.drive("tool_get_timeline", payload)
                self.assertIsNotNone(response.error)
                self.assertNotIn("NoneType", response.error)

    def test_destructive_tools_never_claim_a_failed_call_succeeded(self):
        # unlike and delete guarded with `if result and "error" in result`, so
        # a None result fell through to the success message and told the user
        # the tweet was unliked or deleted when nothing had happened.
        for name, claim in (("tool_unlike_tweet", "Unliked"), ("tool_delete_tweet", "Deleted")):
            with self.subTest(handler=name):
                response = self.drive(name, None)
                self.assertIsNone(response.result, "a failed call must not report success")
                self.assertIsNotNone(response.error)
                self.assertNotIn(claim, response.error)

    def test_destructive_tools_still_succeed_on_a_good_response(self):
        for name, claim in (("tool_unlike_tweet", "Unliked"), ("tool_delete_tweet", "Deleted")):
            with self.subTest(handler=name):
                response = self.drive(name, {"data": {"deleted": True}})
                self.assertIsNone(response.error)
                self.assertIn(claim, response.result)

    def test_helper_handles_every_shape(self):
        self.assertEqual(app.api_error_detail({"error": "boom"}), "boom")
        self.assertEqual(app.api_error_detail({"error": None}), "Unknown error")
        self.assertEqual(app.api_error_detail({}), "Unknown error")
        for bad in (None, [], "nope", 5):
            with self.subTest(result=bad):
                self.assertNotIn("NoneType", app.api_error_detail(bad))


if __name__ == "__main__":
    unittest.main()
