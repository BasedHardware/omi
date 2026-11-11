"""Meeting-treatment eligibility must use the transcript span, not the capture-session window.

`started_at` is the live-socket streaming-session origin, not the moment the conversation's speech
began: it drifts tens of minutes behind wall clock across a long socket (#4056). The verdict's
`duration_s` was the wall window `finished_at - started_at`, so a 90-second desktop call that began
40 minutes into a live socket measured as ~2400s, the 5-minute `too_short` gate never fired, and the
call received full meeting treatment (LLM notes + a persisted "meeting ready" receipt) — the same
defect class #13047 fixed at the discard gate, still live at the policy gate.

Fix: `conversation_duration_seconds` (utils/conversations/duration.py), the repo's single authority
for a conversation's duration, which prefers the transcript span and only degrades to the wall
window when no usable segments exist.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from utils.conversations.meeting_treatment import meeting_treatment_verdict

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _desktop_meeting(segments, started_minutes_ago=40):
    return SimpleNamespace(
        source='desktop',
        external_data={'conversation_role': 'meeting'},
        transcript_segments=segments,
        started_at=NOW - timedelta(minutes=started_minutes_ago),
        finished_at=NOW,
        discarded=False,
    )


def test_short_call_inside_long_socket_is_too_short():
    verdict = meeting_treatment_verdict(_desktop_meeting([{'text': 'hello', 'start': 0, 'end': 90}]))

    assert verdict.eligible is False
    assert verdict.reason == 'too_short'
    # the 90-second transcript span, not the 40-minute capture-session window
    assert 89 < verdict.duration_s < 91


def test_long_call_stays_eligible():
    verdict = meeting_treatment_verdict(_desktop_meeting([{'text': 'talky', 'start': 0, 'end': 400}]))

    assert verdict.eligible is True
    assert verdict.reason == 'eligible'
    assert verdict.duration_s == 400


def test_no_segments_still_falls_back_to_the_wall_window():
    # A transcript-free capture is the case the wall window exists for; it must keep measuring.
    verdict = meeting_treatment_verdict(_desktop_meeting([]))

    assert verdict.duration_s >= 2399
    # no speech recorded, so the speech minimum (not the duration gate) is what excludes it
    assert verdict.reason == 'insufficient_speech'
