"""Regression: action-item write path must never hand Firestore a tz-naive datetime.

``_prepare_action_item_for_write`` normalizes created_at / updated_at / due_at /
completed_at. Extraction models (``ExtractedActionItem`` / ``structured.ActionItem``)
use plain ``datetime``, so LLM due dates often arrive as date-only ISO strings or
tz-naive datetimes. Firestore rejects naive datetimes; a failed batch create on the
fire-and-forget postprocess path silently drops extracted tasks.

Mirrors ``api_key_metadata._coerce_utc_datetime`` and ``mcp_action_items.parse_due_at``.
"""

from datetime import datetime, timezone

from database.action_items import _prepare_action_item_for_write


def test_malformed_due_at_is_dropped_not_raised():
    out = _prepare_action_item_for_write({"description": "x", "due_at": "not-a-real-date"}, partial=True)

    assert "due_at" not in out  # malformed value dropped, no ValueError raised
    assert out["description"] == "x"


def test_valid_iso_string_is_parsed_as_utc():
    out = _prepare_action_item_for_write({"description": "x", "due_at": "2024-01-01T00:00:00Z"}, partial=True)

    assert isinstance(out["due_at"], datetime)
    assert out["due_at"] == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_date_only_iso_string_gets_utc():
    """fromisoformat('YYYY-MM-DD') returns naive; must attach UTC before Firestore."""
    out = _prepare_action_item_for_write({"description": "x", "due_at": "2024-01-01"}, partial=True)

    assert out["due_at"] == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_naive_datetime_gets_utc():
    naive = datetime(2024, 5, 6, 7, 8, 9)
    out = _prepare_action_item_for_write({"description": "x", "due_at": naive}, partial=True)

    assert out["due_at"] == datetime(2024, 5, 6, 7, 8, 9, tzinfo=timezone.utc)


def test_aware_datetime_normalized_to_utc():
    from datetime import timedelta

    plus_five = timezone(timedelta(hours=5))
    local = datetime(2024, 5, 6, 12, 0, tzinfo=plus_five)
    out = _prepare_action_item_for_write({"description": "x", "due_at": local}, partial=True)

    assert out["due_at"] == datetime(2024, 5, 6, 7, 0, tzinfo=timezone.utc)


def test_one_malformed_field_does_not_drop_the_others():
    out = _prepare_action_item_for_write(
        {"description": "x", "created_at": "garbage", "due_at": "2024-01-01T00:00:00Z"},
        partial=True,
    )

    assert "created_at" not in out  # malformed dropped
    assert out["due_at"] == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_overflow_on_utc_normalization_is_dropped_not_raised():
    """Boundary aware values can raise OverflowError in astimezone(UTC).

    A parseable datetime whose offset conversion leaves Python's datetime range
    must drop that field (same as a malformed string) so a batch write still
    succeeds for sibling items — David's #11138 blocker.
    """
    from datetime import timedelta

    # year=1 00:00 at +14h → UTC is before datetime.min
    boundary = datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=14)))
    out = _prepare_action_item_for_write(
        {
            "description": "x",
            "due_at": boundary,
            "created_at": "2024-01-01T00:00:00Z",
        },
        partial=True,
    )

    assert "due_at" not in out
    assert out["created_at"] == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_overflow_iso_string_on_utc_normalization_is_dropped():
    out = _prepare_action_item_for_write(
        {"description": "x", "due_at": "0001-01-01T00:00:00+14:00"},
        partial=True,
    )

    assert "due_at" not in out
    assert out["description"] == "x"
