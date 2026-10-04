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


def _visibility_rows(messages_ref, rows):
    messages_ref.select.return_value.stream.return_value = [
        SimpleNamespace(to_dict=lambda row=row: row) for row in rows
    ]


def test_cache_aligned_history_counts_only_visible_rows_in_the_session():
    fake_db = MagicMock()
    messages_ref = _messages_ref(fake_db)
    messages_ref.where.return_value = messages_ref
    rows = [{'sender': 'human', 'type': 'text'} for _ in range(19)]
    rows += [{'reported': True} for _ in range(2)]
    rows += [{'sender': 'ai', 'metadata': '{"chatFirstIntentSource":"capture_arrival"}'} for _ in range(1201)]
    rows += [{'sender': 'ai', 'reported': True, 'type': 'task'}]
    _visibility_rows(messages_ref, rows)
    visible_messages = [{"id": f"m{i}"} for i in range(11)]
    with patch.object(chat_db, "db", fake_db), patch.object(
        chat_db, "get_messages", return_value=visible_messages
    ) as get_messages:
        assert chat_db.get_cache_aligned_messages("u1", app_id="app-1", chat_session_id="session-1") == visible_messages
    # 19 visible rows select an 11-row epoch, regardless of the automatic count.
    get_messages.assert_called_once_with("u1", limit=11, app_id="app-1", chat_session_id="session-1")
    messages_ref.select.assert_called_once_with(
        ['reported', 'sender', 'metadata', 'message_source', 'type', 'content_blocks']
    )
    filter_ = messages_ref.where.call_args.kwargs['filter']
    assert (filter_.field_path, filter_.value) == ('chat_session_id', 'session-1')
    messages_ref.count.assert_not_called()


def test_cache_aligned_history_excludes_reported_rows_without_overfetching_visible_rows():
    fake_db = MagicMock()
    messages_ref = _messages_ref(fake_db)
    messages_ref.where.return_value = messages_ref
    _visibility_rows(messages_ref, [{} for _ in range(200)] + [{'reported': True} for _ in range(300)])
    visible_messages = [{"id": f"m{i}"} for i in range(16)]
    with patch.object(chat_db, "db", fake_db), patch.object(
        chat_db, "get_messages", return_value=visible_messages
    ) as get_messages:
        assert chat_db.get_cache_aligned_messages("u1", app_id="app-1") == visible_messages
    get_messages.assert_called_once_with("u1", limit=16, app_id="app-1", chat_session_id=None)


def test_cache_aligned_history_without_session_is_scoped_to_app():
    fake_db = MagicMock()
    messages_ref = _messages_ref(fake_db)
    messages_ref.where.return_value = messages_ref
    _visibility_rows(messages_ref, [{}])
    with patch.object(chat_db, "db", fake_db), patch.object(chat_db, "get_messages", return_value=[{"id": "m1"}]):
        assert chat_db.get_cache_aligned_messages("u1", app_id="app-1") == [{"id": "m1"}]
    filter_ = messages_ref.where.call_args.kwargs['filter']
    assert (filter_.field_path, filter_.value) == ('plugin_id', 'app-1')


def test_cache_aligned_history_all_automatic_is_empty_without_loading_payloads():
    fake_db = MagicMock()
    messages_ref = _messages_ref(fake_db)
    messages_ref.where.return_value = messages_ref
    _visibility_rows(messages_ref, [{'metadata': '{"chatFirstIntentId":"old"}'}])
    with patch.object(chat_db, "db", fake_db), patch.object(chat_db, "get_messages") as get_messages:
        assert chat_db.get_cache_aligned_messages("u1") == []
    get_messages.assert_not_called()
