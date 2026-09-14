"""Hermetic regression tests for Linear app query parameterization and limit coercion.

Standard library only: loads plugins/omi-linear-app/main.py under scoped stubs
without polluting global sys.modules.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class App:
    def __init__(self, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def mount(self, *args, **kwargs):
        pass


class Response:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error


def load_app():
    modules = {}
    definitions = {
        "fastapi": dict(FastAPI=App, HTTPException=Exception, Request=object, Query=Mock()),
        "fastapi.responses": dict(HTMLResponse=object, RedirectResponse=Mock(), JSONResponse=Mock()),
        "fastapi.staticfiles": dict(StaticFiles=Mock()),
        "fastapi.templating": dict(Jinja2Templates=Mock()),
        "dotenv": dict(load_dotenv=lambda: None),
        "requests": dict(post=Mock(side_effect=AssertionError("Unexpected HTTP")), RequestException=Exception),
        "db": {
            name: Mock(side_effect=AssertionError("Unexpected storage"))
            for name in (
                "store_linear_tokens",
                "get_linear_tokens",
                "delete_linear_tokens",
                "is_token_expired",
                "store_default_team",
                "get_default_team",
                "get_user_settings",
            )
        },
        "models": {
            name: Response if name == "ChatToolResponse" else SimpleNamespace
            for name in (
                "ChatToolResponse",
                "LinearIssue",
                "LinearTeam",
                "LinearProject",
                "LinearComment",
                "LinearUser",
                "WorkflowState",
            )
        },
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location("linear_params_under_test", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict("os.environ", {}, clear=True):
        spec.loader.exec_module(module)
    return module


class LinearParamCoercionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_app()

    def test_coerce_limit_bounds_and_fallbacks(self):
        # Default fallback
        self.assertEqual(self.module.coerce_limit(None, default=10), 10)
        self.assertEqual(self.module.coerce_limit("invalid", default=5), 5)
        self.assertEqual(self.module.coerce_limit([], default=10), 10)

        # OverflowError handling (e.g. 1e309)
        self.assertEqual(self.module.coerce_limit(float("inf"), default=10), 10)
        self.assertEqual(self.module.coerce_limit(1e309, default=10), 10)

        # String to int conversion
        self.assertEqual(self.module.coerce_limit("15", default=10), 15)

        # Min and Max clamping
        self.assertEqual(self.module.coerce_limit(-10, default=10, min_val=1, max_val=50), 1)
        self.assertEqual(self.module.coerce_limit(0, default=10, min_val=1, max_val=50), 1)
        self.assertEqual(self.module.coerce_limit(999, default=10, min_val=1, max_val=50), 50)
        self.assertEqual(self.module.coerce_limit("1000", default=10, min_val=1, max_val=50), 50)

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

        self.module.linear_graphql_request = mock_graphql
        self.module.get_linear_tokens = lambda uid: {"access_token": "valid"}

        # Call with string limit "20" and status filter "in progress"
        req = SimpleNamespace(json=lambda: asyncio.sleep(0, {"uid": "user_1", "limit": "20", "status": "in progress"}))
        resp = asyncio.run(self.module.tool_list_my_issues(req))

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

        self.module.linear_graphql_request = mock_graphql
        self.module.get_linear_tokens = lambda uid: {"access_token": "valid"}

        # Test with whitespace-padded team key and oversized limit
        req = SimpleNamespace(json=lambda: asyncio.sleep(0, {"uid": "user_2", "limit": "999", "team": "  omi  "}))
        resp = asyncio.run(self.module.tool_list_recent_issues(req))

        self.assertIsNone(resp.error)
        self.assertIn("OMI-42", resp.result)
        self.assertIn("in OMI", resp.result)
        self.assertEqual(len(recorded_calls), 1)

        uid, query, variables = recorded_calls[0]
        self.assertEqual(variables["first"], 50)  # Clamped to max_val 50
        self.assertEqual(variables["filter"], {"team": {"key": {"eq": "OMI"}}})
        self.assertIn("query($first: Int!, $filter: IssueFilter)", query)

        # Test with whitespace-only team key (should normalize to None and not filter or print blank label)
        recorded_calls.clear()
        req_blank_team = SimpleNamespace(json=lambda: asyncio.sleep(0, {"uid": "user_2", "limit": 5, "team": "   "}))
        resp_blank = asyncio.run(self.module.tool_list_recent_issues(req_blank_team))
        self.assertIsNone(resp_blank.error)
        self.assertTrue(resp_blank.result.startswith("📋 Latest 1 issues in Linear:\n\n"))
        self.assertEqual(recorded_calls[0][2], {"first": 5})

        # Test without team key
        recorded_calls.clear()
        req2 = SimpleNamespace(json=lambda: asyncio.sleep(0, {"uid": "user_2", "limit": 3}))
        resp2 = asyncio.run(self.module.tool_list_recent_issues(req2))
        self.assertIsNone(resp2.error)
        self.assertEqual(recorded_calls[0][2], {"first": 3})
        self.assertIn("query($first: Int!)", recorded_calls[0][1])


if __name__ == "__main__":
    unittest.main()
