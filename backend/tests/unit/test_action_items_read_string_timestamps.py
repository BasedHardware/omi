"""Regression: action-item read path must coerce raw ISO-string timestamps.

``prepare_action_item_for_read`` already normalizes datetime-like values (naive
or aware) to UTC via ``.timestamp()``, but left plain strings untouched. A row
written before the write-path normalization existed (or by an external
integration/migration that bypassed it) can still have ``due_at``/``created_at``
stored as a raw ISO string. ``_action_item_list_sort_key`` then compares that
string against a ``datetime`` and raises ``TypeError``, 500ing every reader of
the list (GET /v1/action-items, MCP get_action_items, etc.) (#22181).
"""

from datetime import datetime, timezone

from database.action_item_codec import prepare_action_item_for_read
from database.action_items import _action_item_list_sort_key


def test_iso_string_due_at_is_parsed_to_utc_datetime():
    out = prepare_action_item_for_read({'description': 'x', 'due_at': '2026-10-25T14:00:00Z'})

    assert out['due_at'] == datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc)


def test_malformed_string_timestamp_is_dropped_not_raised():
    out = prepare_action_item_for_read({'description': 'x', 'due_at': 'not-a-real-date'})

    assert 'due_at' not in out
    assert out['description'] == 'x'


def test_date_only_iso_string_gets_utc():
    out = prepare_action_item_for_read({'description': 'x', 'created_at': '2026-01-01'})

    assert out['created_at'] == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_sorting_mixed_string_and_datetime_due_at_no_longer_crashes():
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    raw_items = [
        {'id': 'string-due', 'completed': False, 'due_at': '2026-10-26T14:00:00Z', 'created_at': now},
        {
            'id': 'datetime-due',
            'completed': False,
            'due_at': datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc),
            'created_at': now,
        },
    ]
    items = [prepare_action_item_for_read(dict(item)) for item in raw_items]

    sorted_items = sorted(items, key=_action_item_list_sort_key)

    assert [item['id'] for item in sorted_items] == ['datetime-due', 'string-due']


def test_sorting_string_created_at_no_longer_crashes():
    raw_items = [
        {'id': 'string-created', 'completed': False, 'due_at': None, 'created_at': '2026-01-01T00:00:00Z'},
        {
            'id': 'datetime-created',
            'completed': False,
            'due_at': None,
            'created_at': datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
    ]
    items = [prepare_action_item_for_read(dict(item)) for item in raw_items]

    sorted_items = sorted(items, key=_action_item_list_sort_key)

    assert [item['id'] for item in sorted_items] == ['datetime-created', 'string-created']
