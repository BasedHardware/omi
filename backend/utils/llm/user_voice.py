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

import logging
import re
import statistics
import time
import unicodedata
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

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

# Fallback in-process cache, opt-in state, contact handle map, and last turn profile.
_MEMORY_CACHE: Dict[str, Tuple[float, str]] = {}
_MEMORY_OPT_IN: Dict[str, Any] = {}
_CONTACT_HANDLE_TO_PERSON: Dict[Tuple[str, str], str] = {}
_DISABLED_OPT_IN_UNTIL: Dict[str, float] = {}
_CONTACT_HANDLE_LIMIT = 1024
_DISABLED_OPT_IN_TTL_SECONDS = 30

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
    ']'
)

_GREETING_WORD_RE = (
    r'(?:hey+y*|hi+i*|hello+|yo+|sup|hiya|howdy|morning|good\s+(?:morning|afternoon|evening)|'
    r'dear\s+[a-zA-Z\u00C0-\u024F]+|hola|bonjour|salut|ciao|oi|halo|namaste|salaam)'
)

_GREETING_NAME_SUFFIX_RE = (
    r'(?:\s+(?:dr\.?|mr\.?|ms\.?|mrs\.?|prof\.?)\s+[a-zA-Z\u00C0-\u024F]+|\s+[a-zA-Z\u00C0-\u024F]+)?'
)

_GREETING_PATTERNS = (
    re.compile(
        r'^\s*(' + _GREETING_WORD_RE + _GREETING_NAME_SUFFIX_RE + r')[\s,!.:;-]*',
        re.IGNORECASE,
    ),
)

_GREETING_EXCLAMATION_PREFIX_RE = re.compile(
    r'^(\s*' + _GREETING_WORD_RE + _GREETING_NAME_SUFFIX_RE + r')\s*!+\s+(\S)',
    re.IGNORECASE,
)

_MESSAGE_INTENT_TARGET_RE = re.compile(
    r'\b(?:message|text|tell|ping|write(?:\s+to)?|send(?:\s+a\s+(?:message|text))?\s+to|reply\s+to)\s+'
    r'((?:dr\.?\s+|mr\.?\s+|ms\.?\s+|mrs\.?\s+|prof\.?\s+)?[A-Z][a-zA-Z\u00C0-\u024F]+(?:\s+[A-Z][a-zA-Z\u00C0-\u024F]+)?)',
    re.IGNORECASE,
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
    normalized = _normalize_person_key(person_key) if person_key else 'default'
    return f'user_voice_profile:v1:{uid}:{normalized}'


def _load_user_voice_settings(uid: str, *, firestore_client: Any = None) -> Dict[str, Any]:
    """Load user-voice opt-in settings for ``uid`` from memory override or Firestore user doc."""
    if uid in _MEMORY_OPT_IN and isinstance(_MEMORY_OPT_IN[uid], Mapping):
        return dict(_MEMORY_OPT_IN[uid])

    if firestore_client is not None:
        try:
            col_fn = getattr(firestore_client, 'collection', None)
            if callable(col_fn):
                doc_ref = getattr(col_fn('users'), 'document')(uid)
                snap = getattr(doc_ref, 'get')()
                doc = snap.to_dict() if getattr(snap, 'exists', False) else {}
                if isinstance(doc, Mapping):
                    return dict(doc)
        except Exception as exc:
            logger.debug('Could not read user_voice settings uid=%s err=%s', uid, type(exc).__name__)
        return {}

    if _DISABLED_OPT_IN_UNTIL.get(uid, 0) > time.monotonic():
        return {}

    try:
        from database import users as users_db

        doc = users_db.get_user_profile(uid)
        data = dict(doc or {})
        if not data.get('user_voice_enabled') and not any((data.get('user_voice_people') or {}).values()):
            if len(_DISABLED_OPT_IN_UNTIL) >= _CONTACT_HANDLE_LIMIT:
                _DISABLED_OPT_IN_UNTIL.pop(next(iter(_DISABLED_OPT_IN_UNTIL)), None)
            _DISABLED_OPT_IN_UNTIL[uid] = time.monotonic() + _DISABLED_OPT_IN_TTL_SECONDS
        return data
    except Exception as exc:
        logger.debug('Could not read user_voice settings uid=%s err=%s', uid, type(exc).__name__)

    return {}


def _load_user_conversations_and_messages(
    uid: str,
    *,
    limit_conversations: int = 50,
    limit_messages: int = 50,
) -> Tuple[List[Any], List[Any], List[Any]]:
    """Fetch stored conversations, chat messages, and people for ``uid`` when not passed explicitly."""
    conversations: List[Any] = []
    messages: List[Any] = []
    people: List[Any] = []

    try:
        from database import conversations as conversations_db

        loaded_convs = conversations_db.get_conversations(
            uid=uid,
            limit=limit_conversations,
            statuses=['completed'],
            include_discarded=False,
        )
        conversations = list(loaded_convs or [])
    except Exception as exc:
        logger.debug('Could not load conversations for user_voice uid=%s err=%s', uid, type(exc).__name__)

    try:
        from database import chat as chat_db

        loaded_msgs = chat_db.get_messages(uid, limit=limit_messages)
        messages = list(loaded_msgs or [])
    except Exception as exc:
        logger.debug('Could not load chat messages for user_voice uid=%s err=%s', uid, type(exc).__name__)

    try:
        from database import users as users_db

        loaded_people = users_db.get_people(uid)
        people = list(loaded_people or [])
    except Exception as exc:
        logger.debug('Could not load people for user_voice uid=%s err=%s', uid, type(exc).__name__)

    return conversations, messages, people


def is_user_voice_enabled(
    uid: str,
    person_id: Optional[str] = None,
    *,
    user_settings: Optional[Mapping[str, Any]] = None,
    firestore_client: Any = None,
) -> bool:
    """Return whether user-voice drafting is opted in for ``uid`` (and optionally ``person_id``).

    Supports both account-level opt-in (``user_voice_enabled: bool``) and per-person
    overrides (``user_voice_people: {person_key: bool}``). Strictly defaults to False.
    """
    if isinstance(user_settings, Mapping):
        data: Dict[str, Any] = dict(user_settings)
    else:
        data = _load_user_voice_settings(uid, firestore_client=firestore_client)

    if person_id:
        per_person = data.get('user_voice_people')
        if isinstance(per_person, Mapping):
            if person_id in per_person and per_person[person_id] is not None:
                return bool(per_person[person_id])
            norm_key = _normalize_person_key(person_id)
            for k, v in per_person.items():
                if v is not None and _normalize_person_key(str(k)) == norm_key:
                    return bool(v)

    if 'user_voice_enabled' in data and data['user_voice_enabled'] is not None:
        return bool(data['user_voice_enabled'])

    return False


def _has_any_user_voice_opt_in(
    uid: str,
    *,
    user_settings: Optional[Mapping[str, Any]] = None,
    firestore_client: Any = None,
) -> bool:
    if isinstance(user_settings, Mapping):
        data: Dict[str, Any] = dict(user_settings)
    else:
        data = _load_user_voice_settings(uid, firestore_client=firestore_client)

    if bool(data.get('user_voice_enabled')):
        return True
    per_person = data.get('user_voice_people')
    if isinstance(per_person, Mapping):
        return any(bool(v) for v in per_person.values() if v is not None)
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
    _DISABLED_OPT_IN_UNTIL.pop(uid, None)

    if firestore_client is not None:
        try:
            update: Dict[str, Any] = (
                {f'user_voice_people.{person_id}': bool(enabled)}
                if person_id
                else {'user_voice_enabled': bool(enabled)}
            )
            col_fn = getattr(firestore_client, 'collection', None)
            if callable(col_fn):
                doc_ref = getattr(col_fn('users'), 'document')(uid)
                getattr(doc_ref, 'set')(update, merge=True)
        except Exception as exc:
            logger.warning('Could not persist user_voice opt-in uid=%s err=%s', uid, type(exc).__name__)


def _remember_contact_handle(uid: str, handle: str, name: str) -> None:
    key = (uid, _normalize_person_key(handle))
    if key not in _CONTACT_HANDLE_TO_PERSON and len(_CONTACT_HANDLE_TO_PERSON) >= _CONTACT_HANDLE_LIMIT:
        _CONTACT_HANDLE_TO_PERSON.pop(next(iter(_CONTACT_HANDLE_TO_PERSON)), None)
    _CONTACT_HANDLE_TO_PERSON[key] = name


def record_contact_handles_for_user_voice(uid: str, query: Optional[str], result: Any) -> None:
    """Record handle -> contact name mappings returned by ``search_contacts``."""
    if not isinstance(result, Mapping):
        return
    contacts = result.get('contacts')
    if not isinstance(contacts, list):
        return
    for contact in contacts:
        if not isinstance(contact, Mapping):
            continue
        name = contact.get('name') or contact.get('display_name') or query
        if not isinstance(name, str) or not name.strip():
            continue
        clean_name = name.strip()
        for field_name in ('phones', 'phone_numbers', 'emails', 'email_addresses', 'handles', 'to'):
            items = contact.get(field_name)
            if isinstance(items, list):
                for handle in items:
                    if isinstance(handle, str) and handle.strip():
                        _remember_contact_handle(uid, handle, clean_name)
        for single_field in ('phone', 'email', 'handle'):
            handle = contact.get(single_field)
            if isinstance(handle, str) and handle.strip():
                _remember_contact_handle(uid, handle, clean_name)


def clear_user_voice_state_for_tests() -> None:
    """Clear in-memory caches and opt-in overrides used in unit tests."""
    _MEMORY_CACHE.clear()
    _MEMORY_OPT_IN.clear()
    _CONTACT_HANDLE_TO_PERSON.clear()
    _DISABLED_OPT_IN_UNTIL.clear()


def cache_user_voice_profile(
    uid: str,
    person_key: str,
    profile: UserVoiceProfile,
    *,
    ttl_seconds: int = USER_VOICE_CACHE_TTL_SECONDS,
    now_fn: Callable[[], float] = time.time,
) -> None:
    keys = {person_key}
    for alias in (profile.person_id, profile.person_name, profile.recipient):
        if alias and str(alias).strip():
            keys.add(str(alias).strip())

    payload = profile.model_dump_json()
    expires_at = now_fn() + ttl_seconds
    for raw_key in keys:
        if not raw_key:
            continue
        key = user_voice_cache_key(uid, raw_key)
        _MEMORY_CACHE[key] = (expires_at, payload)
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
    """Return True when ``conv`` explicitly involves the target person as a participant/recipient."""
    if not person_id and not person_name and not recipient:
        return False

    target_id = person_id.strip() if isinstance(person_id, str) and person_id.strip() else None
    target_name = person_name.strip().lower() if isinstance(person_name, str) and person_name.strip() else None
    target_recipient = recipient.strip().lower() if isinstance(recipient, str) and recipient.strip() else None

    if target_id:
        conv_person_ids = _get_field(conv, 'person_ids') or _get_field(conv, 'participant_person_ids') or []
        if isinstance(conv_person_ids, (list, tuple, set)) and target_id in conv_person_ids:
            return True
        if _get_field(conv, 'person_id') == target_id:
            return True

    ext = _get_field(conv, 'external_data')
    if isinstance(ext, Mapping):
        if target_id and ext.get('person_id') == target_id:
            return True
        if target_name:
            ext_pname = ext.get('person_name') or ext.get('contact_name')
            if isinstance(ext_pname, str) and target_name == ext_pname.strip().lower():
                return True
        if target_recipient:
            for k in ('recipient', 'to', 'contact', 'handle', 'phone', 'email'):
                v = ext.get(k)
                if isinstance(v, str) and target_recipient == v.strip().lower():
                    return True
                if isinstance(v, (list, tuple, set)):
                    if any(isinstance(item, str) and target_recipient == item.strip().lower() for item in v):
                        return True

    if target_recipient:
        conv_recipients = _get_field(conv, 'recipients') or _get_field(conv, 'participants') or []
        if isinstance(conv_recipients, (list, tuple, set)):
            for item in conv_recipients:
                if isinstance(item, str) and target_recipient == item.strip().lower():
                    return True
                if isinstance(item, Mapping):
                    for field_name in ('handle', 'phone', 'email', 'name', 'id'):
                        val = item.get(field_name)
                        if isinstance(val, str) and target_recipient == val.strip().lower():
                            return True
        conv_rec = _get_field(conv, 'recipient')
        if isinstance(conv_rec, str) and target_recipient == conv_rec.strip().lower():
            return True

    segments = _get_field(conv, 'transcript_segments') or []
    for seg in segments:
        if target_id and (
            _get_field(seg, 'person_id') == target_id or _get_field(seg, 'speaker_person_id') == target_id
        ):
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

    for msg in messages or ():
        if isinstance(msg, str):
            text = msg.strip()
            if text:
                general.append(text)
            continue

        if _is_locked_record(msg):
            continue

        sender = _get_field(msg, 'sender') or _get_field(msg, 'role')
        sender_val = str(getattr(sender, 'value', sender) or '').strip().lower()
        is_user_msg = _get_field(msg, 'is_user') is True or sender_val in ('human', 'user', 'me')
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

        if is_match:
            matched.append(clean_text)

    return matched, general


def _infer_target_person_from_context(
    *,
    conversations: Sequence[Any] = (),
    messages: Sequence[Any] = (),
    people: Sequence[Any] = (),
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Infer ``(person_id, person_name, recipient)`` for the current turn from user messages & known people."""
    known_candidates: List[Tuple[Optional[str], str, Optional[str]]] = []
    seen_names = set()

    for p in people or ():
        pid = _get_field(p, 'id')
        pname = _get_field(p, 'name')
        if isinstance(pname, str) and pname.strip():
            norm = pname.strip().lower()
            if norm not in seen_names:
                seen_names.add(norm)
                known_candidates.append((str(pid) if pid else None, pname.strip(), None))
        aliases = _get_field(p, 'aliases') or []
        if isinstance(aliases, (list, tuple, set)):
            for alias in aliases:
                if isinstance(alias, str) and alias.strip():
                    norm = alias.strip().lower()
                    if norm not in seen_names:
                        seen_names.add(norm)
                        known_candidates.append((str(pid) if pid else None, alias.strip(), None))

    for conv in conversations or ():
        if _is_locked_record(conv):
            continue
        conv_pids = _get_field(conv, 'person_ids') or []
        first_pid = (
            str(conv_pids[0]) if isinstance(conv_pids, list) and len(conv_pids) == 1 else _get_field(conv, 'person_id')
        )
        participants = _get_field(conv, 'participants') or _get_field(conv, 'people') or []
        for part in participants:
            if isinstance(part, str) and part.strip():
                norm = part.strip().lower()
                if norm not in seen_names:
                    seen_names.add(norm)
                    known_candidates.append((str(first_pid) if first_pid else None, part.strip(), None))
            elif isinstance(part, Mapping):
                pname = part.get('name')
                pid = part.get('id') or first_pid
                prec = part.get('handle') or part.get('phone') or part.get('email')
                if isinstance(pname, str) and pname.strip():
                    norm = pname.strip().lower()
                    if norm not in seen_names:
                        seen_names.add(norm)
                        known_candidates.append((str(pid) if pid else None, pname.strip(), str(prec) if prec else None))
        for seg in _get_field(conv, 'transcript_segments') or ():
            if _get_field(seg, 'is_user') is True:
                continue
            seg_pid = _get_field(seg, 'person_id') or first_pid
            for field_name in ('person_name', 'speaker_name'):
                val = _get_field(seg, field_name)
                if isinstance(val, str) and val.strip():
                    norm = val.strip().lower()
                    if norm not in seen_names:
                        seen_names.add(norm)
                        known_candidates.append((str(seg_pid) if seg_pid else None, val.strip(), None))

    recent_user_texts: List[str] = []
    for msg in reversed(list(messages or ())):
        if isinstance(msg, str):
            if msg.strip():
                recent_user_texts.append(msg.strip())
            continue
        sender = _get_field(msg, 'sender') or _get_field(msg, 'role')
        sender_val = str(getattr(sender, 'value', sender) or '').strip().lower()
        if _get_field(msg, 'is_user') is True or sender_val in ('human', 'user', 'me'):
            msg_pid = _get_field(msg, 'person_id')
            msg_pname = _get_field(msg, 'person_name')
            msg_rec = _get_field(msg, 'recipient') or _get_field(msg, 'to')
            if isinstance(msg_rec, list):
                msg_rec = msg_rec[0] if msg_rec else None
            if msg_pid or msg_pname or msg_rec:
                return (
                    str(msg_pid) if msg_pid else None,
                    str(msg_pname) if msg_pname else None,
                    str(msg_rec) if msg_rec else None,
                )
            text = _get_field(msg, 'text') or _get_field(msg, 'content')
            if isinstance(text, str) and text.strip():
                recent_user_texts.append(text.strip())

    # Match longest candidate name first so "Dr. Chen" wins over "Chen".
    sorted_candidates = sorted(known_candidates, key=lambda item: len(item[1]), reverse=True)
    for text in recent_user_texts:
        for pid, pname, prec in sorted_candidates:
            pat = re.compile(r'(?<!\w)' + re.escape(pname) + r'(?!\w)', re.IGNORECASE)
            if pat.search(text):
                return pid, pname, prec

    for text in recent_user_texts:
        m = _MESSAGE_INTENT_TARGET_RE.search(text)
        if m:
            extracted_name = m.group(1).strip()
            for pid, pname, prec in sorted_candidates:
                if pname.lower() == extracted_name.lower():
                    return pid, pname, prec
            return None, extracted_name, None

    if len(known_candidates) == 1:
        return known_candidates[0]

    return None, None, None


def _classify_line_ending(line: str) -> EndingStyle:
    stripped = line.rstrip()
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
            elif 0x4E00 <= cp <= 0x9FFF or 0x3040 <= cp <= 0x30FF or 0xAC00 <= cp <= 0xD7AF or 0x3400 <= cp <= 0x4DBF:
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
    elif not person_id and not person_name and not recipient:
        lines = list(general_msg_lines)
    else:
        # When targeting a specific person and no conversations matched, fall back to
        # string messages only when raw string history was passed directly.
        raw_string_lines = [m.strip() for m in (messages or ()) if isinstance(m, str) and m.strip()]
        lines = raw_string_lines

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
    target_opt_in_key = person_id or person_name or recipient
    if not is_user_voice_enabled(
        uid,
        person_id=target_opt_in_key,
        user_settings=user_settings,
        firestore_client=firestore_client,
    ):
        return None

    for candidate_key in (person_id, recipient, person_name):
        if candidate_key and str(candidate_key).strip():
            cached = get_cached_user_voice_profile(uid, str(candidate_key), now_fn=now_fn)
            if cached is not None:
                return cached

    if conversations is None:
        loaded_convs, loaded_msgs, loaded_people = _load_user_conversations_and_messages(uid)
        conversations = loaded_convs
        if messages is None:
            messages = loaded_msgs
        if not person_id and not person_name and not recipient:
            person_id, person_name, recipient = _infer_target_person_from_context(
                conversations=conversations,
                messages=messages or (),
                people=loaded_people,
            )

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
    if not text or not text.strip() or profile is None or profile.sample_count <= 0:
        return text

    out = text.strip()

    # 1. Strip AI-style em-dashes when the user doesn't use them in examples.
    if '—' in out and not any('—' in ex for ex in profile.examples):
        if profile.dominant_ending == 'none':
            out = re.sub(r'\s*—\s*', ' ', out)
        else:
            out = re.sub(r'\s*—\s*', ', ', out)

    # 2. Strip emojis if the user never uses emojis with this person.
    if profile.emoji_rate == 0.0 and _EMOJI_RE.search(out):
        out = _EMOJI_RE.sub('', out)
        out = re.sub(r' {2,}', ' ', out).strip()

    # 3. Enforce exclamation mark ceiling ("!" count).
    max_excl = max(0, profile.max_exclamations_per_line)
    if max_excl <= 1:
        out = re.sub(r'!{2,}', '!', out)

    if max_excl == 0:
        # Handle greeting + "!" (e.g. "Hey! Running 5 mins late!") without leaving an unnatural "hey."
        def _replace_greeting_excl(match: re.Match[str]) -> str:
            greeting = match.group(1)
            next_char = match.group(2)
            if profile.dominant_ending == 'none':
                if profile.lowercase_start_rate >= 0.7 and next_char.isupper():
                    next_char = next_char.lower()
                return f'{greeting} {next_char}'
            return f'{greeting}, {next_char}'

        out = _GREETING_EXCLAMATION_PREFIX_RE.sub(_replace_greeting_excl, out, count=1)

        if profile.dominant_ending == 'none':
            # Remove terminal "!" and replace any remaining internal "!" with a comma.
            out = re.sub(r'!+\s*$', '', out)
            out = re.sub(r'!(?=\s)', ',', out)
            out = out.replace('!', '')
        else:
            out = re.sub(r'!(?=\s|$)', '.', out)
    else:
        excl_positions = [m.start() for m in re.finditer(r'!', out)]
        if len(excl_positions) > max_excl:
            drop_set = set(excl_positions[:-max_excl])
            replacement_char = ',' if profile.dominant_ending == 'none' else '.'
            chars = list(out)
            for idx in drop_set:
                chars[idx] = replacement_char
            out = ''.join(chars)

    # 4. Enforce ending punctuation style (period, nothing, "!").
    if profile.dominant_ending == 'none':
        if (out.endswith('.') or out.endswith(',')) and not out.endswith('...'):
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
            person_tokens = {tok.lower() for tok in re.findall(r'[A-Za-z]+', profile.person_name or '') if tok}
            if first_word != 'I' and not first_word.isupper() and first_word.lower() not in person_tokens:
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
    firestore_client: Any = None,
) -> str:
    """Resolve the recipient's cached/built voice profile and polish ``text`` in-place."""
    if not text:
        return text

    recipient = to[0].strip() if isinstance(to, (list, tuple)) and to and to[0] else None
    if not person_name and recipient:
        mapped_name = _CONTACT_HANDLE_TO_PERSON.get((uid, _normalize_person_key(recipient)))
        if mapped_name:
            person_name = mapped_name

    if not _has_any_user_voice_opt_in(uid, user_settings=user_settings, firestore_client=firestore_client):
        return text

    profile = get_or_build_user_voice_profile(
        uid,
        person_id=person_id,
        person_name=person_name,
        recipient=recipient,
        conversations=conversations,
        messages=messages,
        user_settings=user_settings,
        firestore_client=firestore_client,
    )
    if profile is None or profile.sample_count <= 0:
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
    firestore_client: Any = None,
) -> str:
    """Return the ``<user_voice_profile>`` prompt block for ``propose_message`` when opted in."""
    if not _has_any_user_voice_opt_in(uid, user_settings=user_settings, firestore_client=firestore_client):
        return ''

    loaded_people: List[Any] = []
    if conversations is None:
        conversations, loaded_msgs, loaded_people = _load_user_conversations_and_messages(uid)
        if messages is None:
            messages = loaded_msgs

    if not person_id and not person_name and not recipient:
        person_id, person_name, recipient = _infer_target_person_from_context(
            conversations=conversations or (),
            messages=messages or (),
            people=loaded_people,
        )

    profile = get_or_build_user_voice_profile(
        uid,
        person_id=person_id,
        person_name=person_name,
        recipient=recipient,
        conversations=conversations,
        messages=messages,
        user_settings=user_settings,
        firestore_client=firestore_client,
    )
    return format_user_voice_prompt(profile)
