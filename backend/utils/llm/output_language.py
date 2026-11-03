"""One output-language preference for every artifact derived from a conversation."""

from __future__ import annotations

import re

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
    if capture and capture.split('-', 1)[0] != 'en':
        from utils.episodes.output_language import dominant_segment_language, languages_match

        return capture if languages_match(capture, dominant_segment_language(segments)) else 'en'
    return capture or 'en'


def resolve_output_language(uid: str, conversation_language: str | None, segments=None) -> str:
    return capture_output_language(conversation_language, segments, preference=language_preference(uid))
