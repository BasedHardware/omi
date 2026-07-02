"""Chat sessions and messages (v2).

Chat sessions (v2) provide multi-session chat with title, preview, and starring.
Messages are persistence-only writes (no LLM streaming) — they use
/v2/desktop/messages to avoid conflict with chat.py's /v2/messages which
streams AI responses.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

import database.chat as chat_db
import database.llm_usage as llm_usage_db
from database.users import set_chat_message_rating_score
from utils.chat import initial_message_util
from utils.llm.clients import get_llm
from utils.auth_middleware import require_firebase
from utils.other.endpoints import rate_limit_dep

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_firebase)])


# ============================================================================
# MODELS
# ============================================================================


class CreateChatSessionRequest(BaseModel):
    title: str | None = Field(None, max_length=500)
    app_id: str | None = Field(None, max_length=200)


class UpdateChatSessionRequest(BaseModel):
    title: str | None = Field(None, max_length=500)
    starred: bool | None = None


class SaveMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100000)
    sender: str = Field(..., pattern=r'^(human|ai)$')
    app_id: str | None = Field(None, max_length=200)
    session_id: str | None = Field(None, max_length=200)
    metadata: str | None = None
    client_message_id: str | None = Field(None, pattern=r'^[A-Za-z0-9_-]{1,128}$')
    message_source: str = Field('desktop_chat', pattern=r'^(desktop_chat|realtime_voice)$')


class RateMessageRequest(BaseModel):
    rating: int | None = Field(None, ge=-1, le=1)
    app_version: str | None = None


class InitialMessageRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    app_id: str | None = None


class TitleMessageInput(BaseModel):
    text: str
    sender: str


class GenerateTitleRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    messages: List[TitleMessageInput] = Field(..., min_length=1, max_length=50)


# ============================================================================
# CHAT SESSION ENDPOINTS
# ============================================================================


@router.post('/v2/chat-sessions', tags=['chat-sessions'])
def create_chat_session(http_request: Request, body: CreateChatSessionRequest):
    uid = http_request.state.uid
    return chat_db.create_chat_session(uid, title=body.title, app_id=body.app_id)


@router.get('/v2/chat-sessions', tags=['chat-sessions'])
def get_chat_sessions(
    http_request: Request,
    app_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    starred: bool | None = Query(None),
):
    uid = http_request.state.uid
    return chat_db.get_chat_sessions(uid, app_id=app_id, limit=limit, offset=offset, starred=starred)


@router.get('/v2/chat-sessions/{session_id}', tags=['chat-sessions'])
def get_chat_session(http_request: Request, session_id: str):
    uid = http_request.state.uid
    result = chat_db.get_chat_session_by_id(uid, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.patch('/v2/chat-sessions/{session_id}', tags=['chat-sessions'])
def update_chat_session(http_request: Request, session_id: str, body: UpdateChatSessionRequest):
    uid = http_request.state.uid
    result = chat_db.update_chat_session(uid, session_id, title=body.title, starred=body.starred)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.delete('/v2/chat-sessions/{session_id}', tags=['chat-sessions'])
def delete_chat_session(http_request: Request, session_id: str):
    uid = http_request.state.uid
    chat_db.delete_chat_session(uid, session_id, cascade_messages=True)
    return {'status': 'ok'}


# ============================================================================
# MESSAGE ENDPOINTS
# Uses /v2/desktop/messages to avoid conflict with chat.py's /v2/messages
# (chat.py POST streams AI responses; these are persistence-only)
# ============================================================================


@router.post('/v2/desktop/messages', tags=['chat-sessions'])
def save_message(
    http_request: Request,
    body: SaveMessageRequest,
    x_app_platform: str | None = Header(None),
):
    uid = http_request.state.uid
    saved = chat_db.save_message(
        uid,
        text=body.text,
        sender=body.sender,
        app_id=body.app_id,
        session_id=body.session_id,
        metadata=body.metadata,
        client_message_id=body.client_message_id,
        message_source=body.message_source,
    )
    if body.sender == 'human' and body.message_source == 'desktop_chat':
        try:
            llm_usage_db.record_chat_quota_question(
                uid,
                idempotency_key=f'desktop_messages:{saved["id"]}',
                source='desktop_messages',
                message_id=saved['id'],
                chat_session_id=saved.get('session_id'),
                platform=x_app_platform,
            )
        except Exception:
            logger.exception('Failed to record desktop chat quota question uid=%s message_id=%s', uid, saved['id'])
    return saved


@router.get('/v2/desktop/messages', tags=['chat-sessions'])
def get_messages(
    http_request: Request,
    app_id: str | None = Query(None),
    session_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    uid = http_request.state.uid
    return chat_db.get_messages(uid, app_id=app_id, chat_session_id=session_id, limit=limit, offset=offset)


@router.delete('/v2/desktop/messages', tags=['chat-sessions'])
def delete_messages(
    http_request: Request,
    app_id: str | None = Query(None),
    session_id: str | None = Query(None),
):
    uid = http_request.state.uid
    count = chat_db.delete_messages(uid, app_id=app_id, session_id=session_id)
    return {'status': 'ok', 'deleted_count': count}


@router.patch('/v2/desktop/messages/{message_id}/rating', tags=['chat-sessions'])
def rate_message(http_request: Request, message_id: str, body: RateMessageRequest):
    uid = http_request.state.uid
    if body.rating is not None and body.rating not in (1, -1):
        raise HTTPException(status_code=400, detail='Rating must be 1, -1, or null')
    if not chat_db.update_message_rating(uid, message_id, body.rating):
        raise HTTPException(status_code=404, detail='Message not found')
    value = body.rating if body.rating is not None else 0
    set_chat_message_rating_score(uid, message_id, value, platform='desktop', app_version=body.app_version)
    return {'status': 'ok'}


# ============================================================================
# CHAT AI ENDPOINTS (migrated from Rust desktop backend)
# ============================================================================


@router.post('/v2/chat/initial-message', tags=['chat-sessions'], dependencies=[Depends(rate_limit_dep("chat:initial"))])
def create_initial_message(http_request: Request, body: InitialMessageRequest):
    uid = http_request.state.uid
    """Generate an initial greeting message for a chat session.

    Delegates to the shared chat helper which
    handles persona detection, previous message context, and LLM generation.
    """
    ai_message = initial_message_util(uid, body.app_id, chat_session_id=body.session_id)
    return {'message': ai_message.text, 'message_id': ai_message.id}


@router.post('/v2/chat/generate-title', tags=['chat-sessions'], dependencies=[Depends(rate_limit_dep("chat:initial"))])
def generate_session_title(http_request: Request, body: GenerateTitleRequest):
    uid = http_request.state.uid
    """Generate a title for a chat session based on its messages."""
    conversation = '\n'.join(f"{m.sender}: {m.text}" for m in body.messages[:10])
    prompt = (
        "Generate a short, descriptive title (max 6 words) for this chat conversation. "
        "Return ONLY the title text, no quotes or punctuation.\n\n"
        f"{conversation}"
    )
    title = get_llm('session_titles').invoke(prompt).content.strip().strip('"\'')
    if not title:
        title = 'New Chat'

    chat_db.update_chat_session(uid, body.session_id, title=title)
    return {'title': title}


@router.get('/v1/users/stats/chat-messages', tags=['chat-sessions'])
def get_chat_message_count(http_request: Request):
    uid = http_request.state.uid
    """Get total count of chat messages for the user."""
    count = chat_db.get_message_count(uid)
    return {'count': count}
