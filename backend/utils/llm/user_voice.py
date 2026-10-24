"""How the user writes to one person, so drafts sent as them sound like them.

``propose_message`` opens the compose sheet with a body the chat model wrote. The
words then read like Omi rather than like the user, and the user either rewrites
them or sends something that reads like AI to a friend. This module builds a
small, code-only profile of the user's own voice toward ONE person and uses it in
two places, neither of which adds a model call:

1. ``profile_prompt_block`` is attached to the ``search_contacts`` result for a
   contact that matches a known person, which is the moment the model is about to
   draft the message (see ``utils.device_tools``).
2. ``polish_draft`` deterministically fixes the marks a model still gets wrong
   (how the last line ends, how many "!") before the compose sheet opens. It never
   changes words.

Sources are only the user's own lines:

- spoken: transcript segments with ``is_user`` in conversations where that person
  is a tagged speaker. These carry length, greetings, language mix and examples.
- typed: messages the user typed to Omi. Speech-to-text inserts its own
  punctuation, so line endings, "!" and emoji are measured on typed lines when
  there are enough of them, and on all lines otherwise.

Locked, discarded and deleted conversations are never read. The feature is
opt-in (``assistant_settings.drafts.user_voice``); the profile is cached for
seven days, encrypted with the user's key like other user content.
"""

import json
import logging
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field

import database.chat as chat_db
import database.conversations as conversations_db
import database.users as users_db
from database.redis_db import r as redis_client
from utils.encryption import decrypt, encrypt

logger = logging.getLogger(__name__)

USER_VOICE_CACHE_TTL_SECONDS = 7 * 24 * 3600
USER_VOICE_PROFILE_VERSION = 1

# Below this many of the user's own lines a profile is noise; the prompt block
# then says so instead of inventing a style.
USER_VOICE_MIN_LINES = 8
# Endings and "!" come from typed lines only when there are at least this many.
USER_VOICE_MIN_TYPED_LINES = 12

# Bounded reads: one page of recent conversations and recent chat messages.
USER_VOICE_MAX_CONVERSATIONS = 200
USER_VOICE_MAX_TYPED_MESSAGES = 200
USER_VOICE_MAX_LINES = 150
USER_VOICE_MAX_EXAMPLES = 5
USER_VOICE_MAX_EXAMPLE_CHARS = 140

# An ending the user uses less often than this (percent) counts as "never".
RARE_ENDING_PERCENT = 5

_EMOJI_RE = re.compile('[\U0001f300-\U0001faff☀-➿\U0001f1e6-\U0001f1ff]')
_URL_RE = re.compile(r'https?://\S+')
_BANG_RE = re.compile('[!！]')
_LAUGH_RE = re.compile(r'(haha+|hehe+|lol|lmao|哈哈+)$', re.IGNORECASE)
_GREETING_RE = re.compile(
    r'^(hi|hey|hello|yo|dear|good morning|morning|嗨|哈喽|你好|hola|bonjour|ciao)\b',
    re.IGNORECASE,
)
_SCRIPT_NAMES = {
    'LATIN': 'latin',
    'CJK': 'han',
    'HIRAGANA': 'kana',
    'KATAKANA': 'kana',
    'HANGUL': 'hangul',
    'CYRILLIC': 'cyrillic',
    'ARABIC': 'arabic',
    'DEVANAGARI': 'devanagari',
    'HEBREW': 'hebrew',
    'GREEK': 'greek',
    'THAI': 'thai',
}
# Scripts whose sentences end with full-width marks.
_FULL_WIDTH_SCRIPTS = frozenset({'han', 'kana'})
_ENDING_WORDS = {
    'none': 'no punctuation',
    '.': 'a period',
    '!': '"!"',
    '?': 'a question mark',
    'emoji': 'an emoji',
    'laugh': 'a laugh (haha)',
    'ellipsis': '"..."',
}


class UserVoiceProfile(BaseModel):
    version: int = USER_VOICE_PROFILE_VERSION
    person_id: str
    person_name: str
    built_at: datetime
    lines: int = 0
    spoken_lines: int = 0
    typed_lines: int = 0
    # Percent of measured lines, by how the line ends.
    endings: dict[str, int] = Field(default_factory=dict)
    exclamation_rate: int = 0
    exclamations_per_line: float = 0.0
    emoji_rate: int = 0
    # Percent of letters by script, e.g. {'latin': 70, 'han': 30}.
    scripts: dict[str, int] = Field(default_factory=dict)
    lowercase_start_rate: int = 0
    median_chars: int = 0
    p90_chars: int = 0
    greetings: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)

    @property
    def is_reliable(self) -> bool:
        return self.lines >= USER_VOICE_MIN_LINES


class PolishResult(BaseModel):
    text: str
    changes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Measuring lines (pure)
# ---------------------------------------------------------------------------


def _clean(text: Any) -> str:
    return ' '.join(_URL_RE.sub('', str(text or '')).split())


def line_ending(text: str) -> Optional[str]:
    """How a line ends: '.', '!', '?', 'ellipsis', 'emoji', 'laugh' or 'none'."""
    stripped = _clean(text)
    if not stripped:
        return None
    if stripped.endswith(('...', '…')):
        return 'ellipsis'
    last = stripped[-1]
    if _EMOJI_RE.match(last) or unicodedata.category(last) == 'So':
        return 'emoji'
    if last in '.。':
        return '.'
    if last in '!！':
        return '!'
    if last in '?？':
        return '?'
    if _LAUGH_RE.search(stripped):
        return 'laugh'
    return 'none'


def letter_scripts(text: str) -> Counter:
    counts: Counter = Counter()
    for char in text:
        if not char.isalpha():
            continue
        name = unicodedata.name(char, '')
        counts[_SCRIPT_NAMES.get(name.split(' ', 1)[0], 'other')] += 1
    return counts


def _dominant_script(text: str) -> Optional[str]:
    counts = letter_scripts(text)
    return counts.most_common(1)[0][0] if counts else None


def _percent(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _quantile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        return 0
    return sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))]


def build_profile(
    person_id: str,
    person_name: str,
    spoken_lines: Iterable[str],
    typed_lines: Iterable[str],
    *,
    now: Optional[datetime] = None,
) -> UserVoiceProfile:
    """Build the profile from the user's own lines, oldest first."""
    spoken = [line for line in (_clean(t) for t in spoken_lines) if line][-USER_VOICE_MAX_LINES:]
    typed = [line for line in (_clean(t) for t in typed_lines) if line][-USER_VOICE_MAX_LINES:]
    everything = spoken + typed
    profile = UserVoiceProfile(
        person_id=person_id,
        person_name=person_name,
        built_at=now or datetime.now(timezone.utc),
        lines=len(spoken),
        spoken_lines=len(spoken),
        typed_lines=len(typed),
    )
    if not everything:
        return profile

    # Marks: typed lines when there are enough, because STT punctuates for the user.
    marked = typed if len(typed) >= USER_VOICE_MIN_TYPED_LINES else everything
    endings = Counter(e for e in (line_ending(line) for line in marked) if e)
    bang_lines = sum(1 for line in marked if _BANG_RE.search(line))
    bangs = sum(len(_BANG_RE.findall(line)) for line in marked)
    emoji_lines = sum(1 for line in marked if _EMOJI_RE.search(line))
    profile.endings = {k: _percent(v, len(marked)) for k, v in endings.most_common()}
    profile.exclamation_rate = _percent(bang_lines, len(marked))
    profile.exclamations_per_line = round(bangs / len(marked), 2)
    profile.emoji_rate = _percent(emoji_lines, len(marked))

    # Everything else is about this person: the spoken lines, or all lines if none yet.
    personal = spoken or everything
    scripts: Counter = Counter()
    for line in personal:
        scripts.update(letter_scripts(line))
    total_letters = sum(scripts.values())
    profile.scripts = {k: _percent(v, total_letters) for k, v in scripts.most_common() if _percent(v, total_letters)}

    latin_lines = [line for line in personal if _dominant_script(line) == 'latin']
    if len(latin_lines) >= 5:
        profile.lowercase_start_rate = _percent(sum(1 for line in latin_lines if line[0].islower()), len(latin_lines))

    lengths = sorted(len(line) for line in personal)
    profile.median_chars = _quantile(lengths, 0.5)
    profile.p90_chars = _quantile(lengths, 0.9)

    greetings = Counter(m.group(1).lower() for m in (_GREETING_RE.match(line) for line in personal) if m)
    profile.greetings = [g for g, _ in greetings.most_common(3)]

    seen: set[str] = set()
    examples: list[str] = []
    for line in reversed(personal):
        if len(line) > USER_VOICE_MAX_EXAMPLE_CHARS or len(line) < 4 or line.casefold() in seen:
            continue
        seen.add(line.casefold())
        examples.append(line)
        if len(examples) == USER_VOICE_MAX_EXAMPLES:
            break
    profile.examples = examples
    return profile


# ---------------------------------------------------------------------------
# Using the profile (pure)
# ---------------------------------------------------------------------------


def _rare_endings(profile: UserVoiceProfile) -> list[str]:
    return [k for k in ('.', '!') if profile.endings.get(k, 0) < RARE_ENDING_PERCENT]


def allowed_exclamations(profile: Optional[UserVoiceProfile]) -> int:
    if profile is None or not profile.is_reliable:
        return 1
    if profile.exclamation_rate < RARE_ENDING_PERCENT:
        return 0
    return 2 if profile.exclamations_per_line > 1.2 else 1


def profile_prompt_block(profile: Optional[UserVoiceProfile]) -> str:
    """Instructions for the drafting model; empty when there is no profile."""
    if profile is None:
        return ''
    name = profile.person_name
    if not profile.is_reliable:
        return (
            f"Draft to {name} as the user. Few of the user's own lines with {name} are on record, "
            "so keep it short and plain, like a text, not a letter."
        )
    lines = [
        f"Write the message as the user writes to {name} (from {profile.lines} of the user's own lines "
        "with them). Copy this voice, not a generic assistant voice:"
    ]
    if profile.scripts:
        mix = ', '.join(f'{script} {pct}%' for script, pct in profile.scripts.items())
        lines.append(f'- script mix: {mix}; reply in the same language mix')
    ends = ', '.join(f'{_ENDING_WORDS.get(k, k)} {v}%' for k, v in list(profile.endings.items())[:3])
    rare = [_ENDING_WORDS[k] for k in _rare_endings(profile)]
    lines.append(f'- lines end with: {ends}' + (f"; almost never {' or '.join(rare)}" if rare else ''))
    limit = allowed_exclamations(profile)
    lines.append(f'- "!" in {profile.exclamation_rate}% of lines; use at most {limit}')
    lines.append(f'- emoji in {profile.emoji_rate}% of lines' + ('; use none' if profile.emoji_rate == 0 else ''))
    if profile.lowercase_start_rate >= 60:
        lines.append(f'- starts lines lowercase ({profile.lowercase_start_rate}%)')
    lines.append(f'- length: usually about {profile.median_chars} characters (90% under {profile.p90_chars})')
    lines.append(
        f"- greets with: {', '.join(profile.greetings)}" if profile.greetings else '- rarely opens with a greeting'
    )
    if profile.examples:
        quoted = ' / '.join(f'"{e}"' for e in profile.examples)
        lines.append(f'- the user\'s own recent lines (style only, never copy facts from them): {quoted}')
    return '\n'.join(lines)


def polish_draft(text: str, profile: Optional[UserVoiceProfile]) -> PolishResult:
    """Fix marks toward the user's voice. Never changes, adds or drops words."""
    result = PolishResult(text=text or '')
    if not result.text.strip() or profile is None or not profile.is_reliable:
        return result
    draft = result.text.strip()
    full_width = _dominant_script(draft) in _FULL_WIDTH_SCRIPTS

    # 1. "!" count: keep the last ones, calm the earlier ones to a stop.
    allowed = allowed_exclamations(profile)
    count = len(_BANG_RE.findall(draft))
    if count > allowed:
        surplus = count - allowed

        def calm(match: re.Match) -> str:
            nonlocal surplus
            if surplus <= 0:
                return match.group(0)
            surplus -= 1
            rest = draft[match.end() :]
            if rest.strip() and not _BANG_RE.sub('', rest).strip():
                return ''  # part of a final "!!" run whose last mark stays
            if not rest.strip():
                # The last "!" becomes the user's usual stop to this person, if they use one.
                if profile.endings.get('.', 0) < RARE_ENDING_PERCENT:
                    return ''
                return '\u3002' if full_width else '.'
            return '，' if match.group(0) == '！' or full_width else '.'

        draft = _BANG_RE.sub(calm, draft)
        result.changes.append(f'"!" {count} -> {allowed}')

    # 2. The last line ends the way the user ends lines to this person. Only a
    #    short single-line text: an email keeps its full stops.
    if '\n' not in draft and len(draft) < 300:
        ending = line_ending(draft)
        if ending == '.' and profile.endings.get('.', 0) < RARE_ENDING_PERCENT:
            preferred = next((k for k in profile.endings if k in ('none', '!')), 'none')
            if preferred == '!' and len(_BANG_RE.findall(draft)) >= allowed:
                preferred = 'none'
            replacement = '' if preferred == 'none' else ('！' if full_width else '!')
            draft = re.sub(r'[.。]\s*$', replacement, draft)
            result.changes.append(f'last "." -> {"no mark" if preferred == "none" else repr(replacement)}')

    result.text = draft.strip()
    return result


def match_person(contact_name: str, people: Iterable[dict]) -> Optional[dict]:
    """The one Omi person a device contact refers to, or None when unsure.

    Omi people are usually named the way the user says them ("Ada"), contacts by
    full name ("Ada Lovelace"). Exact full-name matches win; otherwise a unique
    first-name match. Two candidates means we do not guess.
    """
    wanted = ' '.join(str(contact_name or '').split()).casefold()
    if not wanted:
        return None
    named = [p for p in people if p.get('name') and not p.get('is_dismissed')]
    exact = [p for p in named if ' '.join(p['name'].split()).casefold() == wanted]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    first = wanted.split(' ', 1)[0]
    by_first = [p for p in named if ' '.join(p['name'].split()).casefold() == first]
    return by_first[0] if len(by_first) == 1 else None


# ---------------------------------------------------------------------------
# Reading the user's lines and the cache (IO)
# ---------------------------------------------------------------------------


def is_user_voice_enabled(uid: str) -> bool:
    settings = users_db.get_assistant_settings(uid) or {}
    drafts = settings.get('drafts')
    return isinstance(drafts, dict) and drafts.get('user_voice') is True


def user_lines_with_person(conversations: Iterable[dict], person_id: str) -> list[str]:
    """The user's own segments in conversations where ``person_id`` speaks, oldest first."""
    lines: list[tuple[Any, float, str]] = []
    for conversation in conversations:
        if conversation.get('is_locked') or conversation.get('discarded') or conversation.get('deleted'):
            continue
        segments = conversation.get('transcript_segments') or []
        if not any(s.get('person_id') == person_id and not s.get('is_user') for s in segments):
            continue
        started = conversation.get('started_at') or conversation.get('created_at') or ''
        for segment in segments:
            if segment.get('is_user') and segment.get('text'):
                lines.append((str(started), float(segment.get('start') or 0), segment['text']))
    lines.sort(key=lambda item: (item[0], item[1]))
    return [text for _, _, text in lines]


def typed_user_lines(messages: Iterable[dict]) -> list[str]:
    """What the user typed to Omi, oldest first (newest-first pages are reversed)."""
    typed = [
        m.get('text') or ''
        for m in messages
        if m.get('sender') == 'human' and (m.get('type') or 'text') == 'text' and m.get('text')
    ]
    return list(reversed(typed))


def _cache_key(uid: str, person_id: str) -> str:
    return f'user_voice:{uid}:{person_id}'


def _read_cached(uid: str, person_id: str) -> Optional[UserVoiceProfile]:
    raw = redis_client.get(_cache_key(uid, person_id))
    if not raw:
        return None
    try:
        data = json.loads(decrypt(raw.decode() if isinstance(raw, bytes) else raw, uid))
        profile = UserVoiceProfile.model_validate(data)
    except Exception:
        return None
    return profile if profile.version == USER_VOICE_PROFILE_VERSION else None


def _write_cached(uid: str, profile: UserVoiceProfile) -> None:
    payload = encrypt(profile.model_dump_json(), uid)
    redis_client.setex(_cache_key(uid, profile.person_id), USER_VOICE_CACHE_TTL_SECONDS, payload)


def invalidate_user_voice(uid: str, person_id: str) -> None:
    redis_client.delete(_cache_key(uid, person_id))


def get_user_voice_profile(uid: str, person: dict) -> UserVoiceProfile:
    """The cached profile for this person, rebuilt when missing or a week old."""
    person_id = person['id']
    cached = _read_cached(uid, person_id)
    if cached is not None:
        return cached
    conversations = conversations_db.get_conversations(uid, limit=USER_VOICE_MAX_CONVERSATIONS)
    messages = chat_db.get_messages(uid, limit=USER_VOICE_MAX_TYPED_MESSAGES)
    profile = build_profile(
        person_id,
        person.get('name') or '',
        user_lines_with_person(conversations, person_id),
        typed_user_lines(messages),
    )
    _write_cached(uid, profile)
    return profile


# ---------------------------------------------------------------------------
# The propose_message seam
# ---------------------------------------------------------------------------

# A contact search can return many people; only the first few get a profile.
USER_VOICE_MAX_CONTACTS = 3


def handle_key(handle: Any) -> Optional[str]:
    """Compare phone numbers by their last ten digits and emails case-insensitively."""
    value = str(handle or '').strip()
    if '@' in value:
        return value.casefold()
    digits = re.sub(r'\D', '', value)
    return digits[-10:] if len(digits) >= 7 else None


def _contact_handles(contact: dict) -> list[str]:
    raw = [contact.get('preferred_messaging_handle')]
    for field in ('phone_numbers', 'email_addresses'):
        raw.extend(entry.get('value') for entry in contact.get(field) or [] if isinstance(entry, dict))
    return [key for key in (handle_key(h) for h in raw) if key]


def annotate_contacts_with_voice(uid: str, result: dict) -> dict[str, UserVoiceProfile]:
    """Attach ``user_voice`` to contacts that are known people; return profiles by handle.

    Runs on the ``search_contacts`` result, so the guidance reaches the model in
    the same turn, just before it writes the ``propose_message`` body.
    """
    contacts = result.get('contacts') if result.get('ok') else None
    if not contacts or not is_user_voice_enabled(uid):
        return {}
    people = users_db.get_people(uid)
    voices: dict[str, UserVoiceProfile] = {}
    for contact in contacts[:USER_VOICE_MAX_CONTACTS]:
        if not isinstance(contact, dict):
            continue
        person = match_person(contact.get('name') or '', people)
        if person is None:
            continue
        profile = get_user_voice_profile(uid, person)
        contact['user_voice'] = profile_prompt_block(profile)
        for key in _contact_handles(contact):
            voices[key] = profile
    return voices


def profile_for_recipients(voices: dict[str, UserVoiceProfile], to: Iterable[str]) -> Optional[UserVoiceProfile]:
    """The profile for a one-person message; a group message is left as written."""
    found = {id(p): p for p in (voices.get(handle_key(h) or '') for h in to or []) if p is not None}
    recipients = [h for h in to or [] if str(h).strip()]
    if len(found) != 1 or len(recipients) != 1:
        return None
    return next(iter(found.values()))
