"""Transcript-free conversation card reads for the hosted MCP surfaces.

Kept out of ``database/conversations.py`` (line-count ratchet): both the
legacy offset read and the ``(created_at DESC, __name__ DESC)`` keyset page
live here. The optional ``extra_field_paths`` widens the projection for the
REST surface (``apps_results``) without inflating the hosted tool reads.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import get_firestore_client
from .conversations import (
    MCP_CONVERSATION_CARD_FIELD_PATHS,
    document_data_with_revision,
    prepare_conversation_for_read,
    conversations_collection,
    is_soft_deleted,
)
from .firestore_index_registry import MCP_CONVERSATION_CARD_QUERY_SPECS
from .helpers import prepare_for_read

logger = logging.getLogger(__name__)

# Upper bound on raw documents a single keyset page may scan while skipping
# soft-deleted tombstones between visible rows.
MCP_CARD_PAGE_SCAN_BUDGET = 500
MCP_CARD_PAGE_MAX_LIMIT = 1000
MCP_CARD_PAGE_MAX_OFFSET = 100000


def _validate_uid(uid: object) -> str:
    """Validate user ID format and reject empty, non-string, or path traversal values."""
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError('Invalid user identifier: uid must be a non-empty string')
    cleaned = uid.strip()
    if '/' in cleaned or '\\' in cleaned or '..' in cleaned:
        raise ValueError('Invalid user identifier: path traversal characters are forbidden')
    return cleaned


def _clamp_limit(limit: int, default: int = 25, max_val: int = MCP_CARD_PAGE_MAX_LIMIT) -> int:
    try:
        val = int(limit)
        return max(1, min(val, max_val))
    except (ValueError, TypeError):
        return default


def _clamp_offset(offset: int, default: int = 0, max_val: int = MCP_CARD_PAGE_MAX_OFFSET) -> int:
    try:
        val = int(offset)
        return max(0, min(val, max_val))
    except (ValueError, TypeError):
        return default


def _normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _clean_categories(categories: Optional[List[str]]) -> Optional[List[str]]:
    if not categories:
        return None
    valid = [c.strip() for c in categories if isinstance(c, str) and c.strip()]
    return valid if valid else None


def _card_field_paths(extra_field_paths: Optional[Sequence[str]]) -> List[str]:
    paths: List[str] = list(MCP_CONVERSATION_CARD_FIELD_PATHS)
    if extra_field_paths:
        paths.extend(extra_field_paths)
    return paths


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
def get_mcp_conversation_cards(
    uid: str,
    limit: int,
    offset: int,
    *,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
    firestore_client: Any = None,
    extra_field_paths: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Return the transcript-free Firestore projection used by hosted MCP lists."""
    valid_uid = _validate_uid(uid)
    safe_limit = _clamp_limit(limit)
    safe_offset = _clamp_offset(offset)
    norm_start = _normalize_datetime(start_date)
    norm_end = _normalize_datetime(end_date)
    if norm_start is not None and norm_end is not None and norm_start > norm_end:
        return []

    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(valid_uid).collection(conversations_collection)
    valid_categories = _clean_categories(categories)
    query_spec = MCP_CONVERSATION_CARD_QUERY_SPECS[
        (bool(valid_categories), norm_start is not None, norm_end is not None)
    ]
    query = query_spec.build(
        collection,
        {
            'discarded': False,
            'status': 'completed',
            'categories': valid_categories,
            'start_date': norm_start,
            'end_date': norm_end,
        },
        field_filter_factory=FieldFilter,
    )
    query = (
        query.order_by('created_at', direction=firestore.Query.DESCENDING)
        .select(_card_field_paths(extra_field_paths))
        .limit(safe_limit)
        .offset(safe_offset)
    )
    conversations: List[Dict[str, Any]] = []
    try:
        for doc in query.stream():
            conversation = document_data_with_revision(doc)
            if conversation is None:
                continue
            if is_soft_deleted(conversation):
                continue
            conversation.setdefault('id', doc.id)
            conversations.append(conversation)
    except Exception:
        logger.exception('Failed streaming conversation cards for uid=%s', valid_uid)
    return conversations


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
def get_mcp_conversation_cards_page(
    uid: str,
    limit: int,
    *,
    after: Optional[Tuple[Any, str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
    firestore_client: Any = None,
    extra_field_paths: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[Tuple[Any, str]]]:
    """Keyset page ordered ``(created_at DESC, __name__ DESC)`` for MCP lists.

    Tombstones are dropped in Python, so the query walks raw windows until
    ``limit + 1`` visible rows, stream exhaustion, or the scan budget.
    ``after`` is the ``(created_at, doc id)`` position returned for the prior
    page. The second return value is the resume position for the next page —
    the last emitted row when a visible lookahead row exists (the lookahead
    itself must not be skipped), the last scanned row when the budget stopped
    the scan before the stream did, or ``None`` at the end of the stream.
    """
    valid_uid = _validate_uid(uid)
    safe_limit = _clamp_limit(limit)
    norm_start = _normalize_datetime(start_date)
    norm_end = _normalize_datetime(end_date)
    if norm_start is not None and norm_end is not None and norm_start > norm_end:
        return [], None

    if after is not None:
        after_ts, after_id = after
        if after_ts is None:
            raise ValueError('conversation keyset timestamp is invalid')
        if not isinstance(after_id, str) or not after_id.strip() or '/' in after_id:
            raise ValueError('conversation keyset doc id is invalid')

    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(valid_uid).collection(conversations_collection)
    valid_categories = _clean_categories(categories)
    query_spec = MCP_CONVERSATION_CARD_QUERY_SPECS[
        (bool(valid_categories), norm_start is not None, norm_end is not None)
    ]
    field_paths = _card_field_paths(extra_field_paths)
    visible: List[Dict[str, Any]] = []
    visible_positions: List[Tuple[Any, str]] = []
    scanned = 0
    last_position = after
    exhausted = False
    while len(visible) < safe_limit + 1 and scanned < MCP_CARD_PAGE_SCAN_BUDGET:
        query = query_spec.build(
            collection,
            {
                'discarded': False,
                'status': 'completed',
                'categories': valid_categories,
                'start_date': norm_start,
                'end_date': norm_end,
            },
            field_filter_factory=FieldFilter,
        )
        query = (
            query.order_by('created_at', direction=firestore.Query.DESCENDING)
            .order_by('__name__', direction=firestore.Query.DESCENDING)
            .select(field_paths)
            .limit(safe_limit + 1)
        )
        if last_position is not None:
            after_ts, after_id = last_position
            if after_ts is None:
                logger.warning('mcp_conversation_pages: skipping None keyset timestamp for doc %s', after_id)
                exhausted = True
                break
            if not isinstance(after_id, str) or not after_id.strip() or '/' in after_id:
                raise ValueError('conversation keyset doc id is invalid')
            query = query.start_after({'created_at': after_ts, '__name__': collection.document(after_id.strip())})
        try:
            raw_docs = list(query.stream())
        except Exception:
            logger.exception('mcp_conversation_pages: query stream failed for uid=%s', valid_uid)
            exhausted = True
            break
        if not raw_docs:
            exhausted = True
            break
        scanned += len(raw_docs)
        for doc in raw_docs:
            raw = doc.to_dict() or {}
            doc_created_at = raw.get('created_at')
            if doc_created_at is not None:
                last_position = (doc_created_at, doc.id)
            conversation = document_data_with_revision(doc)
            if conversation is None:
                continue
            if is_soft_deleted(conversation):
                continue
            conversation.setdefault('id', doc.id)
            visible.append(conversation)
            if doc_created_at is not None:
                visible_positions.append(last_position)
            elif conversation.get('created_at') is not None:
                visible_positions.append((conversation['created_at'], doc.id))
        if len(raw_docs) < safe_limit + 1:
            exhausted = True
            break
    page = visible[:safe_limit]
    if len(visible) > safe_limit:
        resume = visible_positions[safe_limit - 1]
    elif not exhausted and last_position is not None and last_position[0] is not None:
        resume = last_position
    else:
        resume = None
    return page, resume
