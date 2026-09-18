# Calendar capture: discard override, auto-link gating, capture gaps (SCA-381)

Detail moved out of `backend/AGENTS.md` (lean budget). The one-line contract lives in the
backend Service Map; this file carries the full rules.

## Calendar overlap outranks discard

At the discard decision in `backend/utils/conversations/process_conversation.py` `_get_structured`:
when `should_discard_conversation` returns True, the conversation is **kept**
(`discarded=False`) if its `[started_at, finished_at]` overlaps a **non-declined**
calendar meeting:

1. Stored meeting intent — `users/{uid}/meetings` via `backend/database/calendar_meetings.py` `get_meetings_in_time_range`
   + `select_overlapping_meeting` (cheap Firestore read, no provider traffic).
2. Read-only Google Calendar lookup — `get_overlapping_calendar_event(..., require_accepted=True)` in `backend/utils/conversations/calendar_linking.py`:
   cancelled events and events the authenticated attendee declined never keep.

Rules:

- Fail **open**: disconnected calendar, missing token, or lookup errors leave the discard
  verdict standing. The override only fires on a positive overlap hit — never keeps because
  a lookup failed, never fails the conversation.
- No Google Calendar writes in this path.
- A kept scrap then satisfies the auto-link `not discarded` gate, so it can still link.

## Overlap matching (shared, pure)

`backend/utils/conversations/calendar_linking.py` `select_overlapping_calendar_event` holds the rules for
both auto-link and the discard override: overlap ≥ `MIN_OVERLAP_SECONDS` (10s) **and**
(≥ `MIN_OVERLAP_PERCENTAGE` (50%) of the event **or** of the conversation). The OR is a
product decision — a 25s scrap wholly inside a 30m meeting matches through conversation
coverage. `require_accepted=False` (auto-link) keeps the linker's historical behavior of
matching any overlapping event.

## Auto-link gating

`GOOGLE_CALENDAR_AUTO_LINK_ENABLED` (code default off) gates calendar write-back during
conversation processing. Enabled only in the **dev** `backend-listen` runtime env
(`backend/deploy/runtime_env/dev.overlay.yaml`); prod and local stay off.

## Capture gaps

`GET /v1/calendar/capture-gaps?start=&end=` (`backend/routers/google_calendar.py`, auth required)
returns **confirmed**, timed (≤ `MAX_CAPTURE_GAP_EVENT_SECONDS` = 8h; all-day blocks exceed
it) events in the window with **no overlapping non-discarded conversation**. Rows carry
`event_id`, `title`, `start_time`, `end_time`, `status`, `coverage='not_captured'`. The pure
selection is `select_capture_gaps`; it never creates conversations. Coverage uses the same
10s overlap floor. The conversation read is a single-field Firestore range
(`include_discarded=True`, `date_field='started_at'`, one-day pad) so no composite index is
needed; the window is capped at 31 days.
