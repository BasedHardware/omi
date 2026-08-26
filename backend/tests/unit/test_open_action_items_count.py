"""Unit tests for get_open_action_items_count / get_action_items_list_scan_cap.

Cleanup preview (routers/action_items_cleanup.py) uses these to tell a caller
whether get_action_items()'s 2000-item scan cap (_ACTION_ITEMS_LIST_HARD_MAX)
left tasks unscanned on large accounts, instead of silently truncating. These
pin the count() aggregation arithmetic and the deleted-exclusion, mirroring
test_conversation_action_items_count.py's per-conversation counterpart.
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
    # db.collection(...).document(...).collection(...) -> base (no conversation filter)
    return fake_db.collection.return_value.document.return_value.collection.return_value


def test_open_count_is_total_minus_completed():
    fake_db = MagicMock()
    base = _base(fake_db)
    base.count.return_value.get.return_value = _count(10)  # total
    base.where.return_value.count.return_value.get.return_value = _count(4)  # completed
    base.where.return_value.stream.return_value = []  # no soft-retired items

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_open_action_items_count("u1")

    assert result == 6


def test_open_count_never_negative_on_racing_writes():
    fake_db = MagicMock()
    base = _base(fake_db)
    base.count.return_value.get.return_value = _count(1)
    base.where.return_value.count.return_value.get.return_value = _count(4)  # exceeds total
    base.where.return_value.stream.return_value = []

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_open_action_items_count("u1")

    assert result == 0


def test_open_count_excludes_soft_retired():
    fake_db = MagicMock()
    base = _base(fake_db)
    base.count.return_value.get.return_value = _count(6)  # 6 total, 2 of which are deleted
    base.where.return_value.count.return_value.get.return_value = _count(3)  # 3 completed, 1 deleted
    base.where.return_value.stream.return_value = [
        _deleted_doc(completed=True),
        _deleted_doc(completed=False),
    ]

    with patch.object(ai_db, "db", fake_db):
        result = ai_db.get_open_action_items_count("u1")

    # visible total = 6 - 2 = 4; visible completed = 3 - 1 = 2; open = 4 - 2 = 2
    assert result == 2


def test_scan_cap_matches_hard_max_constant():
    assert ai_db.get_action_items_list_scan_cap() == ai_db._ACTION_ITEMS_LIST_HARD_MAX
