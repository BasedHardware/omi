"""One output-language preference for every artifact derived from a conversation."""

from __future__ import annotations

from database import users as users_db


def resolve_output_language(uid: str, conversation_language: str | None) -> str:
    """Explicit user preference, then capture language, then English. Never infer from noise."""
    preference = users_db.get_user_language_preference(uid) if uid else None
    return (preference or '').strip() or (conversation_language or '').strip() or 'en'
