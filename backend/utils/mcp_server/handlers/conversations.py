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
    MCP_CONVERSATION_FETCH_DEFAULT_MAX_CHARS,
    MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS,
    MCP_CONVERSATION_FETCH_MAX_CHARS,
    MCP_CONVERSATION_FETCH_MAX_SEGMENTS,
    MCP_CONVERSATION_LIST_MAX_LIMIT,
    MCP_CONVERSATION_SEARCH_SNIPPET_CHARS,
)
from utils.mcp_server.errors import ToolExecutionError, raise_conversation_index_error
from utils.mcp_server.helpers import (
    bounded_transcript_segments,
    conversation_card,
    parse_mcp_date,
)


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

    try:
        conversations = conversations_db.get_mcp_conversation_cards(
            uid,
            limit,
            offset,
            start_date=start_dt,
            end_date=end_dt,
            categories=valid_categories,
        )
    except FailedPrecondition as e:
        raise_conversation_index_error(e)

    return {"conversations": [conversation_card(conversation) for conversation in conversations]}


def get_conversation_by_id(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    conversation_id = arguments.get("conversation_id")
    if not conversation_id:
        raise ToolExecutionError("conversation_id is required")

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
