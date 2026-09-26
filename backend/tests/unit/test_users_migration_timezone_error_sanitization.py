"""Hermetic error sanitization tests for backend/routers/users.py.

Verifies:
1. Migration handlers (conversation, memory, chat message) sanitize raw exception reflections
   from HTTPException details while recording type(e).__name__ in server logs.
2. Timezone boundary calculation handlers across user endpoints sanitize raw exception text
   into standard generic messages ('Failed to calculate user timezone boundaries').
3. AST structural audit guarantees zero {e} or str(e) reflections remain in these handlers.
"""

import ast
from pathlib import Path
import unittest

ROUTER_PATH = Path(__file__).resolve().parents[2] / "routers" / "users.py"


class UsersMigrationTimezoneErrorSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.router_text = ROUTER_PATH.read_text(encoding="utf-8")

    def test_migration_conversation_no_exception_leak(self):
        self.assertIn('detail=f"Failed to migrate conversation {request.id}"', self.router_text)
        self.assertNotIn('detail=f"Failed to migrate conversation {request.id}: {e}"', self.router_text)
        self.assertIn("Failed to migrate conversation {request.id}: {type(e).__name__}", self.router_text)

    def test_migration_memory_no_exception_leak(self):
        self.assertIn('detail=f"Failed to migrate memory {request.id}"', self.router_text)
        self.assertNotIn('detail=f"Failed to migrate memory {request.id}: {e}"', self.router_text)
        self.assertIn("Failed to migrate memory {request.id}: {type(e).__name__}", self.router_text)

    def test_migration_chat_no_exception_leak(self):
        self.assertIn('detail=f"Failed to migrate chat message {request.id}"', self.router_text)
        self.assertNotIn('detail=f"Failed to migrate chat message {request.id}: {e}"', self.router_text)
        self.assertIn("Failed to migrate chat message {request.id}: {type(e).__name__}", self.router_text)

    def test_batch_migration_no_exception_leak(self):
        self.assertIn('errors.append(f"Failed to migrate batch of type {req_type}")', self.router_text)
        self.assertNotIn('f"Failed to migrate batch of type {req_type}: {e}"', self.router_text)
        self.assertIn("Failed to migrate batch of type {req_type}: {type(e).__name__}", self.router_text)

    def test_timezone_errors_sanitized(self):
        self.assertIn("detail='Failed to calculate user timezone boundaries'", self.router_text)
        self.assertNotIn("detail=f'Timezone error: {str(e)}'", self.router_text)
        self.assertIn("Timezone calculation error for user {uid}: {type(e).__name__}", self.router_text)

    def test_ast_audit_no_migration_or_timezone_exception_leak(self):
        tree = ast.parse(self.router_text)
        for node in ast.walk(tree):
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
                                        val, {"e", "str(e)"}, f"Raw exception reflection found in users.py: {val}"
                                    )


if __name__ == "__main__":
    unittest.main()
