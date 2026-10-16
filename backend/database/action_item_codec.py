"""Shared task row normalization for ordinary writes and conditional inverses."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def prepare_action_item_for_write(action_item_data: Dict[str, Any], *, partial: bool = False) -> Dict[str, Any]:
    """Prepare action item data for writing to database"""
    action_item_data = dict(action_item_data)
    if not partial or 'status' in action_item_data or 'completed' in action_item_data:
        status = action_item_data.get('status')
        completed = action_item_data.get('completed')
        if isinstance(status, str):
            status = status.strip() or None
            action_item_data['status'] = status
        if status is None:
            status = 'completed' if completed is True else 'active'
            action_item_data['status'] = status
        if completed is None:
            action_item_data['completed'] = status == 'completed'
        elif completed != (status == 'completed'):
            raise ValueError('completed must agree with canonical status')
    if not partial:
        action_item_data.setdefault('owner', 'unknown')
        action_item_data.setdefault('source', 'legacy')
        if not isinstance(action_item_data.get('provenance'), list):
            action_item_data['provenance'] = []
        action_item_data.setdefault('provenance', [])
        action_item_data.setdefault('sort_order', 0)
        action_item_data.setdefault('indent_level', 0)
    else:
        for field in ('description', 'owner', 'source', 'provenance', 'sort_order', 'indent_level', 'exported'):
            if field in action_item_data and action_item_data.get(field) is None:
                action_item_data.pop(field)
    # Normalize date fields to timezone-aware UTC datetimes. These can arrive as
    # ISO strings or datetime objects from tool-/LLM-created action items (extraction
    # models use plain ``datetime``, not ``AwareDatetime``). Firestore rejects
    # tz-naive datetimes, and a failed batch create on the fire-and-forget
    # postprocess path silently drops extracted tasks. Mirror
    # ``api_key_metadata._coerce_utc_datetime`` / ``mcp_action_items.parse_due_at``:
    # parse strings tolerantly, attach UTC to naive values, drop only malformed
    # / out-of-range values (ValueError or OverflowError from UTC normalization)
    # so a single bad field cannot 500 the whole create/update or batch.
    for date_field in ('created_at', 'updated_at', 'due_at', 'completed_at'):
        value = action_item_data.get(date_field)
        if value is None or value == '':
            if date_field in action_item_data and value == '':
                action_item_data.pop(date_field, None)
            continue
        try:
            if isinstance(value, datetime):
                parsed = value
            elif isinstance(value, str):
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            else:
                logger.warning(
                    "Dropping non-datetime %s type=%s on action item write",
                    date_field,
                    type(value).__name__,
                )
                action_item_data.pop(date_field, None)
                continue

            # OverflowError: boundary aware values whose offset conversion leaves
            # Python's datetime range (same tolerance as api_key_metadata).
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            logger.warning("Dropping malformed %s=%r on action item write", date_field, value)
            action_item_data.pop(date_field, None)
            continue
        action_item_data[date_field] = parsed

    return action_item_data


def prepare_action_item_for_read(action_item_data: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare action item data for reading from database"""
    # Never mutate the caller's dict — a read must be side-effect free.
    action_item_data = dict(action_item_data)
    # `completed` may be missing OR explicitly null (legacy/partial writes). setdefault
    # won't overwrite an existing null, so drop it first and let status derive a concrete
    # bool — strict client parsers reject a null `completed` and drop the whole page.
    if action_item_data.get('completed') is None:
        action_item_data.pop('completed', None)
    action_item_data.setdefault('status', 'completed' if action_item_data.get('completed') else 'active')
    action_item_data.setdefault('completed', action_item_data['status'] == 'completed')
    action_item_data.setdefault('owner', 'unknown')
    action_item_data.setdefault('source', 'legacy')
    if not isinstance(action_item_data.get('provenance'), list):
        action_item_data['provenance'] = []
    action_item_data.setdefault('sort_order', 0)
    action_item_data.setdefault('indent_level', 0)
    # Normalize every date shape the store can return — ISO strings, Firestore
    # timestamps (``to_datetime``), epoch seconds, and datetimes — to aware UTC.
    # Any failure must degrade to the stored value, never a 500 on read.
    for field in ['created_at', 'updated_at', 'due_at', 'completed_at']:
        if field in action_item_data and action_item_data[field]:
            try:
                value = action_item_data[field]
                parsed = None
                if isinstance(value, datetime):
                    parsed = value
                elif isinstance(value, str):
                    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                elif hasattr(value, 'to_datetime'):
                    parsed = value.to_datetime()
                elif hasattr(value, 'timestamp'):
                    parsed = datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
                if isinstance(parsed, datetime):
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    else:
                        parsed = parsed.astimezone(timezone.utc)
                    action_item_data[field] = parsed
            except (OverflowError, ValueError, OSError, TypeError):
                logger.warning("Leaving unparseable %s on action item read", field)
    return action_item_data
