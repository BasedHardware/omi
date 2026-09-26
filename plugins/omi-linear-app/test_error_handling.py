"""Hermetic error-handling regression suite for omi-linear-app.

Verifies that internal exceptions, unhandled errors, and sensitive system traces
never leak into client HTTP responses or chat-tool errors across all Linear app endpoints.
Uses Python standard library unittest only.

Run: python3 plugins/omi-linear-app/test_error_handling.py
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

SENTINEL_ERROR = "INTERNAL_DB_DISCONNECTED_AT_10.240.0.1_PASSWORD_LEAK"


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


def load_linear_app():
    """Load plugins/omi-linear-app/main.py hermetically without external dependencies."""
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get
        mount = lambda *args, **kwargs: None

    def Query(default=None, **kwargs):
        return default

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _Response:
        def __init__(self, content="", status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code
            self.kwargs = kwargs

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    requests = ModuleType("requests")
    class RequestException(Exception):
        pass
    requests.RequestException = RequestException
    requests.get = lambda *args, **kwargs: None
    requests.post = lambda *args, **kwargs: None

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    fastapi = ModuleType("fastapi")
    fastapi.__path__ = []
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi.Query = Query
    fastapi.HTTPException = HTTPException

    staticfiles = ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = lambda *args, **kwargs: object()

    templating = ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *args, **kwargs: object()

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = _Response
    responses.RedirectResponse = _Response
    responses.JSONResponse = _Response

    db = ModuleType("db")
    for name in (
        "store_linear_tokens",
        "update_linear_tokens",
        "delete_linear_tokens",
        "is_token_expired",
        "store_default_team",
        "get_default_team",
        "get_user_settings",
        "store_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)
    for name in ("get_linear_tokens", "get_oauth_state", "get_user_setting"):
        setattr(db, name, lambda *args, **kwargs: None)

    models = ModuleType("models")
    models.ChatToolResponse = ChatToolResponse
    for m in (
        "LinearIssue",
        "LinearTeam",
        "LinearProject",
        "LinearComment",
        "LinearUser",
        "WorkflowState",
    ):
        setattr(models, m, object)

    main_py_path = Path(__file__).with_name("main.py")
    spec = importlib.util.spec_from_file_location("linear_main_app", main_py_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "requests": requests,
            "dotenv": dotenv,
            "fastapi": fastapi,
            "fastapi.staticfiles": staticfiles,
            "fastapi.templating": templating,
            "fastapi.responses": responses,
            "db": db,
            "models": models,
        },
    ):
        spec.loader.exec_module(module)
    return module


class TestLinearErrorHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_linear_app()

    def setUp(self):
        self.app.get_linear_tokens = lambda uid: {"access_token": "valid_token"}

    def test_graphql_request_does_not_leak_request_exception(self):
        """linear_graphql_request masks raw RequestException from callers."""
        with patch.object(self.app.requests, "post", side_effect=self.app.requests.RequestException(SENTINEL_ERROR)):
            res = self.app.linear_graphql_request("uid123", "query { viewer { id } }")
            self.assertIn("error", res)
            self.assertNotIn(SENTINEL_ERROR, res["error"])
            self.assertEqual(res["error"], "Linear API request failed")

    def test_tool_create_issue_does_not_leak_exception(self):
        """tool_create_issue masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "title": "Test Issue", "team_id": "team_1"})
        with patch.object(self.app, "resolve_team", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_create_issue(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to create issue")

    def test_tool_list_my_issues_does_not_leak_exception(self):
        """tool_list_my_issues masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123"})
        with patch.object(self.app, "linear_graphql_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_list_my_issues(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to list issues")

    def test_tool_list_recent_issues_does_not_leak_exception(self):
        """tool_list_recent_issues masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123"})
        with patch.object(self.app, "linear_graphql_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_list_recent_issues(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to list issues")

    def test_tool_update_issue_status_does_not_leak_exception(self):
        """tool_update_issue_status masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "issue_identifier": "ENG-123", "new_status": "Done"})
        with patch.object(self.app, "get_issue_by_identifier", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_update_issue_status(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to update issue")

    def test_tool_search_issues_does_not_leak_exception(self):
        """tool_search_issues masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "query": "auth"})
        with patch.object(self.app, "linear_graphql_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_search_issues(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Search failed")

    def test_tool_get_issue_does_not_leak_exception(self):
        """tool_get_issue masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "issue_identifier": "ENG-100"})
        with patch.object(self.app, "get_issue_by_identifier", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_get_issue(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to get issue")

    def test_tool_add_comment_does_not_leak_exception(self):
        """tool_add_comment masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "issue_identifier": "ENG-100", "comment": "Fixed"})
        with patch.object(self.app, "get_issue_by_identifier", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_add_comment(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to add comment")


    def test_graphql_http_error_response_does_not_leak_error_message(self):
        """linear_graphql_request masks GraphQL error messages returned in 400+ responses."""
        class FakeResponse:
            status_code = 400
            content = b'{"errors": [{"message": "INTERNAL_DB_DISCONNECTED_AT_10.240.0.1_PASSWORD_LEAK"}]}'
            def json(self):
                return {"errors": [{"message": "INTERNAL_DB_DISCONNECTED_AT_10.240.0.1_PASSWORD_LEAK"}]}

        with patch.object(self.app.requests, "post", return_value=FakeResponse()):
            res = self.app.linear_graphql_request("uid123", "query { viewer { id } }")
            self.assertIn("error", res)
            self.assertNotIn("INTERNAL_DB_DISCONNECTED", res["error"])
            self.assertEqual(res["error"], "Linear API request failed")


if __name__ == "__main__":
    unittest.main()
