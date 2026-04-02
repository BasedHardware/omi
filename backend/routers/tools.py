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
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.retrieval.tool_services.conversations import get_conversations_text, search_conversations_text
from utils.retrieval.tool_services.memories import get_memories_text, search_memories_text
from utils.retrieval.tool_services.action_items import (
    get_action_items_text,
    create_action_item_text,
    update_action_item_text,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------- response envelope ---------------


class ToolResponse(BaseModel):
    tool_name: str
    result_text: str
    is_error: bool = False


def _ok(tool_name: str, text: str) -> dict:
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
):
    result = search_conversations_text(
        uid=uid,
        query=body.query,
        start_date=body.start_date,
        end_date=body.end_date,
        limit=body.limit,
        include_transcript=body.include_transcript,
    )
    return _ok("search_conversations", result)


# --------------- memory endpoints ---------------


@router.get("/v1/tools/memories", response_model=ToolResponse)
def get_memories(
    limit: int = Query(default=50, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    start_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    end_date: Optional[str] = Query(default=None, description="ISO date with timezone"),
    uid: str = Depends(get_current_user_uid),
):
    result = get_memories_text(
        uid=uid,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
    )
    return _ok("get_memories", result)


@router.post("/v1/tools/memories/search", response_model=ToolResponse)
def search_memories(
    body: SearchMemoriesRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "tools:search")),
):
    result = search_memories_text(
        uid=uid,
        query=body.query,
        limit=body.limit,
    )
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
):
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
