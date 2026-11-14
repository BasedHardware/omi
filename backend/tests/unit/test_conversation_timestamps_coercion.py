"""Hermetic unit tests for conversation timestamp coercion and timezone normalization.

Prevents HTTP 500 regressions from AttributeError and TypeError when Firestore
or API callers supply ISO 8601 string timestamps, numeric epoch timestamps,
or None in conversation metadata, revision tracking, and sync merge targets.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from database.conversation_revisions import ensure_timezone_aware, firestore_revision_datetime
from database.conversations import eligible_merge_target, select_closest_conversation

_BASE_UTC = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
_BASE_TS = int(_BASE_UTC.timestamp())


def test_ensure_timezone_aware_with_iso_strings():
    """ISO 8601 strings must parse into aware UTC datetimes without AttributeError."""
    iso_z = "2026-10-25T12:00:00Z"
    result_z = ensure_timezone_aware(iso_z)
    assert result_z == _BASE_UTC
    assert result_z.tzinfo == timezone.utc

    iso_offset = "2026-10-25T14:00:00+02:00"
    result_offset = ensure_timezone_aware(iso_offset)
    assert result_offset == _BASE_UTC
    assert result_offset.tzinfo is not None


def test_ensure_timezone_aware_with_naive_and_aware_datetimes():
    """Naive datetimes must receive UTC tzinfo; aware datetimes must be preserved."""
    naive = datetime(2026, 10, 25, 12, 0, 0)
    result_naive = ensure_timezone_aware(naive)
    assert result_naive == _BASE_UTC
    assert result_naive.tzinfo == timezone.utc

    aware = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    result_aware = ensure_timezone_aware(aware)
    assert result_aware == aware
    assert result_aware.tzinfo == timezone.utc


def test_ensure_timezone_aware_with_numeric_timestamps_and_none():
    """Integer and float unix timestamps must convert cleanly; None falls back gracefully."""
    ts_int = _BASE_TS
    result_int = ensure_timezone_aware(ts_int)
    assert result_int == _BASE_UTC

    ts_float = float(_BASE_TS)
    result_float = ensure_timezone_aware(ts_float)
    assert result_float == _BASE_UTC

    result_none = ensure_timezone_aware(None)
    assert result_none == datetime.min.replace(tzinfo=timezone.utc)

    result_invalid = ensure_timezone_aware("not-a-datetime")
    assert result_invalid == datetime.min.replace(tzinfo=timezone.utc)


def test_firestore_revision_datetime_supports_iso_strings():
    """firestore_revision_datetime must handle ISO string revisions in addition to Firestore timestamps."""
    iso_str = "2026-10-25T12:00:00Z"
    normalized = firestore_revision_datetime(iso_str)
    assert normalized == _BASE_UTC

    invalid = firestore_revision_datetime("unparseable-data")
    assert invalid is None


def test_select_closest_conversation_coerces_iso_strings_and_numeric_timestamps():
    """select_closest_conversation must accept ISO string and numeric timestamps without crashing."""
    target_start = _BASE_TS + 100
    target_end = target_start + 60

    conversations = [
        {
            "id": "conv-iso-near",
            "started_at": (_BASE_UTC + timedelta(seconds=90)).isoformat(),
            "finished_at": (_BASE_UTC + timedelta(seconds=150)).isoformat(),
            "deleted": False,
        },
        {
            "id": "conv-int-far",
            "started_at": _BASE_TS + 600,
            "finished_at": _BASE_TS + 660,
            "deleted": False,
        },
    ]

    chosen = select_closest_conversation(conversations, target_start, target_end)
    assert chosen is not None
    assert chosen["id"] == "conv-iso-near"


def test_select_closest_conversation_guards_against_none_and_corrupt_timestamps():
    """Conversations with None or missing started_at/finished_at must be skipped safely."""
    target_start = _BASE_TS
    target_end = target_start + 60

    conversations = [
        {"id": "conv-null-both", "started_at": None, "finished_at": None, "deleted": False},
        {"id": "conv-null-end", "started_at": _BASE_UTC, "finished_at": None, "deleted": False},
        {"id": "conv-missing-fields", "deleted": False},
        {
            "id": "conv-valid",
            "started_at": _BASE_UTC,
            "finished_at": _BASE_UTC + timedelta(seconds=60),
            "deleted": False,
        },
    ]

    chosen = select_closest_conversation(conversations, target_start, target_end)
    assert chosen is not None
    assert chosen["id"] == "conv-valid"


def test_select_closest_conversation_all_invalid_returns_none():
    """When all candidate rows have unparseable or null timestamps, returns None cleanly."""
    target_start = _BASE_TS
    target_end = target_start + 60

    corrupted = [
        {"id": "bad-1", "started_at": None, "finished_at": None, "deleted": False},
        {"id": "bad-2", "started_at": "invalid-timestamp", "finished_at": "invalid", "deleted": False},
        {
            "id": "deleted-valid",
            "started_at": _BASE_UTC,
            "finished_at": _BASE_UTC + timedelta(seconds=60),
            "deleted": True,
        },
    ]

    assert select_closest_conversation(corrupted, target_start, target_end) is None


def test_action_item_sorting_with_mixed_and_null_created_at():
    """Action items list sort key must handle mixed string, naive, and null conversation_created_at."""
    items = [
        {
            "id": "item-old",
            "conversation_created_at": ensure_timezone_aware("2026-10-20T10:00:00Z"),
        },
        {
            "id": "item-new",
            "conversation_created_at": ensure_timezone_aware(datetime(2026, 10, 25, 12, 0)),
        },
        {
            "id": "item-null",
            "conversation_created_at": ensure_timezone_aware(None),
        },
    ]

    # Verify sorting newest first does not raise TypeError or AttributeError
    items.sort(
        key=lambda x: -(
            x["conversation_created_at"].timestamp() if isinstance(x.get("conversation_created_at"), datetime) else 0.0
        )
    )

    ids = [item["id"] for item in items]
    assert ids == ["item-new", "item-old", "item-null"]
