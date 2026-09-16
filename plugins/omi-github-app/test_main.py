"""Hermetic regression tests for issue #13911.

Drives the real chat-tool handlers in main.py and the real GitHubClient in
github_client.py against mocked module boundaries:

- Optional tool params arrive as JSON null or loosely typed values;
  `coerce_issue_number`/`coerce_limit` must normalize them (or return clean
  validation errors) instead of crashing on int()/min().
- `list_issues`/`get_issue` must return explicit error structures for
  non-200 responses instead of silently returning empty results, and must
  page past pull requests so they cannot starve the requested limit.

Plain python3 + stdlib: all third-party imports are stubbed in sys.modules
while the plugin modules are loaded from disk, same pattern as
test_github_client.py.
"""
import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).resolve().parent


# ---- Third-party stubs -------------------------------------------------

_requests = types.ModuleType("requests")
_requests.get = _requests.post = None

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None


class _HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, **kwargs):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _Request:
    def __init__(self, payload=None):
        self._payload = payload or {}

    async def json(self):
        return self._payload


def _Query(default=None, **kwargs):
    return default


class _FastAPI:
    """Minimal FastAPI stand-in: route decorators record handlers."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.routes = {}

    def _register(self, method, path):
        def decorator(fn):
            self.routes[(method, path)] = fn
            return fn

        return decorator

    def get(self, path, **kwargs):
        return self._register("GET", path)

    def post(self, path, **kwargs):
        return self._register("POST", path)


_fastapi = types.ModuleType("fastapi")
_fastapi.FastAPI = _FastAPI
_fastapi.Request = _Request
_fastapi.HTTPException = _HTTPException
_fastapi.Query = _Query

_responses = types.ModuleType("fastapi.responses")


class _StubResponse:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.status_code = kwargs.get("status_code", 200)


_responses.HTMLResponse = _StubResponse
_responses.RedirectResponse = _StubResponse
_responses.JSONResponse = _StubResponse
_fastapi.responses = _responses


class _BaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


_pydantic = types.ModuleType("pydantic")
_pydantic.BaseModel = _BaseModel

# simple_storage is stubbed so the suite never touches on-disk state
# (its real module reads users_data.json at import).
_simple_storage = types.ModuleType("simple_storage")


class _SimpleUserStorage:
    @staticmethod
    def get_user(uid):
        return None

    @staticmethod
    def is_authenticated(uid):
        return False

    @staticmethod
    def has_selected_repo(uid):
        return False

    @staticmethod
    def save_user(**kwargs):
        return True

    @staticmethod
    def update_repo_selection(uid, selected_repo):
        return False

    @staticmethod
    def save_agent_provider(uid, provider):
        return False

    @staticmethod
    def get_agent_provider(uid):
        return None

    @staticmethod
    def save_agent_api_key(uid, provider, api_key):
        return False

    @staticmethod
    def get_agent_api_key(uid, provider):
        return None

    @staticmethod
    def delete_agent_api_key(uid, provider):
        return False


_simple_storage.SimpleUserStorage = _SimpleUserStorage

# issue_detector is stubbed so no OpenAI client is constructed.
_issue_detector = types.ModuleType("issue_detector")


async def _ai_select_labels(*args, **kwargs):
    return []


_issue_detector.ai_select_labels = _ai_select_labels

STUBS = {
    "requests": _requests,
    "dotenv": _dotenv,
    "fastapi": _fastapi,
    "fastapi.responses": _responses,
    "pydantic": _pydantic,
    "simple_storage": _simple_storage,
    "issue_detector": _issue_detector,
}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Load the real plugin modules in dependency order inside the stubbed
# environment, then expose them under their importable names for main.py.
with patch.dict(sys.modules, STUBS):
    models = _load("models")
    github_client = _load("github_client")
    agent_providers = _load("agent_providers")
    _real = {
        "models": models,
        "github_client": github_client,
        "agent_providers": agent_providers,
    }
    with patch.dict(sys.modules, _real):
        main = _load("main")


# ---- Fakes and helpers --------------------------------------------------


class FakeResponse:
    def __init__(self, payload, status_code=200, links=None, text=""):
        self._payload = payload
        self.status_code = status_code
        self.links = links or {}
        self.text = text

    def json(self):
        return self._payload


USER = {"access_token": "tok", "selected_repo": "owner/repo"}


def call_tool(path, payload):
    handler = main.app.routes[("POST", path)]
    return asyncio.run(handler(_Request(payload)))


def issue_payload(number, pull_request=False):
    issue = {
        "number": number,
        "title": f"Issue {number}",
        "state": "open",
        "body": "body",
        "labels": [],
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "user": {"login": "octocat"},
        "assignees": [],
        "comments": 0,
    }
    if pull_request:
        issue["pull_request"] = {"url": "..."}
    return issue


def authed():
    return patch.object(main.SimpleUserStorage, "get_user", return_value=USER)


# ---- Coercion helpers ----------------------------------------------------


class CoerceIssueNumberTests(unittest.TestCase):
    def test_accepts_clean_and_formatted_values(self):
        for raw in (42, "42", "#42", " 42 ", "  #42  ", 42.0):
            number, error = main.coerce_issue_number(raw)
            self.assertIsNone(error, raw)
            self.assertEqual(number, 42, raw)

    def test_missing_reports_required(self):
        number, error = main.coerce_issue_number(None)
        self.assertIsNone(number)
        self.assertIn("required", error)

    def test_rejects_non_numeric_and_non_positive(self):
        for raw in ("abc", "#abc", "", "#", "4.5", 4.5, 0, -3, True, [], {}):
            number, error = main.coerce_issue_number(raw)
            self.assertIsNone(number, raw)
            self.assertIsNotNone(error, raw)


class CoerceLimitTests(unittest.TestCase):
    def test_none_falls_back_to_default(self):
        limit, error = main.coerce_limit(None)
        self.assertIsNone(error)
        self.assertEqual(limit, 10)

    def test_coerces_strings_floats_and_clamps(self):
        self.assertEqual(main.coerce_limit(5), (5, None))
        self.assertEqual(main.coerce_limit("25"), (25, None))
        self.assertEqual(main.coerce_limit(7.0), (7, None))
        self.assertEqual(main.coerce_limit(500), (50, None))

    def test_rejects_invalid(self):
        for raw in ("abc", "4.5", 4.5, 0, -10, True, [], {}):
            limit, error = main.coerce_limit(raw)
            self.assertIsNone(limit, raw)
            self.assertIsNotNone(error, raw)


# ---- tool_get_issue ------------------------------------------------------


class GetIssueToolTests(unittest.TestCase):
    def test_hash_prefixed_issue_number_is_coerced(self):
        with authed(), patch.object(
            github_client.requests, "get", return_value=FakeResponse(issue_payload(42))
        ) as get:
            resp = call_tool("/tools/get_issue", {"uid": "u1", "issue_number": "#42"})

        self.assertIsNone(resp.error)
        self.assertIn("#42", resp.result)
        self.assertTrue(get.call_args.args[0].endswith("/repos/owner/repo/issues/42"))

    def test_non_numeric_issue_number_returns_validation_error(self):
        with authed(), patch.object(github_client.requests, "get") as get:
            resp = call_tool("/tools/get_issue", {"uid": "u1", "issue_number": "abc"})

        self.assertIsNone(resp.result)
        self.assertIn("Invalid issue number", resp.error)
        get.assert_not_called()

    def test_missing_issue_number_returns_validation_error(self):
        with authed(), patch.object(github_client.requests, "get") as get:
            resp = call_tool("/tools/get_issue", {"uid": "u1"})

        self.assertIn("required", resp.error)
        get.assert_not_called()

    def test_404_reports_not_found(self):
        with authed(), patch.object(
            github_client.requests,
            "get",
            return_value=FakeResponse({"message": "Not Found"}, status_code=404),
        ):
            resp = call_tool("/tools/get_issue", {"uid": "u1", "issue_number": 99})

        self.assertIsNone(resp.result)
        self.assertIn("not found", resp.error.lower())

    def test_api_error_is_propagated_not_reported_as_not_found(self):
        # A 403 rate-limit must surface the GitHub error, not "not found".
        with authed(), patch.object(
            github_client.requests,
            "get",
            return_value=FakeResponse({"message": "API rate limit exceeded"}, status_code=403),
        ):
            resp = call_tool("/tools/get_issue", {"uid": "u1", "issue_number": 99})

        self.assertIsNone(resp.result)
        self.assertIn("403", resp.error)
        self.assertIn("rate limit", resp.error.lower())


# ---- tool_add_comment ----------------------------------------------------


class AddCommentToolTests(unittest.TestCase):
    def test_hash_prefixed_issue_number_is_coerced(self):
        with authed(), patch.object(
            github_client.requests,
            "post",
            return_value=FakeResponse(
                {"id": 1, "html_url": "https://github.com/owner/repo/issues/7#issuecomment-1"},
                status_code=201,
            ),
        ) as post:
            resp = call_tool(
                "/tools/add_comment",
                {"uid": "u1", "issue_number": "#7", "body": "hello"},
            )

        self.assertIsNone(resp.error)
        self.assertIn("#7", resp.result)
        self.assertTrue(post.call_args.args[0].endswith("/repos/owner/repo/issues/7/comments"))

    def test_non_numeric_issue_number_returns_validation_error(self):
        with authed(), patch.object(github_client.requests, "post") as post:
            resp = call_tool(
                "/tools/add_comment",
                {"uid": "u1", "issue_number": "seven", "body": "hello"},
            )

        self.assertIsNone(resp.result)
        self.assertIn("Invalid issue number", resp.error)
        post.assert_not_called()

    def test_api_error_is_propagated(self):
        with authed(), patch.object(
            github_client.requests,
            "post",
            return_value=FakeResponse({"message": "Resource not accessible"}, status_code=403),
        ):
            resp = call_tool(
                "/tools/add_comment",
                {"uid": "u1", "issue_number": 7, "body": "hello"},
            )

        self.assertIsNone(resp.result)
        self.assertIn("Resource not accessible", resp.error)


# ---- tool_list_issues ----------------------------------------------------


class ListIssuesToolTests(unittest.TestCase):
    def test_api_error_is_not_reported_as_empty(self):
        # Regression: a 401 must not surface as "No open issues found".
        with authed(), patch.object(
            github_client.requests,
            "get",
            return_value=FakeResponse({"message": "Bad credentials"}, status_code=401),
        ):
            resp = call_tool("/tools/list_issues", {"uid": "u1"})

        self.assertIsNone(resp.result)
        self.assertIn("401", resp.error)
        self.assertIn("Bad credentials", resp.error)

    def test_pull_requests_cannot_starve_the_limit(self):
        # Page 1 is all pull requests; page 2 holds real issues.
        with authed(), patch.object(
            github_client.requests,
            "get",
            side_effect=[
                FakeResponse(
                    [issue_payload(1, pull_request=True), issue_payload(2, pull_request=True)],
                    links={"next": {"url": "page-2"}},
                ),
                FakeResponse([issue_payload(3), issue_payload(4)]),
            ],
        ) as get:
            resp = call_tool("/tools/list_issues", {"uid": "u1", "limit": 2})

        self.assertIsNone(resp.error)
        self.assertIn("#3", resp.result)
        self.assertIn("#4", resp.result)
        self.assertNotIn("#1", resp.result)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["page"], 2)

    def test_string_limit_is_coerced(self):
        with authed(), patch.object(
            github_client.requests, "get", return_value=FakeResponse([issue_payload(1)])
        ):
            resp = call_tool("/tools/list_issues", {"uid": "u1", "limit": "1"})

        self.assertIsNone(resp.error)
        self.assertIn("#1", resp.result)

    def test_null_limit_uses_default(self):
        with authed(), patch.object(
            github_client.requests, "get", return_value=FakeResponse([issue_payload(1)])
        ):
            resp = call_tool("/tools/list_issues", {"uid": "u1", "limit": None})

        self.assertIsNone(resp.error)
        self.assertIn("#1", resp.result)

    def test_invalid_limit_returns_validation_error(self):
        with authed(), patch.object(github_client.requests, "get") as get:
            resp = call_tool("/tools/list_issues", {"uid": "u1", "limit": "lots"})

        self.assertIsNone(resp.result)
        self.assertIn("Invalid limit", resp.error)
        get.assert_not_called()

    def test_invalid_state_returns_validation_error(self):
        with authed(), patch.object(github_client.requests, "get") as get:
            resp = call_tool("/tools/list_issues", {"uid": "u1", "state": "bogus"})

        self.assertIsNone(resp.result)
        self.assertIn("Invalid state", resp.error)
        get.assert_not_called()

    def test_empty_repo_still_reports_no_issues(self):
        with authed(), patch.object(
            github_client.requests, "get", return_value=FakeResponse([])
        ):
            resp = call_tool("/tools/list_issues", {"uid": "u1"})

        self.assertIsNone(resp.error)
        self.assertIn("No open issues found", resp.result)


# ---- client return shapes ------------------------------------------------


class ClientContractTests(unittest.TestCase):
    def test_list_issues_returns_error_structure_on_failure(self):
        client = github_client.GitHubClient()
        with patch.object(
            github_client.requests,
            "get",
            return_value=FakeResponse({"message": "Not Found"}, status_code=404),
        ):
            result = client.list_issues("tok", "owner/repo")

        self.assertEqual(result["status"], 404)
        self.assertIn("Not Found", result["error"])

    def test_get_issue_returns_error_structure_on_failure(self):
        client = github_client.GitHubClient()
        with patch.object(
            github_client.requests,
            "get",
            return_value=FakeResponse({"message": "Bad credentials"}, status_code=401),
        ):
            result = client.get_issue("tok", "owner/repo", 1)

        self.assertEqual(result["status"], 401)
        self.assertIn("Bad credentials", result["error"])

    def test_get_issue_success_wraps_issue(self):
        client = github_client.GitHubClient()
        with patch.object(
            github_client.requests, "get", return_value=FakeResponse(issue_payload(5))
        ):
            result = client.get_issue("tok", "owner/repo", 5)

        self.assertNotIn("error", result)
        self.assertEqual(result["issue"]["number"], 5)


if __name__ == "__main__":
    unittest.main()
