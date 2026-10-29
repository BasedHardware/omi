"""Hermetic unit and behavioral tests for error sanitization in the goals router.

Verifies that:
1. _sanitize_goal_conflict_error uses an allowlist for known domain conflict messages,
   filtering unexpected tracebacks, internal database strings, and exceptions to a safe generic detail.
2. _raise_goal_store_error sanitizes GoalConflictError details, preserves 404 for GoalNotFoundError,
   and catches unexpected GoalStoreError with a safe HTTP 500 instead of re-raising unhandled.
3. Both create_goal and _raise_goal_store_error route through _sanitize_goal_conflict_error.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "***")

import database.goals as goals_db
from routers import goals as goals_router

BACKEND_DIR = Path(__file__).resolve().parents[2]
GOALS_ROUTER_FILE = BACKEND_DIR / "routers" / "goals.py"


def _get_function_source(function_name: str) -> str:
    source = GOALS_ROUTER_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


def test_create_goal_source_uses_sanitizer():
    source = _get_function_source("create_goal")
    assert "_sanitize_goal_conflict_error" in source
    assert "detail=str(exc)" not in source


def test_raise_goal_store_error_source_handles_all_cases():
    source = _get_function_source("_raise_goal_store_error")
    assert "_sanitize_goal_conflict_error" in source
    assert "logger.error" in source
    assert 'status_code=500, detail="Failed to process goal operation"' in source
    assert "raise exc" not in source


def test_sanitize_goal_conflict_error_allowlist_and_fallback():
    sanitize = getattr(goals_router, "_sanitize_goal_conflict_error", None)
    assert sanitize is not None, "_sanitize_goal_conflict_error must be defined in routers.goals"

    GoalConflictError = goals_db.GoalConflictError

    # 1. Closed allowlist of known safe conflict reasons returned as-is
    assert sanitize(GoalConflictError("account generation mismatch")) == "account generation mismatch"
    assert (
        sanitize(GoalConflictError("idempotency key was reused with different content"))
        == "idempotency key was reused with different content"
    )
    assert sanitize(GoalConflictError("focus full")) == "focus full"
    assert sanitize(GoalConflictError("ended goals cannot be focused")) == "ended goals cannot be focused"

    # 2. Unknown or arbitrary conflict messages strictly fall back to generic message
    assert (
        sanitize(GoalConflictError("some arbitrary unapproved conflict detail"))
        == "Goal conflict encountered. Please verify goal state and retry."
    )

    # 3. Raw traceback filtered to generic message
    raw_tb = "Traceback (most recent call last):\n  File 'goals.py', line 10\nRuntimeError: connection lost"
    assert sanitize(GoalConflictError(raw_tb)) == "Goal conflict encountered. Please verify goal state and retry."

    # 4. Internal database error string with markers filtered to generic message
    unrecognized = "google.cloud.exceptions.Conflict: Firestore write lock timeout at doc/users/123/goals"
    assert sanitize(GoalConflictError(unrecognized)) == "Goal conflict encountered. Please verify goal state and retry."

    # 5. Empty exception message filtered to generic message
    assert sanitize(GoalConflictError("")) == "Goal conflict encountered. Please verify goal state and retry."


def test_raise_goal_store_error_behavioral_contract():
    raise_store_error = getattr(goals_router, "_raise_goal_store_error", None)
    assert raise_store_error is not None, "_raise_goal_store_error must be defined in routers.goals"

    # 1. GoalNotFoundError raises 404
    with pytest.raises(HTTPException) as ctx:
        raise_store_error(goals_db.GoalNotFoundError("goal missing"))
    assert ctx.value.status_code == 404
    assert ctx.value.detail == "Goal not found"

    # 2. GoalConflictError with known cause raises 409 with exact cause
    with pytest.raises(HTTPException) as ctx:
        raise_store_error(goals_db.GoalConflictError("account generation mismatch"))
    assert ctx.value.status_code == 409
    assert ctx.value.detail == "account generation mismatch"

    # 3. GoalConflictError with sensitive traceback raises 409 sanitized
    sensitive_tb = "Traceback (most recent call last):\n  File 'app.py'\nKeyError: internal_key"
    with pytest.raises(HTTPException) as ctx:
        raise_store_error(goals_db.GoalConflictError(sensitive_tb))
    assert ctx.value.status_code == 409
    assert ctx.value.detail == "Goal conflict encountered. Please verify goal state and retry."
    assert "Traceback" not in ctx.value.detail
    assert "KeyError" not in ctx.value.detail

    # 4. Unexpected GoalStoreError raises bounded 500 without leaking internal error
    with pytest.raises(HTTPException) as ctx:
        raise_store_error(goals_db.GoalStoreError("CRITICAL: Redis cluster unreachable at 10.0.0.1:6379"))
    assert ctx.value.status_code == 500
    assert ctx.value.detail == "Failed to process goal operation"
    assert "Redis" not in ctx.value.detail
    assert "10.0.0.1" not in ctx.value.detail
