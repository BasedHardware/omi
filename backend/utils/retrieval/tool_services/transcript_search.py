"""Direct transcript recall shared by mobile chat and desktop/web tools."""

from datetime import datetime
import json
import logging
from typing import Any, Callable

from database import conversations as conversations_db
from database.transcript_search import (
    InvalidTranscriptCursor,
    TranscriptScanPage,
    TranscriptScanRow,
    read_transcript_search_page,
)
from models.conversation import Conversation
from utils.conversations.factory import deserialize_conversation
from utils.conversations.mcp_transcript_search import build_transcript_match_snippets
from utils.conversations.search import conversation_matches_date_range
from utils.conversations.transcript_for_llm import owner_safe_transcript_segments
from utils.model_text import DisplayClock, UNTRUSTED_LEGEND, format_date, untrusted_block
from utils.observability.fallback import record_fallback
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted
from utils.retrieval.safety import safe_isoformat

logger = logging.getLogger(__name__)


def search_saved_transcripts_text(
    uid: str,
    transcript_query: str,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 5,
    cursor: str | None = None,
    conversation_id: str | None = None,
    clock: DisplayClock = DisplayClock.utc(),
    source_sink: list[dict[str, Any]] | None = None,
    citation_for: Callable[[Conversation], str] | None = None,
) -> str:
    """Search literal words in current authorized transcripts, without any index.

    Each call has a fifty-document/six-second budget. Continuation resumes after
    the last examined record, including when the result/character cap stops a
    page early. Never turn incomplete coverage or a lexical miss into a factual
    absence claim.
    """
    query = ' '.join(transcript_query.split())
    if not query or len(query) > 200:
        return 'Error: transcript_query must contain 1–200 characters of literal words or a phrase, not a question.'
    if start_date and end_date and start_date > end_date:
        return 'Error: transcript search start_date must not be after end_date.'
    if cursor is not None and conversation_id:
        return 'Error: a transcript cursor cannot be used with an exact conversation; start that search again.'
    limit = max(1, min(limit, 20))
    budget = ListReadBudget.for_request(None, route='chat_transcript_search', seconds=6.0, max_documents=50)
    # Reserve matching/rendering time for both history and exact-record reads.
    read_budget = ListReadBudget.for_request(None, route='chat_transcript_search', seconds=4.0, max_documents=50)
    try:
        if conversation_id:
            owned = conversations_db.get_conversations_by_id_without_photos(
                uid, [conversation_id], include_discarded=True, read_budget=read_budget
            )
            read_budget.check()
            page = TranscriptScanPage([TranscriptScanRow(row, '') for row in owned], exhausted=True)
        else:
            page = read_transcript_search_page(
                uid, query, cursor=cursor, start_date=start_date, end_date=end_date, budget=read_budget
            )
    except InvalidTranscriptCursor:
        return 'Error: invalid or expired transcript cursor. Restart with the same transcript_query and no cursor.'
    except Exception as error:
        logger.warning('direct transcript search unavailable (%s)', type(error).__name__)
        record_fallback(
            component='firestore_read',
            from_mode='transcript_search',
            to_mode='unavailable',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return 'Error: transcript search unavailable. No absence conclusion is possible; retry this search. Do not guess an answer.'

    if not page.rows and not page.exhausted:
        return 'Error: transcript search made no progress before its deadline. Retry or narrow the dates; no absence conclusion is possible.'

    blocks: list[str] = []
    next_cursor = cursor
    examined = 0
    unreadable = page.unreadable
    complete_page = True

    def within_deadline() -> bool:
        try:
            budget.check()
            return True
        except ListReadBudgetExhausted:
            record_fallback(
                component='firestore_read',
                from_mode='transcript_search',
                to_mode='partial_page',
                reason='capacity_full',
                outcome='degraded',
                log=logger,
            )
            return False

    for entry in page.rows:
        if not within_deadline():
            complete_page = False
            break
        row = entry.conversation
        if row and (
            conversations_db.is_visible_conversation(row)
            and not row.get('is_locked')
            and not row.get('processing_deferred')
            and conversation_matches_date_range(
                row, start_date.timestamp() if start_date else None, end_date.timestamp() if end_date else None
            )
        ):
            segments, owner_note = owner_safe_transcript_segments(
                [s for s in (row.get('transcript_segments') or []) if isinstance(s, dict)]
            )
            snippets = build_transcript_match_snippets(
                segments, query, max_snippets=2, max_chars=1600, center_match=True
            )
            if snippets:
                try:
                    conversation = deserialize_conversation(row)
                except Exception as error:
                    unreadable += 1
                    logger.warning('transcript search skipped an invalid record (%s)', type(error).__name__)
                else:
                    if not within_deadline():
                        complete_page = False
                        break
                    excerpt = '\n\n'.join(snippet['text'] for snippet in snippets)
                    # Leave room for coverage, signed continuation and citation labels.
                    block = untrusted_block(
                        'transcript',
                        f'Title: {str(conversation.structured.title if conversation.structured else "Conversation")[:160]}\n'
                        + (owner_note + '\n' if owner_note else '')
                        + excerpt,
                    )
                    if blocks and (len(blocks) >= limit or sum(map(len, blocks)) + len(block) > 7000):
                        complete_page = False
                        break
                    citation = citation_for(conversation) if citation_for else f'conversation:{conversation.id}'
                    blocks.append(
                        f'Source {citation} (conversation:{conversation.id}), '
                        f'{format_date(conversation.created_at, clock)}:\n{block}'
                    )
                    if source_sink is not None:
                        source_sink.append(
                            {
                                'kind': 'conversation',
                                'source_id': conversation.id,
                                'title': str(
                                    conversation.structured.title if conversation.structured else 'Conversation'
                                )[:160],
                                'preview': ' '.join(excerpt.split())[:600],
                                'created_at': safe_isoformat(conversation.created_at),
                            }
                        )
        examined += 1
        next_cursor = entry.cursor or None
    if complete_page and page.exhausted:
        next_cursor = None
    more = not complete_page or not page.exhausted
    if more and examined == 0:
        return 'Error: transcript search made no progress before its deadline. Retry or narrow the dates; no absence conclusion is possible.'
    coverage = (
        f'Direct transcript search: examined {examined} records on this page; {len(blocks)} matching conversations. '
        'Matching is literal (phrase or all words in one segment), not semantic. '
        'Only the quoted excerpts are evidence; do not infer a precise amount, date or name from a near match. '
        'A request to check again does not supply new evidence.'
    )
    if more:
        # The legacy query field also accepts exact conversation UUIDs/links.
        # Keep literal spoken references on the transcript-search path.
        args: dict[str, Any] = {'query': 'Search saved transcript text', 'transcript_query': query}
        if next_cursor:
            args['transcript_cursor'] = next_cursor
        if start_date:
            args['start_date'] = safe_isoformat(start_date)
        if end_date:
            args['end_date'] = safe_isoformat(end_date)
        coverage += '\nSearch incomplete. Continue the same search with: ' + json.dumps(args)
    else:
        coverage += '\nEnd of this scan. A literal-word miss is not proof that the underlying fact was never recorded.'
    if unreadable:
        coverage += '\nSome records could not be read; coverage is incomplete. Retry before making any absence claim.'
        record_fallback(
            component='firestore_read',
            from_mode='transcript_search',
            to_mode='partial_page',
            reason='other',
            outcome='degraded',
            log=logger,
        )
    return (
        coverage
        + '\n\n'
        + (
            UNTRUSTED_LEGEND + '\n' + '\n\n'.join(blocks)
            if blocks
            else 'No matching transcript excerpts on this page. Do not invent an answer; continue if a cursor is provided, '
            'try another literal phrase or ask for the relevant date/conversation.'
        )
    )
