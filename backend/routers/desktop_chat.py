"""Desktop chat sessions CRUD + message operations.

These endpoints support the desktop app's session-based chat model where
messages are organized into named sessions.  The Python backend's existing
streaming chat (routers/chat.py) is session-aware internally, but the
desktop Swift client expects explicit CRUD for sessions and simple
message save/rating.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import database.chat as chat_db
from utils.other import endpoints as auth
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateChatSessionRequest(BaseModel):
    title: Optional[str] = None
    app_id: Optional[str] = None


class UpdateChatSessionRequest(BaseModel):
    title: Optional[str] = None
    starred: Optional[bool] = None


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    preview: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    app_id: Optional[str] = None
    message_count: int = 0
    starred: bool = False


class SaveMessageRequest(BaseModel):
    text: str
    sender: str
    app_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[str] = None


class SaveMessageResponse(BaseModel):
    id: str
    created_at: datetime


class RateMessageRequest(BaseModel):
    rating: Optional[int] = None


class StatusResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Chat Sessions CRUD
# ---------------------------------------------------------------------------


@router.get('/v2/chat-sessions', response_model=List[ChatSessionResponse], tags=['desktop-chat'])
def list_chat_sessions(
    app_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    starred: Optional[bool] = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    sessions = chat_db.get_chat_sessions(uid, app_id=app_id, limit=limit, offset=offset, starred=starred)
    return sessions


@router.post('/v2/chat-sessions', response_model=ChatSessionResponse, tags=['desktop-chat'])
def create_chat_session(
    request: CreateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    now = datetime.now(timezone.utc)
    session_data = {
        'id': str(uuid.uuid4()),
        'title': request.title or 'New Chat',
        'preview': None,
        'created_at': now,
        'updated_at': now,
        'app_id': request.app_id,
        'plugin_id': request.app_id,  # Python backend uses plugin_id for filtering
        'message_count': 0,
        'starred': False,
    }
    chat_db.add_chat_session(uid, session_data)
    return session_data


@router.get('/v2/chat-sessions/{session_id}', response_model=ChatSessionResponse, tags=['desktop-chat'])
def get_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    session = chat_db.get_chat_session_by_id(uid, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.patch('/v2/chat-sessions/{session_id}', response_model=StatusResponse, tags=['desktop-chat'])
def update_chat_session(
    session_id: str,
    request: UpdateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    session = chat_db.get_chat_session_by_id(uid, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    update_data = {}
    if request.title is not None:
        update_data['title'] = request.title
    if request.starred is not None:
        update_data['starred'] = request.starred
    if update_data:
        update_data['updated_at'] = datetime.now(timezone.utc)
        chat_db.update_chat_session(uid, session_id, update_data)

    return StatusResponse(status='ok')


@router.delete('/v2/chat-sessions/{session_id}', response_model=StatusResponse, tags=['desktop-chat'])
def delete_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    session = chat_db.get_chat_session_by_id(uid, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    chat_db.delete_chat_session(uid, session_id)
    return StatusResponse(status='ok')


# ---------------------------------------------------------------------------
# Desktop message CRUD (simple save, not streaming)
# ---------------------------------------------------------------------------


@router.post('/v2/desktop/messages', response_model=SaveMessageResponse, tags=['desktop-chat'])
def save_message(
    request: SaveMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=422, detail="Message text cannot be empty")
    if request.sender not in ('human', 'ai'):
        raise HTTPException(status_code=422, detail="sender must be 'human' or 'ai'")

    now = datetime.now(timezone.utc)
    message_id = str(uuid.uuid4())
    message_data = {
        'id': message_id,
        'text': request.text,
        'created_at': now,
        'sender': request.sender,
        'app_id': request.app_id,
        'plugin_id': request.app_id,
        'session_id': request.session_id,
        'chat_session_id': request.session_id,
        'rating': None,
        'reported': False,
        'type': 'text',
        'memories_id': [],
        'from_external_integration': False,
        'metadata': request.metadata,
    }
    chat_db.save_message(uid, message_data)

    if request.session_id:
        try:
            chat_db.add_message_to_chat_session(uid, request.session_id, message_id)
        except Exception as e:
            logger.warning(f"Failed to link message to session {request.session_id}: {e}")

    return SaveMessageResponse(id=message_id, created_at=now)


@router.patch('/v2/messages/{message_id}/rating', response_model=StatusResponse, tags=['desktop-chat'])
def rate_message(
    message_id: str,
    request: RateMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if request.rating is not None and request.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="rating must be 1, -1, or null")

    chat_db.update_message_rating(uid, message_id, request.rating)
    return StatusResponse(status='ok')
