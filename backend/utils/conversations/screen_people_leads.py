"""People the owner's screen named during a conversation: call windows, chats, profile pages. Pure.

Window titles carry the strongest identity evidence a meeting leaves on the Mac:
a Telegram or WhatsApp call window titled with one person, or a LinkedIn profile
opened from the calendar invite just before the call. These are leads for the
notes agent to weigh against the transcript, never attendance facts by themselves.
Only titles and a call-marker check on OCR are read; no OCR text is returned.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from utils.conversations.meeting_participants import looks_like_ai_agent_name

LEAD_MINUTES_BEFORE = 10
MAX_LEADS = 8
_LINKEDIN = re.compile(r'^(?:\(\d+\)\s*)?(?P<name>[^|]{3,60}?)\s*\|\s*LinkedIn\b')
_CHAT_SUFFIX = re.compile(r'\s*[–-]\s*\(\d+\)\s*$')
_MESSENGER_APPS = frozenset(
    {'telegram', 'whatsapp', 'signal', 'messages', 'messenger', 'facetime', 'wechat', 'line', 'discord', 'slack'}
)
_CALL_MARKERS = ('end call', 'leave call', 'hang up', 'ongoing call', 'calling…', 'calling...', 'call in progress')
_KIND_RANK = {'call_window': 0, 'profile_page': 1, 'chat_window': 2}


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            return _as_utc(datetime.fromisoformat(value.strip().replace('Z', '+00:00').replace(' ', 'T', 1)))
        except ValueError:
            return None
    return None


def _clean(text: str) -> str:
    # Messenger titles wrap names in bidi isolates (U+2068/U+2069) and marks.
    kept = ''.join(ch for ch in text if unicodedata.category(ch) not in {'Cf', 'Cc'})
    return ' '.join(kept.split())


_NOT_PERSON_WORDS = frozenset(
    'updates alerts support team group bot bots channel home ops status news chat community dev metrics '
    'notifications announcements general'.split()
)


def _person_like(name: str) -> bool:
    """Two to four capitalized words without digits: a person, not a group, channel or app."""
    words = name.split()
    if not 2 <= len(words) <= 4 or any(ch.isdigit() or ch in ':&@#/' for ch in name):
        return False
    if any(word.casefold().strip('.,') in _NOT_PERSON_WORDS for word in words):
        return False
    return all(word[:1].isupper() and any(ch.isalpha() for ch in word) for word in words)


def _row_lead(row: Mapping[str, Any]) -> Optional[tuple[str, str]]:
    title = _clean(str(row.get('windowTitle') or ''))
    app = str(row.get('appName') or '').strip().casefold()
    match = _LINKEDIN.match(title)
    if match:
        name = match.group('name').strip()
        return (name, 'profile_page') if _person_like(name) else None
    if app in _MESSENGER_APPS and title:
        name = _CHAT_SUFFIX.sub('', title).strip()
        if not _person_like(name):
            return None
        ocr = str(row.get('ocrText') or '').casefold()
        return name, 'call_window' if any(marker in ocr for marker in _CALL_MARKERS) else 'chat_window'
    return None


def screen_people_leads(
    rows: Iterable[Any],
    *,
    started_at: datetime,
    finished_at: datetime,
    owner_names: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Leads seen from ten minutes before the start to the end, strongest first."""
    start = _as_utc(started_at)
    end = _as_utc(finished_at) or start
    if start is None or end is None:
        return []
    lo = start - timedelta(minutes=LEAD_MINUTES_BEFORE)
    owners = {_clean(name).casefold() for name in owner_names if name}
    leads: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        at = _as_utc(row.get('timestamp'))
        if at is None or not lo <= at <= end:
            continue
        found = _row_lead(row)
        if found is None:
            continue
        name, kind = found
        key = name.casefold()
        if key in owners or looks_like_ai_agent_name(name):
            continue
        lead = leads.setdefault(
            key,
            {'name': name, 'evidence': set(), 'sightings': 0, 'first_seen_min': None, 'app': row.get('appName')},
        )
        lead['evidence'].add(kind)
        lead['sightings'] += 1
        minute = round((at - start).total_seconds() / 60)
        if lead['first_seen_min'] is None or minute < lead['first_seen_min']:
            lead['first_seen_min'] = minute
    ordered = sorted(
        leads.values(),
        key=lambda lead: (min(_KIND_RANK[kind] for kind in lead['evidence']), -lead['sightings']),
    )
    return [{**lead, 'evidence': sorted(lead['evidence'], key=_KIND_RANK.__getitem__)} for lead in ordered[:MAX_LEADS]]
