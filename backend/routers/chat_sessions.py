"""Chat sessions and messages (v2).

Chat sessions (v2) provide multi-session chat with title, preview, and starring.
Messages are persistence-only writes (no LLM streaming) — they use
/v2/desktop/messages to avoid conflict with chat.py's /v2/messages which
streams AI responses.
"""

from utils.generated_compute import require_generated_compute

import logging
from typing import Any, Callable, List, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

import database.chat as chat_db
import database.llm_usage as llm_usage_db
from database.users import set_chat_message_rating_score
from models.chat import Message
from models.feedback import MAX_COMMENT_LENGTH, FeedbackReason, FeedbackSurface
from utils.feedback import record_chat_message_feedback
from models.chat_session import (
    ChatSessionResponse,
    DeleteMessagesResponse,
    GenerateTitleResponse,
    InitialMessageResponse,
    SaveMessageResponse,
)
from models.shared import StatusResponse
from utils.chat import initial_message_util
from utils.chat_rating_triage import extract_rating_triage_fields
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage
from utils.other import endpoints as auth
from utils.product_metrics import record_product_event

logger = logging.getLogger(__name__)

router = APIRouter()

# `utils.other.endpoints.with_rate_limit` has an untyped `auth_dependency`
# parameter; route access through a cast so this strict-checked file sees a
# concrete callable type instead of `Unknown`.
_auth_module = cast(Any, auth)


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
    content_blocks: list[dict[str, Any]] | None = Field(
        None,
        description='First-class structured chat content; message text remains the required fallback.',
    )
    client_message_id: str | None = Field(None, pattern=r'^[A-Za-z0-9_-]{1,128}$')
    message_source: str = Field('desktop_chat', pattern=r'^(desktop_chat|realtime_voice)$')
    journal_revision: int | None = Field(None, ge=1, le=9_007_199_254_740_991)


# Client `surface` values -> ledger surfaces. The client resolves 'notification'
# for proactive cards (ChatProvider.ratingSurface); rejecting it here would 422
# the PATCH and revert the user's thumbs-down instead of recording it.
_LEDGER_SURFACES = {
    'text': FeedbackSurface.chat_text,
    'voice': FeedbackSurface.chat_voice,
    'notification': FeedbackSurface.chat_notification,
}


class RateMessageRequest(BaseModel):
    rating: int | None = Field(None, ge=-1, le=1)
    app_version: str | None = None
    # `reason`/`comment` are why a thumbs-down happened; `surface` separates
    # main-window chat from floating-bar voice answers, which fail in different
    # ways. All three are optional so an older desktop build keeps working —
    # a rating with no reason records as "not captured", never as "no reason".
    reason: FeedbackReason | None = None
    comment: str | None = Field(None, max_length=MAX_COMMENT_LENGTH)
    surface: str = Field('text', pattern=r'^(text|voice|notification)$')


class InitialMessageRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    app_id: str | None = None


class TitleMessageInput(BaseModel):
    text: str
    sender: str


class GenerateTitleRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    messages: List[TitleMessageInput] = Field(..., min_length=1, max_length=50)


class ChatMessageCountResponse(BaseModel):
    count: int


class DesktopMessageReconcilePageResponse(BaseModel):
    messages: list[Message]
    next_cursor: str | None
    has_more: bool


# ============================================================================
# CHAT SESSION ENDPOINTS
# ============================================================================


@router.post('/v2/chat-sessions', tags=['chat-sessions'], response_model=ChatSessionResponse)
def create_chat_session(
    request: CreateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return chat_db.create_chat_session(uid, title=request.title, app_id=request.app_id)


@router.get('/v2/chat-sessions', tags=['chat-sessions'], response_model=list[ChatSessionResponse])
def get_chat_sessions(
    app_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    starred: bool | None = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    sessions = chat_db.get_chat_sessions(uid, app_id=app_id, limit=limit, offset=offset, starred=starred)
    return ChatSessionResponse.deserialize_many_safe(
        sessions,
        on_error=lambda record, exc: logger.warning(
            'Skipping malformed chat session %s for uid=%s: %s',
            record.get('id') if isinstance(record, dict) else None,
            uid,
            type(exc).__name__,
        ),
    )


@router.get('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=ChatSessionResponse)
def get_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    clean_session_id = session_id.strip() if session_id else ""
    if not clean_session_id:
        raise HTTPException(status_code=400, detail='Invalid session ID')
    result = chat_db.get_chat_session_by_id(uid, clean_session_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.patch('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=ChatSessionResponse)
def update_chat_session(
    session_id: str,
    request: UpdateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    clean_session_id = session_id.strip() if session_id else ""
    if not clean_session_id:
        raise HTTPException(status_code=400, detail='Invalid session ID')
    clean_title = request.title.strip() if request.title is not None else None
    if request.title is not None and not clean_title:
        raise HTTPException(status_code=400, detail='Title cannot be empty')
    result = chat_db.update_chat_session(uid, clean_session_id, title=clean_title, starred=request.starred)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.delete('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=StatusResponse)
def delete_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    clean_session_id = session_id.strip() if session_id else ""
    if not clean_session_id:
        raise HTTPException(status_code=400, detail='Invalid session ID')
    chat_db.delete_chat_session(uid, clean_session_id, cascade_messages=True)
    return {'status': 'ok'}


# ============================================================================
# MESSAGE ENDPOINTS
# Uses /v2/desktop/messages to avoid conflict with chat.py's /v2/messages
# (chat.py POST streams AI responses; these are persistence-only)
# ============================================================================


@router.post('/v2/desktop/messages', tags=['chat-sessions'], response_model=SaveMessageResponse)
def save_message(
    request: SaveMessageRequest,
    http_request: Request,
    x_app_platform: str | None = Header(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        saved = chat_db.save_message(
            uid,
            text=request.text,
            sender=request.sender,
            app_id=request.app_id,
            session_id=request.session_id,
            metadata=request.metadata,
            content_blocks=request.content_blocks,
            client_message_id=request.client_message_id,
            message_source=request.message_source,
            journal_revision=request.journal_revision,
        )
    except chat_db.ClientMessageIdPayloadConflict as exc:
        record_product_event('chat_message_sent', request=http_request, uid=uid, outcome='error')
        raise HTTPException(status_code=409, detail='client_message_id payload conflict') from exc
    if request.sender == 'human' and request.message_source == 'desktop_chat':
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
    record_product_event('chat_message_sent', request=http_request, uid=uid, outcome='ok')
    return saved


@router.get('/v2/desktop/messages', tags=['chat-sessions'], response_model=list[Message])
def get_messages(
    app_id: str | None = Query(None),
    session_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    # One malformed/legacy stored row must not 500 the whole desktop history page.
    return Message.deserialize_many_safe(
        chat_db.get_messages(uid, app_id=app_id, chat_session_id=session_id, limit=limit, offset=offset),
        on_error=lambda record, exc: logger.warning(
            'Skipping malformed desktop chat message %s for uid=%s: %s',
            record.get('id') if isinstance(record, dict) else None,
            uid,
            type(exc).__name__,
        ),
    )


@router.get(
    '/v2/desktop/messages/reconcile',
    tags=['chat-sessions'],
    response_model=DesktopMessageReconcilePageResponse,
)
def reconcile_messages(
    app_id: str | None = Query(None),
    session_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=200),
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        messages, next_cursor, has_more = chat_db.get_messages_reconcile_page(
            uid,
            app_id=app_id,
            chat_session_id=session_id,
            limit=limit,
            cursor_message_id=cursor,
        )
    except chat_db.MessageReconcileCursorError as exc:
        raise HTTPException(status_code=400, detail='invalid message reconciliation cursor') from exc
    # One malformed/legacy stored row must not 500 the reconcile page — guard it
    # the same way the sibling /v2/desktop/messages list does, so the desktop can
    # resume syncing past a poisoned row on the next page.
    return {
        'messages': Message.deserialize_many_safe(
            messages,
            on_error=lambda record, exc: logger.warning(
                'Skipping malformed desktop reconcile message %s for uid=%s: %s',
                record.get('id') if isinstance(record, dict) else None,
                uid,
                type(exc).__name__,
            ),
        ),
        'next_cursor': next_cursor,
        'has_more': has_more,
    }


@router.delete('/v2/desktop/messages', tags=['chat-sessions'], response_model=DeleteMessagesResponse)
def delete_messages(
    app_id: str | None = Query(None),
    session_id: str | None = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    count = chat_db.delete_messages(uid, app_id=app_id, session_id=session_id)
    return {'status': 'ok', 'deleted_count': count}


@router.patch('/v2/desktop/messages/{message_id}/rating', tags=['chat-sessions'], response_model=StatusResponse)
def rate_message(
    message_id: str,
    request: RateMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if request.rating is not None and request.rating not in (1, -1):
        raise HTTPException(status_code=400, detail='Rating must be 1, -1, or null')
    snapshot = chat_db.update_message_rating(uid, message_id, request.rating)
    if snapshot is None:
        raise HTTPException(status_code=404, detail='Message not found')
    # Also write to analytics collection (same as mobile endpoint) so ratings
    # appear in the admin dashboard chat ratings chart.
    value = request.rating if request.rating is not None else 0
    triage = extract_rating_triage_fields(snapshot)
    reason = request.reason.value if request.reason else None
    set_chat_message_rating_score(
        uid,
        message_id,
        value,
        reason=reason,
        platform='desktop',
        app_version=request.app_version,
        notification_kind=triage.get('notification_kind'),
        app_id=triage.get('app_id'),
    )
    record_chat_message_feedback(
        uid,
        message_id,
        value,
        surface=_LEDGER_SURFACES.get(request.surface, FeedbackSurface.chat_text),
        reason=reason,
        comment=request.comment,
        platform='desktop',
        app_version=request.app_version,
    )
    return {'status': 'ok'}


# ============================================================================
# CHAT AI ENDPOINTS (migrated from Rust desktop backend)
# ============================================================================


@router.post('/v2/chat/initial-message', tags=['chat-sessions'], response_model=InitialMessageResponse)
def create_initial_message(
    request: InitialMessageRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "chat:initial"))
    ),
):
    """Generate an initial greeting message for a chat session.

    Delegates to the shared chat helper which
    handles persona detection, previous message context, and LLM generation.
    """
    ai_message = initial_message_util(uid, request.app_id, chat_session_id=request.session_id)
    return {'message': ai_message.text, 'message_id': ai_message.id}


@router.post('/v2/chat/generate-title', tags=['chat-sessions'], response_model=GenerateTitleResponse)
def generate_session_title(
    request: GenerateTitleRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "chat:initial"))
    ),
):
    """Generate a title for a chat session based on its messages."""
    session_id = request.session_id.strip() if request.session_id else ""
    if not session_id:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    # Validate session exists
    session = chat_db.get_chat_session_by_id(uid, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    title = "New Chat"
    try:
        require_generated_compute(uid, 'session_titles')
        conversation = '\n'.join(f"{m.sender}: {m.text}" for m in request.messages[:10])
        prompt = (
            "Generate a short, descriptive title (max 6 words) for this chat conversation. "
            "Return ONLY the title text, no quotes or punctuation.\n\n"
            f"{conversation}"
        )
        with track_usage(uid, Features.CHAT):
            response = cast(Any, get_llm('session_titles').invoke(prompt))

        # Safely extract string content across str, list of dicts, or other LLM response structures
        raw_content = getattr(response, "content", response)
        if isinstance(raw_content, list):
            content_text = " ".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw_content
            )
        elif isinstance(raw_content, str):
            content_text = raw_content
        else:
            content_text = str(raw_content) if raw_content is not None else ""

        candidate_title = content_text.strip().strip('"\'')
        if candidate_title:
            title = candidate_title[:100].strip()
    except Exception as exc:
        logger.warning("generate_session_title LLM generation failed for uid=%s session_id=%s: %s", uid, session_id, exc)
        # Fallback gracefully to first human message or "New Chat"
        first_human_msg = next((m.text.strip() for m in request.messages if m.sender == "human" and m.text.strip()), None)
        if first_human_msg:
            title = first_human_msg[:30].strip()
        else:
            title = "New Chat"

    chat_db.update_chat_session(uid, session_id, title=title)
    return {'title': title}


@router.get('/v1/users/stats/chat-messages', tags=['chat-sessions'], response_model=ChatMessageCountResponse)
def get_chat_message_count(
    uid: str = Depends(auth.get_current_user_uid),
):
    """Get total count of chat messages for the user."""
    count = chat_db.get_message_count(uid)
    return {'count': count}
