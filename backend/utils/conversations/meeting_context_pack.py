"""Bounded background context pack for rich meeting notes.

Gathers prior-meeting gists, people facts, goals, memories, and (flag-gated)
screen text for the notes-v2 dynamic block. Every read is individually
best-effort: a failing source degrades to absent context and never blocks note
generation. Dataclasses and the renderer are pure; only ``gather_*`` does I/O.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

import database.action_items as action_items_db
import database.calendar_meetings as calendar_db
import database.conversations as conversations_db
import database.goals as goals_db
import database.memories as memories_db
import database.screen_activity as screen_activity_db
from database._client import get_firestore_client
from database.auth import get_user_from_uid
from models.calendar_context import CalendarMeetingContext
from utils.conversations.meeting_context import stored_meeting_window
from utils.conversations.meeting_participants import MeetingRoster
from utils.conversations.screen_text_digest import digest_screen_rows
from utils.conversations.meeting_treatment import deduplicated_transcribed_speech_seconds

logger = logging.getLogger(__name__)

MAX_CONTEXT_PACK_CHARACTERS = 6_000
MAX_PRIOR_MEETINGS_CHARACTERS = 1_600
MAX_PEOPLE_CHARACTERS = 900
MAX_GOALS_CHARACTERS = 400
MAX_MEMORIES_CHARACTERS = 850
MAX_SCREEN_CHARACTERS = 2_500

MAX_PRIOR_MEETINGS = 3
MAX_PRIOR_OPEN_ITEMS = 3
MAX_PRIOR_GIST_CHARACTERS = 300
PRIOR_MEETING_LOOKBACK_DAYS = 180
MAX_PEOPLE_DOCS = 100
MAX_SCREEN_ROWS = 80
MIN_CLUSTER_COUNT = 2
MIN_SPEECH_SECONDS = 300

BACKGROUND_CONTEXT_HEADING = 'BACKGROUND CONTEXT (not part of this conversation)'


@dataclass(frozen=True)
class PriorMeetingNote:
    title: str
    date_label: str
    gist: str
    open_items: tuple[str, ...] = ()


@dataclass(frozen=True)
class PersonFact:
    name: str
    relationship: Optional[str] = None
    notes: Optional[str] = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class MeetingContextPack:
    prior_meetings: tuple[PriorMeetingNote, ...] = ()
    people_facts: tuple[PersonFact, ...] = ()
    goals: tuple[str, ...] = ()
    memories: tuple[str, ...] = ()
    screen_text: str = ''

    @property
    def empty(self) -> bool:
        return not (self.prior_meetings or self.people_facts or self.goals or self.memories or self.screen_text)


def _truncate(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + '…'


def _render_part(lines: Iterable[str], cap: int) -> str:
    rendered: list[str] = []
    used = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if used + len(line) + 1 > cap:
            # Truncate the item to what remains of the part budget instead of
            # dropping it — one oversized fact must not crowd out the rest.
            remaining = cap - used - 1
            if remaining < 2:
                break
            line = _truncate(line, remaining)
        rendered.append(line)
        used += len(line) + 1
    return '\n'.join(rendered)


def render_meeting_context_pack(pack: Optional[MeetingContextPack]) -> str:
    """Render the pack as the dynamic BACKGROUND CONTEXT block, <= 6000 chars."""
    if pack is None or pack.empty:
        return ''
    parts: list[str] = [BACKGROUND_CONTEXT_HEADING]
    prior_lines = []
    for note in pack.prior_meetings:
        line = f'- [{note.date_label}] {note.title}'
        if note.gist:
            line += f' — {note.gist}'
        prior_lines.append(line)
        for item in note.open_items:
            prior_lines.append(f'  open: {item}')
    prior = _render_part(prior_lines, MAX_PRIOR_MEETINGS_CHARACTERS)
    if prior:
        parts.append(f'PRIOR MEETINGS\n{prior}')
    people_lines = []
    for fact in pack.people_facts:
        line = f'- {fact.name}'
        detail = fact.relationship or ''
        if fact.aliases:
            detail = f'{detail}; aka {", ".join(fact.aliases)}' if detail else f'aka {", ".join(fact.aliases)}'
        if detail:
            line += f' ({detail})'
        if fact.notes:
            line += f' — {fact.notes}'
        people_lines.append(line)
    people = _render_part(people_lines, MAX_PEOPLE_CHARACTERS)
    if people:
        parts.append(f'PEOPLE\n{people}')
    goals = _render_part((f'- {goal}' for goal in pack.goals), MAX_GOALS_CHARACTERS)
    if goals:
        parts.append(f'GOALS\n{goals}')
    memories = _render_part((f'- {memory}' for memory in pack.memories), MAX_MEMORIES_CHARACTERS)
    if memories:
        parts.append(f'MEMORIES\n{memories}')
    if pack.screen_text:
        parts.append(f'SCREEN ACTIVITY\n{_truncate(pack.screen_text, MAX_SCREEN_CHARACTERS)}')
    rendered = '\n\n'.join(parts)
    if len(rendered) > MAX_CONTEXT_PACK_CHARACTERS:
        rendered = rendered[: MAX_CONTEXT_PACK_CHARACTERS - 1].rstrip() + '…'
    return rendered


def should_gather_meeting_context(conversation: Any, resolved_context: Optional[CalendarMeetingContext]) -> bool:
    """Whether this conversation is meeting-like enough to pay for context reads.

    True for a desktop meeting-role capture, whenever meeting identity already
    resolved, or when the transcript shows a real multi-party conversation
    (>= 2 speaker clusters and >= 300 seconds of deduplicated speech). The rich
    flag check itself stays at the call site so this stays a pure gate.
    """
    source = getattr(conversation, 'source', None)
    external_data = getattr(conversation, 'external_data', None) or {}
    if (
        getattr(source, 'value', source) == 'desktop'
        and isinstance(external_data, Mapping)
        and external_data.get('conversation_role') == 'meeting'
    ):
        return True
    if resolved_context is not None:
        return True
    segments = getattr(conversation, 'transcript_segments', None) or []
    cluster_ids = {
        getattr(segment, 'speaker_id', None) for segment in segments if getattr(segment, 'speaker_id', None) is not None
    }
    if len(cluster_ids) < MIN_CLUSTER_COUNT:
        return False
    return deduplicated_transcribed_speech_seconds(segments) >= MIN_SPEECH_SECONDS


def _log_source_failure(source: str, uid: str, exc: Exception) -> None:
    # No names, emails, transcript text, or exception payloads — only the
    # source and the exception type.
    logger.warning('meeting context pack %s read failed uid=%s: %s', source, uid, type(exc).__name__)


def resolve_owner_identity(uid: str) -> tuple[Optional[str], tuple[str, ...]]:
    """Best-effort owner display name and known email addresses.

    Reads the existing auth helper plus one user profile document; collects
    whichever string/list email fields actually exist. Both reads are cheap and
    individually guarded — an outage yields (None, ()) rather than a failure.
    """
    name: Optional[str] = None
    emails: list[str] = []
    try:
        user = get_user_from_uid(uid)
        if isinstance(user, Mapping):
            display_name = user.get('display_name')
            if isinstance(display_name, str) and display_name.strip() and display_name != 'AnonymousUser':
                name = display_name.strip()
            email = user.get('email')
            if isinstance(email, str) and email.strip():
                emails.append(email.strip())
    except Exception as exc:  # noqa: BLE001 - owner identity is best effort
        _log_source_failure('owner_auth', uid, exc)
    try:
        snapshot = get_firestore_client().collection('users').document(uid).get()
        data = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if isinstance(data, Mapping):
            profile_name = data.get('name')
            if name is None and isinstance(profile_name, str) and profile_name.strip():
                name = profile_name.strip()
            for field_name in ('email', 'emails', 'email_addresses'):
                raw = data.get(field_name)
                values = raw if isinstance(raw, (list, tuple)) else [raw]
                for value in values:
                    if isinstance(value, str) and value.strip() and '@' in value:
                        emails.append(value.strip())
    except Exception as exc:  # noqa: BLE001 - owner identity is best effort
        _log_source_failure('owner_profile', uid, exc)
    deduped = tuple(dict.fromkeys(email.casefold() for email in emails))
    return name, deduped


def load_people_documents(uid: str) -> list[dict[str, Any]]:
    """One bounded read of the user's people catalog, shared by roster and pack."""
    try:
        stream = (
            get_firestore_client()
            .collection('users')
            .document(uid)
            .collection('people')
            .limit(MAX_PEOPLE_DOCS)
            .stream()
        )
        documents: list[dict[str, Any]] = []
        for doc in stream:
            data = doc.to_dict()
            if not isinstance(data, dict):
                continue
            data.setdefault('id', doc.id)
            documents.append(data)
        return documents
    except Exception as exc:  # noqa: BLE001 - people context is best effort
        _log_source_failure('people', uid, exc)
        return []


def _roster_identity(roster: MeetingRoster) -> tuple[set[str], set[str], set[str]]:
    # Non-owner humans only: matching history or memories by the account owner
    # would pull in every conversation they ever had, and an AI agent's name is
    # not a useful identity needle.
    humans = [entry for entry in roster.entries if entry.kind == 'human']
    names = {entry.display_name.casefold() for entry in humans if entry.display_name}
    emails = {entry.email.casefold() for entry in humans if entry.email}
    person_ids = {entry.person_id for entry in humans if entry.person_id}
    return names, emails, person_ids


def _participant_identity(raw_participants: Any) -> tuple[set[str], set[str], set[str]]:
    names: set[str] = set()
    emails: set[str] = set()
    person_ids: set[str] = set()
    if not isinstance(raw_participants, list):
        return names, emails, person_ids
    for participant in raw_participants:
        if not isinstance(participant, Mapping):
            continue
        name = participant.get('name')
        email = participant.get('email')
        pid = participant.get('person_id') or participant.get('personId')
        if isinstance(name, str) and name.strip():
            names.add(name.strip().casefold())
        if isinstance(email, str) and email.strip():
            emails.add(email.strip().casefold())
        if isinstance(pid, str) and pid.strip():
            person_ids.add(pid.strip())
    return names, emails, person_ids


def _context_participants_overlap(context_data: Any, names: set[str], emails: set[str], person_ids: set[str]) -> bool:
    if not isinstance(context_data, Mapping):
        return False
    stored_names, stored_emails, stored_ids = _participant_identity(context_data.get('participants'))
    return bool((stored_names & names) or (stored_emails & emails) or (stored_ids & person_ids))


def _meeting_record_matches(record: Mapping[str, Any], names: set[str], emails: set[str], person_ids: set[str]) -> bool:
    stored_names, stored_emails, stored_ids = _participant_identity(record.get('participants'))
    return bool((stored_names & names) or (stored_emails & emails) or (stored_ids & person_ids))


def _record_person_ids(record: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    segments = record.get('transcript_segments')
    if not isinstance(segments, list):
        return ids
    for segment in segments:
        if isinstance(segment, Mapping):
            pid = segment.get('person_id')
            if isinstance(pid, str) and pid.strip():
                ids.add(pid.strip())
    return ids


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _local_date_label(value: Optional[datetime], timezone_name: Optional[str]) -> str:
    utc = _as_utc(value)
    if utc is None:
        return 'unknown date'
    try:
        tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    except Exception:
        tz = timezone.utc
    return utc.astimezone(tz).strftime('%Y-%m-%d')


def _conversation_gist(conversation_data: Mapping[str, Any]) -> str:
    structured = conversation_data.get('structured')
    if not isinstance(structured, Mapping):
        return ''
    sections = structured.get('sections')
    if isinstance(sections, list):
        for section in sections:
            if isinstance(section, Mapping):
                body = section.get('body_markdown')
                if isinstance(body, str) and body.strip():
                    return _truncate(body, MAX_PRIOR_GIST_CHARACTERS)
    overview = structured.get('overview')
    if isinstance(overview, str) and overview.strip():
        return _truncate(overview, MAX_PRIOR_GIST_CHARACTERS)
    return ''


def _gather_prior_meetings(
    uid: str,
    conversation: Any,
    roster: MeetingRoster,
    started_at: Optional[datetime],
    timezone_name: Optional[str],
) -> tuple[PriorMeetingNote, ...]:
    if started_at is None:
        return ()
    names, emails, person_ids = _roster_identity(roster)
    if not names and not emails and not person_ids:
        return ()
    window_start = started_at - timedelta(days=PRIOR_MEETING_LOOKBACK_DAYS)
    # The database helpers are typed as dict rows but this is a runtime trust
    # boundary — a malformed record degrades instead of aborting the source.
    meetings: Any = None
    conversations: Any = None
    try:
        meetings = calendar_db.list_meetings(uid, start_date=window_start, end_date=started_at, limit=60)
    except Exception as exc:  # noqa: BLE001 - best effort
        _log_source_failure('meetings', uid, exc)
    try:
        conversations = conversations_db.get_conversations_without_photos(
            uid, limit=60, start_date=window_start, end_date=started_at
        )
    except Exception as exc:  # noqa: BLE001 - best effort
        _log_source_failure('prior_conversations', uid, exc)
        conversations = []

    matched_event_ids: set[str] = set()
    matched_windows: list[tuple[datetime, datetime]] = []
    for record in meetings or []:
        if not isinstance(record, Mapping) or not _meeting_record_matches(record, names, emails, person_ids):
            continue
        event_id = record.get('calendar_event_id')
        if isinstance(event_id, str) and event_id:
            matched_event_ids.add(event_id)
        window = stored_meeting_window(dict(record))
        if window is not None:
            matched_windows.append(window)

    current_id = getattr(conversation, 'id', None)
    candidates: list[tuple[datetime, Mapping[str, Any]]] = []
    for record in conversations or []:
        if not isinstance(record, Mapping):
            continue
        record_id = record.get('id')
        if record_id and current_id and record_id == current_id:
            continue
        if record.get('discarded'):
            continue
        external_data = record.get('external_data')
        context_data = external_data.get('calendar_meeting_context') if isinstance(external_data, Mapping) else None
        matched = _context_participants_overlap(context_data, names, emails, person_ids)
        if not matched and person_ids:
            matched = bool(_record_person_ids(record) & person_ids)
        if not matched and isinstance(context_data, Mapping):
            event_id = context_data.get('calendar_event_id')
            if isinstance(event_id, str) and event_id and event_id in matched_event_ids:
                matched = True
        if not matched:
            record_start = _as_utc(record.get('started_at')) or _as_utc(record.get('created_at'))
            if record_start is not None and any(start <= record_start <= end for start, end in matched_windows):
                matched = True
        if not matched:
            continue
        sort_key = _as_utc(record.get('started_at')) or _as_utc(record.get('created_at')) or started_at
        candidates.append((sort_key, record))
    candidates.sort(key=lambda item: item[0], reverse=True)

    notes: list[PriorMeetingNote] = []
    for sort_key, record in candidates[:MAX_PRIOR_MEETINGS]:
        structured = record.get('structured')
        title = ''
        if isinstance(structured, Mapping) and isinstance(structured.get('title'), str):
            title = structured['title'].strip()
        record_external = record.get('external_data')
        record_context = (
            record_external.get('calendar_meeting_context') if isinstance(record_external, Mapping) else None
        )
        if not title and isinstance(record_context, Mapping) and isinstance(record_context.get('title'), str):
            title = record_context['title'].strip()
        open_items: tuple[str, ...] = ()
        record_id = record.get('id')
        if isinstance(record_id, str) and record_id:
            try:
                items: Any = action_items_db.get_action_items(uid, conversation_id=record_id, completed=False, limit=3)
                open_items = tuple(
                    item['description'].strip()
                    for item in items or []
                    if isinstance(item, Mapping)
                    and isinstance(item.get('description'), str)
                    and item['description'].strip()
                )[:MAX_PRIOR_OPEN_ITEMS]
            except Exception as exc:  # noqa: BLE001 - best effort
                _log_source_failure('prior_action_items', uid, exc)
        notes.append(
            PriorMeetingNote(
                title=title or 'Untitled meeting',
                date_label=_local_date_label(sort_key, timezone_name),
                gist=_conversation_gist(record),
                open_items=open_items,
            )
        )
    return tuple(notes)


def _person_email_values(person: Mapping[str, Any]) -> set[str]:
    """Collect email-shaped strings from whichever email fields the doc carries."""
    emails: set[str] = set()
    for field_name in ('email', 'emails', 'email_addresses'):
        raw = person.get(field_name)
        candidates = raw if isinstance(raw, (list, tuple)) else [raw]
        for value in candidates:
            if isinstance(value, str) and '@' in value:
                emails.add(value.strip().casefold())
    return emails


def _gather_people_facts(roster: MeetingRoster, people: Sequence[Mapping[str, Any]]) -> tuple[PersonFact, ...]:
    names, emails, person_ids = _roster_identity(roster)
    facts: list[PersonFact] = []
    seen: set[str] = set()
    for person in people:
        person_id = str(person.get('id')) if person.get('id') else ''
        raw_name = person.get('name')
        name = raw_name if isinstance(raw_name, str) else ''
        person_emails = _person_email_values(person)
        matched = (
            (person_id and person_id in person_ids)
            or (name and name.strip().casefold() in names)
            or bool(person_emails & emails)
        )
        if not matched or not name.strip() or person_id in seen:
            continue
        seen.add(person_id or name.strip().casefold())
        relationship = person.get('relationship') or person.get('role')
        notes_value = person.get('notes') or person.get('note') or person.get('description')
        aliases_raw = person.get('aliases')
        aliases = tuple(
            value.strip()
            for value in (aliases_raw if isinstance(aliases_raw, (list, tuple)) else [])
            if isinstance(value, str) and value.strip() and '@' not in value
        )
        facts.append(
            PersonFact(
                name=name.strip(),
                relationship=relationship.strip() if isinstance(relationship, str) and relationship.strip() else None,
                notes=(
                    _truncate(notes_value.strip(), 200)
                    if isinstance(notes_value, str) and notes_value.strip()
                    else None
                ),
                aliases=aliases[:6],
            )
        )
        if len(facts) >= 8:
            break
    return tuple(facts)


def _gather_goals(uid: str) -> tuple[str, ...]:
    try:
        goals: Any = goals_db.get_user_goals(uid, limit=5)
    except Exception as exc:  # noqa: BLE001 - best effort
        _log_source_failure('goals', uid, exc)
        return ()
    lines: list[str] = []
    for goal in goals or []:
        if not isinstance(goal, Mapping):
            continue
        title = goal.get('title') or goal.get('desired_outcome')
        if isinstance(title, str) and title.strip():
            lines.append(title.strip())
    return tuple(dict.fromkeys(lines))


def _gather_memories(uid: str, roster: MeetingRoster) -> tuple[str, ...]:
    names, emails, _person_ids = _roster_identity(roster)
    orgs = {entry.organization.casefold() for entry in roster.entries if entry.organization and entry.kind == 'human'}
    needles = names | emails | orgs
    if not needles:
        # No usable identity needle — skip the read entirely rather than
        # fetching memories nothing can match against.
        return ()
    try:
        memories: Any = memories_db.get_memories(uid, limit=40)
    except Exception as exc:  # noqa: BLE001 - best effort
        _log_source_failure('memories', uid, exc)
        return ()
    lines: list[str] = []
    for memory in memories or []:
        if not isinstance(memory, Mapping):
            continue
        content = memory.get('content')
        if not isinstance(content, str) or not content.strip():
            continue
        folded = content.casefold()
        if not any(needle in folded for needle in needles):
            continue
        lines.append(content.strip())
        if len(lines) >= 5:
            break
    return tuple(lines)


def _gather_screen_text(uid: str, conversation: Any) -> str:
    started_at = getattr(conversation, 'started_at', None)
    finished_at = getattr(conversation, 'finished_at', None)
    if not isinstance(started_at, datetime) or not isinstance(finished_at, datetime):
        return ''
    try:
        rows: Any = screen_activity_db.get_screen_activity(
            uid, start_date=started_at, end_date=finished_at, limit=MAX_SCREEN_ROWS
        )
    except Exception as exc:  # noqa: BLE001 - best effort
        _log_source_failure('screen_activity', uid, exc)
        return ''
    if not rows:
        return ''
    ordered = sorted((row for row in rows if isinstance(row, Mapping)), key=lambda row: str(row.get('timestamp') or ''))
    return digest_screen_rows(ordered, MAX_SCREEN_CHARACTERS)


def gather_meeting_context_pack(
    uid: str,
    conversation: Any,
    roster: MeetingRoster,
    *,
    people: Optional[Sequence[Mapping[str, Any]]] = None,
    include_screen_text: bool = False,
    timezone_name: Optional[str] = None,
) -> Optional[MeetingContextPack]:
    """Assemble the background pack. Every source degrades independently.

    ``people`` lets the caller reuse the single bounded people-catalog read it
    already made for roster normalization; when omitted the read happens here.
    Returns None when no source produced anything — the dynamic block is then
    simply absent.
    """
    started_at = _as_utc(getattr(conversation, 'started_at', None))
    people_docs = list(people) if people is not None else load_people_documents(uid)

    def _try(label, fn, default):
        # Each source degrades independently even when a helper returns
        # malformed data — one bad read never sinks the other parts.
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - best effort
            _log_source_failure(label, uid, exc)
            return default

    pack = MeetingContextPack(
        prior_meetings=_try(
            'prior_meetings',
            lambda: _gather_prior_meetings(uid, conversation, roster, started_at, timezone_name),
            (),
        ),
        people_facts=_try('people_facts', lambda: _gather_people_facts(roster, people_docs), ()),
        goals=_try('goals', lambda: _gather_goals(uid), ()),
        memories=_try('memories', lambda: _gather_memories(uid, roster), ()),
        screen_text=(
            _try('screen_activity', lambda: _gather_screen_text(uid, conversation), '') if include_screen_text else ''
        ),
    )
    return None if pack.empty else pack


__all__ = [
    'BACKGROUND_CONTEXT_HEADING',
    'MeetingContextPack',
    'PersonFact',
    'PriorMeetingNote',
    'gather_meeting_context_pack',
    'load_people_documents',
    'render_meeting_context_pack',
    'resolve_owner_identity',
    'should_gather_meeting_context',
]
