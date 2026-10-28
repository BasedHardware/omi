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
        return ''  # A preference-read outage falls through to the capture language, never fails the artifact.


def resolve_output_language(uid: str, conversation_language: str | None) -> str:
    """Explicit user preference, then capture language, then English. Never infer from noise."""
    return language_preference(uid) or normalize_language(conversation_language) or 'en'
