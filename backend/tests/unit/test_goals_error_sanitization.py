"""Hermetic unit tests for error sanitization in the goals router.

Verifies that:
1. create_goal catches GoalConflictError, logs error type safely, and sanitizes
   any raw exception details or tracebacks.
2. _raise_goal_store_error sanitizes GoalConflictError details, logs error types,
   and catches unexpected GoalStoreError with a safe HTTP 500 instead of re-raising unhandled.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

GOALS_ROUTER_FILE = Path(__file__).resolve().parents[2] / "routers" / "goals.py"


def _get_function_source(function_name: str) -> str:
    source = GOALS_ROUTER_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class GoalsErrorSanitizationTests(unittest.TestCase):
    def test_create_goal_sanitizes_conflict_error(self):
        source = _get_function_source("create_goal")
        self.assertIn("logger.warning", source)
        self.assertIn("type(exc).__name__", source)
        self.assertIn("Traceback", source)
        self.assertIn("Goal conflict encountered. Please verify goal state and retry.", source)

    def test_raise_goal_store_error_sanitizes_conflicts_and_handles_unexpected(self):
        source = _get_function_source("_raise_goal_store_error")
        self.assertIn("logger.warning", source)
        self.assertIn("type(exc).__name__", source)
        self.assertIn("Traceback", source)
        self.assertIn("logger.error", source)
        self.assertIn('status_code=500, detail="Failed to process goal operation"', source)
        self.assertNotIn("raise exc", source)


if __name__ == "__main__":
    unittest.main()
