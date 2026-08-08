"""Unit test for get_message_count (GET /v1/users/stats/chat-messages).

Reported messages are hidden from every chat view (get_messages / get_app_messages skip
reported == True), so the total-messages stat must exclude them too; otherwise the stat exceeds
the number of messages the user can actually see anywhere. Pinned against a fake Firestore, no
live services.
"""

import os
from unittest.mock import patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.chat as chat_db  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


class _ScriptedCountStore(FakeDocumentStore):
    """A store whose count() returns scripted values in call order, recording the filters seen.

    get_message_count / get_cache_aligned_messages call count() twice — total, then the reported
    subset — so scripting the two return values pins the visible-count math (and, for the
    never-negative case, an eventually-consistent reported > total) without seeding documents.
    The recorded filters let the scope assertions check what the port was actually asked.
    """

    def __init__(self, *counts):
        super().__init__()
        self._counts = list(counts)
        self.count_calls = []

    def count(self, collection, *, filters=None):
        self.count_calls.append([(f[0], f[2]) for f in (filters or [])])
        return self._counts.pop(0)


def test_message_count_excludes_reported(monkeypatch):
    monkeypatch.setattr(chat_db, "_store", lambda: _ScriptedCountStore(3, 1))  # 3 total, 1 reported
    assert chat_db.get_message_count("u1") == 2  # 3 total - 1 reported = 2 visible


def test_message_count_no_reported(monkeypatch):
    monkeypatch.setattr(chat_db, "_store", lambda: _ScriptedCountStore(4, 0))
    assert chat_db.get_message_count("u1") == 4


def test_message_count_never_negative(monkeypatch):
    # Defensive: eventually-consistent aggregations could momentarily report reported > total.
    monkeypatch.setattr(chat_db, "_store", lambda: _ScriptedCountStore(1, 3))
    assert chat_db.get_message_count("u1") == 0


def test_cache_aligned_history_limit_grows_then_resets_without_shrinking_below_previous_window():
    assert [chat_db.cache_aligned_history_limit(total) for total in range(0, 19)] == [
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        10,
    ]
    assert chat_db.cache_aligned_history_limit(25) == 17
    assert chat_db.cache_aligned_history_limit(26) == 10


def test_cache_aligned_history_read_is_scoped_and_overfetches_hidden_records(monkeypatch):
    store = _ScriptedCountStore(21, 2)  # 21 total, 2 reported → 19 visible
    monkeypatch.setattr(chat_db, "_store", lambda: store)
    visible_messages = [{"id": f"m{i}"} for i in range(13)]

    with patch.object(chat_db, "get_messages", return_value=visible_messages) as get_messages:
        result = chat_db.get_cache_aligned_messages("u1", app_id="app-1", chat_session_id="session-1")

    # 21 raw - 2 reported = 19 visible; the 10+8 epoch has grown to 11. raw_limit = 11 + 2 = 13.
    assert result == visible_messages[:11]
    get_messages.assert_called_once_with(
        "u1",
        limit=13,
        app_id="app-1",
        chat_session_id="session-1",
    )
    # Both counts are scoped to the session; the reported count adds the reported predicate.
    assert store.count_calls == [
        [("chat_session_id", "session-1")],
        [("chat_session_id", "session-1"), ("reported", True)],
    ]


def test_cache_aligned_history_caps_reported_overfetch_for_large_lifetime_count(monkeypatch):
    """A large lifetime reported count must not cause unbounded reads.

    A user with hundreds or thousands of old reported messages should not stream
    all of them on every chat send. The raw read is capped to
    CHAT_HISTORY_REPORTED_RAW_SCAN_CAP plus the visible limit.
    """
    # 500 total, 300 reported → 200 visible; visible_limit = 10 + (190 % 8) = 10 + 6 = 16
    store = _ScriptedCountStore(500, 300)
    monkeypatch.setattr(chat_db, "_store", lambda: store)
    visible_messages = [{"id": f"m{i}"} for i in range(66)]

    with patch.object(chat_db, "get_messages", return_value=visible_messages) as get_messages:
        result = chat_db.get_cache_aligned_messages("u1", app_id="app-1")

    expected_raw_limit = 16 + chat_db.CHAT_HISTORY_REPORTED_RAW_SCAN_CAP  # 16 + 50 = 66
    get_messages.assert_called_once_with(
        "u1",
        limit=min(500, expected_raw_limit),
        app_id="app-1",
        chat_session_id=None,
    )
    assert result == visible_messages[:16]


def test_cache_aligned_history_without_session_is_scoped_to_app(monkeypatch):
    store = _ScriptedCountStore(1, 0)
    monkeypatch.setattr(chat_db, "_store", lambda: store)

    with patch.object(chat_db, "get_messages", return_value=[{"id": "m1"}]):
        assert chat_db.get_cache_aligned_messages("u1", app_id="app-1") == [{"id": "m1"}]

    assert store.count_calls == [
        [("plugin_id", "app-1")],
        [("plugin_id", "app-1"), ("reported", True)],
    ]
