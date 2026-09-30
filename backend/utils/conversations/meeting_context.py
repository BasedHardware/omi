"""Bounded, read-only meeting context enrichment before note generation."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import database.calendar_meetings as calendar_db
import database.redis_db as redis_db
from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.conversation import CalendarEventLink, Conversation, CreateConversation

logger = logging.getLogger(__name__)

MAX_SCREEN_CONTEXT_ROWS = 80
MAX_SCREEN_CONTEXT_CHARACTERS = 12_000

# Stored-meeting overlap selection. Deliberately the same thresholds as the Google
# Calendar auto-link path (utils/conversations/calendar_linking.py) so a stored
# system-calendar meeting and a Google event are judged by identical rules.
MIN_OVERLAP_SECONDS = 10
MIN_OVERLAP_PERCENTAGE = 0.50
# How far outside the conversation window a stored meeting may start/end and still
# be a candidate. Recording usually starts late and stops early relative to the invite.
MEETING_SEARCH_TOLERANCE_MINUTES = 30

_CONFERENCING_MARKERS = ('zoom', 'microsoft teams', 'webex', 'facetime', 'google meet', 'meet.google')
_CONFERENCING_URL_MARKERS = ('meet.google.com/', 'zoom.us/j/', 'teams.microsoft.com/l/meetup', 'webex.com/meet')
# Native messaging-call apps already in the desktop ConferencingApps catalog.
# Matched on appName only — a Chrome tab titled "Discord" is not a call.
_MESSAGING_CALL_APPS = ('telegram', 'discord', 'slack', 'whatsapp')
_CALL_CONTROL_MARKERS = (
    'mute',
    'unmute',
    'end call',
    'hang up',
    'leave call',
    'stop video',
    'start video',
    'screen share',
    'screenshare',
    'in call',
    'in-call',
    'camera off',
    'camera on',
)
_CALL_CONTROL_PATTERN = re.compile(
    r'(?<!\w)(?:' + '|'.join(re.escape(marker) for marker in _CALL_CONTROL_MARKERS) + r')(?!\w)'
)
# A Google Meet tab is titled with the bare meeting code ("Meet - amc-iajq-asx").
# Once the call is joined the omnibox URL is often scrolled out of the capture, so
# the title is the only marker left. The code shape keeps this precise.
_MEET_TAB_TITLE = re.compile(r'^meet\s*[-\u2013\u2014]\s*\S', re.IGNORECASE)
_MEET_CODE_TITLE = re.compile(r'^meet\s*[-\u2013]\s*[a-z]{3}-[a-z]{4}-[a-z]{3}\b')
_OCR_UI_WORDS = {
    'audio',
    'camera',
    'chat',
    'leave',
    'meeting',
    'microphone',
    'more',
    'mute',
    'participants',
    'reactions',
    'record',
    'screen',
    'share',
    'stop video',
    'unmute',
}


def _is_messaging_call_app(app_name: str) -> bool:
    hay = (app_name or '').casefold()
    return any(marker in hay for marker in _MESSAGING_CALL_APPS)


def _has_call_control(row: dict[str, Any]) -> bool:
    hay = f'{row.get("windowTitle") or ""} {row.get("ocrText") or ""}'.casefold()
    return _CALL_CONTROL_PATTERN.search(hay) is not None


def is_conferencing_row(row: dict[str, Any]) -> bool:
    if _is_messaging_call_app(str(row.get('appName') or '')):
        return True
    haystack = f'{row.get("appName", "")} {row.get("windowTitle", "")}'.casefold()
    if any(marker in haystack for marker in _CONFERENCING_MARKERS):
        return True
    title = _clean_line(str(row.get('windowTitle') or '')).casefold()
    # A joined Meet tab is titled "Meet - <code>" or "Meet - <meeting name>".
    if _MEET_CODE_TITLE.match(title) or _MEET_TAB_TITLE.match(title):
        return True
    # Browser-hosted meetings show up as a plain tab title ("Meet - abc-defg-hij"),
    # so the app/title pair alone misses them. Match only unambiguous join URLs in
    # the OCR text — a bare 'zoom'/'meet' substring would sweep in unrelated pages.
    ocr_text = str(row.get('ocrText') or '').casefold()
    return any(marker in ocr_text for marker in _CONFERENCING_URL_MARKERS)


_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Conferencing UIs state the roster in a handful of fixed sentences. These are the
# only *free-text* source we trust for a name: everything else on a shared screen
# (browser tab strip, bookmarks bar, dock) looks exactly like a short capitalised
# name and is what made the previous line-scanning extractor emit "Coinflow Portal"
# and "Blocked users" as meeting participants.
_ROSTER_PATTERNS = (
    re.compile(r'^(?P<people>.+?)\s+(?:are|is)\s+in\s+this\s+call\b', re.IGNORECASE),
    re.compile(r'^(?P<people>.+?)\s+(?:has|have)\s+joined\b', re.IGNORECASE),
    re.compile(r'^Meet\s+with\s+(?P<people>.+?)\s*$', re.IGNORECASE),
    re.compile(r'^In\s+call\s+with\s+(?P<people>.+?)\s*$', re.IGNORECASE),
)

# Trailing decorations Meet/Zoom hang off a participant tile or chat line:
# "Ash Kalb 3:44PM", "Ash Kalb (Presenting, annotating)", "Ash Kalb (You)".
_NAME_DECORATION = re.compile(r'\s*(?:\(.*?\)|\d{1,2}:\d{2}\s*(?:AM|PM)?|·.*)\s*$', re.IGNORECASE)

_NON_PERSON_WORDS = {
    'account',
    'admin',
    'all',
    'anyone',
    'call',
    'everyone',
    'guest',
    'guests',
    'host',
    'me',
    'others',
    'participants',
    'people',
    'presenting',
    'you',
}

# One person is never called "X and Y". A line joining people is a roster or an
# event title (a calendar tile for a *different* meeting reads exactly like
# "Aryan Gupta and Nik"); only `_split_roster` may take such a line apart.
_JOINER_WORDS = {'and', 'with', 'vs', 'versus', 'or', 'et'}


def _clean_line(raw_line: str) -> str:
    return re.sub(r'\s+', ' ', raw_line).strip(' •|*·-—\t')


def _looks_like_person_name(value: str) -> bool:
    """A conservative person-name shape: 1-4 capitalised word-ish tokens.

    Deliberately shape-only. It is a *filter* applied to candidates that already
    came from a trusted source (a roster sentence, or a line corroborated by an
    email local part); it is never sufficient on its own.
    """
    if not value or len(value) > 60:
        return False
    words = value.split()
    if not 1 <= len(words) <= 4:
        return False
    if any(word.casefold() in _NON_PERSON_WORDS for word in words):
        return False
    if any(word.casefold().strip(".'’-") in _JOINER_WORDS for word in words):
        return False
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z.'\u2019\-]*", word) for word in words):
        return False
    # Require at least one capitalised token so "are in this" style fragments and
    # lowercase UI text cannot pass.
    return any(word[:1].isupper() for word in words)


def _split_roster(people: str) -> Iterable[str]:
    """Split "Ash Kalb and Boardy Boardman" / "A, B and C" into names."""
    for chunk in re.split(r',|\band\b|&|\+', people, flags=re.IGNORECASE):
        candidate = _clean_line(chunk)
        if _looks_like_person_name(candidate):
            yield candidate


def _roster_names(text: str) -> Iterable[str]:
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        # Roster sentences are short UI chrome, never a 4k-character OCR smear.
        if not line or len(line) > 200:
            continue
        for pattern in _ROSTER_PATTERNS:
            match = pattern.match(line)
            if match:
                yield from _split_roster(match.group('people'))
                break


def _emails(text: str) -> Iterable[str]:
    if '@' not in text:
        return
    for match in _EMAIL_PATTERN.finditer(text):
        yield match.group(0).strip('.').casefold()


def _decorated_name_lines(text: str) -> Iterable[str]:
    """Every line that *could* be a name once tile decorations are stripped.

    On its own this is the noisy set that produced the junk participants; callers
    must corroborate each entry against an email local part before accepting it.
    """
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        if '@' in line or 'http' in line.casefold():
            continue
        line = _clean_line(_NAME_DECORATION.sub('', line))
        if _looks_like_person_name(line):
            yield line


def _row_identity_signal(text: str, row: Optional[dict[str, Any]] = None) -> int:
    """Rank rows by how much identity they carry, so the bounded budget is spent
    on the pre-join/roster frames rather than on whichever frames happen to be
    chronologically first."""
    score = 0
    if any(True for _ in _roster_names(text)):
        score += 2
    if '@' in text and _EMAIL_PATTERN.search(text):
        score += 1
    if row is not None and _is_messaging_call_app(str(row.get('appName') or '')) and _has_call_control(row):
        score += 2
    return score


def _select_conferencing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conferencing = [row for row in rows if is_conferencing_row(row)]
    if not conferencing:
        return []
    combined = [
        (index, row, f'{row.get("windowTitle", "")}\n{row.get("ocrText", "")}')
        for index, row in enumerate(conferencing)
    ]
    # Highest identity signal first; chronological order breaks ties so the budget
    # stays deterministic.
    combined.sort(key=lambda item: (-_row_identity_signal(item[2], item[1]), item[0]))

    selected: list[dict[str, Any]] = []
    used_characters = 0
    for _, row, row_text in combined[:MAX_SCREEN_CONTEXT_ROWS]:
        remaining = MAX_SCREEN_CONTEXT_CHARACTERS - used_characters
        if remaining <= 0:
            break
        selected.append({**row, 'ocrText': row_text[:remaining]})
        used_characters += min(len(row_text), remaining)
    return selected


# Call-tile rule. A video tile labels its person with a bare name and nothing
# else, so no roster sentence or email ever corroborates it (conversation
# 449565eb: a 1:1 Meet whose other participant was on screen the whole call but
# never reached the roster). What corroborates a tile label is persistence: it
# stays on screen across the call while tab-strip text churns. The Swift twin
# (OnDeviceMeetingIdentityService.swift) implements the same rule; both are
# pinned by backend/tests/fixtures/meeting_identity/call_tile_vectors.json.
MIN_TILE_ROWS = 3
MIN_TILE_ROW_SHARE = 0.25
MAX_TILE_NAMES = 8
# A label that recurs across most of the same app's non-call rows too is browser
# chrome (bookmarks bar, tab strip, profile button), not a tile. Only judged with
# enough such rows.
MIN_NON_CALL_ROWS_FOR_CHROME_CHECK = 3
MAX_NON_CALL_ROW_SHARE = 0.5
_TILE_PARTICLES = {'al', 'bin', 'da', 'de', 'del', 'der', 'di', 'du', 'la', 'le', 'van', 'von'}
_OWNER_TILE_MARKER = re.compile(r'\((?:[^)]*[,\s])?you(?:[,\s][^)]*)?\)\s*$', re.IGNORECASE)
_MEET_CODE = re.compile(r'\b[a-z]{3}-[a-z]{4}-[a-z]{3}\b', re.IGNORECASE)
_TITLE_SEPARATORS = re.compile(r'\s[-–—|:]\s')
# Words that make a capitalised line app chrome, a calendar/meeting title, or a
# page name rather than a person. Matched per token, case-insensitively.
_TILE_CHROME_WORDS = frozenset(
    (
        'access account accounts activities admin advisories agenda allow analytics api backgrounds bank '
        'banking billing board bookmarks calendar call camera captions channel chat chrome cloud console '
        'controls cost dashboard dashboards demo docs document drive edit effects everyone feedback file '
        'general github gmail google guest hand help home host inbox intro issues join keys kickoff leave '
        'login meet meeting meetings mic microphone monitor more mute new notes notion options overview '
        'participants pay people platform portal present presentation presenting profile project pull raise '
        'rate reactions record recording registration report requests review roadmap screen search security '
        'settings share sharing sheets sign slack slides standup summary sync tab tabs team teams tokens '
        'untitled unmute update usage users view webex window workspace you zoom'
    ).split()
)
# AI notetakers and assistants join calls as tiles too; they are never human
# participants. Mirrors the agent catalog in meeting_participants.py.
_AI_AGENT_TILE_WORDS = frozenset(
    (
        'agent ai assistant boardy bot chatbot companion fathom fireflies gemini granola meetbot notebot notes '
        'notetaker otter recorder tldv'
    ).split()
)


def _tile_token_ok(token: str) -> bool:
    if token.casefold() in _TILE_PARTICLES:
        return True
    if not token[:1].isupper() or not all(ch.isalpha() or ch in "-'’" for ch in token):
        return False
    return any(ch.islower() for ch in token)


def _tile_name(line: str) -> Optional[str]:
    """The name a call tile shows on this line, if the line is only a name."""
    if '@' in line or 'http' in line.casefold() or _MEET_CODE.search(line):
        return None
    name = _clean_line(_NAME_DECORATION.sub('', line))
    tokens = name.split()
    if not 2 <= len(tokens) <= 4 or len(name) > 60:
        return None
    if not all(_tile_token_ok(token) for token in tokens):
        return None
    if tokens[0].casefold() in _TILE_PARTICLES or tokens[-1].casefold() in _TILE_PARTICLES:
        return None
    folded = {token.casefold().strip("'’-") for token in tokens}
    if folded & (_TILE_CHROME_WORDS | _NON_PERSON_WORDS | _JOINER_WORDS):
        return None
    return name


def is_ai_agent_tile_name(name: str) -> bool:
    tokens = [token.casefold().strip(".'’-") for token in name.split()]
    # Whole tokens only: a suffix test would drop "James Talbot" and "Alice Abbot".
    return any(token in _AI_AGENT_TILE_WORDS for token in tokens)


def _is_owner_name(name: str, owner_names: set[str], owner_locals: set[str]) -> bool:
    folded = name.casefold()
    tokens = folded.split()
    for owner in owner_names:
        owner_tokens = owner.split()
        if folded == owner or (
            len(owner_tokens) >= 2 and tokens[0] == owner_tokens[0] and tokens[-1] == owner_tokens[-1]
        ):
            return True
    joined = ''.join(tokens)
    return any(joined == re.sub(r'[._\-+]', '', local) for local in owner_locals)


_NATIVE_VIDEO_APPS = ('zoom', 'microsoft teams', 'webex', 'facetime')
_UNREAD_TITLE_PREFIX = re.compile(r'^\(\d+\)\s*')
_TITLE_TRAILING_NOISE = re.compile(r'[^\w)]+$')


def _is_call_window_row(row: dict[str, Any]) -> bool:
    """A row whose own window is the video call, the only place a tile label shows.

    Narrower than is_conferencing_row: a row recognised only by a Meet URL in its
    OCR is often another page (a LinkedIn profile, a tab strip), and a messaging
    app's recurring lines are its chat list. Messaging calls keep their own
    window-title rule (_messaging_call_participants).
    """
    app = str(row.get('appName') or '').casefold()
    if _is_messaging_call_app(app):
        return False
    if any(marker in app for marker in _NATIVE_VIDEO_APPS):
        return True
    title = _clean_line(str(row.get('windowTitle') or '')).casefold()
    return bool(_MEET_TAB_TITLE.match(title)) or any(marker in f'{app} {title}' for marker in _CONFERENCING_MARKERS)


def _title_part(part: str) -> str:
    """A window-title segment as it would read on screen: no unread counter, no trailing icon."""
    cleaned = _UNREAD_TITLE_PREFIX.sub('', _clean_line(part))
    return _TITLE_TRAILING_NOISE.sub('', cleaned).strip().casefold()


def _row_text(row: dict[str, Any]) -> str:
    return f'{row.get("windowTitle") or ""}\n{row.get("ocrText") or ""}'


def call_tile_names(
    rows: list[dict[str, Any]],
    *,
    owner_names: Iterable[str] = (),
    owner_emails: Iterable[str] = (),
) -> list[str]:
    """Names shown as call-tile labels, by persistence across the call's rows.

    A candidate is a line that is only a 2-4 token capitalised name (tile
    decorations stripped). It is accepted when it appears in at least
    MIN_TILE_ROWS conferencing rows and at least MIN_TILE_ROW_SHARE of them, is
    not the owner (their tile says "(You)", or it matches a supplied owner name
    or email), not an AI agent, not part of a conferencing window title, and
    not chrome that recurs across the non-call rows as well.
    """
    call_rows = [row for row in rows if _is_call_window_row(row)]
    if len(call_rows) < MIN_TILE_ROWS:
        return []
    owner_set = {_clean_line(name).casefold() for name in owner_names if name and name.strip()}
    owner_locals = {email.strip().casefold().split('@', 1)[0] for email in owner_emails if email and '@' in email}
    title_parts: set[str] = set()
    counts: dict[str, int] = {}
    spelling: dict[str, str] = {}
    order: list[str] = []
    for row in call_rows:
        title = _clean_line(str(row.get('windowTitle') or ''))
        title_parts.update(_title_part(part) for part in _TITLE_SEPARATORS.split(title) if part.strip())
        seen: set[str] = set()
        for raw_line in str(row.get('ocrText') or '').splitlines():
            line = _clean_line(raw_line)
            name = _tile_name(line)
            if name is None:
                continue
            key = name.casefold()
            if _OWNER_TILE_MARKER.search(line):
                owner_set.add(key)
            if key in seen:
                continue
            seen.add(key)
            if key not in counts:
                counts[key] = 0
                spelling[key] = name
                order.append(key)
            counts[key] += 1

    # Browser chrome (tab strip, bookmarks) recurs in the same app's other windows.
    call_apps = {str(row.get('appName') or '').casefold() for row in call_rows}
    non_call_rows = [
        row for row in rows if not _is_call_window_row(row) and str(row.get('appName') or '').casefold() in call_apps
    ]
    minimum = max(MIN_TILE_ROWS, MIN_TILE_ROW_SHARE * len(call_rows))
    accepted: list[str] = []
    for key in order:
        name = spelling[key]
        if counts[key] < minimum or key in title_parts:
            continue
        if _is_owner_name(name, owner_set, owner_locals) or is_ai_agent_tile_name(name):
            continue
        if len(non_call_rows) >= MIN_NON_CALL_ROWS_FOR_CHROME_CHECK:
            elsewhere = sum(
                1
                for row in non_call_rows
                if any(_tile_name(_clean_line(raw)) == name for raw in _row_text(row).splitlines())
            )
            if elsewhere > MAX_NON_CALL_ROW_SHARE * len(non_call_rows):
                continue
        accepted.append(name)
    accepted.sort(key=lambda name: (-counts[name.casefold()], order.index(name.casefold())))
    return accepted[:MAX_TILE_NAMES]


def participants_from_ocr(texts: Iterable[str], *, tile_names: Iterable[str] = ()) -> list[MeetingParticipant]:
    """Identity from conferencing OCR, precision first.

    A name is accepted only from a source that actually asserts participation:
      1. a roster sentence ("X and Y are in this call", "Meet with X"),
      2. a line whose first token matches the local part of an email address seen
         in the same window (so "Boardy Boardman" is corroborated by
         "boardy@boardy.ai", while "Coinflow Portal" has nothing behind it), or
      3. a persistent call-tile label, supplied by ``call_tile_names``.

    Every other line is discarded, including lines that look exactly like names.
    An empty list is the correct answer when nothing is corroborated: injecting
    phantom participants corrupts attribution far more than absent context does.
    """
    roster: list[str] = []
    emails: list[str] = []
    loose: list[str] = []
    for text in texts:
        if not text:
            continue
        for name in _roster_names(text):
            if name not in roster:
                roster.append(name)
        for email in _emails(text):
            if email not in emails:
                emails.append(email)
        for name in _decorated_name_lines(text):
            if name not in loose:
                loose.append(name)

    local_parts = {email.split('@', 1)[0] for email in emails}
    # Split "first.last" / "first_last" local parts so both halves can corroborate.
    local_tokens = {token for part in local_parts for token in re.split(r'[._\-]+', part) if token}

    names: list[str] = list(roster)
    for candidate in loose:
        if candidate in names:
            continue
        tokens = {word.casefold().strip(".'\u2019-") for word in candidate.split()}
        if tokens & local_tokens:
            names.append(candidate)
    known = {name.casefold() for name in names}
    for tile in tile_names:
        if tile.casefold() not in known:
            names.append(tile)
            known.add(tile.casefold())

    participants: list[MeetingParticipant] = []
    used_emails: set[str] = set()
    for name in names[:12]:
        tokens = {word.casefold().strip(".'\u2019-") for word in name.split()}
        match = next(
            (
                email
                for email in emails
                if email not in used_emails
                and {token for token in re.split(r'[._\-]+', email.split('@', 1)[0]) if token} & tokens
            ),
            None,
        )
        if match:
            used_emails.add(match)
        participants.append(MeetingParticipant(name=name, email=match))

    for email in emails:
        if email in used_emails:
            continue
        participants.append(MeetingParticipant(email=email))
        if len(participants) >= 12:
            break
    return participants[:12]


def _dominating_call_windows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        title = _clean_line(str(row.get('windowTitle') or ''))
        if not title:
            continue
        counts[title] = counts.get(title, 0) + 1
    titled_count = sum(counts.values())
    if not titled_count:
        return []
    top_title, top_count = max(counts.items(), key=lambda item: item[1])
    if not _looks_like_person_name(top_title):
        return []
    runner_up = max((count for title, count in counts.items() if title != top_title), default=0)
    if top_count * 2 <= titled_count or top_count <= runner_up:
        return []
    return [row for row in rows if _clean_line(str(row.get('windowTitle') or '')) == top_title]


def _messaging_call_participants(rows: list[dict[str, Any]]) -> list[MeetingParticipant]:
    """Name-shaped native-call window titles, only with call chrome or a dominant window.

    Telegram/Discord/Slack/WhatsApp do not print Meet-style roster sentences. The
    call window's title *is* the other party, but only when in-call chrome (mute /
    end call / video) corroborates a live call, or one title dominates the interval.
    Browsing many chats in the same window must not invent a roster.
    """
    messaging = [row for row in rows if _is_messaging_call_app(str(row.get('appName') or ''))]
    if not messaging:
        return []
    source = [row for row in messaging if _has_call_control(row)] or _dominating_call_windows(messaging)
    names: list[str] = []
    for row in source:
        title = _clean_line(str(row.get('windowTitle') or ''))
        if not _looks_like_person_name(title):
            continue
        if title.casefold() in _OCR_UI_WORDS:
            continue
        if title.casefold() == str(row.get('appName') or '').casefold():
            continue
        if title not in names:
            names.append(title)
    return [MeetingParticipant(name=name) for name in names[:12]]


def context_from_screen_activity(
    rows: list[dict[str, Any]],
    *,
    started_at: datetime,
    finished_at: datetime,
    duration_seconds: Optional[float] = None,
    owner_names: Iterable[str] = (),
    owner_emails: Iterable[str] = (),
) -> Optional[CalendarMeetingContext]:
    """Extract corroborated participants and a title from conferencing rows.

    This deliberately avoids another LLM call. OCR is used only as metadata; the
    transcript remains the authority for note claims. Returns None when no
    participant can be corroborated — a title-only context adds nothing to the
    prompt while implying an identity match that was not made. Call-tile
    persistence is judged over every row, not the character-budgeted selection:
    three full-desktop frames exhaust that budget.
    """
    selected = _select_conferencing_rows(rows)
    if not selected:
        return None

    tiles = call_tile_names(rows, owner_names=owner_names, owner_emails=owner_emails)
    participants = participants_from_ocr((str(row.get('ocrText') or '') for row in selected), tile_names=tiles)
    if not participants:
        participants = _messaging_call_participants(rows)
    if not participants:
        return None

    titles = [str(row.get('windowTitle') or '').strip() for row in selected if row.get('windowTitle')]
    title = next((value for value in titles if value.casefold() not in _OCR_UI_WORDS), 'Video meeting')
    app_name = str(selected[0].get('appName') or '').strip() or None

    # Callers that know the capture-session window is not the call length (#4056) pass the
    # transcript-span duration; the window stays the fallback when only timestamps exist.
    effective_seconds = duration_seconds if duration_seconds is not None else (finished_at - started_at).total_seconds()

    return CalendarMeetingContext(
        calendar_event_id='screen-activity',
        title=title,
        participants=participants,
        platform=app_name,
        start_time=started_at,
        duration_minutes=max(1, int(effective_seconds / 60)),
        calendar_source='screen_activity',
    )


def context_from_calendar_link(link: CalendarEventLink) -> CalendarMeetingContext:
    # `extract_attendees` fills both lists in one pass over the event's
    # attendees, so equal lengths mean entry *i* is one person's name and
    # address. Emitting them as separate name-only and email-only participants
    # described every attendee twice and lost which address belonged to whom.
    # Unequal lengths mean an attendee was missing one half, and positional
    # pairing would then attach the wrong address to a name — keep those apart.
    if len(link.attendees) == len(link.attendee_emails):
        participants = [
            MeetingParticipant(name=name, email=email) for name, email in zip(link.attendees, link.attendee_emails)
        ]
    else:
        participants = [MeetingParticipant(name=name) for name in link.attendees]
        participants.extend(MeetingParticipant(email=email) for email in link.attendee_emails)
    return CalendarMeetingContext(
        calendar_event_id=link.event_id,
        title=link.title,
        participants=participants,
        start_time=link.start_time,
        duration_minutes=max(1, int((link.end_time - link.start_time).total_seconds() / 60)),
        meeting_link=link.html_link,
        calendar_source='google',
    )


def merge_meeting_contexts(
    primary: Optional[CalendarMeetingContext], fallback: Optional[CalendarMeetingContext]
) -> Optional[CalendarMeetingContext]:
    if primary is None:
        return fallback
    if fallback is None:
        return primary
    participants = list(primary.participants)
    seen = {
        (participant.name or '').casefold() + '|' + (participant.email or '').casefold() for participant in participants
    }
    for participant in fallback.participants:
        key = (participant.name or '').casefold() + '|' + (participant.email or '').casefold()
        if key not in seen:
            participants.append(participant)
            seen.add(key)
    return primary.model_copy(
        update={
            'participants': participants,
            'platform': primary.platform or fallback.platform,
            'notes': primary.notes or fallback.notes,
        }
    )


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def stored_meeting_window(record: dict[str, Any]) -> Optional[tuple[datetime, datetime]]:
    """The (start, end) of a stored meeting record, in UTC.

    `end_time` is written by `POST /v1/calendar/meetings`, but older records and
    records round-tripped through `CalendarMeetingContext` only carry
    `duration_minutes`, so derive the end when it is absent.
    """
    start = _as_utc(record.get('start_time'))
    if start is None:
        return None
    end = _as_utc(record.get('end_time'))
    if end is None:
        duration = record.get('duration_minutes')
        if not isinstance(duration, (int, float)) or duration <= 0:
            return None
        end = start + timedelta(minutes=float(duration))
    if end <= start:
        return None
    return start, end


def select_overlapping_meeting(
    records: list[dict[str, Any]],
    *,
    started_at: datetime,
    finished_at: datetime,
) -> Optional[CalendarMeetingContext]:
    """Pick the stored meeting that best overlaps the conversation window.

    Mirrors the Google-Calendar auto-link thresholds: an overlap must be at least
    MIN_OVERLAP_SECONDS long *and* cover MIN_OVERLAP_PERCENTAGE of either the
    meeting or the conversation, so a short recording cannot latch onto an
    all-day block. Calendar-backed records outrank screen-derived records, then
    ties break on longest overlap. Returns None when nothing qualifies — the
    caller degrades to the next source.
    """
    conversation_start = _as_utc(started_at)
    conversation_end = _as_utc(finished_at)
    if conversation_start is None or conversation_end is None or conversation_end <= conversation_start:
        return None
    conversation_duration = (conversation_end - conversation_start).total_seconds()

    best_record: Optional[dict[str, Any]] = None
    best_score: tuple[int, float] = (-1, 0.0)
    for record in records:
        window = stored_meeting_window(record)
        if window is None:
            continue
        meeting_start, meeting_end = window
        overlap = (min(meeting_end, conversation_end) - max(meeting_start, conversation_start)).total_seconds()
        if overlap < MIN_OVERLAP_SECONDS:
            continue
        meeting_duration = (meeting_end - meeting_start).total_seconds()
        covers_meeting = meeting_duration > 0 and overlap / meeting_duration >= MIN_OVERLAP_PERCENTAGE
        covers_conversation = conversation_duration > 0 and overlap / conversation_duration >= MIN_OVERLAP_PERCENTAGE
        if not (covers_meeting or covers_conversation):
            continue
        # A calendar-backed event is authoritative for identity even when a
        # screen-derived row overlaps a little longer. On-device identity is the
        # fallback stored in the same collection, not a peer calendar source.
        source_priority = 0 if record.get('calendar_source') == 'screen_activity' else 1
        score = (source_priority, overlap)
        if score > best_score:
            best_score = score
            best_record = record

    if best_record is None:
        return None
    parsed = CalendarMeetingContext.from_records([best_record])
    return parsed[0] if parsed else None


def resolve_meeting_context(
    *,
    direct: Optional[CalendarMeetingContext],
    stored: Optional[Callable[[], Optional[CalendarMeetingContext]]] = None,
    calendar: Optional[Callable[[], Optional[CalendarMeetingContext]]] = None,
    screen: Optional[Callable[[], Optional[CalendarMeetingContext]]] = None,
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> Optional[CalendarMeetingContext]:
    """Layer identity sources, best first, degrading to None.

    `direct` is the context already on the conversation (sent by the client on the
    create request). The suppliers are called in order and each is optional; a
    supplier that is None is a disabled layer, and a supplier that raises is
    reported via `on_error` and skipped. A better source always wins the scalar
    fields; weaker sources only contribute participants the better ones missed.

    Returning None is a normal outcome, not a failure: summarization proceeds
    without a CALENDAR MEETING CONTEXT block.
    """

    def _call(name: str, supplier: Optional[Callable[[], Optional[CalendarMeetingContext]]]):
        if supplier is None:
            return None
        try:
            return supplier()
        except Exception as exc:  # noqa: BLE001 - no identity source may fail the conversation
            if on_error is not None:
                on_error(name, exc)
            return None

    stored_context = _call('stored', stored)
    stored_screen = stored_context if stored_context and stored_context.calendar_source == 'screen_activity' else None
    stored_calendar = None if stored_screen else stored_context
    direct_screen = direct if direct and direct.calendar_source == 'screen_activity' else None
    direct_calendar = None if direct_screen else direct

    context = merge_meeting_contexts(stored_calendar, direct_calendar)
    context = merge_meeting_contexts(context, _call('calendar', calendar))
    context = merge_meeting_contexts(context, stored_screen)
    context = merge_meeting_contexts(context, direct_screen)
    return merge_meeting_contexts(context, _call('screen', screen))


def stored_meeting_context(conversation: Any) -> Optional[CalendarMeetingContext]:
    direct = getattr(conversation, 'calendar_meeting_context', None)
    if isinstance(direct, CalendarMeetingContext):
        return direct
    if isinstance(direct, dict) and direct:
        return CalendarMeetingContext(**direct)
    raw_external_data = getattr(conversation, 'external_data', None)
    external_data = raw_external_data if isinstance(raw_external_data, dict) else {}
    raw = external_data.get('calendar_meeting_context')
    if isinstance(raw, CalendarMeetingContext):
        return raw
    if isinstance(raw, dict) and raw:
        return CalendarMeetingContext(**raw)
    return None


def store_meeting_context(conversation: Any, context: CalendarMeetingContext) -> None:
    if isinstance(conversation, CreateConversation):
        conversation.calendar_meeting_context = context
        return
    external_data = dict(getattr(conversation, 'external_data', None) or {})
    external_data['calendar_meeting_context'] = context.model_dump(mode='json')
    conversation.external_data = external_data


def meeting_context_from_redis_mapping(uid: str, conversation: Any) -> Optional[CalendarMeetingContext]:
    """Exact conversation->meeting association, when one was recorded.

    `redis_db.set_conversation_meeting_id` is written in exactly one place
    (`routers/listen/conversations.py`, at desktop conversation creation) and only
    when a stored meeting already overlaps that instant, so this is frequently
    absent. It is an optimization, never the only path.
    """
    conversation_id = getattr(conversation, 'id', None)
    if not isinstance(conversation, Conversation) or not conversation_id:
        return None
    try:
        meeting_id = redis_db.get_conversation_meeting_id(conversation_id)
        if not meeting_id:
            return None
        meeting_data = calendar_db.get_meeting(uid, meeting_id)
        if not meeting_data:
            return None
        parsed = CalendarMeetingContext.from_records([meeting_data])
        return parsed[0] if parsed else None
    except Exception as exc:
        logger.error('Error retrieving mapped meeting context for conversation %s: %s', conversation_id, exc)
        return None


def meeting_context_from_time_overlap(
    uid: str, started_at: Optional[datetime], finished_at: Optional[datetime]
) -> Optional[CalendarMeetingContext]:
    """Time-overlap lookup against the user's stored meetings.

    Independent of the Redis mapping and of any OAuth grant: it reads the same
    `users/{uid}/meetings` collection that `POST /v1/calendar/meetings` writes.
    """
    if started_at is None or finished_at is None:
        return None
    try:
        tolerance = timedelta(minutes=MEETING_SEARCH_TOLERANCE_MINUTES)
        records = calendar_db.get_meetings_in_time_range(uid, started_at - tolerance, finished_at + tolerance)
        return select_overlapping_meeting(records, started_at=started_at, finished_at=finished_at)
    except Exception as exc:
        logger.error('Error reading stored meetings by time range for uid %s: %s', uid, exc)
        return None
