"""Hermetic unit and behavioral tests for error sanitization in the goals router.

Verifies that:
1. _sanitize_goal_conflict_error uses an allowlist for known domain conflict messages,
   filtering unexpected tracebacks, internal database strings, and exceptions to a safe generic detail.
2. _raise_goal_store_error sanitizes GoalConflictError details, preserves 404 for GoalNotFoundError,
   and catches unexpected GoalStoreError with a safe HTTP 500 instead of re-raising unhandled.
3. Both create_goal and _raise_goal_store_error route through _sanitize_goal_conflict_error.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from types import ModuleType
import unittest
from unittest.mock import MagicMock
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[2]
GOALS_ROUTER_FILE = BACKEND_DIR / "routers" / "goals.py"


def _get_function_source(function_name: str) -> str:
    source = GOALS_ROUTER_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class GoalsErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}
    _sanitize_fn = None
    _raise_fn = None
    _goals_db = None

    @classmethod
    def setUpClass(cls):
        # Stub heavy external and database dependencies inside setUpClass (not module scope)
        g = ModuleType("google")
        g.__path__ = []
        g_api = ModuleType("google.api_core")
        g_api.__path__ = []
        g_api_exc = ModuleType("google.api_core.exceptions")
        g_api_exc.InvalidArgument = type("InvalidArgument", (Exception,), {})

        cls._stubbed_modules = {
            "google": g,
            "google.api_core": g_api,
            "google.api_core.exceptions": g_api_exc,
        }

        mock_mods = [
            "google.cloud",
            "google.cloud.firestore",
            "google.cloud.firestore_v1",
            "database._client",
            "redis",
            "cachetools",
            "database.action_items_cache",
            "database.workstreams",
            "utils.other.endpoints",
            "utils.subscription",
            "utils.goals_response",
            "utils.llm.goals",
            "routers.canonical_task_access",
            "utils.task_intelligence.proactive_engine",
        ]
        for mod in mock_mods:
            cls._stubbed_modules[mod] = MagicMock()

        for k, v in cls._stubbed_modules.items():
            if k not in sys.modules:
                sys.modules[k] = v

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from database import goals as goals_db
        from routers.goals import _sanitize_goal_conflict_error, _raise_goal_store_error

        cls._goals_db = goals_db
        cls._sanitize_fn = staticmethod(_sanitize_goal_conflict_error)
        cls._raise_fn = staticmethod(_raise_goal_store_error)

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_goal_conflict_error_allowlist_behavior(self):
        sanitize = self._sanitize_fn
        GoalConflictError = self._goals_db.GoalConflictError

        # 1. Closed allowlist of known safe conflict reasons returned as-is
        self.assertEqual(
            sanitize(GoalConflictError("account generation mismatch")),
            "account generation mismatch",
        )
        self.assertEqual(
            sanitize(GoalConflictError("idempotency key was reused with different content")),
            "idempotency key was reused with different content",
        )
        self.assertEqual(
            sanitize(GoalConflictError("focus full")),
            "focus full",
        )
        self.assertEqual(
            sanitize(GoalConflictError("ended goals cannot be focused")),
            "ended goals cannot be focused",
        )

        # 2. Unknown or arbitrary conflict messages strictly fall back to generic message
        self.assertEqual(
            sanitize(GoalConflictError("some arbitrary unapproved conflict detail")),
            "Goal conflict encountered. Please verify goal state and retry.",
        )

        # 2. Raw traceback filtered to generic message
        raw_tb = "Traceback (most recent call last):\n  File 'goals.py', line 10\nRuntimeError: connection lost"
        self.assertEqual(
            sanitize(GoalConflictError(raw_tb)),
            "Goal conflict encountered. Please verify goal state and retry.",
        )

        # 3. Internal database error string with markers filtered to generic message
        unrecognized = "google.cloud.exceptions.Conflict: Firestore write lock timeout at doc/users/123/goals"
        self.assertEqual(
            sanitize(GoalConflictError(unrecognized)),
            "Goal conflict encountered. Please verify goal state and retry.",
        )

        # 4. Multiline error text filtered to generic message
        self.assertEqual(
            sanitize(GoalConflictError("line 1\nline 2 error details")),
            "Goal conflict encountered. Please verify goal state and retry.",
        )

        # 5. Empty exception message filtered to generic message
        self.assertEqual(
            sanitize(GoalConflictError("")),
            "Goal conflict encountered. Please verify goal state and retry.",
        )

    def test_raise_goal_store_error_behavioral_contract(self):
        raise_store_error = self._raise_fn
        goals_db = self._goals_db

        # 1. GoalNotFoundError raises 404
        with self.assertRaises(HTTPException) as ctx:
            raise_store_error(goals_db.GoalNotFoundError("goal missing"))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Goal not found")

        # 2. GoalConflictError with known cause raises 409 with exact cause
        with self.assertRaises(HTTPException) as ctx:
            raise_store_error(goals_db.GoalConflictError("account generation mismatch"))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "account generation mismatch")

        # 3. GoalConflictError with sensitive traceback raises 409 sanitized
        sensitive_tb = "Traceback (most recent call last):\n  File 'app.py'\nKeyError: internal_key"
        with self.assertRaises(HTTPException) as ctx:
            raise_store_error(goals_db.GoalConflictError(sensitive_tb))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "Goal conflict encountered. Please verify goal state and retry.")
        self.assertNotIn("Traceback", ctx.exception.detail)
        self.assertNotIn("KeyError", ctx.exception.detail)

        # 4. Unexpected GoalStoreError raises bounded 500 without leaking internal error
        with self.assertRaises(HTTPException) as ctx:
            raise_store_error(goals_db.GoalStoreError("CRITICAL: Redis cluster unreachable at 10.0.0.1:6379"))
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "Failed to process goal operation")
        self.assertNotIn("Redis", ctx.exception.detail)
        self.assertNotIn("10.0.0.1", ctx.exception.detail)

    def test_create_goal_source_uses_sanitizer(self):
        source = _get_function_source("create_goal")
        self.assertIn("_sanitize_goal_conflict_error", source)
        self.assertNotIn("detail=str(exc)", source)

    def test_raise_goal_store_error_source_handles_all_cases(self):
        source = _get_function_source("_raise_goal_store_error")
        self.assertIn("_sanitize_goal_conflict_error", source)
        self.assertIn("logger.error", source)
        self.assertIn('status_code=500, detail="Failed to process goal operation"', source)
        self.assertNotIn("raise exc", source)


if __name__ == "__main__":
    unittest.main()
