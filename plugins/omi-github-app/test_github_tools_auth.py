"""Hermetic regression tests for the GitHub App chat-tools and settings routes shared-secret guard.

Before this fix, all /tools/* and settings routes trusted the uid,
allowing unauthenticated callers to read private repo lists, inspect issues,
create issues, add comments, overwrite agent keys/providers, or trigger agent
code execution using the victim's stored GitHub OAuth access token.

Covers:
- require_github_tools_auth: 503 when unconfigured/blank, 401 on missing/wrong
  token, bearer + query token accepted (both tools and settings tokens/secrets).
- Route wiring: asserts that all 8 chat-tool routes and all 7 settings routes carry
  the shared-secret dependency, and that public browser setup routes remain unguarded.

fastapi is stubbed if not installed so the suite runs without third-party packages.
"""

import ast
import importlib.util
import os
import sys
from types import ModuleType
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent
SECRET = "test-github-tools-secret"
SETTINGS_SECRET = "test-github-settings-secret"

CHAT_TOOL_PATHS = {
    "/tools/create_issue",
    "/tools/list_repos",
    "/tools/list_issues",
    "/tools/get_issue",
    "/tools/list_labels",
    "/tools/add_issue_comment",
    "/tools/add_comment",
    "/tools/code_feature",
}

SETTINGS_PATHS = {
    "/update-repo",
    "/refresh-repos",
    "/check-repo-access",
    "/save-agent-provider",
    "/save-agent-key",
    "/delete-agent-key",
    "/test-agent",
}

BROWSER_SETUP_PATHS = {
    "/",
    "/auth",
    "/auth/callback",
    "/setup-completed",
    "/health",
    "/.well-known/omi-tools.json",
    "/manifest.json",
}


class _StubHTTPException(Exception):
    def __init__(self, status_code=None, detail=None, **kwargs):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _load_auth_module():
    """Load github_tools_auth.py with fastapi stubbed if not present."""
    module_name = "github_tools_auth_test_target"
    if module_name in sys.modules:
        del sys.modules[module_name]

    fastapi_stub = ModuleType("fastapi")
    fastapi_stub.HTTPException = _StubHTTPException
    fastapi_stub.Request = object

    with patch.dict(sys.modules, {"fastapi": fastapi_stub}):
        spec = importlib.util.spec_from_file_location(
            module_name,
            APP_DIR / "github_tools_auth.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestGitHubToolsAuth(unittest.TestCase):
    def setUp(self):
        self.mod = _load_auth_module()

    def test_missing_secret_fails_closed_with_503(self):
        with patch.dict(os.environ, {}, clear=True):
            req = _FakeRequest(headers={"Authorization": "Bearer any"})
            with self.assertRaises(self.mod.HTTPException) as ctx:
                self.mod.require_github_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 503)

    def test_blank_secret_fails_closed_with_503(self):
        with patch.dict(os.environ, {"GITHUB_TOOLS_SECRET": "   "}, clear=True):
            req = _FakeRequest(headers={"Authorization": "Bearer any"})
            with self.assertRaises(self.mod.HTTPException) as ctx:
                self.mod.require_github_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_returns_401(self):
        with patch.dict(os.environ, {"GITHUB_TOOLS_SECRET": SECRET}, clear=True):
            req = _FakeRequest()
            with self.assertRaises(self.mod.HTTPException) as ctx:
                self.mod.require_github_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_bearer_token_returns_401(self):
        with patch.dict(os.environ, {"GITHUB_TOOLS_SECRET": SECRET}, clear=True):
            req = _FakeRequest(headers={"Authorization": "Bearer wrong-token"})
            with self.assertRaises(self.mod.HTTPException) as ctx:
                self.mod.require_github_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_correct_bearer_token_succeeds(self):
        with patch.dict(os.environ, {"GITHUB_TOOLS_SECRET": SECRET}, clear=True):
            req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
            self.assertIsNone(self.mod.require_github_tools_auth(req))

    def test_correct_query_token_succeeds(self):
        with patch.dict(os.environ, {"GITHUB_TOOLS_SECRET": SECRET}, clear=True):
            req = _FakeRequest(query_params={"github_tools_token": SECRET})
            self.assertIsNone(self.mod.require_github_tools_auth(req))

    def test_settings_secret_env_succeeds(self):
        with patch.dict(os.environ, {"GITHUB_SETTINGS_SECRET": SETTINGS_SECRET}, clear=True):
            req = _FakeRequest(query_params={"github_settings_token": SETTINGS_SECRET})
            self.assertIsNone(self.mod.require_github_tools_auth(req))

    def test_wrong_query_token_returns_401(self):
        with patch.dict(os.environ, {"GITHUB_TOOLS_SECRET": SECRET}, clear=True):
            req = _FakeRequest(query_params={"github_tools_token": "wrong"})
            with self.assertRaises(self.mod.HTTPException) as ctx:
                self.mod.require_github_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 401)


class TestGitHubToolsRouteWiring(unittest.TestCase):
    """Verify that all chat tool routes and settings routes carry the guard."""

    @classmethod
    def setUpClass(cls):
        main_path = APP_DIR / "main.py"
        cls.tree = ast.parse(main_path.read_text(encoding="utf-8"))

    def _extract_routes(self):
        route_guards = {}
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and hasattr(dec.func, "attr"):
                        if dec.func.attr in ("post", "get"):
                            if dec.args and isinstance(dec.args[0], ast.Constant):
                                path = dec.args[0].value
                                guards = []
                                for kw in dec.keywords:
                                    if kw.arg == "dependencies" and isinstance(kw.value, ast.List):
                                        for elt in kw.value.elts:
                                            if isinstance(elt, ast.Call):
                                                for arg in elt.args:
                                                    if isinstance(arg, ast.Name):
                                                        guards.append(arg.id)
                                route_guards[path] = guards
        return route_guards

    def test_all_chat_tool_routes_guarded(self):
        routes = self._extract_routes()
        for path in CHAT_TOOL_PATHS:
            self.assertIn(path, routes, f"Chat tool route {path} not found in main.py")
            self.assertIn(
                "require_github_tools_auth",
                routes[path],
                f"Chat tool route {path} missing require_github_tools_auth dependency",
            )

    def test_all_settings_routes_guarded(self):
        routes = self._extract_routes()
        for path in SETTINGS_PATHS:
            self.assertIn(path, routes, f"Settings route {path} not found in main.py")
            self.assertIn(
                "require_github_tools_auth",
                routes[path],
                f"Settings route {path} missing require_github_tools_auth dependency",
            )

    def test_browser_setup_routes_not_guarded(self):
        routes = self._extract_routes()
        for path in BROWSER_SETUP_PATHS:
            if path in routes:
                self.assertNotIn(
                    "require_github_tools_auth",
                    routes[path],
                    f"Browser route {path} must NOT carry require_github_tools_auth",
                )

    def test_import_fails_closed_without_noop_lambda_fallback(self):
        """Assert main.py does not define a no-op lambda fallback for require_github_tools_auth."""
        main_source = (APP_DIR / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("require_github_tools_auth = lambda", main_source)


if __name__ == "__main__":
    unittest.main()
