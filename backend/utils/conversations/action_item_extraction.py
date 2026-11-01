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
from utils.conversations.action_item_validity import select_valid_items

logger = logging.getLogger(__name__)


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)


def filter_extracted_items(uid: str, items: Sequence[Any], *, conversation: Any = None) -> list[Any]:
    named = any(normalized_name(_field(item, 'owner_name')) not in UNKNOWN_OWNERS | OWNER_ALIASES for item in items)
    profile_name = get_user_full_name(uid) if named else None
    # refactor: superseded by utils.llm.action_item_v2 when ACTION_ITEMS_V2_MODE=serve
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
    from utils.llm.action_item_v2 import select_items

    segments = getattr(conversation, 'transcript_segments', ()) or ()
    return select_valid_items(uid, select_items(uid, items, kept, profile_name), transcript_segments=segments)


def action_items_for_write(
    uid: str, conversation: Any, now: datetime, canonical_fields: Callable[[Any, Any], dict[str, Any]]
) -> list[dict[str, Any]]:
    """Project only admitted extraction items to the shared initial/refresh write payload."""
    from utils.conversations.media_consumers import is_excluded

    if not conversation.id:
        raise ValueError('extracted action items require conversation provenance')
    if is_excluded(uid, conversation, consumer='action_items'):
        return []
    return [
        {
            'description': action_item.description,
            'completed': action_item.completed,
            'created_at': action_item.created_at or now,
            'updated_at': action_item.updated_at or now,
            'due_at': action_item.due_at,
            'completed_at': action_item.completed_at,
            'is_locked': conversation.is_locked,
            **canonical_fields(action_item, conversation),
            'conversation_id': conversation.id,
        }
        for action_item in filter_extracted_items(uid, conversation.structured.action_items, conversation=conversation)
    ]
