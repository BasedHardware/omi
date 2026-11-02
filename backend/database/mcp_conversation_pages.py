"""Transcript-free conversation card reads for the hosted MCP surfaces.

Kept out of ``database/conversations.py`` (line-count ratchet): both the
legacy offset read and the ``(created_at DESC, __name__ DESC)`` keyset page
live here. The optional ``extra_field_paths`` widens the projection for the
REST surface (``apps_results``) without inflating the hosted tool reads.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted
from database.released_memory_projection import projected_stream_list, projected_stream_iter

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from fastapi import HTTPException

from config.firestore_read_levers import lever_enabled

from ._client import get_firestore_client
from .conversations import (
    document_data_with_revision,
    prepare_conversation_for_read,
    conversations_collection,
    is_visible_conversation,
)
from .mcp_read_queries import MCP_CONVERSATION_CARD_QUERY_SPECS, MCP_CONVERSATION_CARD_FIELD_PATHS
from .helpers import prepare_for_read

# Upper bound on raw documents a single page may scan while skipping
# soft-deleted tombstones between visible rows (an offset page counts the rows
# past its first window).
MCP_CARD_PAGE_SCAN_BUDGET = 500
logger = logging.getLogger(__name__)


def _bounded_read_cap(uid: str) -> Optional[int]:
    # The rollout name is shared with the experiment brief; this lever bounds
    # queries, without caching user data or needing write-side invalidation.
    if not lever_enabled('mcp_conversation_cards_cache', uid):
        return None
    try:
        return max(2, int(os.getenv('FSR_MCP_CARDS_MAX_READS', '1501')))
    except ValueError:
        return 1501


def _require_cursor() -> None:
    # Both hosted surfaces already translate this shared typed error. Never
    # disguise an over-budget offset page as the end of a user's collection.
    logger.warning('mcp_conversation_cards_read_cap: rejected request; use a smaller limit and cursor')
    raise HTTPException(
        status_code=400,
        detail='Conversation read limit exceeded. Use a smaller limit and page with cursor instead of offset.',
    )


def _card_field_paths(extra_field_paths: Optional[Sequence[str]]) -> List[str]:
    paths: List[str] = list(MCP_CONVERSATION_CARD_FIELD_PATHS)
    if extra_field_paths:
        paths.extend(extra_field_paths)
    # Firestore masks must not contain both a parent and its nested fields.
    return [
        path
        for path in dict.fromkeys(paths)
        if not any(path.startswith(parent + ".") for parent in paths if parent != path)
    ]


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
    budget: Optional[ListReadBudget] = None,
) -> List[Dict[str, Any]]:
    """Return the transcript-free Firestore projection used by hosted MCP lists.

    ``offset`` skips stored rows. Tombstones still match the indexed filters
    and are dropped in Python, so a full window that loses rows to them keeps
    reading after its last row in keyset order until ``limit`` visible rows,
    stream exhaustion, or the scan budget. Callers read a short result as the
    end of the list. With the WQ6 lever, billed offset skips count toward a
    hard per-call cap and an incomplete capped window raises instead of
    claiming exhaustion. Refill windows request only the missing slots.
    """
    read_cap = _bounded_read_cap(uid)
    if read_cap is not None and (limit < 1 or offset < 0 or offset + limit > read_cap):
        _require_cursor()
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
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING).select(
        _card_field_paths(extra_field_paths)
    )
    window = query.limit(limit).offset(offset)
    conversations: List[Dict[str, Any]] = []
    scanned = 0
    window_size = limit
    try:
        while True:
            fetched = 0
            last_doc = None
            for doc in projected_stream_iter(
                window, budget, surface='mcp_cards', offset_reads=offset if scanned == 0 else 0
            ):
                fetched += 1
                last_doc = doc
                conversation = document_data_with_revision(doc)
                if conversation is None:
                    continue
                if not is_visible_conversation(conversation):
                    continue
                conversation.setdefault('id', doc.id)
                conversations.append(conversation)
            scanned += fetched
            if (
                read_cap is not None
                and len(conversations) < limit
                and fetched == window_size
                and last_doc is not None
                and scanned >= limit + MCP_CARD_PAGE_SCAN_BUDGET
            ):
                _require_cursor()
            if (
                len(conversations) >= limit
                or fetched < window_size
                or last_doc is None
                or scanned >= limit + MCP_CARD_PAGE_SCAN_BUDGET
            ):
                break
            last_created_at = (last_doc.to_dict() or {}).get('created_at')
            if last_created_at is None:
                # Same stop as the keyset page: no resumable position past this row.
                break
            if read_cap is not None:
                remaining = read_cap - offset - scanned
                if remaining <= 0:
                    _require_cursor()
                # Refill only missing slots, rather than discarding an entire
                # second page's surplus visible cards after paying for them.
                window_size = min(limit - len(conversations), remaining)
            window = (
                query.order_by('__name__', direction=firestore.Query.DESCENDING)
                .limit(window_size)
                .start_after({'created_at': last_created_at, '__name__': collection.document(last_doc.id)})
            )
    except ListReadBudgetExhausted:
        pass
    return conversations[:limit]


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
    With the WQ6 lever, every window fits the remaining raw-read budget and
    requests only the visible slots still missing (including lookahead).
    """
    read_cap = _bounded_read_cap(uid)
    if read_cap is not None and (limit < 1 or limit + 1 > read_cap):
        _require_cursor()
    scan_cap = (
        min(read_cap, max(limit + 1, MCP_CARD_PAGE_SCAN_BUDGET)) if read_cap is not None else MCP_CARD_PAGE_SCAN_BUDGET
    )
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)
    query_spec = MCP_CONVERSATION_CARD_QUERY_SPECS[(bool(categories), start_date is not None, end_date is not None)]
    field_paths = _card_field_paths(extra_field_paths)
    visible: List[Dict[str, Any]] = []
    visible_positions: List[Tuple[Any, str]] = []
    scanned = 0
    last_position = after
    exhausted = False
    while len(visible) < limit + 1 and scanned < scan_cap:
        window_size = min(limit + 1 - len(visible), scan_cap - scanned) if read_cap is not None else limit + 1
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
            .limit(window_size)
        )
        if last_position is not None:
            after_ts, after_id = last_position
            if after_ts is None:
                raise ValueError('conversation keyset timestamp is invalid')
            if not isinstance(after_id, str) or not after_id.strip() or '/' in after_id:
                raise ValueError('conversation keyset doc id is invalid')
            query = query.start_after({'created_at': after_ts, '__name__': collection.document(after_id)})
        raw_docs = projected_stream_list(query, surface='mcp_cards')
        if not raw_docs:
            exhausted = True
            break
        scanned += len(raw_docs)
        for doc in raw_docs:
            raw = doc.to_dict() or {}
            doc_created_at = raw.get('created_at')
            if doc_created_at is None:
                # A tombstoned row with no created_at can't seed a resumable
                # keyset position (the next start_after would carry a None
                # timestamp and raise above). Stop the scan here instead of
                # handing back a cursor the following page would reject.
                exhausted = True
                break
            last_position = (doc_created_at, doc.id)
            conversation = document_data_with_revision(doc)
            if conversation is None:
                continue
            if not is_visible_conversation(conversation):
                continue
            conversation.setdefault('id', doc.id)
            visible.append(conversation)
            visible_positions.append(last_position)
        if exhausted:
            break
        if len(raw_docs) < window_size:
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
