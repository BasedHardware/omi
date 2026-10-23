"""Read-only, owner-scoped tools and the prefetched evidence packet for agentic notes.

Authority is a notes *job*: the server binds the owner UID and conversation when
it builds the toolbox; no tool argument can name another owner, and no tool
writes. Records come through the same owner readers Dream's capability layer and
the meeting-context pack use (visibility, lock and screenshot-setting boundaries
included). Every read is bounded and best effort: a failed lookup returns an
error result to the model and never fails the notes.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

import database.action_items as action_items_db
import database.calendar_meetings as calendar_db
import database.screen_activity as screen_activity_db
from database.users import get_ai_user_profile
from models.agent_tools import Search
from utils.agent_capabilities.search import OwnerSearch
from utils.conversations.meeting_context_pack import gather_prior_meetings, load_people_documents
from utils.conversations.screen_people_leads import LEAD_MINUTES_BEFORE, screen_people_leads
from utils.conversations.screen_text_digest import MESSAGING_APPS
from utils.executors import db_executor, run_blocking
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage
from utils.llm.notes_agent_prompt import READ_TOOL_NAMES, VIEW_SCREENSHOT
from utils.llm.shaped_agent import model_json
from utils.model_text import ContextWindow, ToolTimeError, parse_tool_time, to_datetime, utc_z

logger = logging.getLogger(__name__)

MAX_RESULT_CHARACTERS = 6000
SCREEN_TEXT_CHARACTERS = 300
MAX_SCREEN_ROWS = 40
MAX_WINDOW_HOURS = 12
MAX_PEOPLE = 40
MAX_TOP_WINDOWS = 15


def _as_utc(value: Any) -> Optional[datetime]:
    """A server-side stored instant in UTC (naive means UTC); unreadable values are ``None``."""
    moment = to_datetime(value)
    return moment.astimezone(timezone.utc) if moment is not None else None


def _clip(value: Any, limit: int) -> str:
    text = ' '.join(str(value or '').split())
    return text if len(text) <= limit else text[: limit - 1] + '…'


def _bounded(value: Any) -> int:
    return value if isinstance(value, int) and value > 0 else 0


@dataclass
class ToolOutcome:
    content: str
    image: Optional[NotesFrameImage] = None


@dataclass
class NotesToolbox:
    """Tools for one owner's one conversation. Construct only from server-side state."""

    uid: str
    conversation_id: Optional[str]
    started_at: datetime
    finished_at: datetime
    frames: Sequence[NotesFrameImage] = ()
    seen_conversations: set[str] = field(default_factory=set)
    calls: Counter = field(default_factory=Counter)
    _search: Any = None
    # The conversation window: every time-range tool defaults to it (harness tool rule 1).
    window: ContextWindow = field(init=False)

    def __post_init__(self):
        if not self.uid:
            raise ValueError('notes toolbox requires an owner uid')
        self.started_at = _as_utc(self.started_at) or datetime.now(timezone.utc)
        self.finished_at = _as_utc(self.finished_at) or self.started_at
        self.window = ContextWindow(self.started_at, self.finished_at, 'conversation')
        if self._search is None:
            self._search = OwnerSearch(self.uid)
        self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {
            'get_screen_activity': self.get_screen_activity,
            VIEW_SCREENSHOT: self.view_screenshot,
            'get_calendar': self.get_calendar,
            'search_people': self.search_people,
            'search_memories': self.search_memories,
            'search_past_meetings': self.search_past_meetings,
            'get_past_meeting': self.get_past_meeting,
            'search_tasks': self.search_tasks,
        }
        assert set(self._handlers) == READ_TOOL_NAMES

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._handlers)

    async def call(self, name: str, arguments: Mapping[str, Any]) -> ToolOutcome:
        self.calls[name if name in self._handlers else 'unknown'] += 1
        handler = self._handlers.get(name)
        if handler is None:
            return ToolOutcome(json.dumps({'error': f'unknown tool {name}'}))
        try:
            result = await handler(**dict(arguments))
        except ToolTimeError as error:
            return ToolOutcome(json.dumps({'error': str(error)}, ensure_ascii=False))
        except TypeError:
            return ToolOutcome(json.dumps({'error': 'bad arguments; match the tool schema'}))
        except Exception as error:  # noqa: BLE001 - one failed lookup never fails the notes
            logger.warning('notes agent tool failed tool=%s error=%s', name, type(error).__name__)
            return ToolOutcome(json.dumps({'error': 'lookup unavailable; continue without it'}))
        if isinstance(result, ToolOutcome):
            return result
        text = model_json(result)
        if len(text) > MAX_RESULT_CHARACTERS:
            text = text[:MAX_RESULT_CHARACTERS] + '…(truncated)'
        return ToolOutcome(text)

    def _window(self, start: Any, end: Any) -> tuple[datetime, datetime]:
        return self.window.resolve(start, end, max_span=timedelta(hours=MAX_WINDOW_HOURS))

    async def get_screen_activity(self, start: Any = None, end: Any = None, query: str = '', limit: int = 25):
        lo, hi = self._window(start, end)
        rows: Any = await run_blocking(
            db_executor, screen_activity_db.get_screen_activity, self.uid, start_date=lo, end_date=hi, limit=400
        )
        wanted = {word.casefold() for word in str(query or '').split() if len(word) > 2}
        picked = []
        for row in rows or []:
            if not isinstance(row, Mapping):
                continue
            app = str(row.get('appName') or '')
            private = app.strip().casefold() in MESSAGING_APPS
            text = '' if private else str(row.get('ocrText') or '')
            haystack = f"{row.get('windowTitle') or ''} {text}".casefold()
            if wanted and not any(word in haystack for word in wanted):
                continue
            picked.append(
                {
                    'at': row.get('timestamp'),
                    'app': app,
                    'window': _clip(row.get('windowTitle'), 160),
                    **({'text': _clip(text, SCREEN_TEXT_CHARACTERS)} if text else {}),
                }
            )
        cap = max(1, min(_bounded(limit) or 25, MAX_SCREEN_ROWS))
        step = max(1, len(picked) // cap)
        return {'total_rows': len(picked), 'rows': picked[::step][:cap]}

    async def view_screenshot(self, frame_id: str = ''):
        frame = next((item for item in self.frames if item.frame_id == frame_id), None)
        if frame is None:
            return {'error': 'no screenshot with that id for this conversation'}
        return ToolOutcome(json.dumps({'ok': True, 'note': 'image attached in the next message'}), frame)

    async def get_calendar(self, start: Any = None, end: Any = None):
        lo, hi = self._window(start, end)
        meetings: Any = await run_blocking(db_executor, calendar_db.get_meetings_in_time_range, self.uid, lo, hi)
        return {'meetings': [calendar_row(meeting) for meeting in meetings or [] if isinstance(meeting, Mapping)]}

    async def search_people(self, query: str = ''):
        people = await run_blocking(db_executor, load_people_documents, self.uid)
        wanted = [word.casefold() for word in str(query or '').split() if word]
        found = []
        for person in people or []:
            names = [person.get('name'), *(person.get('aliases') or [])]
            blob = ' '.join(str(name) for name in names if isinstance(name, str)).casefold()
            if wanted and not all(word in blob for word in wanted):
                continue
            found.append(person_row(person))
            if len(found) >= MAX_PEOPLE:
                break
        return {'people': found}

    async def _owner_search(self, collection: str, query: str, limit: int, mode: str, **extra):
        request = Search.model_validate(
            {'query': str(query or '')[:500], 'collections': [collection], 'mode': mode, 'limit': limit, **extra}
        )
        result = await self._search.search(request, byte_budget=MAX_RESULT_CHARACTERS)
        return result.get('results') or []

    async def search_memories(self, query: str = '', limit: int = 8):
        hits = await self._owner_search('memory_items', query, min(_bounded(limit) or 8, 15), 'semantic')
        return {'memories': [hit.get('snippet') for hit in hits]}

    async def search_tasks(self, query: str = '', limit: int = 10):
        hits = await self._owner_search('action_items', query, min(_bounded(limit) or 10, 15), 'semantic')
        return {'tasks': [{'id': hit['ref'].partition('/')[2], 'text': hit.get('snippet')} for hit in hits]}

    async def search_past_meetings(
        self, query: str = '', person: str = '', start: Any = None, end: Any = None, limit: int = 6
    ):
        person_ref = None
        if person:
            people = await run_blocking(db_executor, load_people_documents, self.uid)
            wanted = person.strip().casefold()
            match = next((p for p in people or [] if str(p.get('name') or '').strip().casefold() == wanted), None)
            if match is None or not match.get('id'):
                return {'conversations': [], 'note': 'no known person with that exact name; try search_people'}
            person_ref = 'people/' + str(match['id'])
        # Earlier meetings: open start, ending where this conversation began unless told otherwise.
        lo = parse_tool_time(start, field='start')
        hi = parse_tool_time(end, field='end') or self.started_at
        hits = await self._owner_search(
            'conversations',
            query,
            min(_bounded(limit) or 6, 10),
            'lexical' if query else 'temporal',
            start=lo,
            end=hi,
            person_ref=person_ref,
        )
        rows = []
        for hit in hits:
            conversation_id = hit['ref'].partition('/')[2]
            if conversation_id == self.conversation_id:
                continue
            self.seen_conversations.add(conversation_id)
            rows.append({'conversation_id': conversation_id, 'gist': hit.get('snippet')})
        return {'conversations': rows}

    async def get_past_meeting(self, conversation_id: str = ''):
        if conversation_id not in self.seen_conversations or conversation_id == self.conversation_id:
            return {'error': 'unknown conversation id; use one from the packet or search_past_meetings'}
        record = await self._search.read('conversations/' + conversation_id)
        if not isinstance(record, Mapping):
            return {'error': 'that conversation is unavailable'}
        stored = record.get('structured')
        structured: Mapping[str, Any] = stored if isinstance(stored, Mapping) else {}
        open_items: Any = await run_blocking(
            db_executor,
            action_items_db.get_action_items,
            self.uid,
            conversation_id=conversation_id,
            completed=False,
            limit=5,
        )
        return {
            'conversation_id': conversation_id,
            'started_at': record.get('started_at') or record.get('created_at'),
            'title': structured.get('title'),
            'sections': [
                {'heading': section.get('heading'), 'body': _clip(section.get('body_markdown'), 700)}
                for section in (structured.get('sections') or [])[:6]
                if isinstance(section, Mapping)
            ]
            or [{'heading': 'Overview', 'body': _clip(structured.get('overview'), 1200)}],
            'open_tasks': [
                _clip(item.get('description'), 160) for item in open_items or [] if isinstance(item, Mapping)
            ],
        }


def calendar_row(meeting: Mapping[str, Any]) -> dict[str, Any]:
    participants = []
    for participant in meeting.get('participants') or []:
        if isinstance(participant, Mapping):
            participants.append(participant.get('name') or participant.get('email'))
        elif isinstance(participant, str):
            participants.append(participant)
    return {
        'title': _clip(meeting.get('title'), 160),
        'start': meeting.get('start_time'),
        'end': meeting.get('end_time'),
        'platform': meeting.get('platform'),
        'participants': [name for name in participants if name][:20],
        'source': meeting.get('calendar_source'),
    }


def person_row(person: Mapping[str, Any]) -> dict[str, Any]:
    aliases = [alias for alias in person.get('aliases') or [] if isinstance(alias, str) and '@' not in alias]
    note = person.get('relationship') or person.get('notes') or person.get('note') or person.get('description')
    return {
        'name': person.get('name'),
        **({'aliases': aliases[:5]} if aliases else {}),
        **({'note': _clip(note, 160)} if note else {}),
    }


def owner_profile(uid: str) -> str:
    try:
        profile: Any = get_ai_user_profile(uid) or {}
    except Exception as error:  # noqa: BLE001 - a missing profile is just less context
        logger.warning('notes agent owner profile read failed uid=%s: %s', uid, type(error).__name__)
        return ''
    text = profile.get('profile_text') if isinstance(profile, Mapping) else None
    return text if isinstance(text, str) else ''


def _top_windows(rows: Sequence[Any]) -> list[str]:
    titles: Counter = Counter()
    for row in rows:
        if not isinstance(row, Mapping) or not row.get('windowTitle'):
            continue
        titles[f"{row.get('appName') or ''} — {_clip(row.get('windowTitle'), 120)}"] += 1
    return [title for title, _count in titles.most_common(MAX_TOP_WINDOWS)]


def build_packet(
    *,
    uid: str,
    conversation_id: Optional[str],
    started_at: datetime,
    finished_at: datetime,
    timezone_name: str,
    response_language: str,
    length: str,
    transcript_words: int,
    account_owner_name: Optional[str],
    task_intelligence_capture: bool,
    open_tasks: Sequence[Any],
    roster: Any,
    owner_names: Sequence[str] = (),
    background: Optional[str],
    frames: Sequence[NotesFrameImage],
    capture_sources: Sequence[str] = (),
) -> tuple[dict[str, Any], set[str]]:
    """The cheap lookups every agent run gets. Returns ``(packet, seen_conversation_ids)``.

    Holds only per-conversation data; per-user context lives in the stable prefix.
    """
    start, end = _as_utc(started_at) or datetime.now(timezone.utc), _as_utc(finished_at)
    end = end if end and end >= start else start
    calendar: list[dict[str, Any]] = []
    windows: list[str] = []
    try:
        meetings: Any = calendar_db.get_meetings_in_time_range(uid, start, end)
        calendar = [calendar_row(meeting) for meeting in meetings or [] if isinstance(meeting, Mapping)]
    except Exception as error:  # noqa: BLE001 - every packet source degrades independently
        logger.warning('notes agent packet calendar read failed uid=%s: %s', uid, type(error).__name__)
    leads: list[dict[str, Any]] = []
    try:
        rows: Any = screen_activity_db.get_screen_activity(
            uid, start_date=start - timedelta(minutes=LEAD_MINUTES_BEFORE), end_date=end, limit=400
        )
        windows = _top_windows(rows or [])
        leads = screen_people_leads(rows or [], started_at=start, finished_at=end, owner_names=owner_names)
    except Exception as error:  # noqa: BLE001
        logger.warning('notes agent packet screen read failed uid=%s: %s', uid, type(error).__name__)
    listed = []
    for entry in getattr(roster, 'entries', None) or ():
        if getattr(entry, 'kind', None) == 'owner':
            continue
        listed.append(
            {
                'name': getattr(entry, 'display_name', None) or getattr(entry, 'email', None),
                'organization': getattr(entry, 'organization', None),
                'kind': getattr(entry, 'kind', None),
                'via': getattr(entry, 'source', None),
            }
        )
    related = []
    if roster is not None:
        conversation = SimpleNamespace(id=conversation_id, started_at=start)
        for note in gather_prior_meetings(uid, conversation, roster, start, timezone_name):
            related.append(
                {
                    'conversation_id': note.source_id,
                    'date': note.date_label,
                    'title': note.title,
                    'gist': note.gist,
                    'open_tasks': list(note.open_items),
                }
            )
    seen = {item['conversation_id'] for item in related if item['conversation_id']}
    packet = {
        'conversation': {
            'started_at': utc_z(start),
            'finished_at': utc_z(end),
            'timezone': timezone_name or 'UTC',
            'transcript_words': transcript_words,
            'capture_sources': list(capture_sources) or None,
        },
        'response_language': response_language,
        'LENGTH': length,
        'account_owner_name': account_owner_name,
        'task_intelligence_capture': task_intelligence_capture,
        'open_tasks': list(open_tasks)[:30],
        'calendar_overlap': calendar,
        'listed_participants': listed,
        'people_on_screen': leads,
        'top_windows_during_conversation': windows,
        'screenshots': [{'id': frame.frame_id, 'at': frame.offset_label} for frame in frames],
        'related_past_meetings': related,
        'background': background or None,
    }
    return packet, seen
