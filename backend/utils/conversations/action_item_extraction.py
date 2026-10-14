"""Apply extraction guards before either replacement, refresh or candidate capture."""

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from config.action_item_extraction_policy import (
    UNKNOWN_OWNERS,
    OWNER_ALIASES,
    clearly_other_owner,
    clearly_status,
    normalized_name,
)
from database.auth import get_user_full_name
from utils.metrics import OMI_ACTION_ITEM_EXTRACTION_DROPPED_TOTAL

logger = logging.getLogger(__name__)


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)


def filter_extracted_items(uid: str, items: Sequence[Any]) -> list[Any]:
    named = any(normalized_name(_field(item, 'owner_name')) not in UNKNOWN_OWNERS | OWNER_ALIASES for item in items)
    profile_name = get_user_full_name(uid) if named else None
    kept = []
    counts = {'other_owner': 0, 'status_statement': 0}
    for item in items:
        if clearly_other_owner(_field(item, 'owner_name'), profile_name):
            counts['other_owner'] += 1
        elif clearly_status(_field(item, 'description')):
            counts['status_statement'] += 1
        else:
            kept.append(item)
    for reason, count in counts.items():
        if count:
            OMI_ACTION_ITEM_EXTRACTION_DROPPED_TOTAL.labels(reason=reason).inc(count)
            logger.info('event=action_item_extraction_dropped reason=%s count=%d', reason, count)
    return kept


def action_items_for_write(
    uid: str, conversation: Any, now: datetime, canonical_fields: Callable[[Any, Any], dict[str, Any]]
) -> list[dict[str, Any]]:
    """Project only admitted extraction items to the shared initial/refresh write payload."""
    return [
        {
            'description': action_item.description,
            'completed': action_item.completed,
            'created_at': action_item.created_at or now,
            'updated_at': action_item.updated_at or now,
            'due_at': action_item.due_at,
            'completed_at': action_item.completed_at,
            'conversation_id': conversation.id,
            'is_locked': conversation.is_locked,
            **canonical_fields(action_item, conversation),
        }
        for action_item in filter_extracted_items(uid, conversation.structured.action_items)
    ]
