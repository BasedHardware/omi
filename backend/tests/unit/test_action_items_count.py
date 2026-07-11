"""Unit tests for the action-items count endpoint (GET /v1/action-items/count).

The count uses Firestore count() aggregation so a client can render a badge or
summary without paging every item. These tests pin the total/completed/incomplete
arithmetic and the endpoint wiring without any live Firestore.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.action_items as ai_db  # noqa: E402


def _count_result(value):
    # Firestore aggregation returns [[AggregationResult(value=...)]].
    return [[SimpleNamespace(value=value)]]


def test_get_action_items_count_arithmetic():
    fake_db = MagicMock()
    items_ref = fake_db.collection.return_value.document.return_value.collection.return_value
    items_ref.count.return_value.get.return_value = _count_result(5)
    items_ref.where.return_value.count.return_value.get.return_value = _count_result(2)

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count("uid-1")

    assert result == {"total": 5, "completed": 2, "incomplete": 3}
    # Completed filter is a count aggregation on the completed==True subset, not a full read.
    items_ref.where.assert_called_once()


def test_get_action_items_count_never_negative():
    # Defensive: if an eventually-consistent aggregation reports completed > total,
    # incomplete must clamp to 0 rather than go negative.
    fake_db = MagicMock()
    items_ref = fake_db.collection.return_value.document.return_value.collection.return_value
    items_ref.count.return_value.get.return_value = _count_result(1)
    items_ref.where.return_value.count.return_value.get.return_value = _count_result(3)

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count("uid-1")

    assert result == {"total": 1, "completed": 3, "incomplete": 0}


def test_count_endpoint_returns_db_value():
    from routers import action_items as router_mod

    with patch.object(
        router_mod.action_items_db,
        "get_action_items_count",
        return_value={"total": 3, "completed": 1, "incomplete": 2},
    ):
        result = router_mod.get_action_items_count(uid="uid-1")

    assert result == {"total": 3, "completed": 1, "incomplete": 2}
