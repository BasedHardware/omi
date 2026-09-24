"""Conversation tool handlers for the hosted MCP server."""

from typing import Any, Dict, List, Optional, cast

from google.api_core.exceptions import FailedPrecondition

import database.conversations as conversations_db
import database.vector_db as vector_db
from models.conversation_enums import CategoryEnum
from utils.conversations.mcp_transcript_search import (
    attach_match_snippets_to_conversations,
    resolve_mcp_conversation_search_ids,
)
from utils.conversations.render import redact_conversation_for_list
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_data import end_of_day_utc
from utils.mcp_memories import parse_mcp_int
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
    serialize_timestamp,
)
from utils.mcp_server.errors import ToolExecutionError, raise_conversation_index_error
from utils.mcp_server.helpers import (
    bounded_transcript_segments,
    conversation_card,
    parse_mcp_date,
)
from utils.mcp_server.payloads import tool_response_serialized_chars


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

    start_dt = parse_mcp_date(start_date, "start_date")
    end_dt = parse_mcp_date(end_date, "end_date")
    if end_dt is not None:
        # Include the entire end day, matching the integration-router convention.
        end_dt = end_of_day_utc(end_dt)

    valid_categories: List[str] = []
    for cat in categories_list:
        try:
            valid_categories.append(CategoryEnum(cat).value)
        except ValueError:
            pass

    filters = {
        "categories": sorted(valid_categories),
        "start": start_dt.isoformat() if start_dt else None,
        "end": end_dt.isoformat() if end_dt else None,
    }
    after = None
    cursor_token = arguments.get("cursor")
    if cursor_token is not None:
        if offset != 0:
            raise ToolExecutionError("cursor and offset are mutually exclusive.", code=-32602)
        after = conversation_keyset_position(
            decode_cursor(cursor_token, kind="get_conversations", uid=uid, filters=filters)
        )

    if cursor_token is None and offset != 0:
        try:
            fetched = conversations_db.get_mcp_conversation_cards(
                uid,
                limit,
                offset,
                start_date=start_dt,
                end_date=end_dt,
                categories=valid_categories,
            )
        except FailedPrecondition as e:
            raise_conversation_index_error(e)
        return {"conversations": [conversation_card(conversation) for conversation in fetched]}

    try:
        page, resume = conversations_db.get_mcp_conversation_cards_page(
            uid,
            limit,
            after=after,
            start_date=start_dt,
            end_date=end_dt,
            categories=valid_categories,
        )
    except FailedPrecondition as e:
        raise_conversation_index_error(e)

    result: Dict[str, Any] = {"conversations": [conversation_card(conversation) for conversation in page]}
    if resume is not None:
        result["next_cursor"] = encode_cursor(
            kind="get_conversations",
            uid=uid,
            position={"ts": serialize_timestamp(resume[0]), "id": resume[1]},
            filters=filters,
        )
    return result


def get_conversation_by_id(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    conversation_id = arguments.get("conversation_id")
    if not conversation_id:
        raise ToolExecutionError("conversation_id is required")

    max_segments, max_chars = _conversation_fetch_bounds(arguments)

    conversations = conversations_db.get_mcp_conversations_by_id(
        uid,
        [str(conversation_id)],
        include_transcript=True,
        include_discarded=True,
    )
    if not conversations:
        raise ToolExecutionError("Conversation not found", code=-32001)
    conversation = conversations[0]

    if conversation.get('is_locked', False):
        raise ToolExecutionError("A paid plan is required to access this conversation.", code=-32002)

    transcript_segments, truncated = bounded_transcript_segments(
        conversation.get("transcript_segments"),
        max_segments=max_segments,
        max_chars=max_chars,
    )
    result = conversation_card(conversation)
    result["transcript_segments"] = transcript_segments
    return {"conversation": result, "truncated": truncated}


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
    """Fetch several conversations in one bounded read.

    One ``get_all`` Firestore batch read serves the whole id list. Each
    returned item mirrors ``get_conversation_by_id`` (card + bounded
    transcript + per-item ``truncated``); a locked conversation yields a
    per-item paid-plan error so its transcript never reaches the response,
    and ids that resolve to nothing land in ``not_found``. Items are appended
    in request order until the serialized response would exceed
    ``MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS`` — later items are then
    omitted (NOT marked not_found) and the top-level ``truncated`` flag is
    set so the caller can retry the remainder with tighter bounds.
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
        if (
            not isinstance(raw_id, str)
            or not raw_id
            or len(raw_id.encode("utf-8")) > MCP_CONVERSATION_ID_MAX_BYTES
            or "/" in raw_id
        ):
            raise ToolExecutionError(
                "conversation_ids entries must be valid Firestore document ids "
                f"(non-empty, <= {MCP_CONVERSATION_ID_MAX_BYTES} UTF-8 bytes, no '/')",
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
        include_discarded=True,
    )
    by_id = {str(conversation.get("id")): conversation for conversation in conversations}
    not_found = [conversation_id for conversation_id in conversation_ids if conversation_id not in by_id]

    items: List[Dict[str, Any]] = []
    truncated_response = False
    for conversation_id in conversation_ids:
        conversation = by_id.get(conversation_id)
        if conversation is None:
            continue
        if conversation.get("is_locked", False):
            item: Dict[str, Any] = {
                "id": conversation_id,
                "error": {
                    "code": "paid_plan_required",
                    "message": "A paid plan is required to access this conversation.",
                },
            }
        else:
            transcript_segments, truncated = bounded_transcript_segments(
                conversation.get("transcript_segments"),
                max_segments=max_segments,
                max_chars=max_chars,
            )
            card = conversation_card(conversation)
            card["transcript_segments"] = transcript_segments
            item = {"id": conversation_id, "conversation": card, "truncated": truncated}
        # The transport emits the result twice (text + structuredContent)
        # inside the JSON-RPC envelope, so the budget is measured against the
        # largest serialized form, not the inner object. `truncated: false`
        # serializes one char wider than `true`, keeping the probe safe.
        candidate = {"conversations": items + [item], "not_found": not_found, "truncated": False}
        if tool_response_serialized_chars(candidate) > MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS:
            truncated_response = True
            break
        items.append(item)

    return {"conversations": items, "not_found": not_found, "truncated": truncated_response}


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

    # Parse dates to epoch for vector search (UTC-anchored so the filter matches the
    # vector index's UTC epoch created_at; end bound includes the full end day).
    start_dt = parse_mcp_date(start_date, "start_date")
    end_dt = parse_mcp_date(end_date, "end_date")
    starts_at = int(start_dt.timestamp()) if start_dt is not None else None
    if end_dt is not None:
        end_dt = end_of_day_utc(end_dt)
    ends_at = int(end_dt.timestamp()) if end_dt is not None else None

    try:
        conversation_ids = resolve_mcp_conversation_search_ids(
            uid,
            query,
            limit=limit,
            starts_at=starts_at,
            ends_at=ends_at,
            query_vectors=vector_db.query_vectors,
            search_transcript_chunks=vector_db.search_transcript_chunks,
            embed_query=vector_db.embeddings.embed_query,
        )
    except FailedPrecondition as e:
        raise_conversation_index_error(e)
    if not conversation_ids:
        return {"conversations": []}

    try:
        conversations = conversations_db.get_mcp_conversations_by_id(
            uid,
            conversation_ids,
            include_transcript=True,
        )
    except FailedPrecondition as e:
        raise_conversation_index_error(e)

    results: List[Dict[str, Any]] = []
    for conv in conversations:
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
        card["match_snippets"] = snippets
        results.append(card)

    return {"conversations": results}
