from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest

from database.action_item_codec import (
    prepare_action_item_for_read,
    prepare_action_item_for_write,
)


def test_prepare_for_read_does_not_mutate_input():
    original = {"description": "Task 1", "completed": None}
    copied = dict(original)

    result = prepare_action_item_for_read(original)

    assert original == copied
    assert "status" not in original
    assert result["status"] == "active"
    assert result["completed"] is False


def test_prepare_for_read_defaults():
    res = prepare_action_item_for_read({"description": "Test"})

    assert res["description"] == "Test"
    assert res["owner"] == "unknown"
    assert res["source"] == "legacy"
    assert res["provenance"] == []
    assert res["sort_order"] == 0
    assert res["indent_level"] == 0
    assert res["status"] == "active"
    assert res["completed"] is False


@pytest.mark.parametrize(
    "input_dict,expected_status,expected_completed",
    [
        ({"completed": True}, "completed", True),
        ({"completed": False}, "active", False),
        ({"status": "completed"}, "completed", True),
        ({"status": "active"}, "active", False),
        ({"completed": None, "status": "completed"}, "completed", True),
        ({"completed": None}, "active", False),
    ],
)
def test_prepare_for_read_status_and_completed_inference(input_dict, expected_status, expected_completed):
    res = prepare_action_item_for_read(input_dict)
    assert res["status"] == expected_status
    assert res["completed"] is expected_completed


def test_prepare_for_read_date_normalization():
    naive = datetime(2026, 10, 16, 12, 0, 0)
    aware = datetime(2026, 10, 16, 17, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    iso_str = "2026-10-16T12:00:00Z"

    mock_timestamp = MagicMock()
    mock_timestamp.timestamp.return_value = 1760616000.0

    res = prepare_action_item_for_read(
        {
            "created_at": naive,
            "updated_at": aware,
            "due_at": iso_str,
            "completed_at": mock_timestamp,
        }
    )

    assert res["created_at"] == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert res["updated_at"] == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert res["due_at"] == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert res["completed_at"] == datetime.fromtimestamp(1760616000.0, tz=timezone.utc)


def test_prepare_for_read_date_error_boundaries():
    faulty_ts = MagicMock()
    faulty_ts.timestamp.side_effect = OverflowError("Timestamp out of range")

    res = prepare_action_item_for_read(
        {
            "created_at": faulty_ts,
            "due_at": "invalid-iso-string",
        }
    )

    # Must not raise, handles gracefully
    assert res["created_at"] == faulty_ts
    assert res["due_at"] == "invalid-iso-string"


def test_prepare_for_read_provenance_coercion():
    assert prepare_action_item_for_read({"provenance": "not-a-list"})["provenance"] == []
    assert prepare_action_item_for_read({"provenance": None})["provenance"] == []
    assert prepare_action_item_for_read({"provenance": [{"id": "1"}]})["provenance"] == [{"id": "1"}]


def test_prepare_for_write_non_partial_defaults():
    res = prepare_action_item_for_write({"description": "Test"})

    assert res["owner"] == "unknown"
    assert res["source"] == "legacy"
    assert res["provenance"] == []
    assert res["sort_order"] == 0
    assert res["indent_level"] == 0
    assert res["status"] == "active"
    assert res["completed"] is False


def test_prepare_for_write_partial_mode():
    res = prepare_action_item_for_write(
        {"description": "Partial update", "owner": None, "indent_level": None},
        partial=True,
    )

    assert "owner" not in res
    assert "indent_level" not in res
    assert "source" not in res
    assert res["description"] == "Partial update"


def test_prepare_for_write_status_whitespace_stripping():
    res = prepare_action_item_for_write({"status": "  completed  "})
    assert res["status"] == "completed"
    assert res["completed"] is True


def test_prepare_for_write_status_and_completed_agreement():
    with pytest.raises(ValueError, match="completed must agree with canonical status"):
        prepare_action_item_for_write({"status": "completed", "completed": False})

    with pytest.raises(ValueError, match="completed must agree with canonical status"):
        prepare_action_item_for_write({"status": "active", "completed": True})


def test_prepare_for_write_provenance_coercion():
    res = prepare_action_item_for_write({"provenance": "invalid"})
    assert res["provenance"] == []


def test_prepare_for_write_date_normalization_and_drops():
    naive = datetime(2026, 10, 16, 10, 0, 0)
    iso_z = "2026-10-16T10:00:00Z"
    boundary = datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=14)))

    res = prepare_action_item_for_write(
        {
            "created_at": naive,
            "updated_at": iso_z,
            "due_at": "not-a-date",
            "completed_at": boundary,
        },
        partial=True,
    )

    assert res["created_at"] == datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert res["updated_at"] == datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert "due_at" not in res
    assert "completed_at" not in res
