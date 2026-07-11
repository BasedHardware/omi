"""Unit test for get_advice_counts (GET /v1/advice/count).

The count matches the default list visibility (get_advice hides is_dismissed): total counts
non-dismissed advice, unread counts non-dismissed advice with is_read False. Pinned against a fake
Firestore via patch.object on the db proxy, no live services.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.advice as advice_db  # noqa: E402


def _count(value):
    return [[SimpleNamespace(value=value)]]


def _unread_doc(is_dismissed):
    doc = MagicMock()
    doc.to_dict.return_value = {"is_read": False, "is_dismissed": is_dismissed}
    return doc


def test_get_advice_counts_matches_visible_set():
    fake_db = MagicMock()
    col = fake_db.collection.return_value.document.return_value.collection.return_value
    # total = count(is_dismissed == False) aggregation
    col.where.return_value.count.return_value.get.return_value = _count(3)
    # unread = stream(is_read == False) then exclude dismissed: 2 unread streamed, 1 dismissed -> 1 visible
    col.where.return_value.stream.return_value = [_unread_doc(is_dismissed=False), _unread_doc(is_dismissed=True)]

    with patch.object(advice_db, "db", fake_db):
        result = advice_db.get_advice_counts("u1")

    assert result == {"total": 3, "unread": 1}


def test_get_advice_counts_no_unread():
    fake_db = MagicMock()
    col = fake_db.collection.return_value.document.return_value.collection.return_value
    col.where.return_value.count.return_value.get.return_value = _count(5)
    col.where.return_value.stream.return_value = []  # nothing unread

    with patch.object(advice_db, "db", fake_db):
        result = advice_db.get_advice_counts("u1")

    assert result == {"total": 5, "unread": 0}
