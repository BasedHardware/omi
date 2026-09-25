"""Transcript-free conversation card reads for the hosted MCP surfaces.

Kept out of ``database/conversations.py`` (line-count ratchet): both the
legacy offset read and the ``(created_at DESC, __name__ DESC)`` keyset page
live here. The optional ``extra_field_paths`` widens the projection for the
REST surface (``apps_results``) without inflating the hosted tool reads.
"""

from datetime import datetime
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

# Upper bound on raw documents a single keyset page may scan while skipping
# soft-deleted tombstones between visible rows.
MCP_CARD_PAGE_SCAN_BUDGET = 500


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
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)
    query_spec = MCP_CONVERSATION_CARD_QUERY_SPECS[(bool(categories), start_date is not None, end_date is not None)]
    query = query_spec.build(
        collection,
        {
            'discarded': False,
            'status': 'completed',
            'categories': categories,
            'start_date': start_date,
            'end_date': end_date,
        },
        field_filter_factory=FieldFilter,
    )
    query = (
        query.order_by('created_at', direction=firestore.Query.DESCENDING)
        .select(_card_field_paths(extra_field_paths))
        .limit(limit)
        .offset(offset)
    )
    conversations: List[Dict[str, Any]] = []
    for doc in query.stream():
        conversation = document_data_with_revision(doc)
        if conversation is None:
            continue
        if is_soft_deleted(conversation):
            continue
        conversation.setdefault('id', doc.id)
        conversations.append(conversation)
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
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)
    query_spec = MCP_CONVERSATION_CARD_QUERY_SPECS[(bool(categories), start_date is not None, end_date is not None)]
    field_paths = _card_field_paths(extra_field_paths)
    visible: List[Dict[str, Any]] = []
    visible_positions: List[Tuple[Any, str]] = []
    scanned = 0
    last_position = after
    exhausted = False
    while len(visible) < limit + 1 and scanned < MCP_CARD_PAGE_SCAN_BUDGET:
        query = query_spec.build(
            collection,
            {
                'discarded': False,
                'status': 'completed',
                'categories': categories,
                'start_date': start_date,
                'end_date': end_date,
            },
            field_filter_factory=FieldFilter,
        )
        query = (
            query.order_by('created_at', direction=firestore.Query.DESCENDING)
            .order_by('__name__', direction=firestore.Query.DESCENDING)
            .select(field_paths)
            .limit(limit + 1)
        )
        if last_position is not None:
            after_ts, after_id = last_position
            if after_ts is None:
                raise ValueError('conversation keyset timestamp is invalid')
            if not after_id.strip() or '/' in after_id:
                raise ValueError('conversation keyset doc id is invalid')
            query = query.start_after({'created_at': after_ts, '__name__': collection.document(after_id)})
        raw_docs = list(query.stream())
        if not raw_docs:
            exhausted = True
            break
        scanned += len(raw_docs)
        for doc in raw_docs:
            raw = doc.to_dict() or {}
            last_position = (raw.get('created_at'), doc.id)
            conversation = document_data_with_revision(doc)
            if conversation is None:
                continue
            if is_soft_deleted(conversation):
                continue
            conversation.setdefault('id', doc.id)
            visible.append(conversation)
            visible_positions.append(last_position)
        if len(raw_docs) < limit + 1:
            exhausted = True
            break
    page = visible[:limit]
    if len(visible) > limit:
        resume = visible_positions[limit - 1]
    elif not exhausted and last_position is not None:
        resume = last_position
    else:
        resume = None
    return page, resume
