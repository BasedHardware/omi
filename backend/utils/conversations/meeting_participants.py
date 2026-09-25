"""Normalize meeting participants into a factual roster.

Pure helpers: no I/O and no imports outside ``models/``. The roster feeds the
shared prompt prefix and the notes post-validator, so every claim in it must
come from meeting metadata or the user's people catalog — never inferred from
the transcript itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Union

from models.calendar_context import CalendarMeetingContext
from models.conversation_enums import ConversationSource

EntryKind = str  # 'owner' | 'human' | 'ai_agent'


@dataclass(frozen=True)
class RosterEntry:
    """One normalized participant claim."""

    display_name: Optional[str]
    email: Optional[str]
    organization: Optional[str]
    kind: EntryKind
    source: str
    person_id: Optional[str] = None


@dataclass(frozen=True)
class MeetingRoster:
    """The participant list plus the title the prompt may safely show."""

    entries: tuple[RosterEntry, ...]
    display_title: Optional[str]
    # True when display_title came from a screen/window title rather than a
    # calendar record — callers may treat it as weaker identity.
    title_is_window_title: bool


# Maintained catalog of AI notetaker/assistant identities on invites and
# conferencing rosters. Names match exactly (case-insensitive) or via the
# ``* Notetaker`` suffix — a broad substring list misclassifies humans like
# "Jamie" or "Gong". ``*.local`` bot domains and people-catalog agent flags
# are detected separately in ``_looks_ai_agent``.
_AI_AGENT_NAMES = frozenset(
    {
        'boardy',
        'otter',
        'otter.ai',
        'fireflies',
        'fred from fireflies',
        'read.ai',
        'fathom',
        'tl;dv',
        'notetaker',
        'zoom ai companion',
        'gemini',
        'omi agent',
        'o. omi agent',
    }
)
# Agent products that surface with a persona surname or a prefix on real
# rosters ("Boardy Boardman", "O. Omi Agent"). The first token is distinctive
# enough for these brands; phrases match on word boundaries anywhere in the
# name. Plain first names are deliberately absent (see note above).
_AI_AGENT_FIRST_TOKENS = frozenset({'boardy', 'fireflies', 'otter.ai', 'read.ai', 'tl;dv'})
_AI_AGENT_PHRASES = ('omi agent', 'zoom ai companion', 'fred from fireflies', 'notetaker')
_AI_DOMAINS = frozenset(
    {
        'otter.ai',
        'fireflies.ai',
        'boardy.ai',
        'read.ai',
        'fathom.video',
        'tldv.io',
    }
)

# People-catalog resolution and organization derivation are strong signals only
# on a domain someone actually owns. Freemail domains turn a shared local part
# into a guess, so they are excluded from those two — owner local-part matching
# still compares across every domain.
_FREEMAIL_DOMAINS = {
    'gmail.com',
    'googlemail.com',
    'yahoo.com',
    'hotmail.com',
    'outlook.com',
    'live.com',
    'msn.com',
    'icloud.com',
    'me.com',
    'mac.com',
    'aol.com',
    'proton.me',
    'protonmail.com',
    'pm.me',
    'gmx.com',
    'gmx.net',
    'mail.com',
    'zoho.com',
    'yandex.com',
    'fastmail.com',
    'hey.com',
    'duck.com',
}

_BIDI_MARKS = re.compile(r'[‎‏‪-‮⁦-⁩]')
_UNREAD_PREFIX = re.compile(r'^\s*\(?\d{1,4}\)?\s+')
# Telegram-style trailing unread counters: "Release – (68226)".
_UNREAD_SUFFIX = re.compile(r'\s*[-–—|]\s*\(\d{1,6}\)\s*$')
_NAME_DECORATION = re.compile(r'\s*(?:\(.*?\)|\d{1,2}:\d{2}\s*(?:AM|PM)?|·.*)\s*$', re.IGNORECASE)

# A Google Meet window title is "Meet - <code>" (optionally behind an emoji or
# capture chrome); the xxx-yyyy-zzz code shape is unambiguous.
_MEET_CODE_TITLE = re.compile(r'(?<![\w-])meet\s*[-–—]\s*[a-z]{3}-[a-z]{4}-[a-z]{3}\b', re.IGNORECASE)
_ZOOM_TITLE = re.compile(r'(?<!\w)zoom(?:\s+meeting)?\b', re.IGNORECASE)
_TEAMS_TITLE = re.compile(r'(?<!\w)microsoft\s+teams\b', re.IGNORECASE)
# Browser/capture chrome appended after a call title: " - Google Chrome",
# " - David (scalingforever.com)", "| Audio playing".
_CAPTURE_CHROME = re.compile(
    r'\s*[-–—|]\s*(?:camera and microphone recording|microphone and camera recording|audio playing|'
    r'video playing|screen sharing|sharing screen)\b.*$',
    re.IGNORECASE,
)
_BROWSER_PROFILE_SUFFIX = re.compile(r'\s*-\s*[^-|–—]+\s*\([a-z0-9.-]+\.[a-z]{2,}\)\s*$', re.IGNORECASE)

# Window-title chrome only ever applies to screen-derived titles. Calendar
# titles are authoritative and pass through untouched.
_CHROME_ONLY_TITLES = {
    'zoom meeting',
    'zoom',
    'google meet',
    'microsoft teams',
    'teams meeting',
    'microsoft teams meeting',
    'webex meeting',
    'meet',
}
_TITLE_SUFFIXES = (
    'google meet',
    'microsoft teams',
    'teams',
    'zoom',
    'zoom meeting',
    'webex',
    'skype',
    'slack',
    'discord',
    'telegram',
    'whatsapp',
    'facetime',
    'google chrome',
    'chromium',
    'mozilla firefox',
    'firefox',
    'safari',
    'microsoft edge',
    'edge',
    'brave',
    'brave browser',
    'arc',
    'opera',
    'vivaldi',
    'orion',
    'personal - microsoft edge',
    'incognito',
    'private browsing',
)
_TITLE_SUFFIX_RE = re.compile(
    r'\s*[-–—|•·]\s*(?:' + '|'.join(re.escape(s) for s in sorted(_TITLE_SUFFIXES, key=len, reverse=True)) + r')\s*$',
    re.IGNORECASE,
)


def _strip_bidi(value: str) -> str:
    return _BIDI_MARKS.sub('', value or '')


def _clean_whitespace(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()


def clean_display_title(title: Optional[str], *, screen_derived: bool, platform: Optional[str] = None) -> Optional[str]:
    """Normalize a meeting title for display.

    Calendar titles pass through untouched. Screen-derived titles are window
    titles: bidi marks and unread counters, capture/browser chrome, and
    conferencing signatures are normalized to a canonical ``<App> call`` name —
    ``Telegram call: <chat>`` only when the platform really is Telegram, so an
    arbitrary chat app is never tagged as Telegram. A title that is nothing
    but chrome returns None rather than a fake name.
    """
    if not title:
        return None
    if not screen_derived:
        return title.strip() or None
    cleaned = _clean_whitespace(_strip_bidi(title))
    cleaned = _UNREAD_PREFIX.sub('', cleaned)
    cleaned = _UNREAD_SUFFIX.sub('', cleaned)
    if not cleaned:
        return None
    if 'telegram' in (platform or '').casefold():
        topic = _CAPTURE_CHROME.sub('', cleaned).strip(' •|*·-—\t')
        return f'Telegram call: {topic}' if topic else 'Telegram call'
    if _MEET_CODE_TITLE.search(cleaned):
        return 'Google Meet call'
    # Zoom/Teams signatures are only conferencing chrome when they LEAD the
    # title (a trailing " - Zoom" after a person name is just app chrome).
    zoom = _ZOOM_TITLE.search(cleaned)
    if zoom and not cleaned[: zoom.start()].strip(' •|*·-—\t'):
        return 'Zoom call'
    teams = _TEAMS_TITLE.search(cleaned)
    if teams and not cleaned[: teams.start()].strip(' •|*·-—\t'):
        return 'Microsoft Teams call'
    cleaned = _CAPTURE_CHROME.sub('', cleaned)
    for _ in range(4):
        stripped = _BROWSER_PROFILE_SUFFIX.sub('', cleaned)
        stripped = _TITLE_SUFFIX_RE.sub('', stripped).strip(' •|*·-—\t')
        if stripped == cleaned:
            break
        cleaned = stripped
    cleaned = cleaned.strip(' •|*·-—\t')
    if not cleaned:
        return None
    if cleaned.casefold() in _CHROME_ONLY_TITLES:
        return None
    return cleaned


def _clean_person_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    cleaned = _clean_whitespace(_strip_bidi(name))
    cleaned = _UNREAD_PREFIX.sub('', cleaned)
    cleaned = _clean_whitespace(_NAME_DECORATION.sub('', cleaned))
    return cleaned or None


def _first_token(name: Optional[str]) -> str:
    return (name or '').strip().split(' ', 1)[0].casefold() if name and name.strip() else ''


def _surname_token(name: Optional[str]) -> str:
    parts = (name or '').strip().split()
    return parts[-1].casefold() if len(parts) >= 2 else ''


def _surname_compatible(a: str, b: str) -> bool:
    """Surname exact, prefix, or OCR-fragment match — covers truncation like
    'David ZI' next to 'David Zing'. A real conflicting surname (Smith vs
    Zhang) is a different person; a one- or two-letter fragment only shares
    the initial."""
    if not a or not b:
        return True
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 2 and longer.startswith(shorter):
        return True
    return len(shorter) <= 2 and shorter[0] == longer[0]


def _email_domain(email: Optional[str]) -> str:
    if not email or '@' not in email:
        return ''
    return email.split('@', 1)[1].casefold()


def _email_local(email: Optional[str]) -> str:
    if not email or '@' not in email:
        return ''
    return email.split('@', 1)[0].casefold()


def _is_freemail_domain(domain: str) -> bool:
    return domain in _FREEMAIL_DOMAINS


def _looks_ai_agent(name: Optional[str], email: Optional[str], person: Optional[Mapping[str, Any]]) -> bool:
    domain = _email_domain(email)
    if domain.endswith('.local') or domain in _AI_DOMAINS:
        return True
    hay = (name or '').strip().casefold()
    if hay in _AI_AGENT_NAMES or hay.endswith(' notetaker'):
        return True
    tokens = hay.split()
    if tokens and tokens[0] in _AI_AGENT_FIRST_TOKENS:
        return True
    if any(re.search(rf'(?<![\w]){re.escape(phrase)}(?![\w])', hay) for phrase in _AI_AGENT_PHRASES):
        return True
    if person is not None:
        kind = str(person.get('kind') or person.get('type') or '').casefold()
        if kind in {'ai', 'bot', 'ai_agent', 'agent'} or bool(person.get('is_ai_agent')):
            return True
    return False


def _person_emails(person: Mapping[str, Any]) -> set[str]:
    emails: set[str] = set()
    for field in ('email', 'emails', 'email_addresses', 'aliases'):
        raw = person.get(field)
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        for value in values:
            if isinstance(value, str) and '@' in value:
                emails.add(value.strip().casefold())
    return emails


def _person_names(person: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    raw_name = person.get('name')
    if isinstance(raw_name, str) and raw_name.strip():
        names.add(raw_name.strip().casefold())
    for field in ('aliases', 'names'):
        raw = person.get(field)
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        for value in values:
            if isinstance(value, str) and value.strip() and '@' not in value:
                names.add(value.strip().casefold())
    return names


def _person_org(person: Mapping[str, Any]) -> Optional[str]:
    for field in ('organization', 'org', 'company', 'workplace'):
        value = person.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_person(
    name: Optional[str],
    email: Optional[str],
    people: list[Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    """Resolve a participant to a people-catalog entry, precision first.

    Email match wins. Name match requires an exact first token plus a
    surname-compatible second token; a first-name-only participant only
    resolves when exactly one catalog entry carries that first token — two
    different-surnamed people sharing it must never be merged into one person.
    """
    email_cf = (email or '').casefold()
    if email_cf:
        for person in people:
            if email_cf in _person_emails(person):
                return person
    if not name:
        return None
    name_cf = name.strip().casefold()
    exact = [person for person in people if name_cf in _person_names(person)]
    if len(exact) == 1:
        return exact[0]
    first = _first_token(name)
    surname = _surname_token(name)
    candidates: list[Mapping[str, Any]] = []
    for person in people:
        person_name = person.get('name') if isinstance(person.get('name'), str) else None
        person_first = _first_token(person_name)
        if not person_first or person_first != first:
            continue
        person_surname = _surname_token(person_name)
        if surname and person_surname and not _surname_compatible(surname, person_surname):
            continue
        candidates.append(person)
    if len(candidates) == 1:
        return candidates[0]
    if not surname:
        # First-name-only participant: resolvable only when a single catalog
        # entry shares the first token at all.
        return None
    # Multi-token participant with several first-token candidates: keep one
    # only when exactly one is surname-compatible.
    compatible = [
        person
        for person in candidates
        if _surname_compatible(
            surname, _surname_token(person.get('name') if isinstance(person.get('name'), str) else None)
        )
    ]
    return compatible[0] if len(compatible) == 1 else None


def _better_name(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if not a:
        return b
    if not b:
        return a
    a_tokens, b_tokens = len(a.split()), len(b.split())
    if a_tokens != b_tokens:
        return a if a_tokens > b_tokens else b
    return a if len(a) >= len(b) else b


def _merge_entries(entries: list[RosterEntry]) -> list[RosterEntry]:
    """Dedupe aliases that share an email or a resolved person_id, keeping the
    best display name and the richest fields."""
    merged: list[RosterEntry] = []
    index: dict[str, int] = {}
    for entry in entries:
        key = (
            f'email:{entry.email.casefold()}'
            if entry.email
            else (f'person:{entry.person_id}' if entry.person_id else '')
        )
        if key and key in index:
            existing = merged[index[key]]
            merged[index[key]] = RosterEntry(
                display_name=_better_name(existing.display_name, entry.display_name),
                email=existing.email or entry.email,
                organization=existing.organization or entry.organization,
                kind=existing.kind,
                source=existing.source,
                person_id=existing.person_id or entry.person_id,
            )
            continue
        if key:
            index[key] = len(merged)
        merged.append(entry)
    return merged


def normalize_meeting_participants(
    context: Optional[CalendarMeetingContext],
    source: Optional[Union[ConversationSource, str]],
    owner_name: Optional[str],
    owner_emails: Iterable[str],
    people: Iterable[Mapping[str, Any]],
) -> MeetingRoster:
    """Build the factual roster the prompt and post-validator share.

    ``context`` is the resolved meeting context (may be None for a desktop
    meeting capture with no calendar/screen identity — the roster then carries
    only the owner, if the owner is known). ``source`` is the conversation
    source; it only backs the per-entry provenance label when the context
    itself lacks a ``calendar_source``.
    """
    calendar_source = ''
    raw_participants: list[Any] = []
    title: Optional[str] = None
    platform: Optional[str] = None
    screen_derived = False
    if context is not None:
        calendar_source = context.calendar_source or ''
        raw_participants = list(context.participants or [])
        title = context.title
        platform = context.platform
        screen_derived = calendar_source == 'screen_activity'
    fallback_source = getattr(source, 'value', source) or ''
    entry_source = calendar_source or str(fallback_source) or 'unknown'
    display_title = clean_display_title(title, screen_derived=screen_derived, platform=platform)

    owner_email_set = {e.strip().casefold() for e in owner_emails if e.strip()}
    owner_locals = {_email_local(e) for e in owner_email_set if '@' in e}
    owner_first = _first_token(owner_name)
    owner_known = bool(owner_first or owner_email_set)

    people_list = list(people)

    # Pass 1: classify every participant as owner / human / AI agent.
    classified: list[dict[str, Any]] = []
    for participant in raw_participants:
        name = _clean_person_name(getattr(participant, 'name', None))
        email_raw = getattr(participant, 'email', None)
        email = email_raw.strip().casefold() if isinstance(email_raw, str) and email_raw.strip() else None
        classified.append({'name': name, 'email': email, 'domain': _email_domain(email)})

    first_token_counts: dict[str, int] = {}
    for item in classified:
        token = _first_token(item['name'])
        if token:
            first_token_counts[token] = first_token_counts.get(token, 0) + 1

    owner_email_matched = owner_known and any(
        item['email'] and (item['email'] in owner_email_set or _email_local(item['email']) in owner_locals)
        for item in classified
    )
    # The surname anchor prefers the participant the owner already proved by
    # email — richer than the auth display name, which may carry only a first
    # name while the roster spells the surname out.
    email_proved_name = next(
        (
            item['name']
            for item in classified
            if owner_known
            and item['name']
            and item['email']
            and (item['email'] in owner_email_set or _email_local(item['email']) in owner_locals)
        ),
        None,
    )
    owner_surname = _surname_token(email_proved_name) or _surname_token(owner_name)
    owner_entries: list[tuple[RosterEntry, bool]] = []
    human_entries: list[RosterEntry] = []
    ai_entries: list[RosterEntry] = []
    for item in classified:
        name, email, domain = item['name'], item['email'], item['domain']
        person = _resolve_person(name, email, people_list)
        is_owner = False
        email_proved = False
        if owner_known:
            if email and (email in owner_email_set or _email_local(email) in owner_locals):
                # Exact or shared local-part across domains, freemail included.
                is_owner = True
                email_proved = True
            elif name and owner_first and _first_token(name) == owner_first:
                surname_ok = (
                    not _surname_token(name)
                    or not owner_surname
                    or _surname_compatible(_surname_token(name), owner_surname)
                )
                if owner_surname:
                    # A surname-compatible repeat of the owner's first name
                    # (OCR truncation like "David ZI" against the email-proved
                    # "David Zhang") collapses into the owner once another
                    # participant already proved the owner was present.
                    is_owner = surname_ok and (
                        first_token_counts.get(_first_token(name), 0) == 1 or owner_email_matched
                    )
                else:
                    # A first-name-only owner identity never guesses between
                    # several same-first participants.
                    is_owner = surname_ok and first_token_counts.get(_first_token(name), 0) == 1
        if is_owner:
            owner_entries.append(
                (
                    RosterEntry(
                        display_name=name or owner_name,
                        email=email or (sorted(owner_email_set)[0] if owner_email_set else None),
                        organization=_person_org(person) if person is not None else None,
                        kind='owner',
                        source=entry_source,
                        person_id=str(person.get('id')) if person is not None and person.get('id') else None,
                    ),
                    email_proved,
                )
            )
            continue
        if _looks_ai_agent(name, email, person):
            ai_entries.append(
                RosterEntry(
                    display_name=name,
                    email=email,
                    organization=_person_org(person) if person is not None else None,
                    kind='ai_agent',
                    source=entry_source,
                    person_id=str(person.get('id')) if person is not None and person.get('id') else None,
                )
            )
            continue
        organization = _person_org(person) if person is not None else None
        if organization is None and domain and not _is_freemail_domain(domain) and not domain.endswith('.local'):
            organization = domain
        person_name = person.get('name') if person is not None and isinstance(person.get('name'), str) else None
        human_entries.append(
            RosterEntry(
                display_name=_better_name(name, person_name),
                email=email,
                organization=organization,
                kind='human',
                source=entry_source,
                person_id=str(person.get('id')) if person is not None and person.get('id') else None,
            )
        )

    humans = _merge_entries(human_entries)
    ai_agents = _merge_entries(ai_entries)

    entries: list[RosterEntry] = []
    if owner_entries:
        # The email-proved entry carries the canonical verified name; OCR
        # variants only fill gaps, they never outrank it.
        proved = next((entry for entry, email_proved in owner_entries if email_proved), None)
        merged_owner = proved if proved is not None else owner_entries[0][0]
        for extra, _ in owner_entries:
            if extra is merged_owner:
                continue
            merged_owner = RosterEntry(
                display_name=(
                    merged_owner.display_name or extra.display_name
                    if proved is not None
                    else _better_name(merged_owner.display_name, extra.display_name)
                ),
                email=merged_owner.email or extra.email,
                organization=merged_owner.organization or extra.organization,
                kind='owner',
                source=merged_owner.source,
                person_id=merged_owner.person_id or extra.person_id,
            )
        entries.append(merged_owner)
    elif owner_known:
        # Exactly one owner, present even when the invite omits them.
        entries.append(
            RosterEntry(
                display_name=owner_name.strip() if isinstance(owner_name, str) and owner_name.strip() else None,
                email=next(iter(sorted(owner_email_set)), None),
                organization=None,
                kind='owner',
                source=entry_source,
                person_id=None,
            )
        )
    entries.extend(humans)
    entries.extend(ai_agents)
    return MeetingRoster(entries=tuple(entries), display_title=display_title, title_is_window_title=screen_derived)


__all__ = [
    'MeetingRoster',
    'RosterEntry',
    'clean_display_title',
    'normalize_meeting_participants',
]
