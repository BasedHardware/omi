"""Hermetic tests for Slack chat tool endpoints.

Verifies:
1. Channel resolution for raw channel IDs (C..., G..., D...).
2. Slack link/mention formatting (<#C123|general>, <#C123>).
3. Slack archive URL formatting (https://workspace.slack.com/archives/C123).
4. Safe handling of non-string and malformed parameters without 500 AttributeErrors.
5. Search channels by mention syntax or channel ID.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


class SlackApiError(Exception):
    def __init__(self, error="missing_scope"):
        super().__init__(f"Slack error: {error}")
        self.response = {"error": error}


class Response:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SlackChatToolsTests(unittest.TestCase):
    def setUp(self):
        self.sdk = Mock()
        self.sdk.conversations_list.return_value = {
            "ok": True,
            "channels": [
                {"id": "C123", "name": "general", "is_private": False, "is_member": True},
                {"id": "C456", "name": "announcements", "is_private": False, "is_member": True},
                {"id": "G789", "name": "secret-ops", "is_private": True, "is_member": True},
            ]
        }
        self.sdk.chat_postMessage.return_value = {
            "ok": True,
            "ts": "1234567890.123456",
            "channel": "C123",
            "message": {"text": "hello"}
        }
        self.sdk.search_messages.return_value = {
            "ok": True,
            "messages": {"matches": [{"text": "found message", "user": "U123", "ts": "123"}]}
        }
        self.sdk.conversations_history.return_value = {
            "ok": True,
            "messages": [{"text": "history message", "user": "U123", "ts": "123"}]
        }

        framework = types.ModuleType("fastapi")
        app = Mock()
        for method in ("get", "post", "on_event"):
            getattr(app, method).side_effect = lambda *a, **k: lambda f: f
        framework.FastAPI = lambda **kwargs: app
        framework.Request = object
        framework.HTTPException = Exception
        framework.Query = lambda *a, **k: None

        responses = types.ModuleType("fastapi.responses")
        responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = Response

        storage = types.ModuleType("simple_storage")
        storage.SimpleUserStorage = Mock()
        storage.SimpleUserStorage.get_user.return_value = {"access_token": "xoxp-test-token"}
        storage.SimpleSessionStorage = Mock()

        detector = types.ModuleType("message_detector")
        detector.MessageDetector = Mock()

        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None

        slack = types.ModuleType("slack_sdk")
        slack.WebClient = Mock(return_value=self.sdk)

        errors = types.ModuleType("slack_sdk.errors")
        errors.SlackApiError = SlackApiError

        modules = {
            "fastapi": framework,
            "fastapi.responses": responses,
            "simple_storage": storage,
            "message_detector": detector,
            "dotenv": dotenv,
            "requests": types.ModuleType("requests"),
            "slack_sdk": slack,
            "slack_sdk.errors": errors,
        }

        with patch.dict(sys.modules, modules), patch.dict("os.environ", {}, clear=True):
            self.client_mod = load("slack_client_chat_tools", "slack_client.py")
            with patch.dict(sys.modules, {"slack_client": self.client_mod}):
                self.handler = load("slack_handler_chat_tools", "main.py")
        self.client = self.handler.slack_client

    def _make_request(self, payload):
        async def json_payload():
            return payload
        req = types.SimpleNamespace(json=json_payload)
        return req

    # --- Send Message Tests ---

    def test_send_message_resolves_raw_channel_id(self):
        """Passing raw channel ID like 'C123' must resolve and post to that channel."""
        req = self._make_request({"uid": "user1", "channel": "C123", "message": "Hello general"})
        resp = asyncio.run(self.handler.chat_tool_send_message(req))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, {"result": "Successfully sent message to #general"})
        self.sdk.chat_postMessage.assert_called_once_with(channel="C123", text="Hello general")

    def test_send_message_resolves_slack_mention_with_name(self):
        """Passing Slack mention like '<#C123|general>' must resolve and post."""
        req = self._make_request({"uid": "user1", "channel": "<#C123|general>", "message": "Hello"})
        resp = asyncio.run(self.handler.chat_tool_send_message(req))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, {"result": "Successfully sent message to #general"})
        self.sdk.chat_postMessage.assert_called_once_with(channel="C123", text="Hello")

    def test_send_message_resolves_slack_mention_without_name(self):
        """Passing Slack mention like '<#C123>' must resolve to channel name and post."""
        req = self._make_request({"uid": "user1", "channel": "<#C123>", "message": "Hello"})
        resp = asyncio.run(self.handler.chat_tool_send_message(req))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, {"result": "Successfully sent message to #general"})
        self.sdk.chat_postMessage.assert_called_once_with(channel="C123", text="Hello")

    def test_send_message_resolves_slack_archive_url(self):
        """Passing Slack archive URL must resolve the channel ID."""
        req = self._make_request({
            "uid": "user1",
            "channel": "https://myworkspace.slack.com/archives/C123",
            "message": "Hello from URL"
        })
        resp = asyncio.run(self.handler.chat_tool_send_message(req))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, {"result": "Successfully sent message to #general"})
        self.sdk.chat_postMessage.assert_called_once_with(channel="C123", text="Hello from URL")

    def test_send_message_non_string_channel_returns_400_not_500(self):
        """Non-string channel (e.g. integer) must return 400, not crash with 500 AttributeError."""
        req = self._make_request({"uid": "user1", "channel": 12345, "message": "Hello"})
        resp = asyncio.run(self.handler.chat_tool_send_message(req))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.content)
        self.assertNotIn("Internal server error", resp.content.get("error", ""))

    def test_send_message_non_string_message_returns_400_not_500(self):
        """Non-string or empty message must return 400."""
        for invalid_msg in [None, 12345, "", "   ", {"text": "hi"}]:
            with self.subTest(invalid_msg=invalid_msg):
                req = self._make_request({"uid": "user1", "channel": "#general", "message": invalid_msg})
                resp = asyncio.run(self.handler.chat_tool_send_message(req))
                self.assertEqual(resp.status_code, 400)
                self.assertIn("error", resp.content)

    # --- Search Messages Tests ---

    def test_search_messages_resolves_slack_mention(self):
        """Searching messages with channel formatted as '<#C123|general>' must resolve to C123."""
        req = self._make_request({
            "uid": "user1",
            "query": "status update",
            "channel": "<#C123|general>"
        })
        resp = asyncio.run(self.handler.chat_tool_search_messages(req))
        self.assertEqual(resp.status_code, 200)
        self.sdk.search_messages.assert_called_once_with(query="in:C123 status update")

    def test_search_messages_non_string_channel_returns_400_not_500(self):
        """Passing integer channel to search_messages must return 400, not 500 AttributeError."""
        req = self._make_request({
            "uid": "user1",
            "query": "budget",
            "channel": 12345
        })
        resp = asyncio.run(self.handler.chat_tool_search_messages(req))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.content)
        self.assertNotIn("Internal server error", resp.content.get("error", ""))

    def test_search_messages_invalid_query_returns_400(self):
        """Non-string or whitespace query must return 400."""
        for invalid_q in [None, 12345, "", "   ", ["item"]]:
            with self.subTest(invalid_q=invalid_q):
                req = self._make_request({"uid": "user1", "query": invalid_q})
                resp = asyncio.run(self.handler.chat_tool_search_messages(req))
                self.assertEqual(resp.status_code, 400)
                self.assertIn("error", resp.content)

    # --- Search Channels Tests ---

    def test_search_channels_with_non_string_query_no_500(self):
        """Searching channels with integer query must not crash with 500 AttributeError."""
        req = self._make_request({"uid": "user1", "query": 123})
        resp = asyncio.run(self.handler.chat_tool_search_channels(req))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("result", resp.content)

    def test_search_channels_by_mention_and_id(self):
        """Searching channels with mention syntax '<#C123|general>' or 'C123' must find the channel."""
        for q in ["<#C123|general>", "C123", "<#C123>"]:
            with self.subTest(query=q):
                req = self._make_request({"uid": "user1", "query": q})
                resp = asyncio.run(self.handler.chat_tool_search_channels(req))
                self.assertEqual(resp.status_code, 200)
                self.assertIn("general", resp.content.get("result", ""))


if __name__ == "__main__":
    unittest.main()
