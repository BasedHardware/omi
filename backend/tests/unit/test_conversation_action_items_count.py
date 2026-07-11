"""Unit tests for the per-conversation action-items count.

GET /v1/conversations/{conversation_id}/action-items/count returns a task-progress
summary (total / completed / incomplete) for one conversation via Firestore count()
aggregation over the same conversation_id predicate the list uses. These pin the
arithmetic; the endpoint's ownership check and passthrough are covered by the
Public Developer API contract check.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.action_items as ai_db  # noqa: E402


def _count(value):
    return [[SimpleNamespace(value=value)]]


def test_count_by_conversation_arithmetic():
    fake_db = MagicMock()
    # db.collection(...).document(...).collection(...).where(conversation_id==) -> base
    base = fake_db.collection.return_value.document.return_value.collection.return_value.where.return_value
    base.count.return_value.get.return_value = _count(3)  # total in conversation
    base.where.return_value.count.return_value.get.return_value = _count(1)  # completed subset

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count_by_conversation("u1", "c1")

    assert result == {"total": 3, "completed": 1, "incomplete": 2}


def test_count_by_conversation_never_negative():
    fake_db = MagicMock()
    base = fake_db.collection.return_value.document.return_value.collection.return_value.where.return_value
    base.count.return_value.get.return_value = _count(1)
    base.where.return_value.count.return_value.get.return_value = _count(4)

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count_by_conversation("u1", "c1")

    assert result == {"total": 1, "completed": 4, "incomplete": 0}
