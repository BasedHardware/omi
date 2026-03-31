"""Chat sessions and desktop messages.

Chat sessions (v2) provide multi-session chat with title, preview, and starring.
Desktop messages are persistence-only writes (no LLM streaming) — they use
/v2/desktop/messages to avoid conflict with chat.py's /v2/messages which
streams AI responses.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import database.chat as chat_db
from utils.other import endpoints as auth

router = APIRouter()


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


class RateMessageRequest(BaseModel):
    rating: int | None = Field(None, ge=-1, le=1)


# ============================================================================
# CHAT SESSION ENDPOINTS
# ============================================================================


@router.post('/v2/chat-sessions', tags=['chat-sessions'])
def create_chat_session(
    request: CreateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return chat_db.create_desktop_chat_session(uid, title=request.title, app_id=request.app_id)


@router.get('/v2/chat-sessions', tags=['chat-sessions'])
def get_chat_sessions(
    app_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    starred: bool | None = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    return chat_db.get_desktop_chat_sessions(uid, app_id=app_id, limit=limit, offset=offset, starred=starred)


@router.get('/v2/chat-sessions/{session_id}', tags=['chat-sessions'])
def get_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    result = chat_db.get_desktop_chat_session(uid, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.patch('/v2/chat-sessions/{session_id}', tags=['chat-sessions'])
def update_chat_session(
    session_id: str,
    request: UpdateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    result = chat_db.update_desktop_chat_session(uid, session_id, title=request.title, starred=request.starred)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.delete('/v2/chat-sessions/{session_id}', tags=['chat-sessions'])
def delete_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    chat_db.delete_desktop_chat_session(uid, session_id)
    return {'status': 'ok'}


# ============================================================================
# MESSAGE ENDPOINTS
# Uses /v2/desktop/messages to avoid conflict with chat.py's /v2/messages
# (chat.py POST streams AI responses; these are persistence-only)
# ============================================================================


@router.post('/v2/desktop/messages', tags=['chat-sessions'])
def save_message(
    request: SaveMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return chat_db.save_desktop_message(
        uid,
        text=request.text,
        sender=request.sender,
        app_id=request.app_id,
        session_id=request.session_id,
        metadata=request.metadata,
    )


@router.get('/v2/desktop/messages', tags=['chat-sessions'])
def get_messages(
    app_id: str | None = Query(None),
    session_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    return chat_db.get_desktop_messages(uid, app_id=app_id, session_id=session_id, limit=limit, offset=offset)


@router.delete('/v2/desktop/messages', tags=['chat-sessions'])
def delete_messages(
    app_id: str | None = Query(None),
    session_id: str | None = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    count = chat_db.delete_desktop_messages(uid, app_id=app_id, session_id=session_id)
    return {'status': 'ok', 'deleted_count': count}


@router.patch('/v2/desktop/messages/{message_id}/rating', tags=['chat-sessions'])
def rate_message(
    message_id: str,
    request: RateMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if request.rating is not None and request.rating not in (1, -1):
        raise HTTPException(status_code=400, detail='Rating must be 1, -1, or null')
    if not chat_db.rate_desktop_message(uid, message_id, request.rating):
        raise HTTPException(status_code=404, detail='Message not found')
    return {'status': 'ok'}
