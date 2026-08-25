"""Regression test: a malformed ISO date string must not 500 an action-item write.

database.action_items._prepare_action_item_for_write normalizes created_at / updated_at /
due_at / completed_at ISO strings to datetimes. These fields arrive as strings from tool-
and LLM-created action items (not only from validated API models), so a single malformed
value used to raise ValueError('Invalid isoformat string') out of create_action_item /
update_action_item and 500 the request. The write path now drops a malformed date (with a
warning) and keeps the rest of the item, mirroring the tolerant date handling on the read
path and in _coerce_utc_datetime.
"""

from datetime import datetime

from database.action_items import _prepare_action_item_for_write


def test_malformed_due_at_is_dropped_not_raised():
    out = _prepare_action_item_for_write({"description": "x", "due_at": "not-a-real-date"}, partial=True)

    assert "due_at" not in out  # malformed value dropped, no ValueError raised
    assert out["description"] == "x"


def test_valid_iso_string_is_parsed():
    out = _prepare_action_item_for_write({"description": "x", "due_at": "2024-01-01T00:00:00Z"}, partial=True)

    assert isinstance(out["due_at"], datetime)
    assert out["due_at"].year == 2024
    assert out["due_at"].tzinfo is not None


def test_datetime_value_passes_through_unchanged():
    dt = datetime(2024, 5, 6, 7, 8, 9)
    out = _prepare_action_item_for_write({"description": "x", "due_at": dt}, partial=True)

    assert out["due_at"] is dt


def test_one_malformed_field_does_not_drop_the_others():
    out = _prepare_action_item_for_write(
        {"description": "x", "created_at": "garbage", "due_at": "2024-01-01T00:00:00Z"},
        partial=True,
    )

    assert "created_at" not in out  # malformed dropped
    assert isinstance(out["due_at"], datetime)  # sibling good value preserved
