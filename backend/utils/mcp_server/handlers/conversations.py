"""Conversation tool handlers for the hosted MCP server."""

import logging
from dataclasses import dataclass

from utils.other.list_budget import ListReadBudget

from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException
from google.api_core.exceptions import FailedPrecondition

import database.conversations as conversations_db
import database.mcp_conversation_pages as mcp_conversation_pages
import database.vector_db as vector_db
from database.recording_transcript_publication import RESOLVED_RECORDING_ID
from models.conversation_enums import CategoryEnum
from utils.conversations.mcp_transcript_search import (
    attach_match_snippets_to_conversations,
    resolve_mcp_conversation_search_ids,
)
from utils.conversations.search import keyword_search_conversation_ids, conversation_matches_date_range
from utils.observability.fallback import record_fallback
from utils.conversations.render import redact_conversation_for_list
from utils.conversations import transcribing_hold
from utils.external_read_contract import utc_window
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_dates import local_date_window, localize_timestamps
from utils.mcp_memories import parse_mcp_int, parse_mcp_bool
from utils.mcp_server.constants import (
    MCP_CONVERSATION_BATCH_MAX_IDS,
    MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS,
    MCP_CONVERSATION_ID_MAX_BYTES,
    MCP_CONVERSATION_FETCH_DEFAULT_MAX_CHARS,
    conversation_fetch_default_max_segments,
    MCP_CONVERSATION_FETCH_MAX_CHARS,
    MCP_CONVERSATION_FETCH_MAX_SEGMENTS,
    MCP_CONVERSATION_LIST_MAX_LIMIT,
    MCP_CONVERSATION_SEARCH_SNIPPET_CHARS,
)
from utils.mcp_server.cursors import (
    conversation_keyset_position,
    decode_cursor,
    encode_cursor,
    offset_position,
    serialize_timestamp,
)
from utils.mcp_server import search_views
from utils.mcp_server.errors import ToolExecutionError, raise_conversation_index_error
from utils.mcp_server.detail_cursors import decode_detail_cursor, encode_detail_cursor
from utils.mcp_server.helpers import (
    transcript_page,
    conversation_card,
    public_transcript_timing,
    select_card_fields,
)
from utils.mcp_server.payloads import tool_response_serialized_chars
from utils.mcp_server import detail_views

logger = logging.getLogger(__name__)


def _utc_search_window(start_dt: Any, end_dt: Any) -> tuple:
    try:
        return utc_window(start_dt, end_dt)
    except HTTPException as exc:
        raise ToolExecutionError(str(exc.detail), code=-32602) from exc


def conversation_cards_page_core(
    uid: str,
    *,
    limit: int,
    offset: int = 0,
    cursor_token: Optional[str] = None,
    start_dt: Optional[Any] = None,
    end_dt: Optional[Any] = None,
    categories: Optional[List[str]] = None,
    cursor_kind: str,
    extra_field_paths: Optional[List[str]] = None,
    budget: Optional[ListReadBudget] = None,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Shared card page for the MCP ``get_conversations`` tool and REST list.

    ``cursor_kind`` binds the opaque cursor to the calling surface (tool name
    or REST route) so tokens minted on one surface cannot resume the other.
    Returns ``(card dicts, next_cursor)``; the cursor is opaque and carries
    the validated filter fingerprint.
    """
    start_dt, end_dt = _utc_search_window(start_dt, end_dt)
    valid_categories = list(categories or [])
    filters = {
        "categories": sorted(valid_categories),
        "start": start_dt.isoformat() if start_dt else None,
        "end": end_dt.isoformat() if end_dt else None,
    }
    after = None
    if cursor_token is not None:
        if offset != 0:
            raise ToolExecutionError("cursor and offset are mutually exclusive.", code=-32602)
        after = conversation_keyset_position(decode_cursor(cursor_token, kind=cursor_kind, uid=uid, filters=filters))

    if cursor_token is None and offset != 0:
        try:
            fetched = mcp_conversation_pages.get_mcp_conversation_cards(
                uid,
                limit + 1,
                offset,
                start_date=start_dt,
                end_date=end_dt,
                categories=valid_categories,
                extra_field_paths=extra_field_paths,
                **({'budget': budget} if budget is not None else {}),
            )
        except FailedPrecondition as e:
            raise_conversation_index_error(e)
        resume = None
        if len(fetched) > limit and fetched[limit - 1].get("created_at") is not None:
            last = fetched[limit - 1]
            resume = encode_cursor(
                kind=cursor_kind,
                uid=uid,
                position={"ts": serialize_timestamp(last["created_at"]), "id": last["id"]},
                filters=filters,
            )
        return [transcribing_hold.project(row) for row in fetched[:limit]], resume

    try:
        page, resume = mcp_conversation_pages.get_mcp_conversation_cards_page(
            uid,
            limit,
            after=after,
            start_date=start_dt,
            end_date=end_dt,
            categories=valid_categories,
            extra_field_paths=extra_field_paths,
        )
    except FailedPrecondition as e:
        raise_conversation_index_error(e)

    next_cursor = None
    if resume is not None:
        next_cursor = encode_cursor(
            kind=cursor_kind,
            uid=uid,
            position={"ts": serialize_timestamp(resume[0]), "id": resume[1]},
            filters=filters,
        )
    return [transcribing_hold.project(row) for row in page], next_cursor


def is_safe_conversation_id(raw_id: Any) -> bool:
    """Reject ids Firestore itself refuses — ``.``, ``..``, ``__*__``
    reserved ids and any ``/`` — before they reach a document read."""
    return (
        isinstance(raw_id, str)
        and bool(raw_id)
        and len(raw_id.encode("utf-8")) <= MCP_CONVERSATION_ID_MAX_BYTES
        and "/" not in raw_id
        and raw_id not in {".", ".."}
        and not (raw_id.startswith("__") and raw_id.endswith("__"))
    )


def fetch_conversation_for_detail(
    uid: str,
    conversation_id: Any,
    *,
    extra_field_paths: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Shared bounded detail read (card+transcript projection, no photos)."""
    if not is_safe_conversation_id(conversation_id):
        return None
    try:
        conversations = conversations_db.get_mcp_conversations_by_id(
            uid,
            [str(conversation_id)],
            include_transcript=True,
            include_discarded=False,
            allow_published_recording=True,
            extra_field_paths=extra_field_paths,
        )
    except conversations_db.TranscriptSegmentsDecodeError as error:
        raise ToolExecutionError('Stored transcript could not be decoded.', code=-32009, http_status=503) from error
    return transcribing_hold.project(conversations[0]) if conversations else None


def get_conversations(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")
    raw_categories = arguments.get("categories", [])
    categories_list: List[Any] = cast(List[Any], raw_categories) if isinstance(raw_categories, list) else []
    try:
        limit = parse_mcp_int(
            arguments.get("limit"),
            "limit",
            default=20,
            minimum=1,
            maximum=MCP_CONVERSATION_LIST_MAX_LIMIT,
        )
        offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)

    start_dt, end_dt, zone = local_date_window(uid, start_date, end_date, arguments.get('timezone'))

    valid_categories: List[str] = []
    for cat in categories_list:
        try:
            valid_categories.append(CategoryEnum(cat).value)
        except ValueError:
            pass

    page, next_cursor = conversation_cards_page_core(
        uid,
        limit=limit,
        offset=offset,
        cursor_token=arguments.get("cursor"),
        start_dt=start_dt,
        end_dt=end_dt,
        categories=valid_categories,
        cursor_kind="get_conversations",
    )

    result: Dict[str, Any] = {
        "conversations": [
            select_card_fields(conversation_card(conversation), arguments.get("fields")) for conversation in page
        ],
        "has_more": next_cursor is not None,
        "effective_limit": limit,
    }
    if next_cursor is not None:
        result["next_cursor"] = next_cursor
    result["timezone"] = str(zone)
    return localize_timestamps(result, zone)


def get_conversation_by_id(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    conversation_id = arguments.get("conversation_id")
    if not conversation_id:
        raise ToolExecutionError("conversation_id is required")
    if not is_safe_conversation_id(conversation_id):
        raise ToolExecutionError("conversation_id is not a valid document id", code=-32602)

    max_segments, max_chars = _conversation_fetch_bounds(arguments)
    filters = _detail_filters(arguments, conversation_id, max_segments, max_chars)
    view = detail_views.parse_choice(arguments, 'view', detail_views.VIEWS)
    offset = detail_views.start_offset(arguments)
    position = (
        decode_detail_cursor(arguments['cursor'], uid=uid, filters=filters)
        if arguments.get('cursor') is not None
        else {'offset': offset or 0, 'char_offset': 0}
    )

    conversation = fetch_conversation_for_detail(
        uid, conversation_id, extra_field_paths=['structured.sections'] if view == 'outline' else None
    )
    if conversation is None:
        raise ToolExecutionError(
            "Conversation not found. Use the full id from get_conversations; shortened id prefixes are not document ids.",
            code=-32001,
        )

    if conversation.get('is_locked', False):
        raise ToolExecutionError("A paid plan is required to access this conversation.", code=-32002)

    total = len(detail_views.readable_segments(conversation.get('transcript_segments')))
    fmt = filters.get('format', 'segments')
    first_page = arguments.get('cursor') is None
    # One card per request: the budget loop below only re-slices the transcript.
    card = conversation_card(conversation, include_participants=filters['include_participants'])
    if view == 'outline':
        sections = detail_views.outline_sections(conversation)
        result = {
            'conversation': select_card_fields(card, filters['fields']),
            'sections': sections[: detail_views.OUTLINE_MAX_SECTIONS],
            'sections_truncated': len(sections) > detail_views.OUTLINE_MAX_SECTIONS,
            'total_segments': total,
            'truncated': False,
            'next_cursor': None,
        }
        if tool_response_serialized_chars(result) > MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS:
            raise ToolExecutionError(
                'Outline exceeds the 120000-character serialized response budget. '
                'Retry with include_participants=false or fewer fields.',
                code=-32602,
            )
        detail_views.count_page('get_conversation_by_id', view, fmt, True, False)
        return result
    if offset is not None and offset > total:
        raise ToolExecutionError(
            f'offset {offset} is past the end of the transcript (total_segments={total}).', code=-32602
        )

    conversation = detail_views.rendered_segments(conversation, fmt)
    # JSON-RPC carries both text and structuredContent, and SSE escapes Unicode.
    # If metadata/encoding consumes the wire budget, return a smaller lossless
    # page, with a cursor bound to the original requested options.
    page_segments, page_chars = max_segments, max_chars
    while True:
        result = _conversation_detail_page(
            uid,
            conversation,
            filters,
            position=position,
            page_segments=page_segments,
            page_chars=page_chars,
            card=card,
        )
        if tool_response_serialized_chars(result) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS:
            if not filters['summary_only']:
                detail_views.count_page('get_conversation_by_id', view, fmt, first_page, result['truncated'])
            return result
        if filters['summary_only'] or (page_segments == 1 and page_chars == 1):
            break
        page_segments, page_chars = max(1, page_segments // 2), max(1, page_chars // 2)
    raise ToolExecutionError(
        'Conversation exceeds the 120000-character serialized response budget. '
        'Retry with format=lines, include_participants=false, fewer fields, or smaller max_segments/max_chars.',
        code=-32602,
    )


def _detail_filters(
    arguments: Dict[str, Any], conversation_id: str, max_segments: int, max_chars: int
) -> Dict[str, Any]:
    try:
        include_participants = parse_mcp_bool(
            arguments.get("include_participants"), "include_participants", default=True
        )
        summary_only = parse_mcp_bool(arguments.get("summary_only"), "summary_only", default=False)
    except ValueError as exc:
        raise ToolExecutionError(str(exc), code=-32602) from exc
    return {
        'conversation_id': conversation_id,
        'max_segments': max_segments,
        'max_chars': max_chars,
        'fields': arguments.get('fields'),
        'summary_only': summary_only,
        'include_participants': include_participants,
    } | _format_filter(arguments)


def _format_filter(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """The cursor filters name the format only when it is not the default.

    Detail cursors authenticate their filters, so a default read keeps the same
    fingerprint as before ``format`` existed and in-flight cursors still decode.
    """
    fmt = detail_views.parse_choice(arguments, 'format', detail_views.FORMATS)
    return {} if fmt == 'segments' else {'format': fmt}


def _conversation_detail_page(
    uid: str,
    conversation: Dict[str, Any],
    filters: Dict[str, Any],
    *,
    position: Optional[Dict[str, int]] = None,
    page_segments: Optional[int] = None,
    page_chars: Optional[int] = None,
    card: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary_only = filters['summary_only']
    page = transcript_page(
        conversation.get('transcript_segments'),
        max_segments=page_segments or filters['max_segments'],
        max_chars=page_chars or filters['max_chars'],
        **(position or {}),
    )
    result = (
        dict(card)
        if card is not None
        else conversation_card(conversation, include_participants=filters['include_participants'])
    )
    if not summary_only and filters.get('format') == 'lines':
        result.update(detail_views.lines_fields(page.segments))
    elif not summary_only:
        result['transcript_segments'] = page.segments
    next_cursor = (
        encode_detail_cursor(uid=uid, filters=filters, position=page.next_position)
        if page.next_position is not None and not summary_only
        else None
    )
    return {
        'conversation': select_card_fields(result, filters['fields']),
        'total_segments': page.total_segments,
        'truncated': next_cursor is not None,
        'next_cursor': next_cursor,
    }


def _conversation_fetch_bounds(arguments: Dict[str, Any]) -> tuple[int, int]:
    """Parse the shared max_segments/max_chars bounds used by transcript reads."""
    try:
        max_segments = parse_mcp_int(
            arguments.get("max_segments"),
            "max_segments",
            default=conversation_fetch_default_max_segments(),
            minimum=1,
            maximum=MCP_CONVERSATION_FETCH_MAX_SEGMENTS,
        )
        max_chars = parse_mcp_int(
            arguments.get("max_chars"),
            "max_chars",
            default=MCP_CONVERSATION_FETCH_DEFAULT_MAX_CHARS,
            minimum=1,
            maximum=MCP_CONVERSATION_FETCH_MAX_CHARS,
        )
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    return max_segments, max_chars


def get_conversations_by_ids(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    """Fetch up to twenty details with per-item bounds and explicit omissions.

    Each item contains one nested detail, plus its stable id.
    Missing, locked, clipped and omitted records are accounted independently.
    """
    raw_ids = arguments.get("conversation_ids")
    if not isinstance(raw_ids, list):
        raise ToolExecutionError("conversation_ids must be an array of strings", code=-32602)
    if not 1 <= len(raw_ids) <= MCP_CONVERSATION_BATCH_MAX_IDS:
        raise ToolExecutionError(
            f"conversation_ids must contain between 1 and {MCP_CONVERSATION_BATCH_MAX_IDS} ids",
            code=-32602,
        )
    conversation_ids: List[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        if not is_safe_conversation_id(raw_id):
            raise ToolExecutionError(
                "conversation_ids entries must be valid Firestore document ids "
                f"(non-empty, <= {MCP_CONVERSATION_ID_MAX_BYTES} UTF-8 bytes, no '/', "
                "not '.', '..', or a reserved '__*__' id)",
                code=-32602,
            )
        if raw_id not in seen:
            seen.add(raw_id)
            conversation_ids.append(raw_id)

    max_segments, max_chars = _conversation_fetch_bounds(arguments)

    # Fetch requested rows together. Published recordings resolve their bound revisions separately.
    conversations = conversations_db.get_mcp_conversations_by_id(
        uid,
        conversation_ids,
        include_transcript=True,
        include_discarded=False,
        allow_published_recording=True,
    )
    by_id = {
        str(conversation.get(RESOLVED_RECORDING_ID) or conversation.get('id')): transcribing_hold.project(conversation)
        for conversation in conversations
    }
    not_found = [conversation_id for conversation_id in conversation_ids if conversation_id not in by_id]

    filters = {
        'ids': conversation_ids,
        'max_segments': max_segments,
        'max_chars': max_chars,
        'fields': arguments.get('fields'),
        'summary_only': arguments.get('summary_only', False),
        'include_participants': arguments.get('include_participants', True),
        **({'format': arguments['format']} if arguments.get('format') not in (None, 'segments') else {}),
    }
    offset = 0
    if arguments.get('cursor') is not None:
        offset = offset_position(
            decode_cursor(arguments['cursor'], kind='get_conversations_by_ids', uid=uid, filters=filters)
        )
    detail_filters = _detail_filters(arguments, '', max_segments, max_chars)
    found_positions = [(pos, cid) for pos, cid in enumerate(conversation_ids) if pos >= offset and cid in by_id]
    found_ids = [cid for _pos, cid in found_positions]

    def build_item(cid: str) -> Dict[str, Any]:
        conversation = by_id[cid]
        if conversation.get('is_locked', False):
            return {
                'id': cid,
                'error': {
                    'code': 'paid_plan_required',
                    'message': 'A paid plan is required to access this conversation.',
                },
            }
        return {
            'id': cid,
            **_conversation_detail_page(
                uid,
                detail_views.rendered_segments(conversation, detail_filters.get('format', 'segments')),
                {**detail_filters, 'conversation_id': cid},
            ),
            'truncated_fields': [],
        }

    def envelope(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        remaining = found_positions[len(items) :]
        omitted = [cid for _pos, cid in remaining]
        result: Dict[str, Any] = {
            'conversations': items,
            'not_found': not_found,
            'omitted_ids': omitted,
            'next_ids': omitted,
            'truncated': bool(omitted) or any(item.get('truncated', False) for item in items),
        }
        if any(len(cid) == 8 for cid in not_found):
            result['not_found_hint'] = (
                'Use the full id from get_conversations; shortened id prefixes are not document ids.'
            )
        if omitted:
            result['next_cursor'] = encode_cursor(
                kind='get_conversations_by_ids',
                uid=uid,
                position={'offset': remaining[0][0]},
                filters=filters,
            )
        return result

    # Admit complete per-item projections in request order. Never spend the
    # response budget by silently shrinking every transcript to a few characters.
    items: List[Dict[str, Any]] = []
    for cid in found_ids:
        candidate = build_item(cid)
        if tool_response_serialized_chars(envelope(items + [candidate])) > MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS:
            if not items:
                raise ToolExecutionError(
                    'Conversation exceeds the 120000-character serialized response budget. '
                    'Retry with format=lines, include_participants=false, fewer fields, or smaller max_segments/max_chars.',
                    code=-32602,
                )
            break
        items.append(candidate)
    for item in items:
        if 'total_segments' in item and not detail_filters['summary_only']:
            detail_views.count_page(
                'get_conversations_by_ids',
                'transcript',
                detail_filters.get('format', 'segments'),
                True,
                item['truncated'],
            )
    return envelope(items)


def search_conversations_core(
    uid: str,
    query: Any,
    *,
    limit: int,
    start_dt: Optional[Any],
    end_dt: Optional[Any],
    extra_field_paths: Optional[List[str]] = None,
    include_transcript: bool = True,
) -> List[Dict[str, Any]]:
    """Shared hybrid search + batch-read for MCP ``search_conversations`` and REST search.

    Dates arrive already parsed; the caller applies its own input convention
    (date-only end-of-day for the tool, exact instants for REST).
    """
    return search_conversation_hits(
        uid,
        query,
        limit=limit,
        start_dt=start_dt,
        end_dt=end_dt,
        extra_field_paths=extra_field_paths,
        include_transcript=include_transcript,
    ).conversations


@dataclass(frozen=True)
class ConversationSearchHits:
    conversations: List[Dict[str, Any]]
    vector_ids: List[str]
    keyword_ids: List[str]
    vectors_ok: bool
    keyword_ok: bool


class _VectorIndexUnconfigured(RuntimeError):
    pass


def _query_configured_vectors(*args: Any, **kwargs: Any) -> List[str]:
    # An unconfigured index makes query_vectors return [] instead of raising: that is no semantic
    # search at all, so report the index as unavailable rather than as an empty semantic result.
    if getattr(vector_db, 'index', None) is None:
        raise _VectorIndexUnconfigured()
    return vector_db.query_vectors(*args, **kwargs)


def search_conversation_hits(
    uid: str,
    query: Any,
    *,
    limit: int,
    start_dt: Optional[Any],
    end_dt: Optional[Any],
    extra_field_paths: Optional[List[str]] = None,
    include_transcript: bool = True,
) -> ConversationSearchHits:
    """Ask summary vectors and the keyword index, merge, and hydrate once.

    Keyword hits are no longer only a zero-result fallback: one semantic hit
    used to hide every exact title or overview match.
    """
    start_dt, end_dt = _utc_search_window(start_dt, end_dt)
    starts_at = int(start_dt.timestamp()) if start_dt is not None else None
    ends_at = int(end_dt.timestamp()) if end_dt is not None else None

    vectors_ok = keyword_ok = True
    index_error: Optional[FailedPrecondition] = None
    try:
        vector_ids = resolve_mcp_conversation_search_ids(
            uid,
            query,
            limit=limit,
            starts_at=starts_at,
            ends_at=ends_at,
            query_vectors=_query_configured_vectors,
            embed_query=vector_db.embeddings.embed_query,
        )
    except FailedPrecondition as exc:
        # An index still building is one index down: the keyword index may still answer.
        logger.warning("MCP summary vector index not ready")
        vector_ids, vectors_ok, index_error = [], False, exc
    except Exception:
        logger.warning("MCP summary vector search unavailable")
        vector_ids, vectors_ok = [], False
    try:
        keyword_ids = keyword_search_conversation_ids(
            uid,
            query,
            limit=limit,
            start_date=starts_at,
            end_date=ends_at,
            raise_on_error=True,
        )
    except Exception:
        logger.warning("MCP keyword conversation search unavailable")
        keyword_ids, keyword_ok = [], False
    vector_ids = [str(cid) for cid in vector_ids or []]
    keyword_ids = [str(cid) for cid in keyword_ids or []]

    # Date filters must be checked against hydrated storage as well as indexes:
    # stale index metadata must never widen the authorized result window.
    def hydrate(ids: List[str]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        rows = conversations_db.get_mcp_conversations_by_id(
            uid, ids, include_transcript=include_transcript, extra_field_paths=extra_field_paths
        )
        return [
            c
            for c in rows
            if conversation_matches_date_range(
                c, start_dt.timestamp() if start_dt else None, end_dt.timestamp() if end_dt else None
            )
        ]

    ranked = search_views.merge_search_ids(vector_ids, keyword_ids, len(vector_ids) + len(keyword_ids))
    conversations = hydrate(ranked[:limit])
    if len(conversations) < limit and len(ranked) > limit:
        # Stale index ids (deleted or moved records) leave room for the next hits.
        # ranked holds at most 2*limit ids, so this second read stays bounded.
        conversations += hydrate(ranked[limit:])
    # Degraded when either index could not be asked, or no semantic hit survived hydration.
    if not (vectors_ok and keyword_ok) or not any(str(c.get('id')) in set(vector_ids) for c in conversations):
        record_fallback(
            component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded', log=logger
        )
    if not conversations and not keyword_ok and index_error is not None:
        raise_conversation_index_error(index_error)
    if not conversations and not keyword_ok:
        raise ToolExecutionError(
            "No hydrated semantic matches and keyword search is unavailable. "
            "Use get_conversations with a date window; this does not establish that the topic is absent.",
            code=-32009,
            http_status=503,
        )
    return ConversationSearchHits(conversations[:limit], vector_ids, keyword_ids, vectors_ok, keyword_ok)


def search_conversations(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    query = arguments.get("query")
    if not query:
        raise ToolExecutionError("query is required")

    try:
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=10, minimum=1, maximum=100)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")

    start_dt, end_dt, zone = local_date_window(uid, start_date, end_date, arguments.get('timezone'))

    hits = search_conversation_hits(uid, query, limit=limit, start_dt=start_dt, end_dt=end_dt)
    coverage, unavailable = search_views.search_coverage(vectors_ok=hits.vectors_ok, keyword_ok=hits.keyword_ok)
    envelope: Dict[str, Any] = {"search_coverage": coverage, "unavailable_indexes": unavailable}
    if not hits.conversations:
        return {
            "conversations": [],
            **envelope,
            "message": "No indexed matches. Details said only in a transcript may still match: try "
            "search_transcripts with the words as spoken, or browse a date window.",
        }

    results: List[Dict[str, Any]] = []
    for conv in hits.conversations:
        conv = transcribing_hold.project(conv)
        redact_conversation_for_list(conv)
        snippets: List[Dict[str, Any]] = []
        if not conv.get("is_locked", False):
            snippets = (
                attach_match_snippets_to_conversations(
                    [conv],
                    query,
                    max_chars=MCP_CONVERSATION_SEARCH_SNIPPET_CHARS,
                    with_position=True,
                )[0].get("match_snippets")
                or []
            )
        search_views.add_segment_indexes(snippets, conv.get("transcript_segments"))
        card = conversation_card(conv)
        card["match_snippets"] = [public_transcript_timing(snippet) for snippet in snippets]
        card["match_basis"] = search_views.match_basis(
            str(conv.get("id")), hits.vector_ids, hits.keyword_ids, bool(snippets)
        )
        results.append(select_card_fields(card, arguments.get("fields")) | {"match_basis": card["match_basis"]})

    return localize_timestamps({"conversations": results, **envelope, "timezone": str(zone)}, zone)
