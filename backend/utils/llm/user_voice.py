"""Per-person user voice profiling and deterministic draft polishing for propose_message.

Builds a code-only voice profile per recipient from the user's own lines
(``is_user=True`` transcript segments in non-locked conversations plus human
chat messages typed to Omi):
- Typical length (average and median words/characters)
- Line endings (``period``, ``nothing``, ``exclamation``, ``question``)
- Exclamation rate and emoji rate
- Language and script mix (plus lowercase rate)
- Common greetings used with that person
- 3-5 short verbatim examples

Locked conversations (``is_locked=True``) are strictly excluded. Profiles are
cached for 7 days and gated by an opt-in setting. Before the compose sheet
opens in ``propose_message``, a deterministic polish pass fixes ending
punctuation, exclamation count, and casing with no extra model call.
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Profiles are cached for 7 days (604,800 seconds).
USER_VOICE_CACHE_TTL_SECONDS = 7 * 24 * 3600
MIN_VERBATIM_EXAMPLES = 3
MAX_VERBATIM_EXAMPLES = 5
MAX_EXAMPLE_CHARS = 120

_EMOJI_RE = re.compile(
    '['
    '\U0001f300-\U0001f5ff'
    '\U0001f600-\U0001f64f'
    '\U0001f680-\U0001f6ff'
    '\U0001f700-\U0001f77f'
    '\U0001f780-\U0001f7ff'
    '\U0001f800-\U0001f8ff'
    '\U0001f900-\U0001f9ff'
    '\U0001fa00-\U0001fa6f'
    '\U0001fa70-\U0001faff'
    '\u2600-\u26ff'
    '\u2700-\u27bf'
    ']+'
)

_WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)

_GREETING_PATTERNS = (
    r'^(?:good morning|good afternoon|good evening|yo|hey|hi|hello|sup|morning|hola|buenas|salut|coucou|chào|ê|alo|dear)\b[,!.]?',
)

_LANG_STOPWORDS: dict[str, set[str]] = {
    'es': {
        'hola',
        'que',
        'qué',
        'para',
        'con',
        'está',
        'estoy',
        'gracias',
        'pero',
        'como',
        'cómo',
        'más',
        'bien',
        'vamos',
        'mañana',
    },
    'vi': {
        'anh',
        'em',
        'ơi',
        'nhé',
        'nha',
        'được',
        'không',
        'rồi',
        'đang',
        'với',
        'này',
        'chưa',
        'luôn',
        'của',
        'mình',
    },
    'fr': {'salut', 'bonjour', 'merci', 'avec', 'pour', 'dans', 'est', 'suis', 'pas', 'mais', 'bien', 'demain', 'oui'},
    'de': {'hallo', 'danke', 'nicht', 'mit', 'für', 'und', 'ich', 'bin', 'ist', 'wir', 'heute', 'morgen', 'gut'},
    'pt': {
        'olá',
        'oi',
        'obrigado',
        'obrigada',
        'para',
        'com',
        'não',
        'estou',
        'está',
        'bom',
        'bem',
        'amanhã',
        'vamos',
    },
    'en': {
        'the',
        'and',
        'you',
        'are',
        'for',
        'with',
        'that',
        'this',
        'have',
        'from',
        'will',
        'can',
        'just',
        'running',
        'late',
        'hey',
        'hi',
        'thanks',
        'please',
    },
}

# In-memory caches (used alongside Redis when available, and in hermetic unit tests).
_VOICE_PROFILE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_UID_CACHED_KEYS: dict[str, set[str]] = {}
_OPT_IN_STATE: dict[str, bool] = {}
_HANDLE_TO_PERSON_CACHE: dict[str, dict[str, str]] = {}
redis_client: Any = None


def _get_redis() -> Any:
    if redis_client is not None:
        return redis_client
    if not os.environ.get('REDIS_DB_HOST'):
        return None
    try:
        from database.redis_db import r as _r

        return _r
    except Exception:
        return None


@dataclass
class UserVoiceProfile:
    uid: str
    person_key: str
    person_name: str
    sample_count: int = 0
    typical_length_words: float = 0.0
    median_length_words: float = 0.0
    typical_length_chars: float = 0.0
    length_bucket: str = 'medium'
    line_endings: dict[str, float] = field(
        default_factory=lambda: {'period': 0.0, 'nothing': 0.0, 'exclamation': 0.0, 'question': 0.0}
    )
    dominant_ending: str = 'nothing'
    exclamation_rate: float = 0.0
    avg_exclamations_per_line: float = 0.0
    emoji_rate: float = 0.0
    lowercase_rate: float = 0.0
    all_lowercase_rate: float = 0.0
    primary_language: str = 'en'
    script_mix: dict[str, float] = field(default_factory=lambda: {'latin': 1.0})
    greetings: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    created_at: float = 0.0
    expires_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'UserVoiceProfile':
        known_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def normalize_person_key(person: Optional[str]) -> str:
    """Normalize a person name, contact handle, or identifier into a stable cache key."""
    if not person:
        return 'default'
    cleaned = re.sub(r'\s+', ' ', str(person).strip().lower())
    return cleaned or 'default'


def user_voice_cache_key(uid: str, person_key: str) -> str:
    norm_key = normalize_person_key(person_key)
    return f'user_voice_profile:{uid}:{norm_key}'


def user_voice_index_key(uid: str) -> str:
    return f'user_voice_profile_index:{uid}'


def user_voice_opt_in_key(uid: str, person_key: Optional[str] = None) -> str:
    if person_key:
        return f'user_voice_opt_in:{uid}:{normalize_person_key(person_key)}'
    return f'user_voice_opt_in:{uid}:*'


def invalidate_user_voice_cache(uid: str, person_key: Optional[str] = None) -> int:
    """Invalidate cached voice profile(s) for a user (or a specific person) across memory and Redis."""
    if not uid:
        return 0
    removed = 0
    if person_key is not None:
        ckey = user_voice_cache_key(uid, person_key)
        if _VOICE_PROFILE_CACHE.pop(ckey, None) is not None:
            removed += 1
        if uid in _UID_CACHED_KEYS:
            _UID_CACHED_KEYS[uid].discard(ckey)
        try:
            r_client = _get_redis()
            if r_client is not None:
                if hasattr(r_client, 'delete'):
                    r_client.delete(ckey)
        except Exception:
            pass
        return removed

    prefix_profile = f'user_voice_profile:{uid}:'
    keys_to_delete: set[str] = set(_UID_CACHED_KEYS.pop(uid, set()))
    for k in [k for k in _VOICE_PROFILE_CACHE if k.startswith(prefix_profile)]:
        _VOICE_PROFILE_CACHE.pop(k, None)
        keys_to_delete.add(k)
        removed += 1
    try:
        r_client = _get_redis()
        if r_client is not None:
            idx_key = user_voice_index_key(uid)
            raw_idx = r_client.get(idx_key)
            if raw_idx:
                text = raw_idx.decode() if isinstance(raw_idx, (bytes, bytearray)) else str(raw_idx)
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str):
                            keys_to_delete.add(item)
            if hasattr(r_client, 'delete'):
                for k in keys_to_delete:
                    r_client.delete(k)
                r_client.delete(idx_key)
    except Exception:
        pass
    return removed


def on_conversation_deleted_user_voice(uid: str, person_key: Optional[str] = None) -> int:
    """Hook to invalidate cached user voice profiles when conversations are deleted or locked."""
    return invalidate_user_voice_cache(uid, person_key)


def set_user_voice_opt_in(uid: str, enabled: bool, person_key: Optional[str] = None) -> None:
    """Set account-wide or per-person opt-in for user voice drafting and purge cache on opt-out."""
    key = user_voice_opt_in_key(uid, person_key)
    _OPT_IN_STATE[key] = bool(enabled)
    try:
        r_client = _get_redis()
        if r_client is not None:
            r_client.setex(key, USER_VOICE_CACHE_TTL_SECONDS, '1' if enabled else '0')
    except Exception:
        pass
    if not enabled:
        invalidate_user_voice_cache(uid, person_key)


def is_user_voice_opted_in(
    uid: str,
    person_key: Optional[str] = None,
    user_settings: Optional[dict[str, Any]] = None,
) -> bool:
    """Check whether the user has opted into per-person voice drafting."""
    if not uid:
        return False

    if user_settings is not None:
        if user_settings.get('propose_message_user_voice_opt_in') is not None:
            return bool(user_settings['propose_message_user_voice_opt_in'])
        if user_settings.get('user_voice_enabled') is not None:
            return bool(user_settings['user_voice_enabled'])
        per_person = user_settings.get('user_voice_per_person')
        if isinstance(per_person, dict) and person_key:
            norm = normalize_person_key(person_key)
            if norm in per_person:
                return bool(per_person[norm])

    if person_key:
        specific_key = user_voice_opt_in_key(uid, person_key)
        if specific_key in _OPT_IN_STATE:
            return _OPT_IN_STATE[specific_key]

    global_key = user_voice_opt_in_key(uid, None)
    if global_key in _OPT_IN_STATE:
        return _OPT_IN_STATE[global_key]

    try:
        r_client = _get_redis()
        if r_client is not None:
            if person_key:
                raw_specific = r_client.get(user_voice_opt_in_key(uid, person_key))
                if raw_specific is not None:
                    val = raw_specific.decode() if isinstance(raw_specific, (bytes, bytearray)) else str(raw_specific)
                    return val == '1'
            raw_global = r_client.get(global_key)
            if raw_global is not None:
                val = raw_global.decode() if isinstance(raw_global, (bytes, bytearray)) else str(raw_global)
                return val == '1'
    except Exception:
        pass

    return False


def remember_contact_resolution(uid: str, contacts: Iterable[Any]) -> None:
    """Record phone/email handle -> contact display name from search_contacts results."""
    if not uid or not contacts:
        return
    mapping = _HANDLE_TO_PERSON_CACHE.setdefault(uid, {})
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        name = str(contact.get('name') or contact.get('display_name') or '').strip()
        if not name:
            continue
        for field_name in ('phones', 'phone_numbers', 'emails', 'email_addresses', 'handles', 'to'):
            values = contact.get(field_name)
            if isinstance(values, list):
                for handle in values:
                    if handle:
                        mapping[normalize_person_key(str(handle))] = name
        single_handle = contact.get('phone') or contact.get('email') or contact.get('handle')
        if single_handle:
            mapping[normalize_person_key(str(single_handle))] = name


def resolve_person_for_handles(
    uid: str, recipient_handles: Optional[Iterable[str]], explicit_person: Optional[str] = None
) -> str:
    """Resolve a human display name or fallback handle key for propose_message recipients."""
    if explicit_person and str(explicit_person).strip():
        return str(explicit_person).strip()
    mapping = _HANDLE_TO_PERSON_CACHE.get(uid, {})
    if recipient_handles:
        for handle in recipient_handles:
            if not handle:
                continue
            norm = normalize_person_key(str(handle))
            if norm in mapping:
                return mapping[norm]
        first = next((str(h).strip() for h in recipient_handles if h and str(h).strip()), '')
        if first:
            return first
    return 'default'


def clear_user_voice_cache(uid: Optional[str] = None) -> None:
    """Clear cached voice profiles and opt-in state (primarily for tests)."""
    if uid is None:
        _VOICE_PROFILE_CACHE.clear()
        _UID_CACHED_KEYS.clear()
        _OPT_IN_STATE.clear()
        _HANDLE_TO_PERSON_CACHE.clear()
        return
    invalidate_user_voice_cache(uid, None)
    prefix_opt = f'user_voice_opt_in:{uid}:'
    for k in [k for k in _OPT_IN_STATE if k.startswith(prefix_opt)]:
        _OPT_IN_STATE.pop(k, None)
    _HANDLE_TO_PERSON_CACHE.pop(uid, None)


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _is_locked(item: Any) -> bool:
    return bool(_get_field(item, 'is_locked', False))


def _conversation_matches_person(
    conv: Any,
    person_id: Optional[str],
    person_name: Optional[str],
    recipient_handles: Optional[Iterable[str]],
) -> bool:
    """Determine whether a non-locked conversation involves the target person."""
    if not person_id and not person_name and not recipient_handles:
        return True

    target_tokens: set[str] = set()
    if person_name:
        norm_name = normalize_person_key(person_name)
        if norm_name and norm_name != 'default':
            target_tokens.add(norm_name)
            for part in norm_name.split():
                if len(part) >= 2:
                    target_tokens.add(part)
    if recipient_handles:
        for h in recipient_handles:
            if h:
                target_tokens.add(normalize_person_key(str(h)))

    conv_person_ids = _get_field(conv, 'person_ids') or _get_field(conv, 'people') or []
    if person_id and isinstance(conv_person_ids, (list, tuple, set)) and person_id in conv_person_ids:
        return True

    participants = _get_field(conv, 'participants') or _get_field(conv, 'speakers') or []
    if isinstance(participants, (list, tuple, set)):
        for p in participants:
            p_str = normalize_person_key(p.get('name') if isinstance(p, dict) else str(p))
            if p_str in target_tokens or any(tok in p_str for tok in target_tokens):
                return True

    person_field = _get_field(conv, 'person') or _get_field(conv, 'recipient') or _get_field(conv, 'contact_name')
    if person_field:
        p_norm = normalize_person_key(str(person_field))
        if p_norm in target_tokens or any(tok in p_norm for tok in target_tokens):
            return True

    segments = _get_field(conv, 'transcript_segments') or []
    for seg in segments:
        seg_pid = _get_field(seg, 'person_id')
        if person_id and seg_pid and str(seg_pid) == str(person_id):
            return True
        seg_speaker = _get_field(seg, 'speaker_name') or _get_field(seg, 'person_name')
        if seg_speaker:
            s_norm = normalize_person_key(str(seg_speaker))
            if s_norm in target_tokens or any(tok in s_norm for tok in target_tokens):
                return True

    structured = _get_field(conv, 'structured')
    if structured and target_tokens:
        title = str(_get_field(structured, 'title') or '').lower()
        overview = str(_get_field(structured, 'overview') or '').lower()
        combined = f'{title} {overview}'
        for tok in target_tokens:
            if tok and re.search(rf'\b{re.escape(tok)}\b', combined):
                return True

    return False


def extract_user_lines_for_person(
    conversations: Optional[Iterable[Any]] = None,
    chat_messages: Optional[Iterable[Any]] = None,
    *,
    person_id: Optional[str] = None,
    person_name: Optional[str] = None,
    recipient_handles: Optional[Iterable[str]] = None,
) -> list[str]:
    """Extract the user's own lines for a person from non-locked conversations and human chat messages."""
    lines: list[str] = []

    if conversations:
        for conv in conversations:
            # Privacy invariant: locked conversations are strictly excluded.
            if _is_locked(conv):
                continue
            if not _conversation_matches_person(conv, person_id, person_name, recipient_handles):
                continue
            segments = _get_field(conv, 'transcript_segments') or []
            for seg in segments:
                if _is_locked(seg):
                    continue
                if not bool(_get_field(seg, 'is_user', False)):
                    continue
                text = str(_get_field(seg, 'text') or '').strip()
                if text:
                    lines.append(text)

    if chat_messages:
        target_name = normalize_person_key(person_name) if person_name else None
        for msg in chat_messages:
            if _is_locked(msg):
                continue
            sender = str(_get_field(msg, 'sender') or _get_field(msg, 'role') or '').lower()
            is_human = sender in {'human', 'user'} or bool(_get_field(msg, 'is_user', False))
            if not is_human:
                continue
            msg_person = _get_field(msg, 'person_id') or _get_field(msg, 'recipient') or _get_field(msg, 'person_name')
            if person_id and msg_person and str(msg_person) == str(person_id):
                text = str(_get_field(msg, 'text') or _get_field(msg, 'content') or '').strip()
                if text:
                    lines.append(text)
            elif target_name and target_name != 'default' and msg_person:
                if target_name in normalize_person_key(str(msg_person)):
                    text = str(_get_field(msg, 'text') or _get_field(msg, 'content') or '').strip()
                    if text:
                        lines.append(text)
            elif not person_id and (not target_name or target_name == 'default'):
                text = str(_get_field(msg, 'text') or _get_field(msg, 'content') or '').strip()
                if text:
                    lines.append(text)

    return lines


def _classify_line_ending(line: str) -> str:
    stripped = line.rstrip()
    without_emoji = _EMOJI_RE.sub('', stripped).rstrip()
    target = without_emoji if without_emoji else stripped
    if not target:
        return 'nothing'
    last_char = target[-1]
    if last_char == '!':
        return 'exclamation'
    if last_char == '?':
        return 'question'
    if last_char in {'.', '。'}:
        return 'period'
    return 'nothing'


def _detect_script_mix_and_language(lines: list[str]) -> tuple[dict[str, float], str]:
    script_counts: dict[str, int] = {
        'latin': 0,
        'cjk': 0,
        'cyrillic': 0,
        'arabic': 0,
        'devanagari': 0,
        'hangul': 0,
    }
    total_letters = 0

    for line in lines:
        for ch in line:
            if not ch.isalpha():
                continue
            total_letters += 1
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF) or (0x3040 <= cp <= 0x30FF):
                script_counts['cjk'] += 1
            elif 0xAC00 <= cp <= 0xD7AF:
                script_counts['hangul'] += 1
            elif 0x0400 <= cp <= 0x04FF:
                script_counts['cyrillic'] += 1
            elif 0x0600 <= cp <= 0x06FF:
                script_counts['arabic'] += 1
            elif 0x0900 <= cp <= 0x097F:
                script_counts['devanagari'] += 1
            else:
                script_counts['latin'] += 1

    if total_letters == 0:
        return {'latin': 1.0}, 'en'

    script_mix = {k: round(v / total_letters, 4) for k, v in script_counts.items() if v > 0}

    if script_counts['hangul'] / total_letters > 0.3:
        return script_mix, 'ko'
    if script_counts['cjk'] / total_letters > 0.3:
        has_kana = any(0x3040 <= ord(ch) <= 0x30FF for line in lines for ch in line)
        return script_mix, ('ja' if has_kana else 'zh')
    if script_counts['cyrillic'] / total_letters > 0.3:
        return script_mix, 'ru'
    if script_counts['arabic'] / total_letters > 0.3:
        return script_mix, 'ar'
    if script_counts['devanagari'] / total_letters > 0.3:
        return script_mix, 'hi'

    tokens = [w.lower() for line in lines for w in _WORD_RE.findall(line)]
    lang_scores: dict[str, int] = {lang: 0 for lang in _LANG_STOPWORDS}
    for tok in tokens:
        for lang, vocab in _LANG_STOPWORDS.items():
            if tok in vocab:
                lang_scores[lang] += 1

    best_lang = 'en'
    best_score = lang_scores.get('en', 0)
    for lang in ('es', 'vi', 'fr', 'de', 'pt'):
        if lang_scores[lang] > best_score and lang_scores[lang] >= 2:
            best_lang = lang
            best_score = lang_scores[lang]

    return script_mix, best_lang


def _extract_greetings(lines: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        for pat in _GREETING_PATTERNS:
            m = re.match(pat, stripped, flags=re.IGNORECASE)
            if m:
                greeting = m.group(0).strip()
                norm = greeting.lower()
                if norm not in seen:
                    seen.add(norm)
                    found.append(greeting)
                if len(found) >= 5:
                    return found
    return found


def _select_verbatim_examples(lines: list[str]) -> list[str]:
    """Select 3-5 short, representative verbatim examples from the user's own lines."""
    candidates: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        cleaned = re.sub(r'\s+', ' ', raw.strip())
        if not cleaned or len(cleaned) > MAX_EXAMPLE_CHARS:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(cleaned)

    if not candidates:
        return []
    if len(candidates) <= MAX_VERBATIM_EXAMPLES:
        return candidates

    med_len = statistics.median(len(c) for c in candidates)
    ranked = sorted(
        enumerate(candidates),
        key=lambda item: (abs(len(item[1]) - med_len), item[0]),
    )
    chosen_indices = sorted(idx for idx, _ in ranked[:MAX_VERBATIM_EXAMPLES])
    return [candidates[idx] for idx in chosen_indices]


def build_user_voice_profile(
    uid: str,
    person_name: str,
    lines: Iterable[str],
    *,
    person_key: Optional[str] = None,
    now: Optional[float] = None,
) -> UserVoiceProfile:
    """Build a code-only UserVoiceProfile from a list of the user's lines for a person."""
    ts = time.time() if now is None else float(now)
    key = normalize_person_key(person_key or person_name)
    clean_lines = [str(line).strip() for line in lines if line and str(line).strip()]

    if not clean_lines:
        return UserVoiceProfile(
            uid=uid,
            person_key=key,
            person_name=person_name or key,
            sample_count=0,
            created_at=ts,
            expires_at=ts + USER_VOICE_CACHE_TTL_SECONDS,
        )

    n = len(clean_lines)
    word_counts = [len(_WORD_RE.findall(line)) for line in clean_lines]
    char_counts = [len(line) for line in clean_lines]

    avg_words = round(sum(word_counts) / n, 2)
    med_words = round(float(statistics.median(word_counts)), 2)
    avg_chars = round(sum(char_counts) / n, 2)

    if med_words <= 6:
        length_bucket = 'short_fragment'
    elif med_words <= 16:
        length_bucket = 'medium'
    else:
        length_bucket = 'long'

    ending_counts = {'period': 0, 'nothing': 0, 'exclamation': 0, 'question': 0}
    for line in clean_lines:
        ending_counts[_classify_line_ending(line)] += 1

    line_endings = {k: round(v / n, 4) for k, v in ending_counts.items()}
    declarative_candidates = ('nothing', 'period', 'exclamation')
    dominant_ending = max(declarative_candidates, key=lambda k: (ending_counts[k], k == 'nothing'))

    lines_with_excl = sum(1 for line in clean_lines if '!' in line)
    total_excl = sum(line.count('!') for line in clean_lines)
    exclamation_rate = round(lines_with_excl / n, 4)
    avg_exclamations = round(total_excl / n, 4)

    lines_with_emoji = sum(1 for line in clean_lines if _EMOJI_RE.search(line))
    emoji_rate = round(lines_with_emoji / n, 4)

    alpha_start_lines = 0
    lower_start_lines = 0
    alpha_any_lines = 0
    all_lower_lines = 0
    for line in clean_lines:
        first_alpha = next((ch for ch in line if ch.isalpha()), None)
        if first_alpha is not None:
            alpha_start_lines += 1
            if first_alpha.islower():
                lower_start_lines += 1
            alpha_any_lines += 1
            if line == line.lower():
                all_lower_lines += 1

    lowercase_rate = round(lower_start_lines / alpha_start_lines, 4) if alpha_start_lines else 0.0
    all_lowercase_rate = round(all_lower_lines / alpha_any_lines, 4) if alpha_any_lines else 0.0

    script_mix, primary_language = _detect_script_mix_and_language(clean_lines)
    greetings = _extract_greetings(clean_lines)
    examples = _select_verbatim_examples(clean_lines)

    return UserVoiceProfile(
        uid=uid,
        person_key=key,
        person_name=person_name or key,
        sample_count=n,
        typical_length_words=avg_words,
        median_length_words=med_words,
        typical_length_chars=avg_chars,
        length_bucket=length_bucket,
        line_endings=line_endings,
        dominant_ending=dominant_ending,
        exclamation_rate=exclamation_rate,
        avg_exclamations_per_line=avg_exclamations,
        emoji_rate=emoji_rate,
        lowercase_rate=lowercase_rate,
        all_lowercase_rate=all_lowercase_rate,
        primary_language=primary_language,
        script_mix=script_mix,
        greetings=greetings,
        examples=examples,
        created_at=ts,
        expires_at=ts + USER_VOICE_CACHE_TTL_SECONDS,
    )


def get_cached_user_voice_profile(
    uid: str,
    person_key: str,
    *,
    now: Optional[float] = None,
) -> Optional[UserVoiceProfile]:
    """Read a cached UserVoiceProfile if present and within its 7-day TTL."""
    ts = time.time() if now is None else float(now)
    cache_key = user_voice_cache_key(uid, person_key)

    mem_entry = _VOICE_PROFILE_CACHE.get(cache_key)
    if mem_entry is not None:
        expires_at, payload = mem_entry
        if ts < expires_at:
            return UserVoiceProfile.from_dict(payload)
        _VOICE_PROFILE_CACHE.pop(cache_key, None)

    try:
        r_client = _get_redis()
        if r_client is not None:
            raw = r_client.get(cache_key)
            if raw:
                text = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
                data = json.loads(text)
                if isinstance(data, dict):
                    expires_at = float(data.get('expires_at') or (ts + USER_VOICE_CACHE_TTL_SECONDS))
                    if ts < expires_at:
                        _VOICE_PROFILE_CACHE[cache_key] = (expires_at, data)
                        return UserVoiceProfile.from_dict(data)
    except Exception:
        pass

    return None


def cache_user_voice_profile(profile: UserVoiceProfile) -> None:
    """Store a UserVoiceProfile in the 7-day cache."""
    cache_key = user_voice_cache_key(profile.uid, profile.person_key)
    payload = profile.to_dict()
    expires_at = profile.expires_at or (time.time() + USER_VOICE_CACHE_TTL_SECONDS)
    _VOICE_PROFILE_CACHE[cache_key] = (expires_at, payload)
    _UID_CACHED_KEYS.setdefault(profile.uid, set()).add(cache_key)

    try:
        r_client = _get_redis()
        if r_client is not None:
            r_client.setex(cache_key, USER_VOICE_CACHE_TTL_SECONDS, json.dumps(payload))
            idx_key = user_voice_index_key(profile.uid)
            known = sorted(_UID_CACHED_KEYS.get(profile.uid, {cache_key}))
            r_client.setex(idx_key, USER_VOICE_CACHE_TTL_SECONDS, json.dumps(known))
    except Exception:
        pass


def get_or_build_user_voice_profile(
    uid: str,
    person_name: str,
    *,
    person_id: Optional[str] = None,
    recipient_handles: Optional[Iterable[str]] = None,
    conversations: Optional[Iterable[Any]] = None,
    chat_messages: Optional[Iterable[Any]] = None,
    opt_in: Optional[bool] = None,
    user_settings: Optional[dict[str, Any]] = None,
    force_refresh: bool = False,
    now: Optional[float] = None,
) -> Optional[UserVoiceProfile]:
    """Return the 7-day cached voice profile for a person, or build and cache it when opted in."""
    person_key = normalize_person_key(person_id or person_name)
    allowed = opt_in if opt_in is not None else is_user_voice_opted_in(uid, person_key, user_settings=user_settings)
    if not allowed:
        return None

    if not force_refresh:
        cached = get_cached_user_voice_profile(uid, person_key, now=now)
        if cached is not None:
            return cached

    if conversations is None:
        try:
            import database.conversations as conversations_db

            conversations = conversations_db.get_conversations(
                uid=uid, limit=100, statuses=['completed'], include_discarded=False
            )
        except Exception:
            conversations = []
        if chat_messages is None:
            try:
                import database.chat as chat_db

                chat_messages = chat_db.get_messages(uid, limit=100)
            except Exception:
                chat_messages = []
    elif chat_messages is None:
        chat_messages = []

    lines = extract_user_lines_for_person(
        conversations,
        chat_messages,
        person_id=person_id,
        person_name=person_name,
        recipient_handles=recipient_handles,
    )
    profile = build_user_voice_profile(
        uid,
        person_name=person_name or person_key,
        lines=lines,
        person_key=person_key,
        now=now,
    )
    cache_user_voice_profile(profile)
    return profile


def format_user_voice_prompt(profile: Optional[UserVoiceProfile]) -> str:
    """Format a UserVoiceProfile into drafting guidance for propose_message."""
    if profile is None or profile.sample_count == 0:
        return ''

    casing_desc = (
        'all lowercase fragments'
        if profile.all_lowercase_rate >= 0.65
        else ('lowercase sentence starts' if profile.lowercase_rate >= 0.65 else 'standard sentence capitalization')
    )
    ending_desc = {
        'nothing': 'no trailing period (leave line endings bare)',
        'period': 'ends sentences with a period (.)',
        'exclamation': 'frequently ends lines with an exclamation mark (!)',
        'question': 'question-heavy',
    }.get(profile.dominant_ending, 'no trailing period')

    greetings_str = (
        ', '.join(f'"{g}"' for g in profile.greetings[:4]) if profile.greetings else 'none / jumps straight in'
    )
    script_str = ', '.join(f'{k}={int(round(v * 100))}%' for k, v in profile.script_mix.items())

    lines = [
        f'<user_voice_profile recipient="{profile.person_name}">',
        f'- Typical length: ~{profile.median_length_words:.0f} words ({profile.typical_length_chars:.0f} chars, {profile.length_bucket})',
        f'- Casing: {casing_desc} (lowercase start rate={int(round(profile.lowercase_rate * 100))}%)',
        f'- Line endings: dominant={profile.dominant_ending} ({ending_desc})',
        f'- Exclamation rate: {int(round(profile.exclamation_rate * 100))}% of lines (avg {profile.avg_exclamations_per_line:.2f} "!" per line)',
        f'- Emoji rate: {int(round(profile.emoji_rate * 100))}% of lines',
        f'- Language & script mix: language={profile.primary_language}, scripts=({script_str})',
        f'- Typical greetings with {profile.person_name}: {greetings_str}',
    ]
    if profile.examples:
        lines.append(f'- Verbatim examples of how the user writes to {profile.person_name}:')
        for ex in profile.examples[:MAX_VERBATIM_EXAMPLES]:
            lines.append(f'  * "{ex}"')
    lines.append('Write the propose_message draft in this exact voice rather than generic assistant English.')
    lines.append('</user_voice_profile>')
    return '\n'.join(lines)


def polish_draft_in_user_voice(text: str, profile: Optional[UserVoiceProfile]) -> str:
    """Deterministic polish pass before the compose sheet opens (no extra model call).

    Fixes:
    1. Exclamation mark ("!") count and trailing "!" based on the user's exclamation rate
       and dominant line ending for that recipient.
    2. Ending punctuation (strips trailing periods when dominant_ending == 'nothing', or
       adds a trailing period when dominant_ending == 'period').
    3. Casing and greeting punctuation when the user consistently writes in lowercase or
       formal sentence case for that recipient.
    """
    if not text or profile is None or profile.sample_count == 0:
        return text

    polished = text.strip()
    if not polished:
        return text

    # 1. Strip stiff assistant openings ("Hi [Name], ", "Hello [Name], ", "Dear [Name], ")
    # when the user never uses formal greetings with this person or uses casual greetings.
    if profile.lowercase_rate >= 0.7 or profile.length_bucket == 'short_fragment':
        if not profile.greetings:
            polished = re.sub(
                rf'^(?:hi|hello|dear|hey)\s+{re.escape(profile.person_name)}\s*[,!.:-]\s*',
                '',
                polished,
                flags=re.IGNORECASE,
            )
            polished = re.sub(r'^(?:hi|hello|dear)\s*[,!.:-]\s*', '', polished, flags=re.IGNORECASE)
        else:
            preferred_greeting = profile.greetings[0]
            polished = re.sub(
                rf'^(?:hi|hello|dear|hey)(?:\s+{re.escape(profile.person_name)})?\s*[,!.:-]\s*',
                f'{preferred_greeting} ',
                polished,
                flags=re.IGNORECASE,
            )

    # 2. Fix exclamation mark ("!") count at word/clause boundaries (preserves URLs/tokens)
    if profile.exclamation_rate < 0.2 and profile.dominant_ending != 'exclamation':
        if profile.dominant_ending == 'nothing':
            polished = re.sub(r'!+\s*$', '', polished)
            polished = re.sub(r'!+(?=\s|$)', '', polished)
        else:
            polished = re.sub(r'!+\s*$', '.', polished)
            polished = re.sub(r'!+(?=\s|$)', '.', polished)
    else:
        max_bangs = 2 if profile.avg_exclamations_per_line >= 1.5 else 1
        polished = re.sub(r'!{2,}(?=\s|$)', '!' * max_bangs, polished)

    # 3. Fix emoji mismatches when the user never uses emojis with this person
    if profile.emoji_rate == 0.0:
        polished = _EMOJI_RE.sub('', polished).strip()
        polished = re.sub(r'\s{2,}', ' ', polished)

    # 4. Fix casing to match the user's per-person voice
    if profile.all_lowercase_rate >= 0.65:
        polished = polished.lower()
    elif profile.lowercase_rate >= 0.7:
        if polished and polished[0].isalpha():
            polished = polished[0].lower() + polished[1:]
        polished = re.sub(r"\bI'm\b", 'im', polished) if 'im' in ' '.join(profile.examples).lower() else polished
    elif profile.lowercase_rate <= 0.25 and profile.dominant_ending == 'period':
        if polished and polished[0].isalpha() and polished[0].islower():
            polished = polished[0].upper() + polished[1:]

    # 5. Fix ending punctuation (period vs nothing vs exclamation)
    stripped_end = polished.rstrip()
    if stripped_end:
        if profile.dominant_ending == 'nothing' and profile.line_endings.get('nothing', 0.0) >= 0.5:
            stripped_end = re.sub(r'\.+\s*$', '', stripped_end)
            if profile.length_bucket == 'short_fragment' and profile.all_lowercase_rate >= 0.65:
                stripped_end = re.sub(r'\.\s+', ', ', stripped_end)
        elif profile.dominant_ending == 'period' and profile.line_endings.get('period', 0.0) >= 0.5:
            if stripped_end[-1] not in {'.', '?', '!'}:
                stripped_end = stripped_end + '.'
        elif profile.dominant_ending == 'exclamation' and profile.exclamation_rate >= 0.6:
            if stripped_end[-1] == '.':
                stripped_end = stripped_end[:-1] + '!'
            elif stripped_end[-1] not in {'.', '?', '!'}:
                stripped_end = stripped_end + '!'

    return stripped_end


def apply_user_voice_to_propose_message(
    uid: str,
    text: str,
    recipients: Optional[Iterable[str]] = None,
) -> str:
    """Synchronous helper to run opt-in check, profile lookup, and draft polish off the event loop."""
    person_name = resolve_person_for_handles(uid, recipients)
    if not is_user_voice_opted_in(uid, person_name):
        return text
    profile = get_or_build_user_voice_profile(
        uid,
        person_name,
        recipient_handles=recipients,
        opt_in=True,
    )
    return polish_draft_in_user_voice(text, profile)


def enrich_search_contacts_with_user_voice(uid: str, contacts: Iterable[Any]) -> None:
    """Synchronous helper to record contacts and attach user voice profiles off the event loop."""
    remember_contact_resolution(uid, contacts)
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        contact_name = str(contact.get('name') or contact.get('display_name') or '').strip()
        if contact_name and is_user_voice_opted_in(uid, contact_name):
            handles = contact.get('phones') or contact.get('emails') or []
            profile = get_or_build_user_voice_profile(
                uid,
                contact_name,
                recipient_handles=handles if isinstance(handles, list) else [],
                opt_in=True,
            )
            prompt_guidance = format_user_voice_prompt(profile)
            if prompt_guidance:
                contact['user_voice_profile'] = prompt_guidance
