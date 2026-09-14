"""Hermetic regression tests for Linear app query parameterization and limit coercion.

Standard library only: replaces third-party dependencies with lightweight stubs
before importing plugins/omi-linear-app/main.py.
"""

import asyncio
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    requests = types.ModuleType("requests")

    class _RequestException(Exception):
        pass

    exceptions = types.ModuleType("requests.exceptions")
    exceptions.RequestException = _RequestException
    exceptions.Timeout = type("Timeout", (_RequestException,), {})
    requests.exceptions = exceptions
    requests.post = lambda *a, **k: None
    requests.get = lambda *a, **k: None
    sys.modules["requests"] = requests
    sys.modules["requests.exceptions"] = exceptions

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

        def mount(self, *args, **kwargs):
            pass

    class HTTPException(Exception):
        pass

    class Request:
        pass

    def Query(default=None, **kwargs):
        return default

    fastapi.FastAPI = FastAPI
    fastapi.HTTPException = HTTPException
    fastapi.Request = Request
    fastapi.Query = Query
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class _Resp:
        def __init__(self, *args, **kwargs):
            pass

    responses.HTMLResponse = _Resp
    responses.RedirectResponse = _Resp
    responses.JSONResponse = _Resp
    sys.modules["fastapi.responses"] = responses

    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = lambda *a, **k: None
    sys.modules["fastapi.staticfiles"] = staticfiles

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *a, **k: types.SimpleNamespace(TemplateResponse=lambda *a, **k: None)
    sys.modules["fastapi.templating"] = templating

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda *a, **k: (k["default_factory"]() if "default_factory" in k else k.get("default"))
    sys.modules["pydantic"] = pydantic

    omi_sdk = types.ModuleType("omi_plugin_sdk")
    omi_sdk_models = types.ModuleType("omi_plugin_sdk.models")
    omi_sdk_models.Conversation = type("Conversation", (), {})
    omi_sdk_models.EndpointResponse = type("EndpointResponse", (), {})
    omi_sdk_models.Structured = type("Structured", (), {})
    omi_sdk_models.TranscriptSegment = type("TranscriptSegment", (), {})
    sys.modules["omi_plugin_sdk"] = omi_sdk
    sys.modules["omi_plugin_sdk.models"] = omi_sdk_models


_install_module_stubs()
import main  # noqa: E402


class MockRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class LinearParamCoercionTests(unittest.TestCase):
    def test_coerce_limit_bounds_and_fallbacks(self):
        # Default fallback
        self.assertEqual(main.coerce_limit(None, default=10), 10)
        self.assertEqual(main.coerce_limit("invalid", default=5), 5)
        self.assertEqual(main.coerce_limit([], default=10), 10)

        # String to int conversion
        self.assertEqual(main.coerce_limit("15", default=10), 15)

        # Min and Max clamping
        self.assertEqual(main.coerce_limit(-10, default=10, min_val=1, max_val=50), 1)
        self.assertEqual(main.coerce_limit(0, default=10, min_val=1, max_val=50), 1)
        self.assertEqual(main.coerce_limit(999, default=10, min_val=1, max_val=50), 50)
        self.assertEqual(main.coerce_limit("1000", default=10, min_val=1, max_val=50), 50)

    def test_tool_list_my_issues_uses_graphql_variables_and_coerces_limit(self):
        recorded_calls = []

        def mock_graphql(uid, query, variables=None):
            recorded_calls.append((uid, query, variables))
            return {
                "issues": {
                    "nodes": [
                        {
                            "id": "1",
                            "identifier": "ENG-1",
                            "title": "Test Issue",
                            "priority": 1,
                            "state": {"name": "In Progress", "type": "started"},
                        }
                    ]
                }
            }

        orig_graphql = main.linear_graphql_request
        orig_get_tokens = main.get_linear_tokens
        try:
            main.linear_graphql_request = mock_graphql
            main.get_linear_tokens = lambda uid: {"access_token": "valid"}

            # Call with string limit "20" and status filter "in progress"
            req = MockRequest({"uid": "user_1", "limit": "20", "status": "in progress"})
            resp = asyncio.run(main.tool_list_my_issues(req))

            self.assertIsNone(resp.error)
            self.assertIn("ENG-1", resp.result)
            self.assertEqual(len(recorded_calls), 1)

            uid, query, variables = recorded_calls[0]
            self.assertEqual(uid, "user_1")
            self.assertIn("query($first: Int!, $filter: IssueFilter)", query)
            self.assertNotIn("first: 20", query)  # Should not be raw string formatted
            self.assertEqual(variables["first"], 20)
            self.assertIsInstance(variables["first"], int)
            self.assertEqual(
                variables["filter"],
                {
                    "assignee": {"isMe": {"eq": True}},
                    "state": {"type": {"eq": "started"}},
                },
            )
        finally:
            main.linear_graphql_request = orig_graphql
            main.get_linear_tokens = orig_get_tokens

    def test_tool_list_recent_issues_parameterizes_team_and_limit(self):
        recorded_calls = []

        def mock_graphql(uid, query, variables=None):
            recorded_calls.append((uid, query, variables))
            return {
                "issues": {
                    "nodes": [
                        {
                            "id": "2",
                            "identifier": "OMI-42",
                            "title": "Recent Bug",
                            "priority": 2,
                            "state": {"name": "Todo"},
                            "assignee": {"name": "Alice"},
                        }
                    ]
                }
            }

        orig_graphql = main.linear_graphql_request
        orig_get_tokens = main.get_linear_tokens
        try:
            main.linear_graphql_request = mock_graphql
            main.get_linear_tokens = lambda uid: {"access_token": "valid"}

            # Test with unpadded team key and string limit
            req = MockRequest({"uid": "user_2", "limit": "999", "team": "  omi  "})
            resp = asyncio.run(main.tool_list_recent_issues(req))

            self.assertIsNone(resp.error)
            self.assertIn("OMI-42", resp.result)
            self.assertEqual(len(recorded_calls), 1)

            uid, query, variables = recorded_calls[0]
            self.assertEqual(variables["first"], 50)  # Clamped to max_val 50
            self.assertEqual(variables["filter"], {"team": {"key": {"eq": "OMI"}}})
            self.assertIn("query($first: Int!, $filter: IssueFilter)", query)

            # Test without team key
            recorded_calls.clear()
            req2 = MockRequest({"uid": "user_2", "limit": 3})
            resp2 = asyncio.run(main.tool_list_recent_issues(req2))
            self.assertIsNone(resp2.error)
            self.assertEqual(recorded_calls[0][2], {"first": 3})
            self.assertIn("query($first: Int!)", recorded_calls[0][1])
        finally:
            main.linear_graphql_request = orig_graphql
            main.get_linear_tokens = orig_get_tokens


if __name__ == "__main__":
    unittest.main()
