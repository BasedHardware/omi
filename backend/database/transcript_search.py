"""Bounded, owner/query-bound pages of authoritative saved transcripts.

No derived index or offset is required. Invisible records still advance the
bookmark, so a page of tombstones cannot hide the rest of a user's history.
"""

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.conversations import document_data_with_revision, is_visible_conversation, prepare_conversation_for_read
from utils.conversation_page_cursor import BookmarkDict, decode_cursor, encode_cursor, query_scope
from utils.observability.fallback import record_fallback
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted, budgeted_stream_iter

logger = logging.getLogger(__name__)
TRANSCRIPT_PAGE_SIZE = 50


class InvalidTranscriptCursor(ValueError):
    """A bad bookmark must never silently restart or widen a transcript search."""


@dataclass(frozen=True)
class TranscriptScanRow:
    conversation: dict[str, Any] | None
    cursor: str


@dataclass(frozen=True)
class TranscriptScanPage:
    rows: list[TranscriptScanRow]
    exhausted: bool
    unreadable: int = 0


def read_transcript_search_page(
    uid: str,
    query: str,
    *,
    cursor: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    budget: ListReadBudget,
    firestore_client: Any = None,
) -> TranscriptScanPage:
    """Read at most fifty raw records; signing is independent of rollout levers."""
    scope = query_scope(dict(surface='transcript-search-v1', uid=uid, query=query, start=start_date, end=end_date))
    bookmark = None
    if cursor is not None:
        try:
            stamp, doc_id = decode_cursor(cursor, scope)
        except ValueError as error:
            raise InvalidTranscriptCursor('invalid transcript cursor') from error
        bookmark = BookmarkDict({'created_at': stamp, '__name__': doc_id})
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations')
    if start_date is not None:
        ref = ref.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date is not None:
        ref = ref.where(filter=FieldFilter('created_at', '<=', end_date))
    ref = ref.order_by('created_at', direction=firestore.Query.DESCENDING).order_by(
        '__name__', direction=firestore.Query.DESCENDING
    )
    if bookmark is not None:
        ref = ref.start_after(bookmark)
    rows: list[TranscriptScanRow] = []
    unreadable = 0
    stream = budgeted_stream_iter(ref.limit(TRANSCRIPT_PAGE_SIZE), budget)
    try:
        for doc in stream:
            raw = document_data_with_revision(doc) or {}
            token = encode_cursor(raw['created_at'], doc.id, scope)
            conversation = None
            if is_visible_conversation(raw) and not raw.get('is_locked') and not raw.get('processing_deferred'):
                try:
                    conversation = prepare_conversation_for_read(
                        {**raw, 'id': doc.id}, uid, firestore_client=client, read_budget=budget
                    )
                    budget.check()
                except ListReadBudgetExhausted:
                    raise
                except Exception as error:
                    unreadable += 1
                    logger.warning('transcript search could not decode a record (%s)', type(error).__name__)
            rows.append(TranscriptScanRow(conversation, token))
    except ListReadBudgetExhausted:
        record_fallback(
            component='firestore_read',
            from_mode='transcript_search',
            to_mode='partial_page',
            reason='capacity_full',
            outcome='degraded',
            log=logger,
        )
        return TranscriptScanPage(rows, exhausted=False, unreadable=unreadable)
    finally:
        close = getattr(stream, 'close', None)
        if callable(close):
            close()
    return TranscriptScanPage(rows, exhausted=len(rows) < TRANSCRIPT_PAGE_SIZE, unreadable=unreadable)
