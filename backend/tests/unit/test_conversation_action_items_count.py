"""Unit tests for the per-conversation action-items count.

GET /v1/conversations/{conversation_id}/action-items/count returns a task-progress
summary (total / completed / incomplete) for one conversation via Firestore count()
aggregation over the same conversation_id predicate the list uses. Soft-retired items
(``deleted: true``) are hidden from the list/read paths, so the count excludes them too.
These pin the arithmetic and the deleted-exclusion; the endpoint's ownership check and
passthrough are covered by the Public Developer API contract check.
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


def _deleted_doc(completed):
    doc = MagicMock()
    doc.to_dict.return_value = {"completed": completed, "deleted": True}
    return doc


def _base(fake_db):
    # db.collection(...).document(...).collection(...).where(conversation_id==) -> base
    return fake_db.collection.return_value.document.return_value.collection.return_value.where.return_value


def test_count_by_conversation_arithmetic():
    fake_db = MagicMock()
    base = _base(fake_db)
    base.count.return_value.get.return_value = _count(3)  # total in conversation
    base.where.return_value.count.return_value.get.return_value = _count(1)  # completed subset
    base.where.return_value.stream.return_value = []  # no soft-retired items

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count_by_conversation("u1", "c1")

    assert result == {"total": 3, "completed": 1, "incomplete": 2}


def test_count_by_conversation_never_negative():
    fake_db = MagicMock()
    base = _base(fake_db)
    base.count.return_value.get.return_value = _count(1)
    base.where.return_value.count.return_value.get.return_value = _count(4)
    base.where.return_value.stream.return_value = []

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count_by_conversation("u1", "c1")

    assert result == {"total": 1, "completed": 4, "incomplete": 0}


def test_count_by_conversation_excludes_soft_retired():
    # Regression: deleted items in the conversation must not inflate the badge, matching the list
    # path which skips data.get('deleted').
    fake_db = MagicMock()
    base = _base(fake_db)
    base.count.return_value.get.return_value = _count(4)  # 4 total, of which 2 are deleted
    base.where.return_value.count.return_value.get.return_value = _count(2)  # 2 completed, 1 deleted
    base.where.return_value.stream.return_value = [
        _deleted_doc(completed=True),
        _deleted_doc(completed=False),
    ]

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_action_items_count_by_conversation("u1", "c1")

    # visible total = 4 - 2 = 2; visible completed = 2 - 1 = 1; incomplete = 2 - 1 = 1
    assert result == {"total": 2, "completed": 1, "incomplete": 1}
