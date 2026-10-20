"""Chat sessions and messages (v2).

Chat sessions (v2) provide multi-session chat with title, preview, and starring.
Messages are persistence-only writes (no LLM streaming) — they use
/v2/desktop/messages to avoid conflict with chat.py's /v2/messages which
streams AI responses.
"""

from utils.generated_compute import require_generated_compute

import logging
import re
from typing import Any, Callable, List, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

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

# Firestore document ids / cursor values: no separators, no relative segments,
# no reserved `__name__`-style names, and bounded so an oversized key fails here
# instead of at the server.
MAX_DOC_ID_LENGTH = 1500
MAX_CURSOR_LENGTH = 200
_RESERVED_ID_PATTERN = re.compile(r'^__.*__$')
T = Any


def _clean_doc_id(value: Any, field: str) -> str:
    """Validate a value that becomes a Firestore document id path segment.

    `session_id`, `message_id`, `app_id` and `cursor` were forwarded straight to
    `.document(...)` / query builders. A caller-supplied `/` retargeted the
    document path, `.` and `..` are rejected by Firestore as relative segments,
    `__name__`-style ids collide with reserved names, and a >1500-byte key fails
    server-side — each surfaced as an opaque 500 rather than a clean 400.
    """
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f'{field} must be a string')
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f'{field} must not be empty')
    if len(cleaned.encode('utf-8')) > MAX_DOC_ID_LENGTH:
        raise HTTPException(status_code=400, detail=f'{field} is too long')
    if cleaned in ('.', '..') or any(char in cleaned for char in ('/', '\\', '\x00')):
        raise HTTPException(status_code=400, detail=f'{field} contains invalid characters')
    if _RESERVED_ID_PATTERN.match(cleaned):
        raise HTTPException(status_code=400, detail=f'{field} uses a reserved name')
    return cleaned


def _clean_optional_doc_id(value: Any, field: str) -> str | None:
    """Validate an optional id/cursor: absent stays absent, present is checked."""
    if value is None:
        return None
    return _clean_doc_id(value, field)


def _guarded(action: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a store/LLM call, turning failures into a sanitized 500.

    These routes called the data layer bare, so a transient Firestore failure
    surfaced as an unhandled exception carrying the raw driver message.
    HTTPException passes through untouched so 404/409/400 keep their meaning.
    """
    try:
        return action(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001 - boundary: never leak driver text
        logger.error('chat session store call failed: %s', sanitize(error), exc_info=True)
        raise HTTPException(status_code=500, detail='Chat session service unavailable')


def _title_from_content(content: Any) -> str:
    """Extract a title from `BaseChatModel.invoke(...).content`.

    LangChain types the content as `str | list[str | dict]` and providers can
    also return `None`. The previous `response.content.strip()` therefore raised
    `AttributeError: 'list' object has no attribute 'strip'` for content-block
    models and `AttributeError` for `None`, 500ing `POST /v2/chat/generate-title`.
    """
    text = ''
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                block_text = block.get('text')
                if isinstance(block_text, str):
                    parts.append(block_text)
        text = ' '.join(parts)
    elif isinstance(content, dict):
        block_text = content.get('text')
        if isinstance(block_text, str):
            text = block_text
    cleaned = text.strip().strip('"\'').strip()
    return cleaned[:200]


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

    @field_validator('text')
    @classmethod
    def _text_must_not_be_blank(cls, value: str) -> str:
        """`min_length=1` accepts '   ', which stored an empty chat message.

        A whitespace-only body is only meaningful when structured content
        blocks carry the real payload, and that combination is checked on the
        model so the rule holds for every caller.
        """
        if not value.strip():
            raise ValueError('text must not be blank')
        return value


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
    return _guarded(
        chat_db.create_chat_session,
        uid,
        title=request.title,
        app_id=_clean_optional_doc_id(request.app_id, 'app_id'),
    )


@router.get('/v2/chat-sessions', tags=['chat-sessions'], response_model=list[ChatSessionResponse])
def get_chat_sessions(
    app_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    starred: bool | None = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    return _guarded(
        chat_db.get_chat_sessions,
        uid,
        app_id=_clean_optional_doc_id(app_id, 'app_id'),
        limit=limit,
        offset=offset,
        starred=starred,
    )


@router.get('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=ChatSessionResponse)
def get_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    session_id = _clean_doc_id(session_id, 'session_id')
    result = _guarded(chat_db.get_chat_session_by_id, uid, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.patch('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=ChatSessionResponse)
def update_chat_session(
    session_id: str,
    request: UpdateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    session_id = _clean_doc_id(session_id, 'session_id')
    # An empty body (`{}`) used to be accepted and issued a no-op write, and a
    # whitespace-only title overwrote the real one with an empty string.
    title = request.title
    if title is not None:
        title = title.strip()
        if not title:
            raise HTTPException(status_code=400, detail='title must not be blank')
    if title is None and request.starred is None:
        raise HTTPException(status_code=400, detail='No fields to update')

    result = _guarded(chat_db.update_chat_session, uid, session_id, title=title, starred=request.starred)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.delete('/v2/chat-sessions/{session_id}', tags=['chat-sessions'], response_model=StatusResponse)
def delete_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    session_id = _clean_doc_id(session_id, 'session_id')
    _guarded(chat_db.delete_chat_session, uid, session_id, cascade_messages=True)
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
            app_id=_clean_optional_doc_id(request.app_id, 'app_id'),
            session_id=_clean_optional_doc_id(request.session_id, 'session_id'),
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
        record_product_event('chat_message_sent', request=http_request, uid=uid, outcome='error')
        raise
    except Exception as error:  # noqa: BLE001 - boundary: never leak driver text
        record_product_event('chat_message_sent', request=http_request, uid=uid, outcome='error')
        logger.error('save desktop chat message failed: %s', sanitize(error), exc_info=True)
        raise HTTPException(status_code=500, detail='Chat message service unavailable')
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
        _guarded(
            chat_db.get_messages,
            uid,
            app_id=_clean_optional_doc_id(app_id, 'app_id'),
            chat_session_id=_clean_optional_doc_id(session_id, 'session_id'),
            limit=limit,
            offset=offset,
        ),
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
        messages, next_cursor, has_more = _guarded(
            chat_db.get_messages_reconcile_page,
            uid,
            app_id=_clean_optional_doc_id(app_id, 'app_id'),
            chat_session_id=_clean_optional_doc_id(session_id, 'session_id'),
            limit=limit,
            cursor_message_id=_clean_optional_doc_id(cursor, 'cursor'),
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
    count = _guarded(
        chat_db.delete_messages,
        uid,
        app_id=_clean_optional_doc_id(app_id, 'app_id'),
        session_id=_clean_optional_doc_id(session_id, 'session_id'),
    )
    return {'status': 'ok', 'deleted_count': count}


@router.patch('/v2/desktop/messages/{message_id}/rating', tags=['chat-sessions'], response_model=StatusResponse)
def rate_message(
    message_id: str,
    request: RateMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if request.rating is not None and request.rating not in (1, -1):
        raise HTTPException(status_code=400, detail='Rating must be 1, -1, or null')
    message_id = _clean_doc_id(message_id, 'message_id')
    snapshot = _guarded(chat_db.update_message_rating, uid, message_id, request.rating)
    if snapshot is None:
        raise HTTPException(status_code=404, detail='Message not found')
    # Also write to analytics collection (same as mobile endpoint) so ratings
    # appear in the admin dashboard chat ratings chart.
    #
    # These are side effects of an already-persisted rating: a transient failure
    # in either used to fail the whole PATCH, so the client reverted the user's
    # thumbs-down even though the rating itself was saved. Each is isolated.
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
    except Exception as error:  # noqa: BLE001 - analytics must not fail the rating
        logger.error('chat rating score write failed: %s', sanitize(error), exc_info=True)
    try:
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
    except Exception as error:  # noqa: BLE001 - ledger must not fail the rating
        logger.error('chat message feedback write failed: %s', sanitize(error), exc_info=True)
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
    ai_message = _guarded(
        initial_message_util,
        uid,
        _clean_optional_doc_id(request.app_id, 'app_id'),
        chat_session_id=_clean_doc_id(request.session_id, 'session_id'),
    )
    return {'message': ai_message.text, 'message_id': ai_message.id}


@router.post('/v2/chat/generate-title', tags=['chat-sessions'], response_model=GenerateTitleResponse)
def generate_session_title(
    request: GenerateTitleRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "chat:initial"))
    ),
):
    """Generate a title for a chat session based on its messages."""
    require_generated_compute(uid, 'session_titles')
    session_id = _clean_doc_id(request.session_id, 'session_id')
    conversation = '\n'.join(f"{m.sender}: {m.text}" for m in request.messages[:10])
    prompt = (
        "Generate a short, descriptive title (max 6 words) for this chat conversation. "
        "Return ONLY the title text, no quotes or punctuation.\n\n"
        f"{conversation}"
    )
    # `BaseChatModel.invoke(...).content` is typed `str | list[str | dict]` by
    # langchain's stubs and providers can return None, so the title is extracted
    # through `_title_from_content` instead of calling .strip() on the raw value.
    with track_usage(uid, Features.CHAT):
        response = cast(Any, get_llm('session_titles').invoke(prompt))
    title = _title_from_content(getattr(response, 'content', None))
    if not title:
        title = 'New Chat'

    _guarded(chat_db.update_chat_session, uid, session_id, title=title)
    return {'title': title}


@router.get('/v1/users/stats/chat-messages', tags=['chat-sessions'], response_model=ChatMessageCountResponse)
def get_chat_message_count(
    uid: str = Depends(auth.get_current_user_uid),
):
    """Get total count of chat messages for the user."""
    count = _guarded(chat_db.get_message_count, uid)
    return {'count': count}
