"""
Platform tools router — exposes backend tools as REST endpoints for any client.

Unlike /v1/agent/execute-tool (which wraps LangChain tools for VM agents),
these endpoints are direct REST with proper HTTP semantics, designed for
desktop, web, and mobile agent clients.

Endpoints:
- GET   /v1/tools/conversations          — list conversations
- POST  /v1/tools/conversations/search   — semantic search conversations
- GET   /v1/tools/memories               — list memories/facts
- POST  /v1/tools/memories/search        — semantic search memories
- GET   /v1/tools/action-items           — list action items
- POST  /v1/tools/action-items           — create action item
- PATCH /v1/tools/action-items/{id}      — update action item
- POST  /v1/tools/calendar-events        — create calendar event
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator

import database.vector_db as vector_db

# `utils.other.endpoints.with_rate_limit` and
# `utils.conversations.transcript_chunks.hydrate_chunk_texts` are untyped; reach
# them through getattr + cast so the untyped symbol never lands in a typed binding.
from utils.conversations import transcript_chunks as _chunk_utils
from utils.other import endpoints as _endpoints
from utils.other.endpoints import get_current_user_uid
from utils.retrieval.tool_result_boundaries import preserve_chat_memory_tool_result_boundary
from utils.retrieval.tool_services.action_items import (
    create_action_item_text,
    get_action_items_text,
    update_action_item_text,
)
from utils.retrieval.tool_services.conversations import get_conversations_text, search_conversations_text
from utils.retrieval.tool_services.memories import get_memories_text, search_memories_text
from utils.retrieval.tools.calendar_tools import create_calendar_event_tool

logger = logging.getLogger(__name__)

router = APIRouter()

# Typed aliases for untyped utils (getattr yields Any; cast pins the signature).
RateLimitFactory = Callable[[Callable[..., Any], str], Callable[..., Any]]
with_rate_limit: RateLimitFactory = cast(RateLimitFactory, getattr(_endpoints, "with_rate_limit"))
HydrateChunks = Callable[[str, List[Dict[str, Any]]], List[Dict[str, Any]]]
hydrate_chunk_texts: HydrateChunks = cast(HydrateChunks, getattr(_chunk_utils, "hydrate_chunk_texts"))


# --------------- response envelope ---------------


class ToolResponse(BaseModel):
    tool_name: str
    result_text: str
    is_error: bool = False


def _ok(tool_name: str, text: str) -> Dict[str, Any]:
    return {"tool_name": tool_name, "result_text": text, "is_error": text.startswith("Error")}


# --------------- request models ---------------


class SearchConversationsRequest(BaseModel):
    query: str = Field(description="Semantic search query")
    start_date: Optional[str] = Field(default=None, description="ISO date with timezone")
    end_date: Optional[str] = Field(default=None, description="ISO date with timezone")
    limit: int = Field(default=5, ge=1, le=20)
    include_transcript: bool = Field(default=True)


class SearchMemoriesRequest(BaseModel):
    query: str = Field(description="Semantic search query")
    limit: int = Field(default=5, ge=1, le=20)


class CreateActionItemRequest(BaseModel):
    description: str = Field(description="Action item description")
    due_at: Optional[str] = Field(default=None, description="ISO date with timezone")
    conversation_id: Optional[str] = Field(default=None, description="Source conversation ID")


class UpdateActionItemRequest(BaseModel):
    completed: Optional[bool] = Field(default=None)
    description: Optional[str] = Field(default=None)
    due_at: Optional[str] = Field(default=None, description="ISO date with timezone")


class CreateCalendarEventRequest(BaseModel):
    title: str = Field(description="Event title")
    start_time: datetime = Field(description="ISO date/time with timezone")
    end_time: datetime = Field(description="ISO date/time with timezone")
    description: Optional[str] = Field(default=None, description="Event description")
    location: Optional[str] = Field(default=None, description="Event location")
    attendees: Optional[str] = Field(default=None, description="Comma-separated attendee names or email addresses")

    @field_validator('start_time', 'end_time')
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError('datetime must include timezone')
        return value


async def _invoke_calendar_event_tool(tool_input: Dict[str, Any], user_id: str) -> str:
    """Typed adapter for the untyped LangChain `create_calendar_event_tool.ainvoke`."""
    result = await create_calendar_event_tool.ainvoke(  # type: ignore[reportUnknownMemberType]  # langchain Tool.ainvoke is untyped
        tool_input,
        config={"configurable": {"user_id": user_id}},
    )
    return cast(str, result)


# --------------- conversation endpoints ---------------


@router.get("/v1/tools/conversations", response_model=ToolResponse)
def get_conversations(
    start_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    end_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    limit: int = Query(default=20, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    include_transcript: bool = Query(default=True),
    uid: str = Depends(get_current_user_uid),
) -> Dict[str, Any]:
    result = get_conversations_text(
        uid=uid,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        include_transcript=include_transcript,
    )
    return _ok("get_conversations", result)


@router.post("/v1/tools/conversations/search", response_model=ToolResponse)
def search_conversations(
    body: SearchConversationsRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:search")),
) -> Dict[str, Any]:
    result = search_conversations_text(
        uid=uid,
        query=body.query,
        start_date=body.start_date,
        end_date=body.end_date,
        limit=body.limit,
        include_transcript=body.include_transcript,
    )
    return _ok("search_conversations", result)


class SearchChunksRequest(BaseModel):
    query: str = Field(description="Semantic search query")
    limit: int = Field(default=20, ge=1, le=30)


@router.post("/v1/tools/conversations/search-chunks", response_model=ToolResponse)
def search_conversation_chunks(
    body: SearchChunksRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:search")),
) -> Dict[str, Any]:
    """Semantic search over RAW transcript chunks (verbatim evidence with dates).

    Complements /conversations/search, which matches against conversation summaries:
    summaries drop specifics (exact dates, names, numbers), so detail questions need
    this verbatim layer. Returns chunks newest-relevant with their conversation date.
    """
    rows = vector_db.search_transcript_chunks(uid, body.query, limit=body.limit)
    rows = hydrate_chunk_texts(uid, rows)
    if not rows:
        return _ok("search_conversation_chunks", f"No transcript excerpts found matching '{body.query}'.")
    parts: List[str] = []
    for i, r in enumerate(rows, 1):
        parts.append(f"Excerpt {i} (relevance: {r['score']:.2f}):\n{r['text']}")
    return _ok("search_conversation_chunks", "\n\n".join(parts))


# --------------- memory endpoints ---------------


@router.get("/v1/tools/memories", response_model=ToolResponse)
def get_memories(
    limit: int = Query(default=50, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    start_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    end_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    uid: str = Depends(get_current_user_uid),
) -> Dict[str, Any]:
    result = get_memories_text(
        uid=uid,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
    )
    result = preserve_chat_memory_tool_result_boundary('get_memories_tool', result)
    return _ok("get_memories", result)


@router.post("/v1/tools/memories/search", response_model=ToolResponse)
def search_memories(
    body: SearchMemoriesRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:search")),
) -> Dict[str, Any]:
    result = search_memories_text(
        uid=uid,
        query=body.query,
        limit=body.limit,
    )
    result = preserve_chat_memory_tool_result_boundary('search_memories_tool', result)
    return _ok("search_memories", result)


# --------------- action item endpoints ---------------


@router.get("/v1/tools/action-items", response_model=ToolResponse)
def get_action_items(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    completed: Optional[bool] = Query(default=None),
    conversation_id: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    end_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    due_start_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    due_end_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    uid: str = Depends(get_current_user_uid),
) -> Dict[str, Any]:
    result = get_action_items_text(
        uid=uid,
        limit=limit,
        offset=offset,
        completed=completed,
        conversation_id=conversation_id,
        start_date=start_date,
        end_date=end_date,
        due_start_date=due_start_date,
        due_end_date=due_end_date,
    )
    return _ok("get_action_items", result)


@router.post("/v1/tools/action-items", response_model=ToolResponse)
def create_action_item(
    body: CreateActionItemRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:mutate")),
) -> Dict[str, Any]:
    result = create_action_item_text(
        uid=uid,
        description=body.description,
        due_at=body.due_at,
        conversation_id=body.conversation_id,
    )
    return _ok("create_action_item", result)


@router.patch("/v1/tools/action-items/{action_item_id}", response_model=ToolResponse)
def update_action_item(
    action_item_id: str,
    body: UpdateActionItemRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:mutate")),
) -> Dict[str, Any]:
    result = update_action_item_text(
        uid=uid,
        action_item_id=action_item_id,
        completed=body.completed,
        description=body.description,
        due_at=body.due_at,
    )
    return _ok("update_action_item", result)


# --------------- calendar endpoints ---------------


@router.post("/v1/tools/calendar-events", response_model=ToolResponse)
async def create_calendar_event(
    body: CreateCalendarEventRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:mutate")),
) -> Dict[str, Any]:
    result = await _invoke_calendar_event_tool(
        {
            "title": body.title,
            "start_time": body.start_time.isoformat(),
            "end_time": body.end_time.isoformat(),
            "description": body.description,
            "location": body.location,
            "attendees": body.attendees,
        },
        user_id=uid,
    )
    return {
        "tool_name": "create_calendar_event",
        "result_text": result,
        "is_error": not result.startswith("✅ Successfully created calendar event:"),
    }
