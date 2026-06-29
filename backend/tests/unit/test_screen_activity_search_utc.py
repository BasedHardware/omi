"""search_screen_activity_tool must render match timestamps in UTC, not the host's local time (#4643).

The screen-activity search result formatted each match's epoch timestamp with a naive
datetime.fromtimestamp(ts).strftime(...), which uses the host's local timezone, so the time shown in
chat depended on where the backend happened to run. It now passes tz=timezone.utc, matching how
conversation search and the other timestamp fixes render times. These are source-level structural
checks, since the tool has a heavy import graph (Firestore, vector search, OCR fetch).
"""

from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "utils" / "retrieval" / "tools" / "screen_activity_tools.py"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_timezone_is_imported():
    assert "from datetime import datetime, timezone" in _source()


def test_search_result_timestamp_is_utc():
    source = _source()
    start = source.index("def search_screen_activity_tool")
    next_def = source.find("\ndef ", start + 1)
    func = source[start:] if next_def == -1 else source[start:next_def]

    # The timestamp must be made timezone-aware (UTC) before formatting.
    assert "datetime.fromtimestamp(ts, tz=timezone.utc)" in func
    # The naive form (no tzinfo) must be gone.
    assert "datetime.fromtimestamp(ts).strftime" not in func
