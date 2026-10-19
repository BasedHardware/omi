"""Chat sessions and messages (v2).

Chat sessions (v2) provide multi-session chat with title, preview, and starring.
Messages are persistence-only writes (no LLM streaming) — they use
/v2/desktop/messages to avoid conflict with chat.py's /v2/messages which
streams AI responses.
"""

from utils.generated_compute import require_generated_compute

import logging
import re
from typing import Any, Callable, List, Optional, cast

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
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.product_metrics import record_product_event

logger = logging.getLogger(__name__)

router = APIRouter()

# `utils.other.endpoints.with_rate_limit` has an untyped `auth_dependency`
# parameter; route access through a cast so this strict-checked file sees a
# concrete callable type instead of `Unknown`.
_auth_module = cast(Any, auth)

_RESERVED_DOC_ID_RE = re.compile(r'^__.*__$')
_MAX_DOC_ID_BYTES = 1500


# ============================================================================
# HELPERS
# ============================================================================


def _is_valid_doc_id(value: str) -> bool:
    if not value or value in ('.', '..') or '/' in value:
        return False
    if _RESERVED_DOC_ID_RE.match(value):
        return False
    if len(value.encode('utf-8')) > _MAX_DOC_ID_BYTES:
        return False
    return True


def _require_doc_id(value: str, field_name: str) -> str:
    stripped = value.strip() if isinstance(value, str) else ''
    if not _is_valid_doc_id(stripped):
        raise HTTPException(status_code=400, detail=f'Valid {field_name} is required')
    return stripped


def _optional_doc_id(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip() if isinstance(value, str) else ''
    if not stripped:
        return None
    if not _is_valid_doc_id(stripped):
        raise HTTPException(status_code=400, detail=f'Valid {field_name} is required')
    return stripped


def _extract_llm_text(content: Any) -> str:
    """Extract plain text from a LangChain AIMessage content payload (str, list of blocks, or None)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text_val = item.get('text')
                if isinstance(text_val, str):
                    parts.append(text_val)
        return ' '.join(parts)
    return ''


def _log_failure(action: str, uid: str, error: Exception) -> None:
    logger.error(f'chat_sessions {action} failed uid={uid}: {sanitize(str(error))}', exc_info=True)


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
    title = request.title.strip() or None if isinstance(request.title, str) else None
    app_id = _optional_doc_id(request.app_id, 'app_id')
    try:
        return chat_db.create_chat_session(uid, title=title, app_id=app_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('create_session', uid, e)
        raise HTTPException(status_code=500, detail='Failed to create chat session')


@router.get('/v2/chat-sessions', tags=['chat-sessions'], response_model=list[ChatSessionResponse])
def get_chat_sessions(
    app_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    starred: bool | None = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    normalized_app_id = _optional_doc_id(app_id, 'app_id')
    try:
        return chat_db.get_chat_sessions(uid, app_id=normalized_app_id, limit=limit, offset=offset, starred=starred)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('list_sessions', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load chat sessions')


@router.get('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=ChatSessionResponse)
def get_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    session_id = _require_doc_id(session_id, 'session_id')
    try:
        result = chat_db.get_chat_session_by_id(uid, session_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('get_session', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load chat session')
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.patch('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=ChatSessionResponse)
def update_chat_session(
    session_id: str,
    request: UpdateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    session_id = _require_doc_id(session_id, 'session_id')
    title: str | None = None
    if request.title is not None:
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail='title cannot be empty or whitespace only')
    if title is None and request.starred is None:
        raise HTTPException(status_code=400, detail='At least one of title or starred is required')
    try:
        result = chat_db.update_chat_session(uid, session_id, title=title, starred=request.starred)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('update_session', uid, e)
        raise HTTPException(status_code=500, detail='Failed to update chat session')
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.delete('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=StatusResponse)
def delete_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    session_id = _require_doc_id(session_id, 'session_id')
    try:
        chat_db.delete_chat_session(uid, session_id, cascade_messages=True)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('delete_session', uid, e)
        raise HTTPException(status_code=500, detail='Failed to delete chat session')
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
    if not request.text.strip() and not request.content_blocks:
        raise HTTPException(status_code=400, detail='text cannot be empty or whitespace only')
    app_id = _optional_doc_id(request.app_id, 'app_id')
    session_id = _optional_doc_id(request.session_id, 'session_id')
    try:
        saved = chat_db.save_message(
            uid,
            text=request.text,
            sender=request.sender,
            app_id=app_id,
            session_id=session_id,
            metadata=request.metadata,
            content_blocks=request.content_blocks,
            client_message_id=request.client_message_id,
            message_source=request.message_source,
            journal_revision=request.journal_revision,
        )
    except chat_db.ClientMessageIdPayloadConflict as exc:
        record_product_event('chat_message_sent', request=http_request, uid=uid, outcome='error')
        raise HTTPException(status_code=409, detail='client_message_id payload conflict') from exc
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('save_message', uid, e)
        raise HTTPException(status_code=500, detail='Failed to save message')
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
    normalized_app_id = _optional_doc_id(app_id, 'app_id')
    normalized_session_id = _optional_doc_id(session_id, 'session_id')
    try:
        raw_messages = chat_db.get_messages(
            uid, app_id=normalized_app_id, chat_session_id=normalized_session_id, limit=limit, offset=offset
        )
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('get_messages', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load messages')
    # One malformed/legacy stored row must not 500 the whole desktop history page.
    return Message.deserialize_many_safe(
        raw_messages,
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
    normalized_app_id = _optional_doc_id(app_id, 'app_id')
    normalized_session_id = _optional_doc_id(session_id, 'session_id')
    normalized_cursor = _optional_doc_id(cursor, 'cursor') if cursor is not None else None
    if cursor is not None and normalized_cursor is None:
        raise HTTPException(status_code=400, detail='invalid message reconciliation cursor')
    try:
        messages, next_cursor, has_more = chat_db.get_messages_reconcile_page(
            uid,
            app_id=normalized_app_id,
            chat_session_id=normalized_session_id,
            limit=limit,
            cursor_message_id=normalized_cursor,
        )
    except chat_db.MessageReconcileCursorError as exc:
        raise HTTPException(status_code=400, detail='invalid message reconciliation cursor') from exc
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('reconcile_messages', uid, e)
        raise HTTPException(status_code=500, detail='Failed to reconcile messages')
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
    normalized_app_id = _optional_doc_id(app_id, 'app_id')
    normalized_session_id = _optional_doc_id(session_id, 'session_id')
    try:
        count = chat_db.delete_messages(uid, app_id=normalized_app_id, session_id=normalized_session_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('delete_messages', uid, e)
        raise HTTPException(status_code=500, detail='Failed to delete messages')
    return {'status': 'ok', 'deleted_count': count}


@router.patch('/v2/desktop/messages/{message_id}/rating', tags=['chat-sessions'], response_model=StatusResponse)
def rate_message(
    message_id: str,
    request: RateMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    message_id = _require_doc_id(message_id, 'message_id')
    if request.rating is not None and request.rating not in (1, -1):
        raise HTTPException(status_code=400, detail='Rating must be 1, -1, or null')
    try:
        snapshot = chat_db.update_message_rating(uid, message_id, request.rating)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('rate_message', uid, e)
        raise HTTPException(status_code=500, detail='Failed to update message rating')
    if snapshot is None:
        raise HTTPException(status_code=404, detail='Message not found')
    # Also write to analytics collection (same as mobile endpoint) so ratings
    # appear in the admin dashboard chat ratings chart.
    value = request.rating if request.rating is not None else 0
    triage = extract_rating_triage_fields(snapshot)
    reason = request.reason.value if request.reason else None
    try:
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
    except Exception as e:
        _log_failure('rate_message_analytics', uid, e)
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
    session_id = _require_doc_id(request.session_id, 'session_id')
    app_id = _optional_doc_id(request.app_id, 'app_id')
    try:
        ai_message = initial_message_util(uid, app_id, chat_session_id=session_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('initial_message', uid, e)
        raise HTTPException(status_code=500, detail='Failed to generate initial message')
    return {'message': ai_message.text, 'message_id': ai_message.id}


@router.post('/v2/chat/generate-title', tags=['chat-sessions'], response_model=GenerateTitleResponse)
def generate_session_title(
    request: GenerateTitleRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "chat:initial"))
    ),
):
    """Generate a title for a chat session based on its messages."""
    session_id = _require_doc_id(request.session_id, 'session_id')
    require_generated_compute(uid, 'session_titles')
    conversation = '\n'.join(f"{m.sender}: {m.text}" for m in request.messages[:10])
    prompt = (
        "Generate a short, descriptive title (max 6 words) for this chat conversation. "
        "Return ONLY the title text, no quotes or punctuation.\n\n"
        f"{conversation}"
    )
    try:
        with track_usage(uid, Features.CHAT):
            response = cast(Any, get_llm('session_titles').invoke(prompt))
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('generate_title_llm', uid, e)
        raise HTTPException(status_code=500, detail='Failed to generate session title')

    raw_title = _extract_llm_text(getattr(response, 'content', None))
    title = raw_title.strip().strip('"\'').strip()[:500]
    if not title:
        title = 'New Chat'

    try:
        chat_db.update_chat_session(uid, session_id, title=title)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('generate_title_store', uid, e)
        raise HTTPException(status_code=500, detail='Failed to generate session title')
    return {'title': title}


@router.get('/v1/users/stats/chat-messages', tags=['chat-sessions'], response_model=ChatMessageCountResponse)
def get_chat_message_count(
    uid: str = Depends(auth.get_current_user_uid),
):
    """Get total count of chat messages for the user."""
    try:
        count = chat_db.get_message_count(uid)
    except HTTPException:
        raise
    except Exception as e:
        _log_failure('get_message_count', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load chat message count')
    return {'count': count}
