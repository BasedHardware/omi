"""Per-person user voice profiling and deterministic draft polishing for ``propose_message``.

Builds a code-only profile of how the user writes or talks to ONE specific person
from the user's own lines (transcript segments where ``is_user`` is True in
non-locked conversations with that person, plus messages the user typed to Omi).
Profiles are gated by an opt-in setting and cached for 7 days.

When ``propose_message`` is used, the profile is injected into the drafting prompt
and a deterministic polish pass fixes what the model still gets wrong (ending
punctuation, ``!`` count, casing) before the compose sheet opens — with zero extra
model calls.
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import time
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

try:
    from database.redis_db import r as redis_client
except Exception:  # pragma: no cover - defensive import fallback
    redis_client = None

logger = logging.getLogger(__name__)

# 7 days in seconds.
USER_VOICE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
USER_VOICE_MIN_EXAMPLES = 3
USER_VOICE_MAX_EXAMPLES = 5
USER_VOICE_MAX_EXAMPLE_CHARS = 140

EndingStyle = Literal['none', 'period', 'exclamation', 'question']

# Fallback in-process cache and opt-in state used when Redis/Firestore are not wired.
_MEMORY_CACHE: Dict[str, Tuple[float, str]] = {}
_MEMORY_OPT_IN: Dict[str, Any] = {}

_EMOJI_RE = re.compile(
    '['
    '\U0001F300-\U0001F5FF'
    '\U0001F600-\U0001F64F'
    '\U0001F680-\U0001F6FF'
    '\U0001F700-\U0001F77F'
    '\U0001F780-\U0001F7FF'
    '\U0001F800-\U0001F8FF'
    '\U0001F900-\U0001F9FF'
    '\U0001FA00-\U0001FA6F'
    '\U0001FA70-\U0001FAFF'
    '\u2600-\u26FF'
    '\u2700-\u27BF'
    ']'
)

_GREETING_PATTERNS = (
    re.compile(
        r'^\s*((?:hey+y*|hi+i*|hello+|yo+|sup|hiya|howdy|morning|good\s+(?:morning|afternoon|evening)|'
        r'dear\s+[a-zA-Z\u00C0-\u024F]+|hola|bonjour|salut|ciao|oi|halo|namaste|salaam)'
        r'(?:\s+[a-zA-Z\u00C0-\u024F]+)?)[\s,!.:;-]*',
        re.IGNORECASE,
    ),
)

_SPANISH_STOPWORDS = frozenset({'hola', 'gracias', 'para', 'pero', 'como', 'estoy', 'vamos', 'bien', 'porque', 'que'})
_FRENCH_STOPWORDS = frozenset({'bonjour', 'salut', 'merci', 'avec', 'pour', 'dans', 'est', 'pas', 'oui', 'mais'})
_GERMAN_STOPWORDS = frozenset({'hallo', 'danke', 'nicht', 'und', 'ich', 'wir', 'sind', 'bitte', 'auch', 'mit'})
_PORTUGUESE_STOPWORDS = frozenset({'oi', 'ola', 'obrigado', 'obrigada', 'para', 'com', 'nao', 'sim', 'vamos', 'voce'})
_VIETNAMESE_STOPWORDS = frozenset({'xin', 'chao', 'cam', 'khong', 'duoc', 'nha', 'nhe', 'anh', 'em', 'minh'})
_ENGLISH_STOPWORDS = frozenset({'the', 'and', 'you', 'that', 'for', 'with', 'are', 'this', 'have', 'from', 'hey', 'hi'})


class UserVoiceProfile(BaseModel):
    """Code-only profile of how a user talks or writes to one specific person."""

    person_id: Optional[str] = None
    person_name: Optional[str] = None
    recipient: Optional[str] = None
    sample_count: int = 0
    typical_word_count: int = 0
    typical_char_length: int = 0
    dominant_ending: EndingStyle = 'none'
    ending_rates: Dict[str, float] = Field(
        default_factory=lambda: {'none': 1.0, 'period': 0.0, 'exclamation': 0.0, 'question': 0.0}
    )
    exclamation_rate: float = 0.0
    max_exclamations_per_line: int = 0
    emoji_rate: float = 0.0
    lowercase_start_rate: float = 0.0
    languages: List[str] = Field(default_factory=lambda: ['en'])
    script_mix: Dict[str, float] = Field(default_factory=lambda: {'latin': 1.0})
    greetings: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)

    def to_prompt_block(self) -> str:
        return format_user_voice_prompt(self)


def _normalize_person_key(
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    recipient: Optional[str] = None,
) -> str:
    for candidate in (person_id, recipient, person_name):
        if candidate and str(candidate).strip():
            return re.sub(r'\s+', '_', str(candidate).strip().lower())
    return 'default'


def user_voice_cache_key(uid: str, person_key: str) -> str:
    return f'user_voice_profile:v1:{uid}:{person_key}'


def is_user_voice_enabled(
    uid: str,
    person_id: Optional[str] = None,
    *,
    user_settings: Optional[Mapping[str, Any]] = None,
    firestore_client: Any = None,
) -> bool:
    """Return whether user-voice drafting is opted in for ``uid`` (and optionally ``person_id``).

    Supports both account-level opt-in (``user_voice_enabled: bool``) and per-person
    overrides (``user_voice_people: {person_id: bool}``). Defaults to False unless
    opted in.
    """
    data: Dict[str, Any] = {}
    if isinstance(user_settings, Mapping):
        data.update(user_settings)
    elif uid in _MEMORY_OPT_IN and isinstance(_MEMORY_OPT_IN[uid], Mapping):
        data.update(_MEMORY_OPT_IN[uid])
    elif firestore_client is not None:
        try:
            snap = firestore_client.collection('users').document(uid).get()
            doc = snap.to_dict() if getattr(snap, 'exists', False) else {}
            if isinstance(doc, Mapping):
                data.update(doc)
        except Exception as exc:
            logger.debug('Could not read user_voice opt-in from firestore uid=%s err=%s', uid, type(exc).__name__)

    if person_id:
        per_person = data.get('user_voice_people')
        if isinstance(per_person, Mapping) and person_id in per_person and per_person[person_id] is not None:
            return bool(per_person[person_id])

    if 'user_voice_enabled' in data and data['user_voice_enabled'] is not None:
        return bool(data['user_voice_enabled'])

    env_default = os.getenv('OMI_USER_VOICE_DEFAULT_ENABLED', '').strip().lower()
    if env_default in ('1', 'true', 'yes', 'on'):
        return True
    return False


def set_user_voice_enabled(
    uid: str,
    enabled: bool,
    *,
    person_id: Optional[str] = None,
    firestore_client: Any = None,
) -> None:
    """Set account-level or per-person opt-in for user-voice drafting."""
    entry = dict(_MEMORY_OPT_IN.get(uid) or {})
    if person_id:
        people_map = dict(entry.get('user_voice_people') or {})
        people_map[person_id] = bool(enabled)
        entry['user_voice_people'] = people_map
    else:
        entry['user_voice_enabled'] = bool(enabled)
    _MEMORY_OPT_IN[uid] = entry

    if firestore_client is not None:
        try:
            update: Dict[str, Any] = (
                {f'user_voice_people.{person_id}': bool(enabled)}
                if person_id
                else {'user_voice_enabled': bool(enabled)}
            )
            firestore_client.collection('users').document(uid).set(update, merge=True)
        except Exception as exc:
            logger.warning('Could not persist user_voice opt-in uid=%s err=%s', uid, type(exc).__name__)


def clear_user_voice_state_for_tests() -> None:
    """Clear in-memory caches and opt-in overrides used in unit tests."""
    _MEMORY_CACHE.clear()
    _MEMORY_OPT_IN.clear()


def cache_user_voice_profile(
    uid: str,
    person_key: str,
    profile: UserVoiceProfile,
    *,
    ttl_seconds: int = USER_VOICE_CACHE_TTL_SECONDS,
    now_fn: Callable[[], float] = time.time,
) -> None:
    key = user_voice_cache_key(uid, person_key)
    payload = profile.model_dump_json()
    _MEMORY_CACHE[key] = (now_fn() + ttl_seconds, payload)
    if redis_client is not None:
        try:
            redis_client.setex(key, ttl_seconds, payload)
        except Exception as exc:
            logger.debug('Redis cache write skipped for user_voice key=%s err=%s', key, type(exc).__name__)


def get_cached_user_voice_profile(
    uid: str,
    person_key: str,
    *,
    now_fn: Callable[[], float] = time.time,
) -> Optional[UserVoiceProfile]:
    key = user_voice_cache_key(uid, person_key)
    if redis_client is not None:
        try:
            raw = redis_client.get(key)
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8')
                return UserVoiceProfile.model_validate_json(raw)
        except Exception as exc:
            logger.debug('Redis cache read skipped for user_voice key=%s err=%s', key, type(exc).__name__)

    cached = _MEMORY_CACHE.get(key)
    if cached is None:
        return None
    expires_at, payload = cached
    if now_fn() >= expires_at:
        _MEMORY_CACHE.pop(key, None)
        return None
    try:
        return UserVoiceProfile.model_validate_json(payload)
    except Exception:
        _MEMORY_CACHE.pop(key, None)
        return None


def invalidate_user_voice_profile(uid: str, person_key: str) -> None:
    key = user_voice_cache_key(uid, person_key)
    _MEMORY_CACHE.pop(key, None)
    if redis_client is not None:
        try:
            redis_client.delete(key)
        except Exception:
            pass


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _is_locked_record(record: Any) -> bool:
    if record is None:
        return False
    if bool(_get_field(record, 'is_locked', False)):
        return True
    status = _get_field(record, 'status')
    if isinstance(status, str) and status.strip().lower() == 'locked':
        return True
    return False


def _conversation_matches_person(
    conv: Any,
    *,
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    recipient: Optional[str] = None,
) -> bool:
    """Return True when ``conv`` involves the target person."""
    if not person_id and not person_name and not recipient:
        return True

    target_id = person_id.strip() if isinstance(person_id, str) and person_id.strip() else None
    target_name = person_name.strip().lower() if isinstance(person_name, str) and person_name.strip() else None
    target_recipient = recipient.strip().lower() if isinstance(recipient, str) and recipient.strip() else None

    if target_id:
        conv_person_ids = _get_field(conv, 'person_ids') or _get_field(conv, 'participant_person_ids') or []
        if isinstance(conv_person_ids, (list, tuple, set)) and target_id in conv_person_ids:
            return True
        if _get_field(conv, 'person_id') == target_id:
            return True

    if target_recipient:
        conv_recipients = _get_field(conv, 'recipients') or _get_field(conv, 'participants') or []
        if isinstance(conv_recipients, (list, tuple, set)):
            for item in conv_recipients:
                if isinstance(item, str) and target_recipient in item.strip().lower():
                    return True
                elif isinstance(item, Mapping):
                    for field_name in ('handle', 'phone', 'email', 'name', 'id'):
                        val = item.get(field_name)
                        if isinstance(val, str) and target_recipient == val.strip().lower():
                            return True
        if isinstance(_get_field(conv, 'recipient'), str) and target_recipient == _get_field(conv, 'recipient').strip().lower():
            return True

    segments = _get_field(conv, 'transcript_segments') or []
    for seg in segments:
        if target_id and _get_field(seg, 'person_id') == target_id:
            return True
        if target_name:
            for field_name in ('person_name', 'speaker_name', 'speaker'):
                val = _get_field(seg, field_name)
                if isinstance(val, str) and target_name == val.strip().lower():
                    return True

    if target_name:
        participants = _get_field(conv, 'participants') or _get_field(conv, 'people') or []
        for p in participants:
            if isinstance(p, str) and target_name == p.strip().lower():
                return True
            if isinstance(p, Mapping):
                p_name = p.get('name')
                if isinstance(p_name, str) and target_name == p_name.strip().lower():
                    return True
        structured = _get_field(conv, 'structured')
        if structured is not None:
            title = _get_field(structured, 'title') or ''
            overview = _get_field(structured, 'overview') or ''
            pattern = re.compile(r'\b' + re.escape(target_name) + r'\b', re.IGNORECASE)
            if (isinstance(title, str) and pattern.search(title)) or (
                isinstance(overview, str) and pattern.search(overview)
            ):
                return True

    return False


def _extract_user_lines_from_conversations(
    conversations: Sequence[Any],
    *,
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    recipient: Optional[str] = None,
) -> List[str]:
    lines: List[str] = []
    for conv in conversations or ():
        if _is_locked_record(conv):
            continue
        if not _conversation_matches_person(
            conv,
            person_id=person_id,
            person_name=person_name,
            recipient=recipient,
        ):
            continue
        segments = _get_field(conv, 'transcript_segments') or []
        for seg in segments:
            if _is_locked_record(seg):
                continue
            if _get_field(seg, 'is_user') is not True:
                continue
            text = _get_field(seg, 'text')
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())
    return lines


def _extract_user_lines_from_messages(
    messages: Sequence[Any],
    *,
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    recipient: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    """Return ``(person_matched_lines, all_user_typed_lines)`` from Omi messages."""
    matched: List[str] = []
    general: List[str] = []
    target_id = person_id.strip() if isinstance(person_id, str) and person_id.strip() else None
    target_name = person_name.strip().lower() if isinstance(person_name, str) and person_name.strip() else None
    target_recipient = recipient.strip().lower() if isinstance(recipient, str) and recipient.strip() else None
    name_re = re.compile(r'\b' + re.escape(target_name) + r'\b', re.IGNORECASE) if target_name else None

    for msg in messages or ():
        if isinstance(msg, str):
            text = msg.strip()
            if text:
                general.append(text)
                if name_re and name_re.search(text):
                    matched.append(text)
            continue

        if _is_locked_record(msg):
            continue

        sender = _get_field(msg, 'sender') or _get_field(msg, 'role')
        sender_val = getattr(sender, 'value', sender)
        is_user_msg = (
            _get_field(msg, 'is_user') is True
            or sender_val in ('human', 'user')
            or sender is None
        )
        if not is_user_msg:
            continue

        text = _get_field(msg, 'text') or _get_field(msg, 'content')
        if not isinstance(text, str) or not text.strip():
            continue
        clean_text = text.strip()
        general.append(clean_text)

        msg_person_id = _get_field(msg, 'person_id')
        msg_recipient = _get_field(msg, 'recipient') or _get_field(msg, 'to')
        msg_person_name = _get_field(msg, 'person_name')

        is_match = False
        if target_id and msg_person_id == target_id:
            is_match = True
        elif target_recipient and isinstance(msg_recipient, str) and target_recipient == msg_recipient.strip().lower():
            is_match = True
        elif target_recipient and isinstance(msg_recipient, (list, tuple, set)):
            if any(isinstance(r, str) and target_recipient == r.strip().lower() for r in msg_recipient):
                is_match = True
        elif target_name and isinstance(msg_person_name, str) and target_name == msg_person_name.strip().lower():
            is_match = True
        elif name_re and name_re.search(clean_text):
            is_match = True

        if is_match:
            matched.append(clean_text)

    return matched, general


def _classify_line_ending(line: str) -> EndingStyle:
    stripped = line.rstrip()
    # Strip trailing closing quotes/parens or emojis to inspect punctuation underneath,
    # unless there is no punctuation at all.
    while stripped and (_EMOJI_RE.match(stripped[-1]) or stripped[-1] in '"\')]}'):
        stripped = stripped[:-1].rstrip()
    if not stripped:
        return 'none'
    last = stripped[-1]
    if last in ('!', '！'):
        return 'exclamation'
    if last in ('?', '？', '؟'):
        return 'question'
    if last in ('.', '。', '۔', '।'):
        return 'period'
    return 'none'


def _detect_script_and_languages(lines: Sequence[str]) -> Tuple[Dict[str, float], List[str]]:
    script_counts: Dict[str, int] = {}
    total_letters = 0

    for line in lines:
        for ch in line:
            if not ch.isalpha():
                continue
            total_letters += 1
            cp = ord(ch)
            if 0x0400 <= cp <= 0x052F:
                script = 'cyrillic'
            elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
                script = 'arabic'
            elif 0x0900 <= cp <= 0x097F:
                script = 'devanagari'
            elif (
                0x4E00 <= cp <= 0x9FFF
                or 0x3040 <= cp <= 0x30FF
                or 0xAC00 <= cp <= 0xD7AF
                or 0x3400 <= cp <= 0x4DBF
            ):
                script = 'cjk'
            elif 0x0370 <= cp <= 0x03FF:
                script = 'greek'
            elif 0x0590 <= cp <= 0x05FF:
                script = 'hebrew'
            else:
                name = unicodedata.name(ch, '')
                script = 'latin' if 'LATIN' in name else 'other'
            script_counts[script] = script_counts.get(script, 0) + 1

    if total_letters == 0:
        return {'latin': 1.0}, ['en']

    script_mix = {
        script: round(count / total_letters, 3)
        for script, count in sorted(script_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if count > 0
    }

    tokens = re.findall(r"[\w']+", ' '.join(lines).lower())
    token_set = set(tokens)
    languages: List[str] = []

    if 'latin' in script_mix:
        lang_scores = {
            'en': len(token_set & _ENGLISH_STOPWORDS),
            'es': len(token_set & _SPANISH_STOPWORDS),
            'fr': len(token_set & _FRENCH_STOPWORDS),
            'de': len(token_set & _GERMAN_STOPWORDS),
            'pt': len(token_set & _PORTUGUESE_STOPWORDS),
            'vi': len(token_set & _VIETNAMESE_STOPWORDS),
        }
        best_score = max(lang_scores.values(), default=0)
        if best_score > 0:
            for code, score in sorted(lang_scores.items(), key=lambda kv: (-kv[1], kv[0])):
                if score > 0 and score >= max(1, best_score // 2):
                    languages.append(code)
        else:
            languages.append('en')

    if 'cjk' in script_mix:
        languages.append('cjk')
    if 'cyrillic' in script_mix:
        languages.append('ru')
    if 'arabic' in script_mix:
        languages.append('ar')
    if 'devanagari' in script_mix:
        languages.append('hi')

    return script_mix, languages or ['en']


def _extract_greetings(lines: Sequence[str], max_greetings: int = 4) -> List[str]:
    counts: Dict[str, Tuple[int, str]] = {}
    for line in lines:
        for pat in _GREETING_PATTERNS:
            m = pat.match(line)
            if not m:
                continue
            raw = m.group(1).strip()
            if not raw:
                continue
            norm = raw.lower()
            prev_count, prev_surface = counts.get(norm, (0, raw))
            counts[norm] = (prev_count + 1, prev_surface)
            break

    ranked = sorted(counts.values(), key=lambda item: (-item[0], item[1].lower()))
    return [surface for _count, surface in ranked[:max_greetings]]


def _select_representative_examples(
    lines: Sequence[str],
    typical_words: int,
    *,
    min_examples: int = USER_VOICE_MIN_EXAMPLES,
    max_examples: int = USER_VOICE_MAX_EXAMPLES,
) -> List[str]:
    seen = set()
    unique: List[str] = []
    for line in lines:
        compact = re.sub(r'\s+', ' ', line).strip()
        if not compact or len(compact) > USER_VOICE_MAX_EXAMPLE_CHARS:
            continue
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(compact)

    if not unique:
        for line in lines:
            compact = re.sub(r'\s+', ' ', line).strip()[:USER_VOICE_MAX_EXAMPLE_CHARS]
            if compact and compact.lower() not in seen:
                seen.add(compact.lower())
                unique.append(compact)

    ranked = sorted(
        enumerate(unique),
        key=lambda idx_line: (abs(len(idx_line[1].split()) - max(1, typical_words)), idx_line[0]),
    )
    chosen_indices = sorted(idx for idx, _ in ranked[:max_examples])
    examples = [unique[i] for i in chosen_indices]
    return examples[: max(min_examples, min(max_examples, len(examples)))]


def build_user_voice_profile(
    *,
    conversations: Optional[Sequence[Any]] = None,
    messages: Optional[Sequence[Any]] = None,
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    recipient: Optional[str] = None,
) -> UserVoiceProfile:
    """Build a deterministic ``UserVoiceProfile`` for one person without any LLM call."""
    conv_lines = _extract_user_lines_from_conversations(
        conversations or (),
        person_id=person_id,
        person_name=person_name,
        recipient=recipient,
    )
    matched_msg_lines, general_msg_lines = _extract_user_lines_from_messages(
        messages or (),
        person_id=person_id,
        person_name=person_name,
        recipient=recipient,
    )

    if conv_lines or matched_msg_lines:
        lines = [*matched_msg_lines, *conv_lines]
    else:
        lines = list(general_msg_lines)

    if not lines:
        return UserVoiceProfile(
            person_id=person_id,
            person_name=person_name,
            recipient=recipient,
        )

    word_counts = [max(1, len(line.split())) for line in lines]
    char_lengths = [len(line) for line in lines]
    typical_words = int(round(statistics.median(word_counts)))
    typical_chars = int(round(statistics.median(char_lengths)))

    ending_buckets: Dict[str, int] = {'none': 0, 'period': 0, 'exclamation': 0, 'question': 0}
    exclamation_lines = 0
    exclamation_counts: List[int] = []
    emoji_lines = 0
    lowercase_starts = 0
    alpha_starts = 0

    for line in lines:
        ending = _classify_line_ending(line)
        ending_buckets[ending] = ending_buckets.get(ending, 0) + 1

        excl_count = line.count('!') + line.count('！')
        exclamation_counts.append(excl_count)
        if excl_count > 0:
            exclamation_lines += 1

        if _EMOJI_RE.search(line):
            emoji_lines += 1

        stripped = line.lstrip()
        if stripped and stripped[0].isalpha():
            alpha_starts += 1
            if stripped[0].islower():
                lowercase_starts += 1

    total = len(lines)
    ending_rates = {k: round(v / total, 3) for k, v in ending_buckets.items()}

    # Tie-break non-question endings deterministically: period vs exclamation vs none.
    non_question_candidates: List[EndingStyle] = ['none', 'period', 'exclamation']
    dominant_ending: EndingStyle = max(
        non_question_candidates,
        key=lambda style: (ending_buckets[style], 1 if style == 'none' else 0),
    )
    if ending_buckets[dominant_ending] == 0 and ending_buckets['question'] > 0:
        dominant_ending = 'question'

    exclamation_rate = round(exclamation_lines / total, 3)
    if exclamation_rate < 0.2:
        max_exclamations = 0
    else:
        sorted_excl = sorted(exclamation_counts)
        p75_idx = min(len(sorted_excl) - 1, int(round(0.75 * (len(sorted_excl) - 1))))
        max_exclamations = max(1, sorted_excl[p75_idx])

    emoji_rate = round(emoji_lines / total, 3)
    lowercase_start_rate = round(lowercase_starts / alpha_starts, 3) if alpha_starts else 0.0
    script_mix, languages = _detect_script_and_languages(lines)
    greetings = _extract_greetings(lines)
    examples = _select_representative_examples(lines, typical_words)

    return UserVoiceProfile(
        person_id=person_id,
        person_name=person_name,
        recipient=recipient,
        sample_count=total,
        typical_word_count=typical_words,
        typical_char_length=typical_chars,
        dominant_ending=dominant_ending,
        ending_rates=ending_rates,
        exclamation_rate=exclamation_rate,
        max_exclamations_per_line=max_exclamations,
        emoji_rate=emoji_rate,
        lowercase_start_rate=lowercase_start_rate,
        languages=languages,
        script_mix=script_mix,
        greetings=greetings,
        examples=examples,
    )


def get_or_build_user_voice_profile(
    uid: str,
    *,
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    recipient: Optional[str] = None,
    conversations: Optional[Sequence[Any]] = None,
    messages: Optional[Sequence[Any]] = None,
    user_settings: Optional[Mapping[str, Any]] = None,
    firestore_client: Any = None,
    ttl_seconds: int = USER_VOICE_CACHE_TTL_SECONDS,
    now_fn: Callable[[], float] = time.time,
) -> Optional[UserVoiceProfile]:
    """Return the cached or freshly built ``UserVoiceProfile`` when opt-in is enabled."""
    if not is_user_voice_enabled(
        uid,
        person_id=person_id,
        user_settings=user_settings,
        firestore_client=firestore_client,
    ):
        return None

    person_key = _normalize_person_key(person_id=person_id, person_name=person_name, recipient=recipient)
    cached = get_cached_user_voice_profile(uid, person_key, now_fn=now_fn)
    if cached is not None:
        return cached

    profile = build_user_voice_profile(
        conversations=conversations,
        messages=messages,
        person_id=person_id,
        person_name=person_name,
        recipient=recipient,
    )
    if profile.sample_count > 0:
        cache_user_voice_profile(uid, person_key, profile, ttl_seconds=ttl_seconds, now_fn=now_fn)
    return profile


def format_user_voice_prompt(profile: Optional[UserVoiceProfile]) -> str:
    """Render ``profile`` as a prompt block for the drafting model."""
    if profile is None or profile.sample_count <= 0:
        return ''

    target_label = profile.person_name or profile.recipient or profile.person_id or 'this recipient'
    ending_desc = {
        'none': 'no trailing period (leave the end of the line bare)',
        'period': 'a period (.)',
        'exclamation': 'an exclamation mark (!)',
        'question': 'a question mark (?) when asking',
    }.get(profile.dominant_ending, profile.dominant_ending)

    script_parts = [f'{k}:{int(round(v * 100))}%' for k, v in profile.script_mix.items()]
    greetings_str = ', '.join(f'"{g}"' for g in profile.greetings) if profile.greetings else 'none'
    examples_lines = '\n'.join(f'  - "{ex}"' for ex in profile.examples)

    lines = [
        f'<user_voice_profile recipient="{target_label}">',
        f"Write the message body in the user's own voice for {target_label}, not assistant voice:",
        f'- Typical length: ~{profile.typical_word_count} words (~{profile.typical_char_length} chars)',
        f'- Line ending: {ending_desc}',
        f'- Exclamation rate: {profile.exclamation_rate:.2f} (max {profile.max_exclamations_per_line} "!" per line)',
        f'- Emoji rate: {profile.emoji_rate:.2f}',
        f'- Lowercase start rate: {profile.lowercase_start_rate:.2f}',
        f'- Languages / script mix: {", ".join(profile.languages)} ({", ".join(script_parts)})',
        f'- Greetings used with {target_label}: {greetings_str}',
    ]
    if examples_lines:
        lines.append('- Real examples from the user to this person:')
        lines.append(examples_lines)
    lines.append('</user_voice_profile>')
    return '\n'.join(lines)


def polish_draft_in_user_voice(text: str, profile: Optional[UserVoiceProfile]) -> str:
    """Deterministically fix model-drafted punctuation, ``!`` count, and casing.

    Runs in pure Python with no model calls before the compose sheet opens.
    """
    if not isinstance(text, str) or not text.strip() or profile is None or profile.sample_count <= 0:
        return text

    out = text.strip()

    # 1. Strip AI-style em-dashes when the user doesn't use them in examples.
    if '—' in out and not any('—' in ex for ex in profile.examples):
        out = re.sub(r'\s*—\s*', ', ', out)

    # 2. Enforce exclamation mark ceiling ("!" count).
    max_excl = max(0, profile.max_exclamations_per_line)
    # Collapse repeated "!!!" -> "!" unless the user genuinely uses multi-exclamations.
    if max_excl <= 1:
        out = re.sub(r'!{2,}', '!', out)

    if max_excl == 0:
        # Replace mid-sentence "!" with "." (or nothing at the very end if dominant_ending == 'none').
        out = re.sub(r'!(?=\s|$)', '.', out)
    else:
        excl_positions = [m.start() for m in re.finditer(r'!', out)]
        if len(excl_positions) > max_excl:
            # Keep only the last `max_excl` exclamation marks; turn earlier ones into periods.
            drop_set = set(excl_positions[:-max_excl])
            chars = list(out)
            for idx in drop_set:
                chars[idx] = '.'
            out = ''.join(chars)

    # 3. Strip emojis if the user never uses emojis with this person.
    if profile.emoji_rate == 0.0 and _EMOJI_RE.search(out):
        out = _EMOJI_RE.sub('', out)
        out = re.sub(r' {2,}', ' ', out).strip()

    # 4. Enforce ending punctuation style (period, nothing, "!").
    if profile.dominant_ending == 'none':
        # Strip a single trailing period (preserve ellipsis "...").
        if out.endswith('.') and not out.endswith('...'):
            out = out[:-1].rstrip()
    elif profile.dominant_ending == 'period':
        if out.endswith('!') and max_excl == 0:
            out = out[:-1].rstrip() + '.'
        elif out and out[-1].isalnum():
            out = out + '.'
    elif profile.dominant_ending == 'exclamation':
        if out.endswith('.') and not out.endswith('...'):
            out = out[:-1].rstrip() + '!'
        elif out and out[-1].isalnum() and '!' not in out:
            out = out + '!'

    # 5. Match lowercase opening habit when the user strongly prefers lowercase starts.
    if profile.lowercase_start_rate >= 0.7 and len(out) >= 2:
        first_word_match = re.match(r'^([A-Za-z]+)', out)
        if first_word_match:
            first_word = first_word_match.group(1)
            person_tokens = {
                tok.lower()
                for tok in re.findall(r'[A-Za-z]+', profile.person_name or '')
                if tok
            }
            if (
                first_word != 'I'
                and not first_word.isupper()
                and first_word.lower() not in person_tokens
            ):
                out = out[0].lower() + out[1:]

    return out


def apply_user_voice_to_proposed_message(
    uid: str,
    *,
    to: Optional[Sequence[str]] = None,
    text: str,
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    conversations: Optional[Sequence[Any]] = None,
    messages: Optional[Sequence[Any]] = None,
    user_settings: Optional[Mapping[str, Any]] = None,
) -> str:
    """Resolve the recipient's cached/built voice profile and polish ``text`` in-place."""
    if not isinstance(text, str) or not text:
        return text
    recipient = to[0] if isinstance(to, (list, tuple)) and to else None
    profile = get_or_build_user_voice_profile(
        uid,
        person_id=person_id,
        person_name=person_name,
        recipient=recipient,
        conversations=conversations,
        messages=messages,
        user_settings=user_settings,
    )
    if profile is None:
        return text
    return polish_draft_in_user_voice(text, profile)


def build_propose_message_voice_prompt_for_turn(
    uid: str,
    *,
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    recipient: Optional[str] = None,
    conversations: Optional[Sequence[Any]] = None,
    messages: Optional[Sequence[Any]] = None,
    user_settings: Optional[Mapping[str, Any]] = None,
) -> str:
    """Return the ``<user_voice_profile>`` prompt block for ``propose_message`` when opted in."""
    profile = get_or_build_user_voice_profile(
        uid,
        person_id=person_id,
        person_name=person_name,
        recipient=recipient,
        conversations=conversations,
        messages=messages,
        user_settings=user_settings,
    )
    return format_user_voice_prompt(profile)

