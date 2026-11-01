"""Developer read endpoints backed by the same handlers as hosted MCP."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from dependencies import (
    ApiKeyAuth,
    get_api_key_auth,
    get_auth_with_conversations_read,
    get_developer_memory_default_memory_read_context,
    check_developer_api_key_rate_limit,
)
from utils.external_read_contract import reject_unknown_query, utc_window
from utils.scopes import has_scope
from utils.memory.product_authorization import ProductAuthorizationContext

router = APIRouter()


class ConversationSearchResponse(BaseModel):
    conversations: List[Dict[str, Any]] = Field(default_factory=list)
    search_coverage: str
    message: Optional[str] = None


class MemorySearchResponse(BaseModel):
    memories: List[Dict[str, Any]] = Field(default_factory=list)
    effective_limit: int = 20
    search_coverage: str
    message: Optional[str] = None


class PeopleResponse(BaseModel):
    people: List[Dict[str, Any]] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    profile: Optional[Dict[str, Any]] = None
    profile_text: Optional[str] = None
    generated_at: Optional[Any] = None
    data_sources_used: Optional[Any] = None
    message: Optional[str] = None


class ScreenActivityResponse(BaseModel):
    screen_activity: List[Dict[str, Any]] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    has_more: bool


def external_read_scope(scope: str):
    async def authorize(request: Request, auth: ApiKeyAuth = Depends(get_api_key_auth)) -> ApiKeyAuth:
        if not has_scope(auth.scopes, scope):
            raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {scope}")
        # Share the existing read ceiling; new endpoints cannot multiply a key's budget.
        await check_developer_api_key_rate_limit(request=request, auth=auth, policy_name="dev:conversations_read")
        return auth

    return authorize


def _tool_call(handler, uid: str, arguments: dict, auth_context=None):
    from utils.mcp_server.errors import ToolExecutionError

    try:
        return handler(uid, arguments, auth_context)
    except ToolExecutionError as exc:
        raise HTTPException(
            status_code=exc.http_status or (400 if exc.code == -32602 else 503), detail=exc.message
        ) from exc


@router.get(
    '/v1/dev/user/conversations/search',
    tags=['Conversations'],
    operation_id='searchConversations',
    response_model=ConversationSearchResponse,
)
def search_conversations(
    request: Request,
    query: str = Query(..., min_length=1, max_length=2000),
    limit: int = Query(10, ge=1, le=100),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    auth: ApiKeyAuth = Depends(get_auth_with_conversations_read),
):
    from utils.mcp_server.handlers.conversations import search_conversations_core
    from utils.mcp_server.helpers import conversation_card
    from utils.mcp_server.errors import ToolExecutionError

    reject_unknown_query(request, {'query', 'limit', 'start_date', 'end_date'})
    start_date, end_date = utc_window(start_date, end_date)
    if not query.strip():
        raise HTTPException(status_code=400, detail='query must not be blank')
    try:
        rows = search_conversations_core(
            auth.uid,
            query,
            limit=limit,
            start_dt=start_date,
            end_dt=end_date,
            include_transcript=False,
        )
    except ToolExecutionError as exc:
        raise HTTPException(status_code=exc.http_status or 503, detail=exc.message) from exc
    return {
        'conversations': [conversation_card(row, include_display=False) for row in rows],
        'search_coverage': 'summary_vectors_with_keyword_recovery',
        'message': 'Unindexed content may still match; browse a date window.' if not rows else None,
    }


@router.get(
    '/v1/dev/user/memories/search',
    tags=['Memories'],
    operation_id='searchMemories',
    response_model=MemorySearchResponse,
)
def search_memories(
    request: Request,
    query: str = Query(..., min_length=1, max_length=2000),
    limit: int = Query(10, ge=1, le=20),
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_read_context),
):
    from database._client import db
    from utils.memory.product_authorization import authorize_memory_external_default_memory_read
    from utils.mcp_server.handlers.memories import search_memories_core

    reject_unknown_query(request, {'query', 'limit'})
    if not query.strip():
        raise HTTPException(status_code=400, detail='query must not be blank')
    grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not grant.allowed:
        raise HTTPException(status_code=grant.status_code, detail='This credential is not permitted to read memories.')
    return search_memories_core(auth_context.uid, query, limit=limit)


@router.get('/v1/dev/user/people', tags=['People'], operation_id='listPeople', response_model=PeopleResponse)
def get_people(request: Request, auth: ApiKeyAuth = Depends(external_read_scope('people:read'))):
    from utils.mcp_server.handlers.other import get_people as handler

    reject_unknown_query(request, set())
    return _tool_call(handler, auth.uid, {})


@router.get(
    '/v1/dev/user/profile',
    tags=['Profile'],
    operation_id='getUserProfile',
    response_model=ProfileResponse,
    response_model_exclude_unset=True,
)
def get_profile(request: Request, auth: ApiKeyAuth = Depends(external_read_scope('profile:read'))):
    from utils.mcp_server.handlers.profile import get_user_profile

    reject_unknown_query(request, set())
    return _tool_call(get_user_profile, auth.uid, {})


@router.get(
    '/v1/dev/user/screen-activity',
    tags=['Screen Activity'],
    operation_id='listScreenActivity',
    response_model=ScreenActivityResponse,
)
def get_screen_activity(
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    app: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = None,
    auth: ApiKeyAuth = Depends(external_read_scope('screen_activity:read')),
):
    from utils.mcp_server.handlers.other import screen_activity_core
    from utils.mcp_server.helpers import parse_mcp_date
    from utils.mcp_data import end_of_day_utc
    from utils.mcp_server.errors import ToolExecutionError

    reject_unknown_query(request, {'start_date', 'end_date', 'app', 'limit', 'cursor'})
    try:
        start = parse_mcp_date(start_date, 'start_date')
        end = parse_mcp_date(end_date, 'end_date')
        end = end_of_day_utc(end) if end is not None else None
        utc_window(start, end)
        result = screen_activity_core(
            auth.uid,
            start=start,
            end=end,
            app=app,
            summary=False,
            group_by='none',
            limit=limit,
            cursor_token=cursor,
            cursor_kind='developer_screen_activity',
        )
    except ToolExecutionError as exc:
        raise HTTPException(
            status_code=exc.http_status or (400 if exc.code == -32602 else 503), detail=exc.message
        ) from exc
    result['has_more'] = bool(result.get('next_cursor'))
    return result
