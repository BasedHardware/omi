"""``get_deleted_conversations``: what the user deleted, so agents can drop their copies.

Conversations have no truthful ``updated_since`` feed (their ``updated_at`` is
document metadata, not a stored revision), but deletions do: each one leaves a
durable, content-free tombstone with ``deleted_at``. Agents that keep a copy of
the user's conversations page this feed from their last watermark and remove
every listed id.

Two limits, stated in the tool description and ``docs/mcp-rest-sync.md``:
``deleted_at`` is stamped when the delete is requested, so a tombstone can commit
a moment after a later one was already served (resume from the watermark minus a
minute and dedupe by id); and conversations absorbed by a merge leave no
tombstone (the merged conversation is new; reconcile held ids with
``get_conversations_by_ids``, whose ``not_found`` lists ids that are gone).
"""

from typing import Any, Dict, List, Optional, Tuple

from google.api_core.exceptions import FailedPrecondition

from database import conversation_deletion_feed
from utils.mcp_memories import parse_mcp_int, parse_sync_timestamp
from utils.mcp_server.cursors import decode_cursor, encode_cursor, serialize_timestamp, timestamp_keyset_position
from utils.mcp_server.errors import ToolExecutionError, raise_conversation_index_error
from utils.memory.product_authorization import ProductAuthorizationContext

DELETIONS_DEFAULT_LIMIT = 100
DELETIONS_MAX_LIMIT = 500

DELETED_CONVERSATIONS_INPUT: Dict[str, Any] = {
    'type': 'object',
    'properties': {
        'deleted_since': {'type': 'string', 'description': 'ISO 8601 with a timezone offset, inclusive'},
        'limit': {
            'type': 'integer',
            'default': DELETIONS_DEFAULT_LIMIT,
            'minimum': 1,
            'maximum': DELETIONS_MAX_LIMIT,
        },
        'cursor': {'type': 'string', 'description': 'next_cursor from the previous call with the same deleted_since'},
    },
}
DELETED_CONVERSATIONS_OUTPUT: Dict[str, Any] = {
    'deleted': {
        'type': 'array',
        'items': {
            'type': 'object',
            'required': ['id', 'deleted_at'],
            'properties': {
                'id': {'type': 'string'},
                'deleted_at': {'type': 'string', 'format': 'date-time'},
            },
        },
    },
    'has_more': {'type': 'boolean'},
    'next_cursor': {'type': ['string', 'null']},
}


def deleted_conversations_page_core(
    uid: str,
    *,
    deleted_since: Any,
    limit: int,
    cursor_token: Optional[str],
    cursor_kind: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Shared by the MCP tool and ``GET /v1/mcp/conversations/deleted``."""
    filters = {'deleted_since': deleted_since.isoformat() if deleted_since is not None else None}
    after = None
    if cursor_token is not None:
        after = timestamp_keyset_position(decode_cursor(cursor_token, kind=cursor_kind, uid=uid, filters=filters))
    try:
        rows, resume = conversation_deletion_feed.get_deleted_conversations_page(
            uid, deleted_since=deleted_since, after=after, limit=limit
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc), code=-32602) from exc
    except FailedPrecondition as exc:
        raise_conversation_index_error(exc)
    next_cursor = (
        encode_cursor(
            kind=cursor_kind,
            uid=uid,
            position={'ts': serialize_timestamp(resume[0]), 'id': resume[1]},
            filters=filters,
        )
        if resume is not None
        else None
    )
    return rows, next_cursor


def get_deleted_conversations(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    try:
        deleted_since = parse_sync_timestamp(arguments.get('deleted_since'), 'deleted_since')
        limit = parse_mcp_int(
            arguments.get('limit'), 'limit', default=DELETIONS_DEFAULT_LIMIT, minimum=1, maximum=DELETIONS_MAX_LIMIT
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc), code=-32602) from exc
    rows, next_cursor = deleted_conversations_page_core(
        uid,
        deleted_since=deleted_since,
        limit=limit,
        cursor_token=arguments.get('cursor'),
        cursor_kind='get_deleted_conversations',
    )
    return {'deleted': rows, 'has_more': next_cursor is not None, 'next_cursor': next_cursor}
