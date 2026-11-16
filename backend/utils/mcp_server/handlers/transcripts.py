"""``search_transcripts``: literal words in saved transcripts, located to the segment.

Reuses the bounded owner/query-bound scan that chat transcript recall uses
(``database.transcript_search``): no derived index, fifty records per call,
newest first, and a signed cursor that resumes after the last record examined,
including invisible ones. Hits carry ``segment_index`` so an agent can read
around them with ``get_conversation_by_id`` ``offset``.
"""

import logging
from typing import Any, Dict, List, Optional

import database.conversations as conversations_db
from database.transcript_search import InvalidTranscriptCursor, read_transcript_search_page
from utils.conversations import transcribing_hold
from utils.conversations.mcp_transcript_search import build_transcript_match_snippets
from utils.conversations.search import conversation_matches_date_range
from utils.mcp_dates import local_date_window, localize_timestamps
from utils.mcp_memories import parse_mcp_int
from utils.mcp_server import search_views
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.handlers.conversations import fetch_conversation_for_detail
from utils.mcp_server.helpers import public_transcript_timing
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.observability.fallback import record_fallback
from utils.other.list_budget import ListReadBudget

logger = logging.getLogger(__name__)

_HIT_FIELDS = ('segment_index', 'segment_id', 'start', 'end', 'speaker_key', 'speaker_label', 'text')


def search_transcripts(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    query = ' '.join(str(arguments.get('query') or '').split())
    if not query or len(query) > search_views.TRANSCRIPT_QUERY_MAX_CHARS:
        raise ToolExecutionError(
            'query must be 1-200 characters of literal words or a short phrase, not a question.', code=-32602
        )
    conversation_id = arguments.get('conversation_id')
    cursor = arguments.get('cursor')
    if cursor is not None and conversation_id:
        raise ToolExecutionError(
            'cursor cannot be combined with conversation_id; search it without a cursor.', code=-32602
        )
    try:
        limit = parse_mcp_int(
            arguments.get('limit'),
            'limit',
            default=search_views.TRANSCRIPT_SEARCH_DEFAULT_LIMIT,
            minimum=1,
            maximum=search_views.TRANSCRIPT_SEARCH_MAX_LIMIT,
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc), code=-32602) from exc
    start_dt, end_dt, zone = local_date_window(
        uid, arguments.get('start_date'), arguments.get('end_date'), arguments.get('timezone')
    )

    if conversation_id:
        row = fetch_conversation_for_detail(uid, conversation_id)
        if row is None:
            raise ToolExecutionError(
                'Conversation not found. Use the full id from get_conversations or search results.', code=-32001
            )
        if row.get('is_locked', False):
            raise ToolExecutionError('A paid plan is required to access this conversation.', code=-32002)
        entries: List[tuple] = [(row, None)]
        exhausted, unreadable = True, 0
    else:
        budget = ListReadBudget.for_request(
            None,
            route='mcp_transcript_search',
            seconds=search_views.TRANSCRIPT_SCAN_SECONDS,
            max_documents=search_views.TRANSCRIPT_SCAN_DOCUMENTS,
        )
        try:
            page = read_transcript_search_page(
                uid, query, cursor=cursor, start_date=start_dt, end_date=end_dt, budget=budget
            )
        except InvalidTranscriptCursor as exc:
            raise ToolExecutionError(
                'Invalid or expired cursor. Restart with the same query and dates and no cursor.', code=-32602
            ) from exc
        except Exception as exc:
            logger.warning('MCP transcript search unavailable (%s)', type(exc).__name__)
            record_fallback(
                component='firestore_read',
                from_mode='transcript_search',
                to_mode='unavailable',
                reason='other',
                outcome='degraded',
                log=logger,
            )
            raise ToolExecutionError(
                'Transcript search is unavailable. Retry; this does not establish that the words are absent.',
                code=-32009,
                http_status=503,
            ) from exc
        if not page.rows and not page.exhausted:
            raise ToolExecutionError(
                'Transcript search made no progress before its deadline. Retry or narrow the dates.',
                code=-32009,
                http_status=503,
            )
        entries = [(entry.conversation, entry.cursor) for entry in page.rows]
        exhausted, unreadable = page.exhausted, page.unreadable

    matches: List[Dict[str, Any]] = []
    examined = 0
    next_cursor = cursor
    stopped_early = False
    start_ts = start_dt.timestamp() if start_dt else None
    end_ts = end_dt.timestamp() if end_dt else None
    for row, row_cursor in entries:
        if len(matches) >= limit:
            stopped_early = True
            break
        examined += 1
        next_cursor = row_cursor or next_cursor
        if not _searchable(row, start_ts, end_ts, scoped=bool(conversation_id)):
            continue
        match = _conversation_match(transcribing_hold.project(row), query)
        if match is not None:
            matches.append(match)

    complete = exhausted and not stopped_early
    result: Dict[str, Any] = {
        'matches': matches,
        'examined': examined,
        'complete': complete,
        'unreadable': unreadable,
        'next_cursor': None if complete or conversation_id else next_cursor,
        'search_coverage': 'literal_transcript_scan' + ('' if complete else '_partial'),
    }
    return localize_timestamps(result, zone)


def _searchable(row: Optional[Dict[str, Any]], start_ts: Optional[float], end_ts: Optional[float], *, scoped: bool):
    if not row or row.get('is_locked') or row.get('processing_deferred') or row.get('discarded'):
        return False
    if not scoped and not conversations_db.is_visible_conversation(row):
        return False
    return scoped or conversation_matches_date_range(row, start_ts, end_ts)


def _conversation_match(row: Dict[str, Any], query: str) -> Optional[Dict[str, Any]]:
    segments = row.get('transcript_segments')
    snippets = build_transcript_match_snippets(
        segments if isinstance(segments, list) else [],
        query,
        context_neighbors=0,
        max_snippets=search_views.TRANSCRIPT_HITS_PER_CONVERSATION + 1,
        max_chars=search_views.TRANSCRIPT_HIT_MAX_CHARS,
        center_match=True,
    )
    if not snippets:
        return None
    search_views.add_segment_indexes(snippets, segments)
    hits = [
        {key: value for key, value in public_transcript_timing(snippet).items() if key in _HIT_FIELDS}
        for snippet in snippets[: search_views.TRANSCRIPT_HITS_PER_CONVERSATION]
    ]
    structured = row.get('structured') if isinstance(row.get('structured'), dict) else {}
    return {
        'conversation': {
            'id': row.get('id'),
            'title': structured.get('title'),
            'created_at': row.get('created_at'),
            'started_at': row.get('started_at'),
            'finished_at': row.get('finished_at'),
        },
        'hits': hits,
        'more_hits': len(snippets) > search_views.TRANSCRIPT_HITS_PER_CONVERSATION,
    }
