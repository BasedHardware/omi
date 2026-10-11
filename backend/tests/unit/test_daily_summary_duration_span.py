"""Daily-summary duration must use the transcript span, not the capture-session window.

`generate_comprehensive_daily_summary` summed `finished_at - started_at` per conversation.
`started_at` is the live-socket streaming-session origin, not the moment the speech began (#4056):
a conversation recorded 42 minutes into a socket contributed the whole socket window to the day's
`total_duration_minutes` even when its transcript spanned 8 seconds. The mobile recap then rendered
"42 min" while the conversation row itself showed 0.

`conversation_duration_seconds` (utils/conversations/duration.py) is the repo's single authority
and already powers the discard gate (#13047); this consumer was not routed through it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from utils.llm.external_integrations import _total_duration_minutes

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _conv(segments, started_minutes_ago=42):
    return SimpleNamespace(
        transcript_segments=segments,
        started_at=NOW - timedelta(minutes=started_minutes_ago),
        finished_at=NOW,
        discarded=False,
    )


def test_short_dictation_inside_long_socket_counts_seconds_not_the_window():
    minutes = _total_duration_minutes([_conv([{'text': 'hi', 'start': 0, 'end': 8}])])

    assert minutes < 1  # 8 seconds, not the 42-minute socket window


def test_transcript_free_capture_still_counts_the_wall_window():
    minutes = _total_duration_minutes([_conv([])])

    assert 41.9 <= minutes <= 42.1


def test_per_conversation_spans_add_up():
    minutes = _total_duration_minutes(
        [
            _conv([{'text': 'a', 'start': 0, 'end': 120}]),  # 2 min span
            _conv([{'text': 'b', 'start': 0, 'end': 60}], started_minutes_ago=10),  # 1 min span
        ]
    )

    assert 2.9 <= minutes <= 3.1
