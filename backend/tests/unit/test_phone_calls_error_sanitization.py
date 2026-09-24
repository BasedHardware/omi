"""Hermetic error sanitization tests for backend/routers/phone_calls.py.

Verifies that unexpected exceptions, internal Twilio traces, and sensitive details
never leak into client-facing HTTPException detail payloads.
"""

import ast
from pathlib import Path
import unittest

ROUTER_PATH = Path(__file__).resolve().parents[2] / "routers" / "phone_calls.py"


class PhoneCallsErrorSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.router_text = ROUTER_PATH.read_text(encoding="utf-8")

    def test_verification_error_sanitized(self):
        # Must raise generic message, not f"... {str(e)}"
        self.assertIn('detail="Failed to start verification"', self.router_text)
        self.assertNotIn('detail=f"Failed to start verification: {str(e)}"', self.router_text)
        # Server logging should use type(e).__name__
        self.assertIn("Failed to start phone verification: {type(e).__name__}", self.router_text)

    def test_token_error_sanitized(self):
        # Must raise generic message, not f"... {str(e)}"
        self.assertIn('detail="Failed to generate token"', self.router_text)
        self.assertNotIn('detail=f"Failed to generate token: {str(e)}"', self.router_text)
        # Server logging should use type(e).__name__
        self.assertIn("Failed to generate phone token: {type(e).__name__}", self.router_text)

    def test_ast_audit_no_exception_leak(self):
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
                                        val,
                                        {"e", "exc", "err", "str(e)", "str(exc)"},
                                        f"Raw exception reflection found in phone_calls.py: {val}",
                                    )


if __name__ == "__main__":
    unittest.main()
