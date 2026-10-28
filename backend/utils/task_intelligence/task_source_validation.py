"""Validate task conversation links only inside the authenticated account."""

from collections.abc import Mapping, Sequence
from typing import Any

from config.refactor_modes import default_on
from database import conversations as conversations_db

SOURCE_LINKS_ENABLED_ENV = 'ACTION_ITEM_SOURCE_LINKS_ENABLED'


class TaskSourceValidationError(ValueError):
    """A supplied source is unavailable to this account (including deleted rows)."""


def validate_task_sources(uid: str, items: Sequence[Mapping[str, Any]]) -> None:
    if not default_on(SOURCE_LINKS_ENABLED_ENV):
        return
    checked: set[str] = set()
    for item in items:
        sources = [item.get('conversation_id')]
        sources.extend(ref.get('id') for ref in item.get('provenance', ()) if ref.get('kind') == 'conversation')
        for source in sources:
            if source is None:
                continue  # Explicit standalone tasks have no conversation source.
            if not isinstance(source, str) or not source.strip() or '/' in source:
                raise TaskSourceValidationError('Task source conversation is unavailable.')
            if source in checked:
                continue
            # Never search another account to distinguish foreign from missing.
            row = conversations_db.get_conversation(uid, source)
            if not row or row.get('deleted'):
                raise TaskSourceValidationError('Task source conversation is unavailable.')
            checked.add(source)
