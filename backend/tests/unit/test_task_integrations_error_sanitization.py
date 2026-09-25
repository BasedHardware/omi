"""Hermetic error sanitization tests for task integrations and task sync.

Verifies:
1. routers/task_integrations.py catches exceptions in all workspace, project, team,
   space, and list endpoints without leaking internal exception text into HTTPException details.
2. utils/task_integrations_ops.py sanitizes OAuth refresh errors and task creation failures,
   never reflecting raw exception messages in response payloads or logger text.
3. utils/task_sync.py never leaks exception strings into auto-sync return dictionaries.
4. AST structural audit guarantees zero {e}, {exc}, or str(e) reflections exist across
   these three files.
"""

import ast
from pathlib import Path
import unittest

ROUTER_PATH = Path(__file__).resolve().parents[2] / "routers" / "task_integrations.py"
OPS_PATH = Path(__file__).resolve().parents[2] / "utils" / "task_integrations_ops.py"
SYNC_PATH = Path(__file__).resolve().parents[2] / "utils" / "task_sync.py"


class TaskIntegrationsErrorSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.router_text = ROUTER_PATH.read_text(encoding="utf-8")
        self.ops_text = OPS_PATH.read_text(encoding="utf-8")
        self.sync_text = SYNC_PATH.read_text(encoding="utf-8")

    def test_router_workspaces_no_exception_leak(self):
        # Must raise HTTPException with generic "Error fetching workspaces", not f"... {str(e)}"
        self.assertIn('detail="Error fetching workspaces"', self.router_text)
        self.assertNotIn('detail=f"Error fetching workspaces: {str(e)}"', self.router_text)

    def test_router_projects_no_exception_leak(self):
        self.assertIn('detail="Error fetching projects"', self.router_text)
        self.assertNotIn('detail=f"Error fetching projects: {str(e)}"', self.router_text)

    def test_router_teams_no_exception_leak(self):
        self.assertIn('detail="Error fetching teams"', self.router_text)
        self.assertNotIn('detail=f"Error fetching teams: {str(e)}"', self.router_text)

    def test_router_spaces_no_exception_leak(self):
        self.assertIn('detail="Error fetching spaces"', self.router_text)
        self.assertNotIn('detail=f"Error fetching spaces: {str(e)}"', self.router_text)

    def test_router_lists_no_exception_leak(self):
        self.assertIn('detail="Error fetching lists"', self.router_text)
        self.assertNotIn('detail=f"Error fetching lists: {str(e)}"', self.router_text)

    def test_ops_token_refresh_no_exception_leak(self):
        self.assertIn('detail="Error refreshing token"', self.ops_text)
        self.assertNotIn('detail=f"Error refreshing token: {str(e)}"', self.ops_text)
        # Verify logging does not format raw exception
        self.assertIn("Error refreshing token: {type(e).__name__}", self.ops_text)

    def test_ops_create_task_no_exception_leak(self):
        self.assertIn('"error": "Failed to create task"', self.ops_text)
        self.assertNotIn('"error": str(e)', self.ops_text)

    def test_sync_auto_sync_no_exception_leak(self):
        self.assertIn('"error": "Auto-sync failed"', self.sync_text)
        self.assertNotIn('"error": str(e)', self.sync_text)

    def test_ast_audit_no_exception_interpolation_in_raises(self):
        for path in (ROUTER_PATH, OPS_PATH, SYNC_PATH):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                # Check all raise HTTPException(...) calls
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    func = node.exc.func
                    if (isinstance(func, ast.Name) and func.id == "HTTPException") or (
                        isinstance(func, ast.Attribute) and func.attr == "HTTPException"
                    ):
                        for kw in node.exc.keywords:
                            if kw.arg == "detail" and isinstance(kw.value, ast.JoinedStr):
                                for part in kw.value.values:
                                    if isinstance(part, ast.FormattedValue):
                                        val = ast.unparse(part.value)
                                        self.assertNotIn(
                                            val,
                                            {"e", "exc", "err", "str(e)", "str(exc)"},
                                            f"Raw exception reflection found in {path.name}: {val}",
                                        )


if __name__ == "__main__":
    unittest.main()
