"""Unit test for get_message_count (GET /v1/users/stats/chat-messages).

Reported messages are hidden from every chat view (get_messages / get_app_messages skip
reported == True), so the total-messages stat must exclude them too; otherwise the stat exceeds
the number of messages the user can actually see anywhere. Pinned against a fake Firestore, no
live services.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.chat as chat_db  # noqa: E402


def _count(value):
    # Firestore aggregation returns [[AggregationResult(value=...)]].
    return [[SimpleNamespace(value=value)]]


def _messages_ref(fake_db):
    return fake_db.collection.return_value.document.return_value.collection.return_value


def test_message_count_excludes_reported():
    fake_db = MagicMock()
    messages_ref = _messages_ref(fake_db)
    messages_ref.count.return_value.get.return_value = _count(3)  # total incl reported
    messages_ref.where.return_value.count.return_value.get.return_value = _count(1)  # reported subset

    with patch.object(chat_db, "db", fake_db):
        assert chat_db.get_message_count("u1") == 2  # 3 total - 1 reported = 2 visible


def test_message_count_no_reported():
    fake_db = MagicMock()
    messages_ref = _messages_ref(fake_db)
    messages_ref.count.return_value.get.return_value = _count(4)
    messages_ref.where.return_value.count.return_value.get.return_value = _count(0)

    with patch.object(chat_db, "db", fake_db):
        assert chat_db.get_message_count("u1") == 4


def test_message_count_never_negative():
    # Defensive: eventually-consistent aggregations could momentarily report reported > total.
    fake_db = MagicMock()
    messages_ref = _messages_ref(fake_db)
    messages_ref.count.return_value.get.return_value = _count(1)
    messages_ref.where.return_value.count.return_value.get.return_value = _count(3)

    with patch.object(chat_db, "db", fake_db):
        assert chat_db.get_message_count("u1") == 0
