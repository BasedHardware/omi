"""One output-language preference for every artifact derived from a conversation."""

from __future__ import annotations

# Sentinel codes that name no single language; they must never reach a prompt
# ("Write all output in multi"). Capture tags and preferences can both carry them.
NON_LANGUAGE_CODES = frozenset({'multi', 'auto', 'unknown', 'none'})


def normalize_language(value: str | None) -> str:
    """A single lowercase code, or '' for blank and sentinel values such as ``multi``."""
    code = str(value or '').strip().lower()
    return code if code and code not in NON_LANGUAGE_CODES else ''


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
