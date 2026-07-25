"""Contract tests for utils.llm.temporal.date_in_tz.

The conversation metadata-extraction prompts (retrieve_metadata_from_message / _from_text /
_fields_from_transcript in utils/llm/chat.py) ground the model's notion of "today" with the
conversation's created_at rendered in the user's timezone. They previously did this with a raw
``created_at.astimezone(ZoneInfo(tz))``, which raises ``ValueError`` when the user has no saved
timezone (``tz == ''`` -> ``ZoneInfo('')``) — the default conversation path, so timezone-less
users silently lost search metadata — and reinterprets naive timestamps as server-local time
(issues #4643, #6214).

Those call sites now delegate to ``date_in_tz``. These tests lock the guarantees they rely on:
an empty/None/invalid timezone falls back to UTC (never raises), and a naive datetime is read
as UTC rather than as the process-local time.
"""

from datetime import datetime, timezone

from utils.llm.temporal import date_in_tz


class TestDateInTzTimezoneFallback:
    def test_empty_string_tz_falls_back_to_utc_without_raising(self):
        # This is the exact input that made the old chat.py expression raise ValueError.
        dt = datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)
        assert date_in_tz(dt, "") == "2026-01-15"

    def test_none_tz_falls_back_to_utc(self):
        dt = datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)
        assert date_in_tz(dt, None) == "2026-01-15"

    def test_invalid_tz_falls_back_to_utc(self):
        dt = datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)
        assert date_in_tz(dt, "Not/AZone") == "2026-01-15"

    def test_valid_tz_shifts_the_calendar_date(self):
        # 00:30 UTC on Jan 16 is still Jan 15 in Los Angeles (UTC-8).
        dt = datetime(2026, 1, 16, 0, 30, tzinfo=timezone.utc)
        assert date_in_tz(dt, "America/Los_Angeles") == "2026-01-15"


class TestDateInTzNaiveDatetime:
    def test_naive_datetime_is_treated_as_utc(self):
        # A naive 00:30 must be read as 00:30 UTC. Rendered in Tokyo (UTC+9) that is 09:30
        # on the same day; the buggy "assume server-local" behavior would vary by host.
        naive = datetime(2026, 1, 15, 0, 30)
        assert date_in_tz(naive, "Asia/Tokyo") == "2026-01-15"

    def test_naive_datetime_utc_fallback_matches_wall_date(self):
        naive = datetime(2026, 1, 15, 23, 30)
        assert date_in_tz(naive, "") == "2026-01-15"
