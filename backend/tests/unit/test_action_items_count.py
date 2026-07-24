"""Unit tests for the action-items count endpoint (GET /v1/action-items/count).

The count uses Firestore count() aggregation so a client can render a badge or
summary without paging every item. Soft-retired items (``deleted: true``) are
hidden from the list/read paths, so the count must exclude them too. These tests
pin the total/completed/incomplete arithmetic and the deleted-exclusion without any
live Firestore.
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


def _deleted_doc(completed):
    doc = MagicMock()
    doc.to_dict.return_value = {"completed": completed, "deleted": True}
    return doc


def _fake_items_ref(fake_db):
    return fake_db.collection.return_value.document.return_value.collection.return_value


def test_get_action_items_count_arithmetic():
    fake_db = MagicMock()
    items_ref = _fake_items_ref(fake_db)
    items_ref.count.return_value.get.return_value = _count_result(5)
    items_ref.where.return_value.count.return_value.get.return_value = _count_result(2)
    items_ref.where.return_value.stream.return_value = []  # no soft-retired items

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count("uid-1")

    assert result == {"total": 5, "completed": 2, "incomplete": 3}


def test_get_action_items_count_never_negative():
    # Defensive: if an eventually-consistent aggregation reports completed > total,
    # incomplete must clamp to 0 rather than go negative.
    fake_db = MagicMock()
    items_ref = _fake_items_ref(fake_db)
    items_ref.count.return_value.get.return_value = _count_result(1)
    items_ref.where.return_value.count.return_value.get.return_value = _count_result(3)
    items_ref.where.return_value.stream.return_value = []

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count("uid-1")

    assert result == {"total": 1, "completed": 3, "incomplete": 0}


def test_get_action_items_count_excludes_soft_retired():
    # Regression for the count drifting from the visible list: get_action_items skips
    # data.get('deleted'), so deleted items must not inflate total/completed/incomplete.
    fake_db = MagicMock()
    items_ref = _fake_items_ref(fake_db)
    # Raw aggregates include the deleted docs.
    items_ref.count.return_value.get.return_value = _count_result(5)  # 5 total, of which 2 are deleted
    items_ref.where.return_value.count.return_value.get.return_value = _count_result(3)  # 3 completed, 1 deleted
    items_ref.where.return_value.stream.return_value = [
        _deleted_doc(completed=True),
        _deleted_doc(completed=False),
    ]

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count("uid-1")

    # visible total = 5 - 2 = 3; visible completed = 3 - 1 = 2; incomplete = 3 - 2 = 1
    assert result == {"total": 3, "completed": 2, "incomplete": 1}


# The endpoint itself is a trivial passthrough to get_action_items_count and is covered by the
# Public Developer API contract check (route + response_model). A unit test for it would import the
# whole routers.action_items graph, tripping the fast-unit duration guard for no added signal.
