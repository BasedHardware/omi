"""Conversation tool handlers for the hosted MCP server."""

import logging

from utils.other.list_budget import ListReadBudget

from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException
from google.api_core.exceptions import FailedPrecondition

import database.conversations as conversations_db
import database.mcp_conversation_pages as mcp_conversation_pages
import database.vector_db as vector_db
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
    MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS,
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
from utils.mcp_server.errors import ToolExecutionError, raise_conversation_index_error
from utils.mcp_server.helpers import (
    bounded_transcript_segments,
    conversation_card,
    public_transcript_timing,
    select_card_fields,
)
from utils.mcp_server.payloads import tool_response_serialized_chars

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
    conversations = conversations_db.get_mcp_conversations_by_id(
        uid,
        [str(conversation_id)],
        include_transcript=True,
        include_discarded=False,
        extra_field_paths=extra_field_paths,
    )
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

    conversation = fetch_conversation_for_detail(uid, conversation_id)
    if conversation is None:
        raise ToolExecutionError(
            "Conversation not found. Use the full id from get_conversations; shortened id prefixes are not document ids.",
            code=-32001,
        )

    if conversation.get('is_locked', False):
        raise ToolExecutionError("A paid plan is required to access this conversation.", code=-32002)

    transcript_segments, truncated = bounded_transcript_segments(
        conversation.get("transcript_segments"),
        max_segments=max_segments,
        max_chars=max_chars,
    )
    try:
        include_participants = parse_mcp_bool(
            arguments.get("include_participants"), "include_participants", default=True
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc), code=-32602) from exc
    result = conversation_card(conversation, include_participants=include_participants)
    try:
        summary_only = parse_mcp_bool(arguments.get("summary_only"), "summary_only", default=False)
    except ValueError as exc:
        raise ToolExecutionError(str(exc), code=-32602) from exc
    if not summary_only:
        result["transcript_segments"] = transcript_segments
    return {
        "conversation": select_card_fields(result, arguments.get("fields")),
        "truncated": truncated and not summary_only,
    }


def _conversation_fetch_bounds(arguments: Dict[str, Any]) -> tuple[int, int]:
    """Parse the shared max_segments/max_chars bounds used by transcript reads."""
    try:
        max_segments = parse_mcp_int(
            arguments.get("max_segments"),
            "max_segments",
            default=MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS,
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

    # Exactly one batch document read for the whole id list.
    conversations = conversations_db.get_mcp_conversations_by_id(
        uid,
        conversation_ids,
        include_transcript=True,
        include_discarded=False,
    )
    by_id = {str(conversation.get("id")): transcribing_hold.project(conversation) for conversation in conversations}
    not_found = [conversation_id for conversation_id in conversation_ids if conversation_id not in by_id]

    filters = {
        'ids': conversation_ids,
        'max_segments': max_segments,
        'max_chars': max_chars,
        'fields': arguments.get('fields'),
        'summary_only': arguments.get('summary_only', False),
        'include_participants': arguments.get('include_participants', True),
    }
    offset = 0
    if arguments.get('cursor') is not None:
        offset = offset_position(
            decode_cursor(arguments['cursor'], kind='get_conversations_by_ids', uid=uid, filters=filters)
        )
    try:
        summary_only = parse_mcp_bool(arguments.get('summary_only'), 'summary_only', default=False)
        include_participants = parse_mcp_bool(
            arguments.get('include_participants'), 'include_participants', default=True
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc), code=-32602) from exc
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
        card = conversation_card(conversation, include_participants=include_participants)
        segments, clipped = bounded_transcript_segments(
            conversation.get('transcript_segments'), max_segments=max_segments, max_chars=max_chars
        )
        if not summary_only:
            card['transcript_segments'] = segments
        return {
            'id': cid,
            'conversation': select_card_fields(card, arguments.get('fields')),
            'truncated': clipped and not summary_only,
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
                    'Retry with include_participants=false, fewer fields, or smaller max_segments/max_chars.',
                    code=-32602,
                )
            break
        items.append(candidate)
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
    """Shared vector-search + batch-read for MCP ``search_conversations`` and REST search.

    Dates arrive already parsed; the caller applies its own input convention
    (date-only end-of-day for the tool, exact instants for REST).
    """
    start_dt, end_dt = _utc_search_window(start_dt, end_dt)
    starts_at = int(start_dt.timestamp()) if start_dt is not None else None
    ends_at = int(end_dt.timestamp()) if end_dt is not None else None

    # Date filters must be checked against hydrated storage as well as indexes:
    # stale index metadata must never widen the authorized result window.
    try:
        conversation_ids = resolve_mcp_conversation_search_ids(
            uid,
            query,
            limit=limit,
            starts_at=starts_at,
            ends_at=ends_at,
            query_vectors=vector_db.query_vectors,
            embed_query=vector_db.embeddings.embed_query,
        )
    except FailedPrecondition as exc:
        raise_conversation_index_error(exc)
    except Exception:
        logger.warning("MCP summary vector search unavailable")
        conversation_ids = []
    conversations = (
        conversations_db.get_mcp_conversations_by_id(
            uid,
            conversation_ids,
            include_transcript=include_transcript,
            extra_field_paths=extra_field_paths,
        )
        if conversation_ids
        else []
    )
    conversations = [
        c
        for c in conversations
        if conversation_matches_date_range(
            c, start_dt.timestamp() if start_dt else None, end_dt.timestamp() if end_dt else None
        )
    ]
    if conversations:
        return conversations[:limit]

    record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded', log=logger)
    try:
        keyword_ids = keyword_search_conversation_ids(
            uid,
            query,
            limit=limit,
            start_date=starts_at,
            end_date=ends_at,
            raise_on_error=True,
        )
    except Exception as exc:
        raise ToolExecutionError(
            "No hydrated semantic matches and keyword search is unavailable. "
            "Use get_conversations with a date window; this does not establish that the topic is absent.",
            code=-32009,
            http_status=503,
        ) from exc
    if not keyword_ids:
        return []
    rows = conversations_db.get_mcp_conversations_by_id(
        uid,
        keyword_ids,
        include_transcript=include_transcript,
        extra_field_paths=extra_field_paths,
    )
    return [
        c
        for c in rows
        if conversation_matches_date_range(
            c, start_dt.timestamp() if start_dt else None, end_dt.timestamp() if end_dt else None
        )
    ][:limit]


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

    conversations = search_conversations_core(
        uid,
        query,
        limit=limit,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    if not conversations:
        return {
            "conversations": [],
            "search_coverage": "summary_vectors_and_keyword_recovery",
            "message": "No indexed matches. Unindexed content may still match; browse a date window.",
        }

    results: List[Dict[str, Any]] = []
    for conv in conversations:
        conv = transcribing_hold.project(conv)
        redact_conversation_for_list(conv)
        snippets: List[Dict[str, Any]] = []
        if not conv.get("is_locked", False):
            snippets = (
                attach_match_snippets_to_conversations(
                    [conv],
                    query,
                    max_chars=MCP_CONVERSATION_SEARCH_SNIPPET_CHARS,
                )[
                    0
                ].get("match_snippets")
                or []
            )
        card = conversation_card(conv)
        card["match_snippets"] = [public_transcript_timing(snippet) for snippet in snippets]
        results.append(select_card_fields(card, arguments.get("fields")))

    return localize_timestamps(
        {"conversations": results, "search_coverage": "summary_vectors_with_keyword_recovery", "timezone": str(zone)},
        zone,
    )
