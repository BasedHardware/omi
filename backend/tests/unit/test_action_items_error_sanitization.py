"""Hermetic unit tests for error sanitization in action_items router.

Verifies that:
1. TaskRelationshipConflictError exception details are sanitized across create_action_item,
   update_action_item, and create_action_items_batch.
2. Domain validation messages pass through cleanly, while arbitrary/internal errors fall back
   to a standardized message without leaking database internals or tracebacks.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "***")

import pytest
from fastapi import HTTPException

import database.action_items as action_items_db
from routers import action_items as action_items_router

BACKEND_DIR = Path(__file__).resolve().parents[2]
ACTION_ITEMS_ROUTER_FILE = BACKEND_DIR / "routers" / "action_items.py"


def test_sanitize_task_relationship_error_safe_messages():
    sanitize = getattr(action_items_router, "_sanitize_task_relationship_error", None)
    assert sanitize is not None, "_sanitize_task_relationship_error must be implemented in routers.action_items"

    fallback = "Task relationship conflict"

    safe_cases = [
        "goal does not exist",
        "goal account generation mismatch",
        "ended goal cannot receive new task links",
        "workstream does not exist",
        "workstream account generation mismatch",
        "task goal_id must match workstream goal_id",
        "document id belongs to another account generation",
    ]

    for safe in safe_cases:
        err = action_items_db.TaskRelationshipConflictError(safe)
        assert sanitize(err, fallback) == safe


def test_sanitize_task_relationship_error_filters_sensitive_internals():
    sanitize = getattr(action_items_router, "_sanitize_task_relationship_error", None)
    assert sanitize is not None, "_sanitize_task_relationship_error must be implemented in routers.action_items"

    fallback = "Task relationship conflict"

    sensitive_cases = [
        "internal firestore transaction contention: /databases/(default)/documents/users/u1/action_items/x",
        "Traceback (most recent call last):\n  File 'db.py', line 12\nKeyError: 'workstream_id'",
        "PostgresDeadlockDetected: process 9218 waiting for ShareLock on transaction 88129",
        "",
        "   ",
        "some unknown arbitrary database conflict detail",
    ]

    for leak in sensitive_cases:
        err = action_items_db.TaskRelationshipConflictError(leak)
        assert sanitize(err, fallback) == fallback


def test_no_raw_str_exc_in_task_relationship_handlers():
    source = ACTION_ITEMS_ROUTER_FILE.read_text(encoding="utf-8")
    assert "_sanitize_task_relationship_error" in source

    chunks = source.split("TaskRelationshipConflictError as exc:")[1:]
    assert len(chunks) == 3, f"Expected 3 TaskRelationshipConflictError handlers, found {len(chunks)}"

    for chunk in chunks:
        handler_block = chunk[:200]
        assert "detail=str(exc)" not in handler_block
        assert "_sanitize_task_relationship_error" in handler_block


def test_create_action_item_sanitizes_conflict():
    create_action_item = action_items_router.create_action_item

    req_mock = MagicMock()
    req_mock.goal_id = "g-1"
    req_mock.workstream_id = "w-1"
    req_mock.storage_payload.return_value = {"description": "test"}

    # 1. Known safe message propagates cleanly
    with patch.object(action_items_router.task_links, "validate_task_links"), patch.object(
        action_items_router.action_items_db,
        "create_action_item",
        side_effect=action_items_db.TaskRelationshipConflictError("goal does not exist"),
    ):
        with pytest.raises(HTTPException) as ctx:
            create_action_item(req_mock, uid="user-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "goal does not exist"

    # 2. Raw internal exception details are sanitized
    with patch.object(action_items_router.task_links, "validate_task_links"), patch.object(
        action_items_router.action_items_db,
        "create_action_item",
        side_effect=action_items_db.TaskRelationshipConflictError("firestore document internal lock failure"),
    ):
        with pytest.raises(HTTPException) as ctx:
            create_action_item(req_mock, uid="user-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "Task relationship conflict"
