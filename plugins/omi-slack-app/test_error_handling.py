"""Hermetic error-handling regression suite for omi-slack-app.

Verifies that internal exceptions, unhandled errors, and sensitive system traces
never leak into client HTTP responses across all public handlers and tool routes.
Uses Python stdlib only.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch


class SlackApiError(Exception):
    def __init__(self, message="API error"):
        super().__init__(message)
        self.response = {"error": "api_error"}


class JSONResponse:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


class HTMLResponse:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


class RedirectResponse:
    def __init__(self, url, status_code=307, **kwargs):
        self.url = url
        self.status_code = status_code


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SlackErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        self.sdk = Mock()
        self.sdk.conversations_list.return_value = {"ok": True, "channels": []}
        self.sdk.search_messages.return_value = {"ok": True, "messages": {"matches": []}}
        self.sdk.conversations_history.return_value = {"ok": True, "messages": []}

        framework = types.ModuleType("fastapi")
        app = Mock()
        for method in ("get", "post", "on_event"):
            getattr(app, method).side_effect = lambda *a, **k: lambda f: f
        framework.FastAPI = lambda **kwargs: app
        framework.Request = object
        framework.HTTPException = HTTPException
        framework.Query = lambda *a, **k: None

        responses = types.ModuleType("fastapi.responses")
        responses.HTMLResponse = HTMLResponse
        responses.RedirectResponse = RedirectResponse
        responses.JSONResponse = JSONResponse

        self.storage_mod = types.ModuleType("simple_storage")
        self.storage_mock = Mock()
        self.storage_mock.get_user.return_value = {
            "access_token": "xoxp-mock-user-token",
            "team_id": "T123",
            "team_name": "Test Team",
            "selected_channel": "C123",
            "available_channels": [{"id": "C123", "name": "general"}]
        }
        self.storage_mock.update_channel_selection.return_value = True
        self.storage_mock.save_user = Mock()
        self.storage_mod.SimpleUserStorage = self.storage_mock
        self.storage_mod.SimpleSessionStorage = Mock()
        self.storage_mod.users = {"test-uid": {"access_token": "xoxp-mock"}}
        self.storage_mod.sessions = {}
        self.storage_mod.save_users = Mock()
        self.storage_mod.save_sessions = Mock()

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
            "simple_storage": self.storage_mod,
            "message_detector": detector,
            "dotenv": dotenv,
            "requests": types.ModuleType("requests"),
            "slack_sdk": slack,
            "slack_sdk.errors": errors,
        }

        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.client_mod = load_module("slack_client", "slack_client.py")
        modules["slack_client"] = self.client_mod
        self.patcher_client = patch.dict(sys.modules, {"slack_client": self.client_mod})
        self.patcher_client.start()
        self.addCleanup(self.patcher_client.stop)

        self.main_mod = load_module("slack_handler", "main.py")

    def test_auth_start_hides_raw_exception(self):
        with patch.object(self.main_mod.slack_client, "get_authorization_url", side_effect=RuntimeError("internal /private/key.pem leak")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(self.main_mod.auth_start(uid="test-uid"))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "OAuth initialization failed")
            self.assertNotIn("key.pem", ctx.exception.detail)
            self.assertNotIn("internal", ctx.exception.detail)

    def test_update_channel_hides_raw_exception(self):
        with patch.object(self.main_mod.SimpleUserStorage, "update_channel_selection", side_effect=RuntimeError("disk error /var/secrets")):
            res = asyncio.run(self.main_mod.update_channel(uid="test-uid", channel="C999"))
            self.assertEqual(res, {"success": False, "error": "Failed to update default channel"})
            self.assertNotIn("secrets", str(res))

    def test_refresh_channels_hides_raw_exception(self):
        with patch.object(self.main_mod.slack_client, "list_channels", side_effect=RuntimeError("auth token leak xoxb-secret")):
            res = asyncio.run(self.main_mod.refresh_channels(uid="test-uid"))
            self.assertEqual(res, {"success": False, "error": "Failed to refresh channels"})
            self.assertNotIn("xoxb-secret", str(res))

    def test_logout_hides_raw_exception(self):
        self.storage_mod.save_users.side_effect = RuntimeError("corrupted database file /etc/shadow")
        res = asyncio.run(self.main_mod.logout(uid="test-uid"))
        self.assertEqual(res, {"success": False, "error": "Failed to log out"})
        self.assertNotIn("shadow", str(res))

    def test_webhook_json_parse_hides_raw_exception(self):
        mock_request = MagicMock()
        mock_request.json = AsyncMock(side_effect=ValueError("SyntaxError line 42 col 12 sensitive buffer"))
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self.main_mod.webhook(mock_request, uid="test-uid"))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid JSON payload")
        self.assertNotIn("sensitive buffer", ctx.exception.detail)

    def test_chat_tool_send_message_hides_raw_exception(self):
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "uid": "test-uid",
            "message": "hello",
            "channel": "general"
        })
        with patch.object(self.main_mod.slack_client, "list_channels", return_value=[{"id": "C123", "name": "general"}]):
            with patch.object(self.main_mod.slack_client, "send_message", side_effect=RuntimeError("upstream socket crash /tmp/ipc.sock")):
                res = asyncio.run(self.main_mod.chat_tool_send_message(mock_request))
                self.assertEqual(res.status_code, 500)
                self.assertEqual(res.content, {"error": "Internal server error"})
                self.assertNotIn("ipc.sock", str(res.content))

    def test_chat_tool_search_messages_hides_raw_exception(self):
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "uid": "test-uid",
            "query": "urgent",
            "channel": "general"
        })
        with patch.object(self.main_mod.slack_client, "search_messages", side_effect=RuntimeError("internal query planner failure credentials:xyz")):
            res = asyncio.run(self.main_mod.chat_tool_search_messages(mock_request))
            self.assertEqual(res.status_code, 500)
            self.assertEqual(res.content, {"error": "Internal server error"})
            self.assertNotIn("credentials:xyz", str(res.content))

    def test_chat_tool_search_channels_hides_raw_exception(self):
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "uid": "test-uid",
            "query": "ops"
        })
        with patch.object(self.main_mod.slack_client, "search_channels", side_effect=RuntimeError("redis pool exhausted memory address 0xdeadbeef")):
            res = asyncio.run(self.main_mod.chat_tool_search_channels(mock_request))
            self.assertEqual(res.status_code, 500)
            self.assertEqual(res.content, {"error": "Internal server error"})
            self.assertNotIn("0xdeadbeef", str(res.content))

    def test_slack_client_methods_hide_raw_exception(self):
        client_inst = self.client_mod.SlackClient()
        with patch.object(self.client_mod, "WebClient", side_effect=RuntimeError("connection pool secret leak")):
            res_send = asyncio.run(client_inst.send_message("fake-token", "C123", "hello"))
            self.assertEqual(res_send, {"success": False, "error": "Internal error sending message"})
            self.assertNotIn("secret leak", str(res_send))

            res_history = client_inst.get_channel_history("fake-token", "C123")
            self.assertEqual(res_history, {"success": False, "error": "Internal error getting channel history"})
            self.assertNotIn("secret leak", str(res_history))

            res_search = asyncio.run(client_inst.search_messages("fake-token", "query"))
            self.assertEqual(res_search, {"success": False, "error": "Internal error searching messages"})
            self.assertNotIn("secret leak", str(res_search))


if __name__ == "__main__":
    unittest.main()
