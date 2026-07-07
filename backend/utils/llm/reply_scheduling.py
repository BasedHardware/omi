"""
Availability-aware scheduling for reply drafting.

When an inbound message proposes or asks about a time, this module grounds the reply
in the user's REAL Google Calendar: it detects the scheduling intent, reads the
relevant window, computes free/busy against the proposed slot(s), and renders a fenced
AVAILABILITY block the drafter uses to answer concretely (accept an open slot, or flag a
conflict and offer a nearby one). After drafting, `judge_accepted_slot` decides whether
the draft actually committed to a slot, and `create_hold` creates a tentative "hold"
event the user confirms or discards.

Kept separate from reply_draft.py on purpose (mirrors reply_media.py): the routers
`await build_availability_context()` as an async pre-step, pass the resulting text into
the sync `draft_reply(..., availability_context=...)`, then `await create_hold()` as an
async post-step. All calendar network I/O lives here (async); all LLM calls are wrapped
via `run_blocking(llm_executor, ...)` so they never block the event loop.

v1 signal: Google Calendar only. Routine/sleep/Gmail/action-item constraints are
deliberately out of scope (see the plan's Follow-ups).
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage

import database.notifications as notification_db
import database.users as users_db
from utils.conversations.calendar_utils import parse_event_times
from utils.executors import db_executor, llm_executor, run_blocking
from utils.llm.clients import get_llm
from utils.llm.reply_draft import UNTRUSTED_DATA_NOTICE, _fence, draft_reply
from utils.log_sanitizer import sanitize_pii
from utils.retrieval.tools.calendar_tools import (
    create_google_calendar_event,
    get_google_calendar_events,
)
from utils.retrieval.tools.google_utils import refresh_google_token

logger = logging.getLogger(__name__)

# How many events to read for the availability window. A day rarely has more than a
# handful; this is a generous cap so a busy day still renders fully.
MAX_WINDOW_EVENTS = 50
# Default hold duration when the proposal gives a start but no explicit end.
DEFAULT_HOLD_MINUTES = 60
# Bound the window we'll read so a bad extraction ("next year") can't pull a huge range.
MAX_WINDOW_DAYS = 14

# Cheap prefilter: only run the (LLM) extraction when the recent inbound text smells
# like scheduling. Keeps every normal draft at zero extra latency/cost. Intentionally
# broad — false positives are caught by the extractor returning is_scheduling=false.
_SCHEDULE_HINT_RE = re.compile(
    r"""
    \b(
        free | avail(?:able|ability) | busy | when\s+are\s+you | what\s+time |
        meet(?:ing|up)? | catch\s*up | hang(?:out)? | grab | call | chat |
        lunch | dinner | breakfast | brunch | coffee | drinks? |
        tomorrow | tonight | today | tmrw | tmr | weekend |
        mon(?:day)? | tue(?:s|sday)? | wed(?:nesday)? | thu(?:rs|rsday)? |
        fri(?:day)? | sat(?:urday)? | sun(?:day)? |
        \d{1,2}\s*(?:am|pm) | \d{1,2}:\d{2} | o'?clock | noon | midnight |
        next\s+week | this\s+week | schedul | reschedul | book\s+a
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class ProposedSlot:
    """A concrete candidate time extracted from the conversation (tz-aware)."""

    start: datetime
    end: datetime
    label: str = ""


@dataclass
class ScheduleProposal:
    """The extracted scheduling intent. `slots` may be empty when the sender asks about
    availability without naming a specific time ("when are you free this week?") — we
    still surface the user's schedule for the window so the drafter can answer."""

    is_scheduling: bool
    slots: List[ProposedSlot] = field(default_factory=list)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None


@dataclass
class AvailabilityContext:
    """Result of the async pre-step. `text` is the fenced block injected into the draft
    prompt; `proposal` carries the machine-readable slots for the hold post-step;
    `has_calendar` is False when the user hasn't connected Google Calendar (the text
    then tells the drafter to stay non-committal)."""

    text: str = ""
    proposal: Optional[ScheduleProposal] = None
    has_calendar: bool = False


# ---------------------------------------------------------------------------
# Prefilter + inbound text
# ---------------------------------------------------------------------------


def _recent_inbound_text(thread: List[dict], limit: int = 5) -> str:
    """The most recent inbound (not-from-user) messages, oldest→newest, as one string."""
    recents: List[str] = []
    for m in reversed(thread or []):
        if m.get('is_from_me'):
            continue
        text = (m.get('text') or '').strip()
        if text:
            recents.append(text)
        if len(recents) >= limit:
            break
    return "\n".join(reversed(recents)).strip()


def looks_like_scheduling(thread: List[dict]) -> bool:
    """Cheap regex prefilter — True when recent inbound text mentions times/availability."""
    return bool(_SCHEDULE_HINT_RE.search(_recent_inbound_text(thread)))


# ---------------------------------------------------------------------------
# Timezone + datetime helpers (kept local to avoid importing the heavy chat module)
# ---------------------------------------------------------------------------


def _resolve_tz(uid: str) -> tuple[ZoneInfo, str]:
    """Return (tzinfo, label) for the user, falling back to UTC. Blocking (Firestore)."""
    try:
        tz = notification_db.get_user_time_zone(uid)
        if tz:
            return ZoneInfo(tz), tz
    except Exception as e:
        logger.warning(f"reply_scheduling: tz lookup failed uid={uid}: {e}")
    return ZoneInfo("UTC"), "UTC"


def _parse_iso(value) -> Optional[datetime]:
    """Parse an ISO-8601 string to a tz-aware datetime (naive → UTC). None on failure."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Extraction (LLM)
# ---------------------------------------------------------------------------


def _parse_json_object(text: str) -> Optional[dict]:
    """Extract the first JSON object from a model reply (tolerates code fences)."""
    t = (text or '').strip()
    if t.startswith('```'):
        nl = t.find('\n')
        if nl != -1:
            t = t[nl + 1 :]
        if t.endswith('```'):
            t = t[:-3]
    start = t.find('{')
    end = t.rfind('}')
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(t[start : end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _build_extraction_prompt(inbound_text: str, now_local: datetime, tz_label: str) -> tuple[str, str]:
    """(system, user) for the scheduling-intent extractor. Trusted instructions in the
    system message; the untrusted inbound text is fenced in the user message."""
    system_prompt = (
        "You extract scheduling intent from a chat message so a calendar can be checked. "
        f"{UNTRUSTED_DATA_NOTICE}\n\n"
        f"The user's current local time is {now_local.strftime('%Y-%m-%d %H:%M')} ({tz_label}), "
        f"ISO {now_local.isoformat()}. Resolve all relative times ('tomorrow', 'Friday 1pm', 'tonight') "
        f"against this, and ALWAYS include the user's timezone offset in every ISO time you output.\n\n"
        "Decide if the message is proposing or asking about a time to meet/talk/do something.\n"
        "Return ONLY a JSON object with these keys:\n"
        '  "is_scheduling": boolean — true if it proposes or asks about a specific time or availability.\n'
        '  "proposed": array of {"start_iso","end_iso","label"} — each concrete time offered. '
        "If a start is given without a duration, make end_iso one hour after start_iso. "
        "label is a short activity name (e.g. \"lunch\", \"call\") or \"\" if none. "
        "Empty array when the sender asks about availability without naming a specific time.\n"
        '  "window_start_iso" / "window_end_iso": the ISO datetime range to check on the calendar '
        "(the day or days the message is about). Keep it within two weeks of now.\n\n"
        "If the message is not about scheduling at all, return "
        '{"is_scheduling": false, "proposed": [], "window_start_iso": null, "window_end_iso": null}. '
        "Output the JSON object and nothing else."
    )
    user_prompt = f"MESSAGE(S) TO ANALYZE:\n<message>\n{_fence(inbound_text)}\n</message>"
    return system_prompt, user_prompt


def _invoke_llm(system_prompt: str, user_prompt: str) -> str:
    """Blocking LLM call with real system/user separation. Wrap in run_blocking."""
    response = get_llm('memories').invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    return response.content if hasattr(response, 'content') else str(response)


def _proposal_from_obj(obj: dict, now_local: datetime) -> ScheduleProposal:
    """Build a ScheduleProposal from the parsed extractor JSON, bounding the window."""
    if not obj.get('is_scheduling'):
        return ScheduleProposal(is_scheduling=False)

    slots: List[ProposedSlot] = []
    for item in obj.get('proposed') or []:
        if not isinstance(item, dict):
            continue
        start = _parse_iso(item.get('start_iso'))
        if start is None:
            continue
        end = _parse_iso(item.get('end_iso')) or (start + timedelta(minutes=DEFAULT_HOLD_MINUTES))
        if end <= start:
            end = start + timedelta(minutes=DEFAULT_HOLD_MINUTES)
        label = item.get('label') if isinstance(item.get('label'), str) else ""
        slots.append(ProposedSlot(start=start, end=end, label=(label or "").strip()))

    now_utc = now_local.astimezone(timezone.utc)
    window_start = _parse_iso(obj.get('window_start_iso'))
    window_end = _parse_iso(obj.get('window_end_iso'))
    # Fall back to / bound the window using the slots and a sane cap so a bad extraction
    # can't pull an enormous range.
    if slots:
        window_start = window_start or min(s.start for s in slots)
        window_end = window_end or max(s.end for s in slots)
    window_start = window_start or now_utc
    window_end = window_end or (window_start + timedelta(days=7))
    if window_start < now_utc - timedelta(days=1):
        window_start = now_utc
    max_end = window_start + timedelta(days=MAX_WINDOW_DAYS)
    if window_end > max_end:
        window_end = max_end
    if window_end <= window_start:
        window_end = window_start + timedelta(days=1)

    return ScheduleProposal(is_scheduling=True, slots=slots, window_start=window_start, window_end=window_end)


# ---------------------------------------------------------------------------
# Free/busy (pure) + rendering
# ---------------------------------------------------------------------------


def _event_is_busy(ev: dict) -> bool:
    """Whether an event actually blocks time. Skip cancelled events and ones the user
    marked 'free' (transparency=transparent) so those don't manufacture false conflicts."""
    if ev.get('status') == 'cancelled':
        return False
    if ev.get('transparency') == 'transparent':
        return False
    return True


def compute_conflicts(events: List[dict], slots: List[ProposedSlot]) -> List[tuple]:
    """Pure: for each slot, return (slot, [conflicting events]) where a conflict is a
    busy event overlapping the slot. No network — testable directly."""
    results = []
    for slot in slots:
        conflicts = []
        for ev in events or []:
            if not _event_is_busy(ev):
                continue
            s, e = parse_event_times(ev)
            if s is None or e is None:
                continue
            if s < slot.end and e > slot.start:  # half-open overlap
                conflicts.append(ev)
        results.append((slot, conflicts))
    return results


def _fmt_time(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime('%a %b %-d, %-I:%M %p')


def _event_line(ev: dict, tz: ZoneInfo) -> str:
    title = (ev.get('summary') or 'Untitled').strip()
    s, e = parse_event_times(ev)
    if s and e:
        return f"{title} ({_fmt_time(s, tz)} – {e.astimezone(tz).strftime('%-I:%M %p')})"
    return title


def render_availability_block(
    proposal: ScheduleProposal, events: List[dict], tz: ZoneInfo, tz_label: str, now_local: datetime
) -> str:
    """Render the fenced AVAILABILITY text the drafter reads. Grounded entirely in the
    user's real calendar for the window."""
    lines: List[str] = [f"Current time: {_fmt_time(now_local, tz)} ({tz_label})."]

    if proposal.slots:
        for slot, conflicts in compute_conflicts(events, proposal.slots):
            when = _fmt_time(slot.start, tz)
            label = f" ({slot.label})" if slot.label else ""
            if conflicts:
                names = "; ".join(_event_line(c, tz) for c in conflicts[:3])
                lines.append(f"- {when}{label}: CONFLICT — you already have: {names}.")
            else:
                lines.append(f"- {when}{label}: FREE — nothing else on your calendar then.")
    else:
        lines.append("The sender is asking about your availability without naming a specific time.")

    busy = [e for e in (events or []) if _event_is_busy(e)]
    if busy:
        shown = "; ".join(_event_line(e, tz) for e in busy[:8])
        lines.append(f"Everything on your calendar in this window: {shown}.")
    else:
        lines.append("You have nothing else on your calendar in this window.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Calendar access (async) with 401 refresh
# ---------------------------------------------------------------------------


async def _read_events(uid: str, integration: dict, time_min: datetime, time_max: datetime) -> List[dict]:
    """Read calendar events for the window, refreshing the token once on a 401."""
    access_token = integration.get('access_token')
    try:
        return await get_google_calendar_events(
            access_token=access_token, time_min=time_min, time_max=time_max, max_results=MAX_WINDOW_EVENTS
        )
    except Exception as e:
        msg = str(e).lower()
        if "401" in msg or "authentication failed" in msg:
            new_token = await refresh_google_token(uid, integration)
            if new_token:
                return await get_google_calendar_events(
                    access_token=new_token, time_min=time_min, time_max=time_max, max_results=MAX_WINDOW_EVENTS
                )
        raise


async def build_availability_context(uid: str, thread: List[dict]) -> AvailabilityContext:
    """Async pre-step. Detects scheduling intent and, if present, grounds it in the
    user's real calendar. Degrades gracefully — anything that fails returns an empty or
    soft context so the draft still proceeds."""
    if not looks_like_scheduling(thread):
        return AvailabilityContext()

    inbound = _recent_inbound_text(thread)
    if not inbound:
        return AvailabilityContext()

    tz, tz_label = await run_blocking(db_executor, _resolve_tz, uid)
    now_local = datetime.now(tz)

    # Extract scheduling intent (one small LLM call, only past the prefilter).
    try:
        system_prompt, user_prompt = _build_extraction_prompt(inbound, now_local, tz_label)
        raw = await run_blocking(llm_executor, _invoke_llm, system_prompt, user_prompt)
        obj = _parse_json_object(raw)
    except Exception as e:
        logger.warning(f"reply_scheduling: extraction failed uid={uid}: {e}")
        return AvailabilityContext()
    if not obj:
        return AvailabilityContext()

    proposal = _proposal_from_obj(obj, now_local)
    if not proposal.is_scheduling:
        return AvailabilityContext()

    # Is Google Calendar connected? If not, tell the drafter to stay non-committal.
    integration = await run_blocking(db_executor, users_db.get_integration, uid, 'google_calendar')
    if not integration or not integration.get('connected') or not integration.get('access_token'):
        text = (
            "The sender is proposing/asking about a time, but your calendar isn't connected, so it can't be "
            "checked. Do NOT accept the time AND do NOT decline it — you don't know if you're free. Say you'll "
            "check and confirm, in the user's voice (e.g. that you'll get back to them)."
        )
        return AvailabilityContext(text=text, proposal=proposal, has_calendar=False)

    try:
        events = await _read_events(uid, integration, proposal.window_start, proposal.window_end)
    except Exception as e:
        logger.warning(f"reply_scheduling: calendar read failed uid={uid}: {e}")
        text = (
            "The sender is proposing/asking about a time, but your calendar couldn't be reached just now, so it "
            "can't be checked. Do NOT accept the time AND do NOT decline it — you don't know if you're free. Say "
            "you'll check and confirm, in the user's voice."
        )
        return AvailabilityContext(text=text, proposal=proposal, has_calendar=False)

    text = render_availability_block(proposal, events, tz, tz_label, now_local)
    return AvailabilityContext(text=text, proposal=proposal, has_calendar=True)


# ---------------------------------------------------------------------------
# Accept-slot judge (LLM) + hold creation (async)
# ---------------------------------------------------------------------------


def _build_accept_prompt(draft: str, slots: List[ProposedSlot], tz_label: str) -> tuple[str, str]:
    numbered = "\n".join(f"{i}. {_fence(s.label or 'meet')} at {s.start.isoformat()}" for i, s in enumerate(slots))
    system_prompt = (
        "You judge whether a short reply agrees to meet at one of the proposed times. "
        f"{UNTRUSTED_DATA_NOTICE}\n\n"
        "Only count it as accepted if the reply clearly says yes to a specific one of the listed times "
        "(e.g. 'yeah 1 works', 'sounds good', 'see you then'). A counter-proposal, a maybe, a decline, or "
        "a question is NOT an acceptance.\n"
        'Return ONLY a JSON object: {"accepted": boolean, "slot_index": integer}. '
        "slot_index is the 0-based index of the accepted time, or -1 when not accepted."
    )
    user_prompt = f"PROPOSED TIMES ({tz_label}):\n{numbered}\n\n" f"THE REPLY:\n<reply>\n{_fence(draft)}\n</reply>"
    return system_prompt, user_prompt


def judge_accepted_slot(draft: str, proposal: ScheduleProposal) -> Optional[ProposedSlot]:
    """Blocking LLM judge: did `draft` accept one of the proposed slots? Returns the
    accepted ProposedSlot or None. Wrap in run_blocking(llm_executor, ...)."""
    slots = proposal.slots if proposal else []
    if not draft or not slots:
        return None
    try:
        system_prompt, user_prompt = _build_accept_prompt(draft, slots, "local")
        raw = _invoke_llm(system_prompt, user_prompt)
        obj = _parse_json_object(raw)
    except Exception as e:
        logger.warning(f"reply_scheduling: accept judge failed: {e}")
        return None
    if not obj or not obj.get('accepted'):
        return None
    idx = obj.get('slot_index')
    if not isinstance(idx, int) or not (0 <= idx < len(slots)):
        return None
    return slots[idx]


async def create_hold(uid: str, slot: ProposedSlot, person_name: str) -> Optional[dict]:
    """Create a tentative "hold" event for an accepted slot. Returns a HoldEvent-shaped
    dict, or None on failure. Refreshes the token once on a 401."""
    integration = await run_blocking(db_executor, users_db.get_integration, uid, 'google_calendar')
    if not integration or not integration.get('connected') or not integration.get('access_token'):
        return None

    label = (slot.label or "").strip()
    title = f"[Hold] {label}" if label else f"[Hold] with {person_name}"
    description = f"Tentative hold created by Omi from your reply to {person_name}. Confirm or discard it."

    async def _create(token: str) -> dict:
        return await create_google_calendar_event(
            access_token=token,
            summary=title,
            start_time=slot.start,
            end_time=slot.end,
            description=description,
            status='tentative',
        )

    try:
        try:
            event = await _create(integration.get('access_token'))
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "authentication failed" in msg:
                new_token = await refresh_google_token(uid, integration)
                if not new_token:
                    raise
                event = await _create(new_token)
            else:
                raise
    except Exception as e:
        logger.warning(f"reply_scheduling: hold creation failed uid={uid}: {sanitize_pii(str(e))}")
        return None

    return {
        'event_id': event.get('id', ''),
        'title': title,
        'start_time': slot.start,
        'end_time': slot.end,
        'html_link': event.get('htmlLink'),
    }


# ---------------------------------------------------------------------------
# Orchestration — shared by the iMessage/Telegram/WhatsApp draft-reply routers
# ---------------------------------------------------------------------------


async def draft_reply_with_scheduling(
    uid: str,
    person_ref: str,
    thread: List[dict],
    intent: Optional[str],
    is_group: bool,
    media_context: str,
) -> tuple[dict, Optional[dict]]:
    """The full draft flow with availability awareness, shared by all three connectors.

    Pre-step (async): build the calendar-grounded availability context. Draft (sync, on
    llm_executor): generate the reply with that context. Post-step (async): if the reply
    accepted a concrete proposed slot, create a tentative hold. Returns (result, hold)
    where `result` is the draft_reply dict and `hold` is a HoldEvent-shaped dict or None.
    """
    avail = await build_availability_context(uid, thread)
    result = await run_blocking(
        llm_executor, draft_reply, uid, person_ref, thread, intent, is_group, media_context, avail.text
    )

    hold = None
    draft = result.get('draft')
    # Only try to hold when we produced a real 1:1-style reply grounded in a verified
    # calendar with concrete proposed slots. Ambiguous/abstained drafts never hold. An
    # escalated (needs_input) reply is a SUGGESTION the user hasn't sent yet — creating a
    # tentative calendar hold before they approve it would orphan the hold if they edit or
    # discard the reply, so skip the hold until they confirm.
    if (
        draft
        and avail.has_calendar
        and avail.proposal
        and avail.proposal.slots
        and not result.get('ambiguous')
        and not result.get('abstain')
        and not result.get('needs_input')
    ):
        accepted = await run_blocking(llm_executor, judge_accepted_slot, draft, avail.proposal)
        if accepted:
            hold = await create_hold(uid, accepted, result.get('name') or person_ref)

    return result, hold
