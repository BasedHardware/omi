"""Hermetic unit tests for error sanitization in action_items router.

Verifies that:
1. TaskRelationshipConflictError exception details are sanitized across create_action_item,
   update_action_item, and create_action_items_batch.
2. TaskLinkValidationError exception details are sanitized across create_action_item,
   update_action_item, and create_action_items_batch.
3. Domain validation messages pass through cleanly, while arbitrary/internal errors fall back
   to a standardized message without leaking database internals or tracebacks.
4. SAFE_TASK_RELATIONSHIP_MESSAGES is exported as a module constant.
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
from utils.task_intelligence import task_links

BACKEND_DIR = Path(__file__).resolve().parents[2]
ACTION_ITEMS_ROUTER_FILE = BACKEND_DIR / "routers" / "action_items.py"


def test_safe_task_relationship_messages_constant():
    safe_messages = getattr(action_items_router, "SAFE_TASK_RELATIONSHIP_MESSAGES", None)
    assert safe_messages is not None, "SAFE_TASK_RELATIONSHIP_MESSAGES must be exported as a module constant"

    expected = {
        "goal does not exist",
        "goal account generation mismatch",
        "ended goal cannot receive new task links",
        "workstream does not exist",
        "workstream account generation mismatch",
        "task goal_id must match workstream goal_id",
        "document id belongs to another account generation",
    }
    assert set(safe_messages) == expected


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

        link_err = task_links.TaskLinkValidationError(safe)
        assert sanitize(link_err, fallback) == safe


def test_sanitize_task_relationship_error_filters_sensitive_internals():
    sanitize = getattr(action_items_router, "_sanitize_task_relationship_error", None)
    assert sanitize is not None, "_sanitize_task_relationship_error must be implemented in routers.action_items"

    fallback = "Task relationship conflict"

    sensitive_cases = [
        "internal firestore transaction contention: /databases/(default)/documents/users/u1/action_items/x",
        "Traceback (most recent call last):\n  File 'db.py', line 12\nKeyError: 'workstream_id'",
        "PostgresDeadlockDetected: process 9218 waiting for ShareLock on transaction 88129",
        "Ticket 04 workstream goal resolver is not registered",
        "Ticket 04 goal resolver is not registered",
        "",
        "   ",
        "some unknown arbitrary database conflict detail",
    ]

    for leak in sensitive_cases:
        err = action_items_db.TaskRelationshipConflictError(leak)
        assert sanitize(err, fallback) == fallback

        link_err = task_links.TaskLinkValidationError(leak)
        assert sanitize(link_err, fallback) == fallback


def test_no_raw_str_exc_in_task_relationship_handlers():
    source = ACTION_ITEMS_ROUTER_FILE.read_text(encoding="utf-8")
    assert "_sanitize_task_relationship_error" in source

    chunks = source.split("TaskRelationshipConflictError as exc:")[1:]
    assert len(chunks) == 3, f"Expected 3 TaskRelationshipConflictError handlers, found {len(chunks)}"

    for chunk in chunks:
        handler_block = chunk[:200]
        assert "detail=str(exc)" not in handler_block
        assert "_sanitize_task_relationship_error" in handler_block


def test_no_raw_str_exc_in_task_link_validation_handlers():
    source = ACTION_ITEMS_ROUTER_FILE.read_text(encoding="utf-8")

    chunks = source.split("TaskLinkValidationError as exc:")[1:]
    assert len(chunks) == 3, f"Expected 3 TaskLinkValidationError handlers, found {len(chunks)}"

    for chunk in chunks:
        handler_block = chunk[:200]
        assert "detail=str(exc)" not in handler_block, "TaskLinkValidationError must not reflect detail=str(exc)"
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


def test_task_link_validation_error_sanitization_in_endpoints():
    req_mock = MagicMock()
    req_mock.goal_id = "g-1"
    req_mock.workstream_id = "w-1"
    req_mock.model_fields_set = {"goal_id", "workstream_id"}
    req_mock.description = None
    req_mock.completed = False
    req_mock.status = "open"
    req_mock.owner = None
    req_mock.storage_payload.return_value = {"description": "test"}

    # 1. create_action_item with safe message
    with patch.object(
        action_items_router.task_links,
        "validate_task_links",
        side_effect=task_links.TaskLinkValidationError("goal does not exist"),
    ):
        with pytest.raises(HTTPException) as ctx:
            action_items_router.create_action_item(req_mock, uid="user-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "goal does not exist"

    # 2. create_action_item with internal message (e.g. resolver unregistered)
    with patch.object(
        action_items_router.task_links,
        "validate_task_links",
        side_effect=task_links.TaskLinkResolverUnavailableError("Ticket 04 goal resolver is not registered"),
    ):
        with pytest.raises(HTTPException) as ctx:
            action_items_router.create_action_item(req_mock, uid="user-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "Task relationship conflict"

    # 3. update_action_item with internal message
    with patch.object(
        action_items_router.action_items_db,
        "get_action_item",
        return_value={"id": "act-1", "goal_id": "g-old", "workstream_id": "w-old"},
    ), patch.object(
        action_items_router.task_links,
        "validate_task_links",
        side_effect=task_links.TaskLinkValidationError("internal leak in link check"),
    ):
        with pytest.raises(HTTPException) as ctx:
            action_items_router.update_action_item("act-1", req_mock, uid="user-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "Task relationship conflict"

    # 4. create_action_items_batch with internal message
    batch_item = MagicMock()
    batch_item.goal_id = "g-1"
    batch_item.workstream_id = "w-1"
    batch_item.storage_payload.return_value = {"description": "test"}
    with patch.object(
        action_items_router.task_links,
        "validate_task_links",
        side_effect=task_links.TaskLinkValidationError("sensitive internal db traceback"),
    ):
        with pytest.raises(HTTPException) as ctx:
            action_items_router.create_action_items_batch([batch_item], uid="user-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "Task relationship conflict"
