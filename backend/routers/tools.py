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
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator

import database.vector_db as vector_db
from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.conversations.transcript_chunks import hydrate_chunk_texts
from utils.retrieval.safety import safe_isoformat
from utils.retrieval.tool_services.conversations import get_conversations_text, search_conversations_text
from utils.retrieval.tool_services.memories import get_memories_text, search_memories_text
from utils.retrieval.tool_result_boundaries import preserve_chat_memory_tool_result_boundary
from utils.retrieval.tool_services.action_items import (
    get_action_items_text,
    create_action_item_text,
    update_action_item_text,
)
from utils.retrieval.tools.calendar_tools import create_calendar_event_tool

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------- response envelope ---------------


class ToolSource(BaseModel):
    kind: str = Field(max_length=32)
    source_id: str = Field(max_length=512)
    title: str = Field(default='', max_length=160)
    preview: str = Field(default='', max_length=600)
    created_at: Optional[str] = Field(default=None, max_length=80)
    moment_timestamp_ms: Optional[int] = None
    app_name: Optional[str] = Field(default=None, max_length=80)
    url: Optional[str] = Field(default=None, max_length=2048)

    @field_validator('url')
    @classmethod
    def require_http_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('url must be an absolute HTTP(S) URL')
        return value


class ToolResponse(BaseModel):
    tool_name: str
    result_text: str
    is_error: bool = False
    sources: list[ToolSource] = Field(default_factory=list)


def _ok(tool_name: str, text: str, sources: Optional[list[dict]] = None) -> dict:
    is_error = text.startswith("Error")
    return {
        "tool_name": tool_name,
        "result_text": text,
        "is_error": is_error,
        "sources": [] if is_error else (sources or []),
    }


# --------------- request models ---------------


class SearchConversationsRequest(BaseModel):
    query: str = Field(description="Natural-language topic, canonical conversation UUID, or h.omi.me share URL")
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


# --------------- conversation endpoints ---------------


@router.get("/v1/tools/conversations", response_model=ToolResponse)
def get_conversations(
    start_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    end_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    limit: int = Query(default=20, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    include_transcript: bool = Query(default=True),
    uid: str = Depends(get_current_user_uid),
):
    sources: list[dict] = []
    result = get_conversations_text(
        uid=uid,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        include_transcript=include_transcript,
        source_sink=sources,
    )
    return _ok("get_conversations", result, sources)


@router.post("/v1/tools/conversations/search", response_model=ToolResponse)
def search_conversations(
    body: SearchConversationsRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:search")),
):
    sources: list[dict] = []
    result = search_conversations_text(
        uid=uid,
        query=body.query,
        start_date=body.start_date,
        end_date=body.end_date,
        limit=body.limit,
        include_transcript=body.include_transcript,
        source_sink=sources,
    )
    return _ok("search_conversations", result, sources)


class SearchChunksRequest(BaseModel):
    query: str = Field(description="Semantic search query")
    limit: int = Field(default=20, ge=1, le=30)


def _transcript_chunk_source(row: dict[str, Any]) -> dict[str, Any]:
    """Typed source for one hydrated chunk row, shaped exactly like the sibling
    conversation sources (`_append_conversation_source`): kind 'conversation' with
    the PARENT conversation id, so chunk citations share the summary results' ref
    namespace and no client citation validation changes. The preview is the
    verbatim excerpt flattened to one line — it is quoted into client prompts, so
    it must not be able to forge line-oriented prompt structure."""
    created_at: Optional[str] = None
    ts = row.get('created_at')
    if isinstance(ts, (int, float)) and ts > 0:
        created_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    else:
        created_at = safe_isoformat(row.get('conversation_started_at'))
    return {
        'kind': 'conversation',
        'source_id': str(row['conversation_id']),
        'title': str(row.get('conversation_title') or 'Conversation')[:160],
        'preview': ' '.join(str(row.get('text') or '').split())[:600],
        'created_at': created_at,
    }


@router.post("/v1/tools/conversations/search-chunks", response_model=ToolResponse)
def search_conversation_chunks(
    body: SearchChunksRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:search")),
):
    """Semantic search over RAW transcript chunks (verbatim evidence with dates).

    Complements /conversations/search, which matches against conversation summaries:
    summaries drop specifics (exact dates, names, numbers), so detail questions need
    this verbatim layer. Returns chunks newest-relevant with their conversation date,
    plus typed sources (one per parent conversation, best chunk first) so clients can
    cite verbatim evidence the same way they cite summary results.
    """
    rows = vector_db.search_transcript_chunks(uid, body.query, limit=body.limit)
    rows = hydrate_chunk_texts(uid, rows)
    if not rows:
        return _ok("search_conversation_chunks", f"No transcript excerpts found matching '{body.query}'.")
    parts = []
    sources: list[dict] = []
    seen_conversation_ids: set[str] = set()
    for i, r in enumerate(rows, 1):
        parts.append(f"Excerpt {i} (relevance: {r['score']:.2f}):\n{r['text']}")
        conversation_id = r.get('conversation_id')
        if not conversation_id or conversation_id in seen_conversation_ids:
            continue
        seen_conversation_ids.add(conversation_id)
        sources.append(_transcript_chunk_source(r))
    return _ok("search_conversation_chunks", "\n\n".join(parts), sources)


# --------------- memory endpoints ---------------


@router.get("/v1/tools/memories", response_model=ToolResponse)
def get_memories(
    limit: int = Query(default=50, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    start_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    end_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    uid: str = Depends(get_current_user_uid),
):
    sources: list[dict] = []
    result = get_memories_text(
        uid=uid,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
        source_sink=sources,
    )
    bounded_result = preserve_chat_memory_tool_result_boundary('get_memories_tool', result)
    if bounded_result != result:
        sources = []
    result = bounded_result
    return _ok("get_memories", result, sources)


@router.post("/v1/tools/memories/search", response_model=ToolResponse)
def search_memories(
    body: SearchMemoriesRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:search")),
):
    sources: list[dict] = []
    result = search_memories_text(
        uid=uid,
        query=body.query,
        limit=body.limit,
        source_sink=sources,
    )
    bounded_result = preserve_chat_memory_tool_result_boundary('search_memories_tool', result)
    if bounded_result != result:
        sources = []
    result = bounded_result
    return _ok("search_memories", result, sources)


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
):
    sources: list[dict] = []
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
        source_sink=sources,
    )
    return _ok("get_action_items", result, sources)


@router.post("/v1/tools/action-items", response_model=ToolResponse)
def create_action_item(
    body: CreateActionItemRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:mutate")),
):
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
):
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
):
    result = await create_calendar_event_tool.ainvoke(
        {
            "title": body.title,
            "start_time": body.start_time.isoformat(),
            "end_time": body.end_time.isoformat(),
            "description": body.description,
            "location": body.location,
            "attendees": body.attendees,
        },
        config={"configurable": {"user_id": uid}},
    )
    return {
        "tool_name": "create_calendar_event",
        "result_text": result,
        "is_error": not result.startswith("✅ Successfully created calendar event:"),
    }
