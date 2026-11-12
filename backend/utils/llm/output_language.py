"""One output-language preference for every artifact derived from a conversation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Mapping, Optional

from config.episodes import episode_output_language_pinned
from utils.translation_language import detect_language

from utils.user_language import normalize_user_language

# Sentinel codes that name no single language; they must never reach a prompt
# ("Write all output in multi"). Capture tags and preferences can both carry them.
NON_LANGUAGE_CODES = frozenset({'multi', 'auto', 'unknown', 'none', 'und'})
_SAFE_LANGUAGE_TAG = re.compile(r'[a-z]{2,3}(?:-(?:[a-z]{4}|[a-z]{2}|[0-9]{3}))?')


def normalize_language(value: str | None) -> str:
    """Return a supported BCP-47 language token, or ``''`` for unsafe/unknown values."""
    raw = str(value or '').strip()
    if not raw or raw.lower() in NON_LANGUAGE_CODES:
        return ''
    normalized = normalize_user_language(raw)
    code = normalized.lower() if normalized else ''
    if not code or code in NON_LANGUAGE_CODES or not _SAFE_LANGUAGE_TAG.fullmatch(code):
        return ''
    return code


def language_preference(uid: str) -> str:
    """The user's explicit preference, normalized; '' when unset, unreadable or a sentinel."""
    from database import users as users_db

    try:
        return normalize_language(users_db.get_user_language_preference(uid) if uid else None)
    except Exception:
        return ''  # A preference-read outage uses the guarded capture fallback, never fails the artifact.


def capture_output_language(conversation_language: str | None, segments=None, *, preference: str = '') -> str:
    """Explicit preference; otherwise a non-English capture needs transcript agreement."""
    preferred = normalize_language(preference)
    if preferred:
        return preferred
    capture = normalize_language(conversation_language)
    if not episode_output_language_pinned() or segments is None:
        return capture or 'en'
    if capture and capture.split('-', 1)[0] != 'en':
        return capture if languages_match(capture, dominant_segment_language(segments)) else 'en'
    return capture or 'en'


def resolve_output_language(uid: str, conversation_language: str | None, segments=None) -> str:
    return capture_output_language(conversation_language, segments, preference=language_preference(uid))


# Detection stays local and ignores short untagged speech.
_MIN_STATE_DETECT_CHARS = 20
_SEGMENT_LANGUAGE_FIELDS = ('language', 'language_code', 'language_tag', 'detected_language', '_provider_language')


def languages_match(left: Optional[str], right: Optional[str]) -> bool:
    """Compare safe language tags at the base-language precision of local detection."""
    a, b = normalize_language(left), normalize_language(right)
    return bool(a and b and (a == b or a.split('-', 1)[0] == b.split('-', 1)[0]))


def dominant_segment_language(segments: Any) -> str:
    """Choose the character-weighted dominant language from an in-memory segment batch.

    Prefer an existing per-segment language tag. When the stream did not retain one,
    detect only sufficiently long segments locally; no provider call or database read
    is made. Short/noisy text is deliberately left unknown.
    """
    weights: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for segment in segments or ():
        field = segment.get if isinstance(segment, Mapping) else lambda key: getattr(segment, key, None)
        text = str(field('text') or '')
        letters = sum(char.isalpha() for char in text)
        language = ''
        for key in _SEGMENT_LANGUAGE_FIELDS:
            language = normalize_language(field(key))
            if language:
                break
        if not language and letters >= _MIN_STATE_DETECT_CHARS:
            language = normalize_language(detect_language(text, hint_language='en'))
        if language:
            first_seen.setdefault(language, len(first_seen))
            weights[language] += max(letters, 1)
    if not weights:
        return ''
    return max(weights, key=lambda language: (weights[language], -first_seen[language]))
