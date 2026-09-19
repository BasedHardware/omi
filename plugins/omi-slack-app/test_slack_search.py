"""Hermetic production client/handler regression for #13156.

Only SDK, storage, and framework import boundaries are replaced; both complete
production modules execute, with no live Slack or filesystem-backed user data.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class SlackApiError(Exception):
    def __init__(self):
        super().__init__("lookup unavailable")
        self.response = {"error": "missing_scope"}


class Response:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SearchScopeTests(unittest.TestCase):
    def setUp(self):
        self.sdk = Mock()
        self.sdk.conversations_list.return_value = {"ok": True, "channels": []}
        self.sdk.search_messages.return_value = {
            "ok": True, "messages": {"matches": [{"text": "fixture result"}]}
        }
        self.sdk.conversations_history.return_value = {
            "ok": True, "messages": [{"text": "human"}, {"text": "bot", "bot_id": "B"}]
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
        storage.SimpleUserStorage.get_user.return_value = {"access_token": "fixture"}
        storage.SimpleSessionStorage = Mock()
        detector = types.ModuleType("message_detector")
        detector.MessageDetector = Mock()
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        slack = types.ModuleType("slack_sdk")
        slack.WebClient = Mock(return_value=self.sdk)
        errors = types.ModuleType("slack_sdk.errors")
        errors.SlackApiError = SlackApiError
        modules = {"fastapi": framework, "fastapi.responses": responses,
                   "simple_storage": storage, "message_detector": detector,
                   "dotenv": dotenv, "requests": types.ModuleType("requests"),
                   "slack_sdk": slack, "slack_sdk.errors": errors}
        with patch.dict(sys.modules, modules), patch.dict("os.environ", {}, clear=True):
            self.module = load("slack_client", "slack_client.py")
            with patch.dict(sys.modules, {"slack_client": self.module}):
                self.handler = load("slack_handler", "main.py")
        self.client = self.handler.slack_client

    def search(self, channel, query="budget", handler=False):
        if handler:
            async def payload():
                return {"uid": "fixture-user", "query": query, "channel": channel}
            return asyncio.run(self.handler.chat_tool_search_messages(types.SimpleNamespace(json=payload)))
        return asyncio.run(self.client.search_messages("fixture", query, channel))

    def test_unresolved_name_never_searches_workspace(self):
        for handler in (False, True):
            for query in ("budget", "today"):
                for failure in (None, SlackApiError(), {"ok": False, "error": "missing_scope"}):
                    with self.subTest(handler=handler, query=query, failure=failure):
                        self.sdk.reset_mock()
                        self.sdk.conversations_list.side_effect = failure if isinstance(failure, Exception) else None
                        self.sdk.conversations_list.return_value = failure or {"ok": True, "channels": []}
                        result = self.search("#missing", query, handler)
                        self.sdk.search_messages.assert_not_called()
                        self.sdk.conversations_history.assert_not_called()
                        if handler:
                            self.assertEqual(result.status_code, 400)
                            self.assertIn("channel_not_found_or_unavailable", result.content["error"])
                        else:
                            self.assertEqual(result, {"success": False, "error": "channel_not_found_or_unavailable"})

    def test_resolved_name_and_direct_ids_remain_scoped(self):
        self.sdk.conversations_list.return_value = {
            "ok": True, "channels": [{"id": "C123", "name": "general"}]
        }
        for handler in (False, True):
            for channel in ("#GENERAL", "C123", "G123"):
                with self.subTest(handler=handler, channel=channel):
                    self.sdk.reset_mock()
                    self.search(channel, handler=handler)
                    expected = "C123" if channel == "#GENERAL" else channel
                    self.sdk.search_messages.assert_called_once_with(query=f"in:{expected} budget")

    def test_direct_id_with_failed_lookup_and_no_channel(self):
        self.sdk.conversations_list.side_effect = SlackApiError()
        for handler in (False, True):
            for channel in ("C123", "G123", None):
                with self.subTest(handler=handler, channel=channel):
                    self.sdk.reset_mock()
                    self.search(channel, handler=handler)
                    expected = f"in:{channel} budget" if channel else "budget"
                    self.sdk.search_messages.assert_called_once_with(query=expected)

    def test_history_and_failed_history_fallback_keep_scope(self):
        for handler in (False, True):
            for success in (True, False):
                with self.subTest(handler=handler, success=success):
                    self.sdk.reset_mock()
                    self.sdk.conversations_history.return_value["ok"] = success
                    result = self.search("C123", "today", handler)
                    self.assertEqual(self.sdk.conversations_history.call_args.kwargs["channel"], "C123")
                    if success:
                        self.sdk.search_messages.assert_not_called()
                        if not handler:
                            self.assertEqual(result["matches"], [{"text": "human"}])
                    else:
                        self.sdk.search_messages.assert_called_once_with(query="in:C123 today")

    def test_list_callers_keep_empty_list_error_contract(self):
        self.sdk.conversations_list.side_effect = SlackApiError()
        self.assertEqual(self.client.list_channels("fixture"), [])
        self.assertEqual(self.client.search_channels("fixture", "all"), [])


if __name__ == "__main__":
    unittest.main()
