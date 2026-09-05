import asyncio
import binascii
import json
import tempfile
import uuid
import re
import base64
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path
from utils.executors import critical_executor, db_executor, llm_executor, storage_executor, sync_executor, run_blocking

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    File,
    Form,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from multipart.multipart import shutil
from pydantic import BaseModel

import database.chat as chat_db
from utils.chat_session_target import resolve_chat_target
import database.llm_usage as llm_usage_db
from database.apps import record_app_usage
from models.app import App, UsageHistoryType
from models.chat import (
    ChatEvidenceEnvelope,
    ChatSession,
    Message,
    SendMessageRequest,
    MessageSender,
    ResponseMessage,
    MessageConversation,
    FileChat,
    RateMessageRequest,
    ShareChatMessagesRequest,
)
from utils.apps import get_available_app_by_id
from utils.conversation_helpers import extract_memory_ids
from utils.chat import (
    acquire_chat_session,
    emit_stream_error_fallback,
    initial_message_util,
    process_voice_message_segment_stream,
    resolve_voice_message_language,
    transcribe_voice_message_segment,
    transcribe_pcm_bytes,
)
from utils.sync.files import retrieve_file_paths, decode_files_to_wav
from utils.stt.streaming import STTService, connect_stt_socket_with_fallback, drain_stt_socket
from utils.stt.streaming import get_stt_service_for_language, process_audio_modulate, process_audio_parakeet
from utils.stt.provider_resilience import close_rejected_socket, fallback_socket_is_serving
from utils.stt.pre_recorded import get_prerecorded_service
from config.prerecorded_stt import TranscriptionOutcome
from config.stt_provider_policy import MODULATE_PROVIDER, STTServingSurface, provider_for_service
from utils.stt.outcomes import TranscriptionFailure, failure_from_exception
from utils.observability.transcription import TranscriptionAttempt
from utils.llm.goals import extract_and_update_goal_progress
from database.redis_db import try_acquire_goal_extraction_lock, check_rate_limit, store_chat_share, get_chat_share
from database.users import set_chat_message_rating_score
from utils.chat_rating_triage import extract_rating_triage_fields
from utils.feedback import record_chat_message_feedback
from utils.rate_limit_config import get_effective_limit, RATE_LIMIT_SHADOW
from utils.llm.gateway_client import CHAT_AGENT_ROUTE_DIRECT, get_chat_agent_route
from utils.subscription import enforce_chat_quota, is_trial_paywalled
from utils import share_links
from utils.other import endpoints as auth, storage
from utils.other.chat_file import FileChatTool, UnsupportedChatFileError
from utils.multipart import (
    CHAT_FILE_MAX_PART_SIZE,
    MultipartMaxPartSizeRoute,
    VOICE_MESSAGE_MAX_PART_SIZE,
    max_part_size,
    parse_multipart_form,
)
from utils.retrieval.graph import execute_chat_stream
from utils.llm.usage_tracker import set_usage_context, reset_usage_context, Features
from utils.users import get_user_display_name
from utils.log_sanitizer import sanitize_pii
from utils.chat_followup import followup_content_blocks
from utils.observability import submit_langsmith_feedback
from utils.observability.fallback import record_fallback
from utils.journey_metrics_contract import resolve_client_kind, resolve_client_kind_from_headers
from utils.observability.journeys import ClientJourneyAttempt, JourneyAttempt
from utils.voice_duration_limiter import (
    MAX_SESSION_DURATION_S,
    compute_pcm_duration_ms,
    read_wav_duration_ms,
    try_consume_budget,
    try_reserve_session_budget,
    settle_reserved_duration,
    record_actual_duration,
)
from testing.parity_pack_v0.live_capture import SurfaceParityCapture
import logging

logger = logging.getLogger(__name__)

router = APIRouter(route_class=MultipartMaxPartSizeRoute)

# WS idle timeout: close if no audio bytes received for this long
_WS_IDLE_TIMEOUT_S = 60

# Hard body-size cap for octet-stream uploads (200 MB).
# Prevents memory exhaustion from oversized payloads regardless of budget.
_MAX_PCM_BODY_BYTES = 200_000_000


class VoiceMessageTranscriptionResponse(BaseModel):
    transcript: str
    language: Optional[str] = None
    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None
    outcome: Optional[TranscriptionOutcome] = None


class TranscriptionErrorDetail(BaseModel):
    error: str
    outcome: TranscriptionOutcome
    provider: str
    retryable: bool
    message: str


class TranscriptionErrorResponse(BaseModel):
    detail: TranscriptionErrorDetail


def _transcription_http_error(failure: TranscriptionFailure) -> HTTPException:
    logger.warning(
        'Transcription request failed: outcome=%s provider=%s retryable=%s',
        failure.outcome.value,
        failure.provider,
        failure.retryable,
    )
    return HTTPException(status_code=failure.status_code, detail=failure.as_detail())


def _cleanup_temp_voice_wavs(paths: List[str], uid: str) -> None:
    for path in paths:
        if path.startswith(f'/tmp/{uid}_'):
            try:
                Path(path).unlink()
            except OSError:
                pass


class MessageReportResponse(BaseModel):
    message: str


class ChatRatingResponse(BaseModel):
    status: str


class ShareChatMessagesResponse(BaseModel):
    url: str
    token: str


class SharedChatMessage(BaseModel):
    id: str
    text: str
    sender: str
    created_at: Optional[str] = None


class SharedChatMessagesResponse(BaseModel):
    sender_name: str
    messages: List[SharedChatMessage] = []
    count: int


def _parse_context_keywords(raw: Optional[str]) -> List[str]:
    if not raw:
        return []

    keywords = []
    seen = set()
    for item in raw.split(','):
        keyword = item.strip()
        if len(keyword) < 2 or len(keyword) > 80:
            continue
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(keyword)
        if len(keywords) >= 100:
            break
    return keywords


def _mobile_chat_stream_succeeded(frame: str) -> bool:
    """A mobile answer succeeds only at a terminal frame with renderable text."""

    if not frame.startswith('done: '):
        return False
    try:
        payload = json.loads(base64.b64decode(frame.removeprefix('done: ').strip()).decode('utf-8'))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    answer = payload.get('text') if isinstance(payload, dict) else None
    return isinstance(answer, str) and bool(answer.strip())


def _mobile_chat_stream_failed(frame: str) -> bool:
    """Typed in-band errors are failures even when a fallback done frame follows."""

    return frame.lstrip().startswith('error: ')


def filter_messages(messages, app_id):
    logger.info(f'filter_messages {len(messages)} {app_id}')
    collected = []
    for message in messages:
        if message.sender == MessageSender.ai and message.plugin_id != app_id:
            break
        collected.append(message)
    logger.info(f'filter_messages output: {len(collected)}')
    return collected


def _build_quota_exceeded_reply(
    uid: str,
    data: SendMessageRequest,
    compat_app_id: Optional[str],
    detail: dict,
    chat_session: Optional[ChatSession] = None,
) -> ResponseMessage:
    """Persist the user's question + a canned AI reply and return it.

    Both messages join `chat_session` when the request named one. Without it the
    turn is stored unthreaded: the client shows it optimistically against the
    session the user is looking at, and then it disappears on the next history
    load, because that read is scoped to the session and these rows belong to no
    session at all.

    Mobile clients render the reply as a normal AI message, so users on
    older builds without structured 402 handling at least see *why* nothing
    happened instead of a silent failure. Desktop never reaches this path —
    its client-side quota pre-check in AgentBridge throws BridgeError.quotaExceeded
    before the request fires.
    """
    now = datetime.now(timezone.utc)
    user_msg = Message(
        id=str(uuid.uuid4()),
        text=data.text,
        created_at=now,
        sender='human',
        type='text',
        app_id=compat_app_id,
        chat_session_id=chat_session.id if chat_session else None,
    )
    chat_db.add_message(uid, user_msg.model_dump())
    if chat_session:
        chat_db.add_message_to_chat_session(uid, chat_session.id, user_msg.id)

    plan = detail.get('plan') or 'Free'
    unit = detail.get('unit')
    limit = detail.get('limit')
    reset_at = detail.get('reset_at')
    if unit == 'cost_usd' and isinstance(limit, (int, float)):
        limit_phrase = f"your ${int(limit)} monthly AI compute budget"
    elif isinstance(limit, (int, float)):
        limit_phrase = f"your {int(limit)} monthly chat question limit"
    else:
        limit_phrase = "your monthly chat limit"
    reset_phrase = ''
    if reset_at:
        try:
            reset_dt = datetime.fromtimestamp(int(reset_at), tz=timezone.utc)
            reset_phrase = f' Your limit resets on {reset_dt.strftime("%B %-d")}.'
        except (TypeError, ValueError):
            pass

    canned = (
        f"You've reached {limit_phrase} on the {plan} plan.{reset_phrase}\n\n"
        "Upgrade your plan to keep chatting, or bring your own API keys in Settings "
        "to use Omi free."
    )
    ai_msg = Message(
        id=str(uuid.uuid4()),
        text=canned,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        type='text',
        app_id=compat_app_id,
        chat_session_id=chat_session.id if chat_session else None,
    )
    chat_db.add_message(uid, ai_msg.model_dump())
    if chat_session:
        chat_db.add_message_to_chat_session(uid, chat_session.id, ai_msg.id)
    return ResponseMessage(**ai_msg.model_dump(), ask_for_nps=False)


def _build_quota_accounting_unavailable_reply(compat_app_id: Optional[str]) -> ResponseMessage:
    """SSE-visible retry copy when Free-plan counter persistence fails.

    Returned as an in-memory ``done:`` frame only — do not persist a human or AI
    message here. Persisting before accounting succeeds would orphan user text on
    retries (fresh message ids / idempotency keys under the same outage).
    """
    ai_msg = Message(
        id=str(uuid.uuid4()),
        text=("Usage accounting is temporarily unavailable. Please retry in a moment — " "your message was not saved."),
        created_at=datetime.now(timezone.utc),
        sender='ai',
        type='text',
        app_id=compat_app_id,
    )
    return ResponseMessage(**ai_msg.model_dump(), ask_for_nps=False)


def _record_chat_quota_question(
    uid: str,
    *,
    idempotency_key: str,
    source: str,
    message_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> None:
    """Persist the free-plan question counter. Callers that are about to invoke a
    billable provider must treat failures as request failures (fail-closed)."""
    llm_usage_db.record_chat_quota_question(
        uid,
        idempotency_key=idempotency_key,
        source=source,
        message_id=message_id,
        chat_session_id=chat_session_id,
        platform=platform,
    )


def _record_chat_quota_question_best_effort(
    uid: str,
    *,
    idempotency_key: str,
    source: str,
    message_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> None:
    """Best-effort counter write for paths where the billable work already happened
    (e.g. voice stream after a visible ``message:`` frame)."""
    try:
        _record_chat_quota_question(
            uid,
            idempotency_key=idempotency_key,
            source=source,
            message_id=message_id,
            chat_session_id=chat_session_id,
            platform=platform,
        )
    except Exception:
        logger.exception('Failed to record chat quota question source=%s uid=%s', source, uid)


def _required_chat_quota_provider() -> str | None:
    # Direct agent chat consumes managed Anthropic unless an Anthropic BYOK key
    # is on the request. Other BYOK providers must stay metered on this path.
    return 'anthropic' if get_chat_agent_route() == CHAT_AGENT_ROUTE_DIRECT else None


@router.post('/v2/messages', tags=['chat'], response_model=ResponseMessage)
def send_message(
    data: SendMessageRequest,
    request: Request,
    plugin_id: Optional[str] = None,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:send_message")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    # Catalog hard-cap exhaustion is returned as a canned AI reply instead of a
    # raw 402 (which older mobile clients render as a generic server error).
    # Catalog overage plans return normally. Desktop pre-checks via
    # /v1/users/me/usage-quota and never reaches this path when over.
    try:
        enforce_chat_quota(uid, platform=x_app_platform, required_llm_provider=_required_chat_quota_provider())
    except HTTPException as exc:
        if exc.status_code != 402 or not isinstance(exc.detail, dict):
            raise
        if exc.detail.get('error') != 'quota_exceeded':
            raise
        _compat_id = app_id or plugin_id
        if _compat_id in ['null', '']:
            _compat_id = None
        # Resolved here rather than at the happy path's `_resolve_chat_session`
        # below: quota enforcement returns before that line is ever reached, and
        # the canned reply still belongs in the session the request named.
        _quota_target = resolve_chat_target(uid, _compat_id, chat_session_id)
        response_msg = _build_quota_exceeded_reply(
            uid,
            data,
            _quota_target.app_id,
            exc.detail,
            ChatSession(**_quota_target.session) if _quota_target.session else None,
        )

        def _quota_exceeded_stream():
            encoded = base64.b64encode(bytes(response_msg.model_dump_json(), 'utf-8')).decode('utf-8')
            yield f"done: {encoded}\n\n"

        return StreamingResponse(_quota_exceeded_stream(), media_type="text/event-stream")

    compat_app_id = app_id or plugin_id
    logger.info(f'send_message {sanitize_pii(data.text)} {compat_app_id} {uid}')

    if compat_app_id in ['null', '']:
        compat_app_id = None

    # get chat session — a named session also decides which app this turn runs as
    target = resolve_chat_target(uid, compat_app_id, chat_session_id)
    compat_app_id = target.app_id
    chat_session = ChatSession(**target.session) if target.session else None

    message = Message(
        id=str(uuid.uuid4()),
        text=data.text,
        created_at=datetime.now(timezone.utc),
        sender='human',
        type='text',
        app_id=compat_app_id,
    )
    # Ensure chat session exists when files are attached
    if data.file_ids and not chat_session:
        chat_session = acquire_chat_session(uid, compat_app_id)
        chat_session = ChatSession(**chat_session) if isinstance(chat_session, dict) else chat_session

    if data.file_ids is not None and chat_session:
        new_file_ids = chat_session.retrieve_new_file(data.file_ids)
        chat_session.add_file_ids(data.file_ids)
        chat_db.add_files_to_chat_session(uid, chat_session.id, data.file_ids)

        if len(new_file_ids) > 0:
            message.files_id = new_file_ids
            files = chat_db.get_chat_files(uid, new_file_ids)
            files = [FileChat(**f) if f else None for f in files]
            message.files = files

    if chat_session:
        message.chat_session_id = chat_session.id

    # Fail-closed before persisting the human turn or starting billable work:
    # a Firestore outage must not leave Free-plan turns uncounted, orphan
    # messages on retry, or return a bare HTTP 503 that mobile SSE silently drops.
    try:
        _record_chat_quota_question(
            uid,
            idempotency_key=f'v2_messages:{message.id}',
            source='v2_messages',
            message_id=message.id,
            chat_session_id=message.chat_session_id,
            platform=x_app_platform,
        )
    except Exception:
        logger.exception('Failed to record chat quota question source=v2_messages uid=%s', uid)
        response_msg = _build_quota_accounting_unavailable_reply(compat_app_id)

        def _quota_accounting_unavailable_stream():
            encoded = base64.b64encode(bytes(response_msg.model_dump_json(), 'utf-8')).decode('utf-8')
            yield f"done: {encoded}\n\n"

        return StreamingResponse(_quota_accounting_unavailable_stream(), media_type="text/event-stream")

    if chat_session:
        chat_db.add_message_to_chat_session(uid, chat_session.id, message.id)

    chat_db.add_message(uid, message.model_dump())

    # Check for goal progress (background) — rate-limited to one call per user per 5 min
    if try_acquire_goal_extraction_lock(uid):
        llm_executor.submit(extract_and_update_goal_progress, uid, data.text)

    app = get_available_app_by_id(compat_app_id, uid)
    app = App(**app) if app else None

    app_id_from_app = app.id if app else None

    # Skip a malformed/legacy stored message rather than 500 the whole chat send.
    messages = list(
        reversed(
            Message.deserialize_many_safe(
                chat_db.get_cache_aligned_messages(uid, app_id=compat_app_id, chat_session_id=message.chat_session_id),
                on_error=lambda record, exc: logger.warning(
                    'Skipping malformed chat message %s for uid=%s: %s',
                    record.get('id') if isinstance(record, dict) else None,
                    uid,
                    type(exc).__name__,
                ),
            )
        )
    )

    def process_message(response: str, callback_data: dict):
        memories = callback_data.get('memories_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)
        langsmith_run_id = callback_data.get('langsmith_run_id')
        prompt_name = callback_data.get('prompt_name')
        prompt_commit = callback_data.get('prompt_commit')
        chart_data = callback_data.get('chart_data')
        evidence_payload = callback_data.get('evidence')
        evidence = None
        if evidence_payload is not None:
            try:
                evidence = ChatEvidenceEnvelope.model_validate(evidence_payload)
            except ValueError as evidence_exc:
                # Evidence is optional UI chrome. A malformed tool reference must
                # never prevent persistence or delivery of the answer text.
                logger.warning(
                    'dropping invalid chat evidence uid=%s error_type=%s',
                    uid,
                    type(evidence_exc).__name__,
                )

        # cited extraction
        cited_conversation_idxs = {int(i) for i in re.findall(r'\[(\d+)\]', response)}
        if len(cited_conversation_idxs) > 0:
            response = re.sub(r'\[\d+\]', '', response)
        memories = [memories[i - 1] for i in cited_conversation_idxs if 0 < i and i <= len(memories)]

        memories_id = extract_memory_ids(memories) if memories else []

        ai_message_id = str(uuid.uuid4())
        ai_message = Message(
            id=ai_message_id,
            text=response,
            created_at=datetime.now(timezone.utc),
            sender='ai',
            app_id=app_id_from_app,
            type='text',
            memories_id=memories_id,
            chart_data=chart_data,
            langsmith_run_id=langsmith_run_id,  # Store run_id for feedback tracking
            prompt_name=prompt_name,  # LangSmith prompt name for versioning
            prompt_commit=prompt_commit,  # LangSmith prompt commit for traceability
            evidence=evidence,
            # One grounded next question, as a chip the client can tap. Empty for
            # any turn that failed or has nothing to go one hop further into.
            content_blocks=followup_content_blocks(
                ai_message_id,
                callback_data.get('followup'),
                visible_text=response,
                failed=bool(callback_data.get('error')),
            ),
        )
        if chat_session:
            ai_message.chat_session_id = chat_session.id
            chat_db.add_message_to_chat_session(uid, chat_session.id, ai_message.id)

        chat_db.add_message(uid, ai_message.model_dump())
        ai_message.memories = [MessageConversation(**m) for m in (memories if len(memories) < 5 else memories[:5])]
        usage_app_id = app_id_from_app or compat_app_id
        if usage_app_id:
            try:
                record_app_usage(
                    uid,
                    usage_app_id,
                    UsageHistoryType.chat_message_sent,
                    message_id=ai_message.id,
                )
            except Exception as analytics_exc:
                # Message is already durable; analytics must not change the client-visible id.
                logger.error(
                    'chat stream app usage recording failed for uid=%s message_id=%s: %s',
                    uid,
                    ai_message.id,
                    type(analytics_exc).__name__,
                )

        return ai_message, ask_for_nps

    journey_attempt = JourneyAttempt('chat_response')
    mobile_journey_attempt = ClientJourneyAttempt(
        'mobile_chat',
        resolve_client_kind_from_headers(request.headers),
    )

    async def generate_stream():
        callback_data = {}
        answered = False
        stream_exhausted = False
        streamed_terminal_error = False
        # Set usage context for streaming (can't use 'with' across yields)
        usage_token = set_usage_context(uid, Features.CHAT)

        def emit_done_frame(response: str) -> str:
            """Persist a terminal answer. Typed stream errors stay failed for journey/fallback SLIs.

            If Firestore persistence fails, still emit an in-memory ``done:`` frame (same
            fail-open contract as ``emit_stream_error_fallback``) so the text client is
            not left with only an earlier ``error:`` frame.
            """
            persist_outcome = 'degraded'
            try:
                ai_message, ask_for_nps = process_message(response, callback_data)
            except Exception as persist_exc:
                logger.error(
                    'chat stream terminal answer persistence failed for uid=%s: %s',
                    uid,
                    type(persist_exc).__name__,
                )
                persist_outcome = 'exhausted'
                ai_message = Message(
                    id=str(uuid.uuid4()),
                    text=response,
                    created_at=datetime.now(timezone.utc),
                    sender='ai',
                    app_id=app_id_from_app,
                    type='text',
                )
                if chat_session:
                    ai_message.chat_session_id = chat_session.id
                ask_for_nps = False
            response_message = ResponseMessage(**ai_message.model_dump())
            response_message.ask_for_nps = ask_for_nps
            encoded_response = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode('utf-8')
            if callback_data.get('error'):
                journey_attempt.finish('failure')
                record_fallback(
                    component='other',
                    from_mode='llm_answer',
                    to_mode='canned_reply',
                    reason='other',
                    outcome=persist_outcome,
                )
            else:
                if persist_outcome == 'exhausted':
                    journey_attempt.finish('failure')
                    record_fallback(
                        component='other',
                        from_mode='llm_answer',
                        to_mode='canned_reply',
                        reason='other',
                        outcome='exhausted',
                    )
                else:
                    journey_attempt.finish('success')
            return f"done: {encoded_response}\n\n"

        try:
            async for chunk in execute_chat_stream(
                uid,
                messages,
                app,
                cited=True,
                callback_data=callback_data,
                chat_session=chat_session,
                context=data.context,
                platform=x_app_platform,
                client_kind=mobile_journey_attempt.client_kind,
            ):
                if chunk:
                    if chunk.startswith('error: '):
                        streamed_terminal_error = True
                    msg = chunk.replace("\n", "__CRLF__")
                    yield f'{msg}\n\n'
                else:
                    response = callback_data.get('answer')
                    if response:
                        # This is the furthest server-observable client boundary:
                        # a yielded terminal frame is not a client-render acknowledgement.
                        yield emit_done_frame(response)
                        answered = True

            if not answered:
                # Prefer a staged typed answer (timeout / gateway) even if the producer
                # forgot the None sentinel. Only emit the generic canned sorry when no
                # typed answer was staged — including persona paths that yield ``error:``
                # without setting ``callback_data['answer']`` (those still need ``done:``).
                response = callback_data.get('answer')
                if response:
                    yield emit_done_frame(response)
                else:
                    if streamed_terminal_error:
                        logger.error(
                            'chat stream ended without an answer uid=%s reason=%s route=%s (error=%s)',
                            uid,
                            callback_data.get('error') or 'stream_failure',
                            callback_data.get('route') or 'unknown',
                            True,
                        )
                    yield await emit_stream_error_fallback(
                        uid,
                        app_id_from_app,
                        chat_session,
                        label='chat',
                        error_recorded=bool(callback_data.get('error')),
                        reason=callback_data.get('error'),
                        route=callback_data.get('route'),
                    )
            stream_exhausted = True
        except asyncio.CancelledError:
            journey_attempt.finish('cancelled')
            raise
        except Exception:
            journey_attempt.finish('failure')
            raise
        finally:
            reset_usage_context(usage_token)
            if not journey_attempt.finished:
                journey_attempt.finish('failure' if stream_exhausted else 'cancelled')

    observed_stream = mobile_journey_attempt.observe_stream(
        generate_stream(),
        success_when=_mobile_chat_stream_succeeded,
        failure_when=_mobile_chat_stream_failed,
        failure_class='provider_error',
        missing_success_class='empty_answer',
    )
    return StreamingResponse(observed_stream, media_type="text/event-stream")


@router.post('/v2/messages/{message_id}/report', tags=['chat'], response_model=MessageReportResponse)
def report_message(message_id: str, uid: str = Depends(auth.get_current_user_uid)):
    result = chat_db.get_message(uid, message_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Message not found')
    message, msg_doc_id = result
    if message.sender != 'ai':
        raise HTTPException(status_code=400, detail='Only AI messages can be reported')
    if message.reported:
        raise HTTPException(status_code=400, detail='Message already reported')
    chat_db.report_message(uid, msg_doc_id)
    return {'message': 'Message reported'}


@router.delete('/v2/messages', tags=['chat'], response_model=Message)
def clear_chat_messages(
    app_id: Optional[str] = None,
    plugin_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):
    explicit = bool(chat_session_id)
    compat_app_id = app_id or plugin_id
    if compat_app_id in ['null', '']:
        compat_app_id = None

    # get the targeted chat session. Its own app id scopes the delete: the
    # message rows carry the session's `plugin_id`, so filtering by the query
    # string's app instead deletes the session record and orphans its messages.
    target = resolve_chat_target(uid, compat_app_id, chat_session_id)
    compat_app_id = target.app_id
    chat_session = target.session
    chat_session_id = target.session_id

    err = chat_db.clear_chat(uid, app_id=compat_app_id, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')

    # clean thread chat file
    if chat_session and chat_session.get('id'):
        try:
            fc_tool = FileChatTool(uid, chat_session['id'])
            fc_tool.cleanup()
        except ValueError:
            # Session not found, continue with cleanup
            pass

    # clear session
    if chat_session_id is not None and not explicit:
        chat_db.delete_chat_session(uid, chat_session_id)
    return initial_message_util(uid, compat_app_id, chat_session_id=chat_session_id if explicit else None)


@router.post('/v2/initial-message', tags=['chat'], response_model=Message)
def create_initial_message(
    app_id: Optional[str] = None,
    plugin_id: Optional[str] = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:initial")),
):
    compat_app_id = app_id or plugin_id
    return initial_message_util(uid, compat_app_id)


@router.get('/v2/messages', response_model=List[Message], tags=['chat'])
def get_messages(
    plugin_id: Optional[str] = None,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    compat_app_id = app_id or plugin_id
    if compat_app_id in ['null', '']:
        compat_app_id = None

    target = resolve_chat_target(uid, compat_app_id, chat_session_id)
    compat_app_id = target.app_id
    chat_session_id = target.session_id

    messages = chat_db.get_messages(
        uid,
        limit=limit,
        offset=offset,
        include_conversations=True,
        app_id=compat_app_id,
        chat_session_id=chat_session_id,
    )
    logger.info(f'get_messages {len(messages)} {compat_app_id}')

    # Debug: Check for messages with ratings
    rated_messages = [m for m in messages if m.get('rating') is not None]
    if rated_messages:
        logger.info(f'📊 Messages with ratings: {len(rated_messages)}')
        for m in rated_messages[:5]:  # Show first 5
            logger.info(f"  - Message {m.get('id')}: rating={m.get('rating')}")

    if not messages:
        # The greeting belongs to the session that was read, not to whatever
        # session `acquire_chat_session` would pick for the app.
        return [] if offset > 0 else [initial_message_util(uid, compat_app_id, chat_session_id=chat_session_id)]
    return messages


@router.post(
    "/v2/voice-messages",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent event stream of chat message chunks.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
@max_part_size(VOICE_MESSAGE_MAX_PART_SIZE)
def create_voice_message_stream(
    files: List[UploadFile] = File(...),
    language: Optional[str] = Form(None),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "voice:message")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    enforce_chat_quota(uid, platform=x_app_platform, required_llm_provider=_required_chat_quota_provider())

    resolved_language = resolve_voice_message_language(uid, language)
    stt_provider, _, _stt_model = get_prerecorded_service(resolved_language)
    paths: List[str] = []
    wav_paths: List[str] = []

    def _record_preparation_failure(failure: TranscriptionFailure) -> None:
        preparation_attempt = TranscriptionAttempt(
            route='voice_chat_sse',
            provider=stt_provider,
            platform=x_app_platform,
        )
        preparation_attempt.finish(failure.outcome)

    try:
        paths = retrieve_file_paths(files, uid)
        if not paths:
            raise TranscriptionFailure(
                TranscriptionOutcome.INVALID_INPUT,
                provider=stt_provider,
                retryable=False,
            )
        wav_paths = decode_files_to_wav(paths)
        if not wav_paths:
            raise TranscriptionFailure(
                TranscriptionOutcome.INVALID_INPUT,
                provider=stt_provider,
                retryable=False,
            )

        # Daily budget check (first file only — matches actual DG usage).
        # A quota rejection is not an STT attempt and therefore is not an
        # invalid-input or provider-outcome metric.
        # An unreadable duration must not skip the budget check (STT still
        # runs on it) — charge the worst case instead of charging nothing.
        first_wav = wav_paths[0]
        duration_ms = read_wav_duration_ms(first_wav)
        budget_duration_ms = duration_ms if duration_ms is not None else MAX_SESSION_DURATION_S * 1000
        allowed, used_ms, remaining_ms = try_consume_budget(uid, budget_duration_ms)
        if not allowed:
            raise HTTPException(status_code=429, detail='Daily transcription budget exhausted')
    except TranscriptionFailure as failure:
        _record_preparation_failure(failure)
        _cleanup_temp_voice_wavs(paths + wav_paths, uid)
        raise _transcription_http_error(failure) from failure
    except HTTPException as error:
        _cleanup_temp_voice_wavs(paths + wav_paths, uid)
        if error.status_code == 429:
            raise
        failure = TranscriptionFailure(
            TranscriptionOutcome.INVALID_INPUT,
            provider=stt_provider,
            retryable=False,
        )
        _record_preparation_failure(failure)
        raise _transcription_http_error(failure) from error
    except Exception as error:
        failure = failure_from_exception(error, provider=stt_provider)
        _record_preparation_failure(failure)
        _cleanup_temp_voice_wavs(paths + wav_paths, uid)
        raise _transcription_http_error(failure) from error

    # process
    async def generate_stream():
        attempt = TranscriptionAttempt(
            route='voice_chat_sse',
            provider=stt_provider,
            platform=x_app_platform,
        )
        quota_recorded = False
        try:
            async for chunk in process_voice_message_segment_stream(
                first_wav, uid, language=resolved_language, platform=x_app_platform
            ):
                if chunk.startswith('message: '):
                    attempt.finish(TranscriptionOutcome.SUCCESS)
                if not quota_recorded and chunk.startswith('message: '):
                    payload = chunk.removeprefix('message: ').strip()
                    try:
                        message_data = json.loads(base64.b64decode(payload).decode('utf-8'))
                        await run_blocking(
                            db_executor,
                            _record_chat_quota_question_best_effort,
                            uid,
                            idempotency_key=f"v2_voice_messages:{message_data.get('id') or first_wav}",
                            source='v2_voice_messages',
                            message_id=message_data.get('id'),
                            chat_session_id=message_data.get('chat_session_id'),
                            platform=x_app_platform,
                        )
                        quota_recorded = True
                    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
                        logger.warning('Failed to record voice chat quota question: %s', exc)
                yield chunk
            if not attempt.finished:
                attempt.finish(TranscriptionOutcome.EXPECTED_SILENCE)
        except Exception as error:
            if attempt.finished:
                raise
            failure = failure_from_exception(error, provider=stt_provider)
            attempt.finish(failure.outcome)
            yield f"error: {json.dumps(failure.as_detail(), separators=(',', ':'))}\n\n"
        finally:
            if not attempt.finished:
                attempt.finish(TranscriptionOutcome.UPSTREAM_ERROR)
            await run_blocking(storage_executor, _cleanup_temp_voice_wavs, paths + wav_paths, uid)
            paths.clear()
            wav_paths.clear()

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


@router.post(
    "/v2/voice-message/transcribe",
    response_model=VoiceMessageTranscriptionResponse,
    responses={
        400: {"model": TranscriptionErrorResponse, "description": "Invalid audio input"},
        502: {"model": TranscriptionErrorResponse, "description": "Upstream or unexpected-empty result"},
        503: {"model": TranscriptionErrorResponse, "description": "Provider configuration unavailable"},
        504: {"model": TranscriptionErrorResponse, "description": "Provider timeout"},
    },
)
async def transcribe_voice_message(
    request: Request,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "voice:transcribe")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    """Transcribe audio and return the transcript text.

    Accepts two content types:
    - multipart/form-data: file upload with optional 'language' form field (mobile)
    - application/octet-stream: raw PCM bytes with query params (desktop PTT)

    Returns {"transcript": "...", "language": "..."}.
    """
    # Trial paywall: reject paywalled desktop PTT before hitting Deepgram.
    # Narrow to trial-only on purpose — full enforce_chat_quota here would
    # change mobile behavior for users past their existing 30/mo chat cap.
    if await run_blocking(db_executor, is_trial_paywalled, uid, x_app_platform):
        raise HTTPException(status_code=402, detail={'error': 'quota_exceeded', 'plan_type': 'basic'})

    content_type = request.headers.get("content-type", "")

    if "application/octet-stream" in content_type:
        # Check Content-Length before buffering to reject oversized payloads early
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                parsed_content_length = int(content_length)
            except ValueError as error:
                failure = TranscriptionFailure(
                    TranscriptionOutcome.INVALID_INPUT,
                    provider=None,
                    retryable=False,
                )
                raise _transcription_http_error(failure) from error
            if parsed_content_length > _MAX_PCM_BODY_BYTES:
                raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_PCM_BODY_BYTES} bytes)')

        audio_bytes = await request.body()
        if not audio_bytes or len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail='No audio data provided')

        if len(audio_bytes) > _MAX_PCM_BODY_BYTES:
            del audio_bytes
            raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_PCM_BODY_BYTES} bytes)')

        language = request.query_params.get("language")
        resolved_language = await run_blocking(db_executor, resolve_voice_message_language, uid, language)
        stt_provider, _, stt_model = get_prerecorded_service(resolved_language)
        context_keywords = _parse_context_keywords(request.query_params.get("keywords"))
        encoding = request.query_params.get("encoding", "linear16")
        try:
            sample_rate = int(request.query_params.get("sample_rate", "16000"))
            channels = int(request.query_params.get("channels", "1"))
        except ValueError:
            del audio_bytes
            raise _transcription_http_error(
                TranscriptionFailure(
                    TranscriptionOutcome.INVALID_INPUT,
                    provider=stt_provider,
                    retryable=False,
                )
            )

        if sample_rate < 8000 or sample_rate > 48000:
            del audio_bytes
            raise _transcription_http_error(
                TranscriptionFailure(
                    TranscriptionOutcome.INVALID_INPUT,
                    provider=stt_provider,
                    retryable=False,
                )
            )
        if channels < 1 or channels > 2:
            del audio_bytes
            raise _transcription_http_error(
                TranscriptionFailure(
                    TranscriptionOutcome.INVALID_INPUT,
                    provider=stt_provider,
                    retryable=False,
                )
            )

        parity_capture = SurfaceParityCapture.from_environ(
            principal_id=uid,
            session_id=str(uuid.uuid4()),
            surface="ptt",
            source="desktop_ptt_http",
            provider_lane="stt",
            route_or_model=stt_model or stt_provider or "prerecorded",
            request={
                "encoding": encoding,
                "sample_rate": sample_rate,
                "channels": channels,
                "language": resolved_language,
                "keyword_count": len(context_keywords),
            },
        )
        parity_capture.observe_audio("client", audio_bytes)

        # Daily budget check
        duration_ms = compute_pcm_duration_ms(len(audio_bytes), sample_rate, channels)
        allowed, used_ms, remaining_ms = try_consume_budget(uid, duration_ms)
        if not allowed:
            del audio_bytes
            raise HTTPException(status_code=429, detail='Daily transcription budget exhausted')

        attempt = TranscriptionAttempt(
            route='voice_rest_pcm',
            provider=stt_provider,
            platform=x_app_platform,
        )
        try:
            transcript, detected_language = await run_blocking(
                sync_executor,
                transcribe_pcm_bytes,
                audio_bytes,
                uid,
                language=resolved_language,
                encoding=encoding,
                sample_rate=sample_rate,
                channels=channels,
                keywords=context_keywords,
            )
            outcome = TranscriptionOutcome.SUCCESS if transcript else TranscriptionOutcome.EXPECTED_SILENCE
            parity_capture.observe(
                "inbound",
                {
                    "type": "transcript",
                    "text": transcript or "",
                    "detected_language": detected_language,
                    "outcome": outcome.value,
                },
            )
            attempt.finish(outcome)
        except Exception as error:
            failure = failure_from_exception(error, provider=stt_provider)
            attempt.finish(failure.outcome)
            raise _transcription_http_error(failure) from error
        finally:
            if not attempt.finished:
                attempt.finish(TranscriptionOutcome.UPSTREAM_ERROR)
            parity_capture.persist()
            del audio_bytes

        response = {
            "transcript": transcript or "",
            "stt_provider": stt_provider,
            "stt_model": stt_model,
            "outcome": outcome.value,
        }
        if detected_language:
            response["language"] = detected_language
        return response

    # Multipart file upload mode (original behavior)
    form = await parse_multipart_form(request, max_part_size=VOICE_MESSAGE_MAX_PART_SIZE)
    files = form.getlist("files")
    language = form.get("language")
    upload_files = [f for f in files if hasattr(f, 'file')]
    if not upload_files:
        raise HTTPException(status_code=400, detail='No files provided')
    if any(not file.filename for file in upload_files):
        raise HTTPException(status_code=400, detail='Each uploaded file must have a filename')

    wav_paths = []
    other_file_paths = []
    resolved_language = await run_blocking(db_executor, resolve_voice_message_language, uid, language)
    stt_provider, _, stt_model = get_prerecorded_service(resolved_language)
    transcripts = []
    detected_languages = []
    attempt: TranscriptionAttempt | None = None

    def _record_multipart_preparation_failure(failure: TranscriptionFailure) -> None:
        """Emit a typed terminal result for rejected multipart audio."""
        preparation_attempt = TranscriptionAttempt(
            route='voice_rest_multipart',
            provider=stt_provider,
            platform=x_app_platform,
        )
        preparation_attempt.finish(failure.outcome)

    # Process all files in a single loop
    def _save_wav(path, file_obj):
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file_obj, buffer)

    try:
        # Preprocessing belongs inside the same customer-visible failure
        # boundary as provider work. In particular, decode_files_to_wav can
        # reject corrupt input with HTTPException before a provider call.
        for file in upload_files:
            filename = file.filename
            assert filename is not None
            if (suffix := Path(filename).suffix.lower()) in ('.wav', '.webm', '.mp4'):
                temp_path = f"/tmp/{uid}_{uuid.uuid4()}{suffix}"
                await run_blocking(storage_executor, _save_wav, temp_path, file.file)
                wav_paths.append(temp_path)
            else:
                path = await run_blocking(storage_executor, retrieve_file_paths, [file], uid)
                if path:
                    other_file_paths.extend(path)

        if other_file_paths:
            converted_wav_paths = await run_blocking(storage_executor, decode_files_to_wav, other_file_paths)
            if converted_wav_paths:
                wav_paths.extend(converted_wav_paths)

        if not wav_paths:
            raise TranscriptionFailure(
                TranscriptionOutcome.INVALID_INPUT,
                provider=stt_provider,
                retryable=False,
            )

        # Daily budget check (sum all files). This is not a provider outcome,
        # so do it before recording an accepted transcription attempt.
        # An unreadable duration must not skip the budget check (STT still
        # runs on it) — charge the worst case instead of charging nothing.
        total_duration_ms = 0
        for wav_path in wav_paths:
            duration_ms = await run_blocking(storage_executor, read_wav_duration_ms, wav_path)
            total_duration_ms += duration_ms if duration_ms is not None else MAX_SESSION_DURATION_S * 1000
        allowed, used_ms, remaining_ms = try_consume_budget(uid, total_duration_ms)
        if not allowed:
            raise HTTPException(status_code=429, detail='Daily transcription budget exhausted')

        is_multi = resolved_language == 'multi'
        attempt = TranscriptionAttempt(
            route='voice_rest_multipart',
            provider=stt_provider,
            platform=x_app_platform,
        )
        for wav_path in wav_paths:
            transcript, detected_language = await run_blocking(
                sync_executor, transcribe_voice_message_segment, wav_path, uid, language=resolved_language
            )
            if transcript:
                transcripts.append(transcript)
            if is_multi and detected_language:
                detected_languages.append(detected_language)

        if is_multi:
            unique_languages = {lang for lang in detected_languages if lang}
            detected_language = None
            if len(unique_languages) == 1:
                detected_language = unique_languages.pop()
            elif len(unique_languages) > 1:
                detected_language = "multi"
        else:
            detected_language = None

        combined_transcript = " ".join(transcripts)
        outcome = TranscriptionOutcome.SUCCESS if combined_transcript else TranscriptionOutcome.EXPECTED_SILENCE
        attempt.finish(outcome)
        response = {
            "transcript": combined_transcript,
            "stt_provider": stt_provider,
            "stt_model": stt_model,
            "outcome": outcome.value,
        }
        if detected_language:
            response["language"] = detected_language
        return response
    except TranscriptionFailure as failure:
        if attempt is None:
            _record_multipart_preparation_failure(failure)
        else:
            attempt.finish(failure.outcome)
        raise _transcription_http_error(failure) from failure
    except HTTPException as error:
        if error.status_code == 429:
            raise
        failure = TranscriptionFailure(
            TranscriptionOutcome.INVALID_INPUT,
            provider=stt_provider,
            retryable=False,
        )
        if attempt is None:
            _record_multipart_preparation_failure(failure)
        else:
            attempt.finish(failure.outcome)
        raise _transcription_http_error(failure) from error
    except Exception as error:
        failure = failure_from_exception(error, provider=stt_provider)
        if attempt is None:
            _record_multipart_preparation_failure(failure)
        else:
            attempt.finish(failure.outcome)
        raise _transcription_http_error(failure) from error
    finally:
        if attempt is not None and not attempt.finished:
            attempt.finish(TranscriptionOutcome.UPSTREAM_ERROR)
        # retrieve_file_paths and conversion can both allocate uid-scoped
        # inputs. Clean every path even when preprocessing fails before the
        # previous provider-only try/finally boundary.
        await run_blocking(storage_executor, _cleanup_temp_voice_wavs, wav_paths + other_file_paths, uid)
        transcripts.clear()
        detected_languages.clear()
        wav_paths.clear()
        other_file_paths.clear()


class _PTTStreamSession:
    """PTT transcribe-stream state exposed as the shared ``LiveSTTSession``.

    ``send_live_stt_audio`` and ``terminate_live_stt_session`` operate on this
    protocol, so the PTT surface shares listen's failover-aware send path and
    terminal handling instead of carrying its own copy. Only the terminal path
    writes to it; the endpoint's closure state stays authoritative and adopts
    the verdict (``_mark_stt_terminal``) right after the shared call returns.
    """

    def __init__(self) -> None:
        self.active = True
        self.close_code: Optional[int] = None
        self.stt_terminal_failure = False
        self.live_transcription_attempt: Optional[object] = None
        self.client_live_transcription_attempt: Optional[object] = None


@router.websocket("/v2/voice-message/transcribe-stream")
async def transcribe_voice_message_stream(
    websocket: WebSocket,
    uid: str = Depends(auth.get_current_user_uid_ws_listen),
    language: str = 'en',
    sample_rate: int = 16000,
    codec: str = 'linear16',
    channels: int = 1,
    keywords: Optional[str] = None,
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    """WebSocket endpoint for PTT live mode transcription-only streaming.

    Receives binary PCM audio chunks, streams them to the selected non-Deepgram
    provider, and returns
    transcript segments in real-time. No conversation lifecycle, no memory
    extraction, no pusher — just audio in, transcript out.

    Query params:
        language: Language code (default 'en')
        sample_rate: Audio sample rate in Hz (default 16000)
        codec: Audio codec, must be 'linear16' (default 'linear16')
        channels: Number of audio channels (default 1)
        keywords: Comma-separated context terms to boost recognition

    Client sends:
        - binary frames: audio data (PCM 16-bit)
        - text "finalize": flush remaining audio + trigger provider finalization
    Server sends: JSON arrays of transcript segments
        [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.5, "text": "Hello world",
          "is_user": false, "person_id": null}]
        A recoverable mid-session provider death fails over to the next
        provider in the chain transparently. When the chain is exhausted the
        client first receives a service-status event
        ({"type": "service_status", "status": "stt_failed", ...}) and then a
        WebSocket close 1011 — the same terminal contract as /v4/listen.
    """
    # Lazy: a module-level live_failure import circularly loads
    # observability.transcription while chat tests import this module.
    from utils.stt.live_failure import (
        MAX_STT_FAILOVERS,
        live_stt_socket_is_dead,
        live_stt_upstream_failure,
        send_live_stt_audio,
        terminate_live_stt_session,
    )

    await websocket.accept()

    # Paywalled desktop users — close before opening a provider connection for
    # a PTT stream that would not be allowed to chat anyway.
    if await run_blocking(db_executor, is_trial_paywalled, uid, x_app_platform):
        await websocket.close(code=1008, reason='trial_expired')
        return

    if codec != 'linear16':
        await websocket.close(code=1008, reason='Unsupported codec; only linear16 is supported')
        return

    if sample_rate < 8000 or sample_rate > 48000:
        await websocket.close(code=1008, reason='sample_rate must be between 8000 and 48000')
        return

    if channels < 1 or channels > 2:
        await websocket.close(code=1008, reason='channels must be 1 or 2')
        return

    # Deepgram was the only PTT provider that accepted stereo. Parakeet and
    # Modulate (the retired-DG replacements) wire a mono PCM path: sending
    # interleaved stereo here would be billed as two channels while being
    # transcribed as mono, corrupting timing and quality. Reject channels > 1
    # explicitly instead of silently downmixing or double-billing.
    if channels != 1:
        await websocket.close(code=1008, reason='Only mono (channels=1) is supported by this transcription provider')
        return

    # Inline rate limiting for WebSocket (can't use Depends(with_rate_limit))
    try:
        max_requests, window = get_effective_limit('voice:transcribe_stream')
        allowed, remaining, retry_after = await run_blocking(
            critical_executor, check_rate_limit, uid, 'voice:transcribe_stream', max_requests, window
        )
        if not allowed:
            if not RATE_LIMIT_SHADOW:
                await websocket.close(code=1008, reason=f'Rate limit exceeded. Retry in {retry_after}s.')
                return
            logger.warning(f'[shadow] rate_limit_exceeded policy=voice:transcribe_stream uid={uid}')
    except Exception:
        pass  # Fail-open, consistent with Redis rate limiting elsewhere

    # Daily budget reservation is taken inside the session try/finally so every
    # exit path (including STT connect failure) can settle/refund.
    budget_remaining_ms = None  # None = fail-open (no mid-session enforcement)
    budget_reserved_ms = 0

    websocket_active = True
    dg_socket = None
    sender_task = None
    stt_audio_buffer = bytearray()
    received_audio_bytes = 0  # Includes buffered bytes for admission/budget enforcement.
    accepted_audio_bytes = 0  # Only bytes the provider explicitly accepted.
    # A terminal provider failure after either audio handoff or finalization.
    stt_send_failed = False
    stt_drained = False
    finalization_requested = False
    client_disconnected = False
    usage_recorded = False
    # 30ms flush threshold for the live-STT transport (16-bit PCM = 2 bytes per sample per channel).
    bytes_per_second = sample_rate * channels * 2
    stt_buffer_flush_size = int(bytes_per_second * 0.03)
    # Providers that already died for this session; the failover chain excludes
    # them so a rebuild never lands on the provider that just failed.
    stt_failed_providers: set[str] = set()

    journey_attempt = ClientJourneyAttempt(
        'realtime_voice',
        resolve_client_kind(
            x_app_platform=x_app_platform,
            user_agent=websocket.headers.get('user-agent'),
        ),
    )
    ptt_session = _PTTStreamSession()
    # The shared terminal path fails this attempt with 'provider_error' itself;
    # ClientJourneyAttempt is one-shot, so the finally block cannot double-fail.
    ptt_session.client_live_transcription_attempt = journey_attempt
    stt_service, stt_language, stt_model = get_stt_service_for_language(language, surface=STTServingSurface.PTT)
    if stt_service is None or stt_language is None or stt_model is None:
        journey_attempt.fail('dependency_unavailable')
        await websocket.close(code=1011, reason='Transcription service unavailable')
        return
    context_keywords = _parse_context_keywords(keywords)
    parity_capture = SurfaceParityCapture.from_environ(
        principal_id=uid,
        session_id=str(uuid.uuid4()),
        surface="ptt",
        source="desktop_ptt_stream",
        provider_lane="stt",
        route_or_model=stt_model,
        request={
            "codec": codec,
            "sample_rate": sample_rate,
            "channels": channels,
            "language": stt_language,
            "keyword_count": len(context_keywords),
        },
    )

    loop = asyncio.get_running_loop()

    # Provider callbacks can run off-loop — bridge to async via
    # loop.call_soon_threadsafe so asyncio.Queue wakeups are reliable.
    _SENTINEL = object()
    segment_queue = asyncio.Queue()

    def stream_transcript(segments):
        parity_capture.observe("inbound", {"type": "transcript", "segments": segments})
        loop.call_soon_threadsafe(segment_queue.put_nowait, segments)

    async def segment_sender():
        """Forward segments from the thread-safe queue to the WebSocket."""
        nonlocal client_disconnected, websocket_active
        while websocket_active:
            try:
                segments = await asyncio.wait_for(segment_queue.get(), timeout=0.5)
                if segments is _SENTINEL:
                    break
                await websocket.send_json(segments)
                if isinstance(segments, list) and any(
                    isinstance(segment, dict) and str(segment.get('text') or '').strip() for segment in segments
                ):
                    journey_attempt.succeed()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning(f'transcribe-stream: segment_sender error uid={uid}: {e}')
                client_disconnected = True
                websocket_active = False
                break

    def serving_provider() -> Optional[str]:
        """Provider actually serving this stream, read at use time.

        The connect-time fallback and the mid-session failover can both hand
        the session to a different provider, so a value snapshotted before the
        socket exists attributes the wrong provider's failure (#11306).
        """
        return getattr(stt_service, 'value', stt_service)

    def _mark_stt_terminal() -> None:
        """Adopt a terminal live-STT verdict in this endpoint's closure state."""
        nonlocal websocket_active, stt_send_failed
        if stt_send_failed:
            return
        stt_send_failed = True
        websocket_active = False
        logger.error('event=ptt_transcription_stream outcome=provider_terminal_failure')

    async def close_stt_failure(reason: str = 'connection_lost') -> None:
        """Expose an unusable live-STT session before the caller drops audio."""
        if stt_send_failed:
            return
        _mark_stt_terminal()
        # The shared terminal fails the journey attempt, sends the terminal
        # service-status event, and closes 1011 — the listen wire contract.
        await terminate_live_stt_session(
            websocket,
            ptt_session,
            failure=live_stt_upstream_failure(serving_provider()),
            reason=reason,
            platform=x_app_platform,
        )

    async def failover_stt_socket() -> bool:
        """Swap a dead provider socket for the next one in the PTT chain.

        Same shape as listen's ``_failover_stt_socket``: the send path observes
        a provider death on the very next chunk — Modulate/Velma accepts the
        upgrade and only then dies on the first audio send — so a recoverable
        death must rebuild the socket instead of ending the session with 1011.
        The PTT surface has no separate death-monitor task, so this single
        receive loop is the only caller and no failover lock is needed.
        """
        nonlocal dg_socket, stt_service, stt_language, stt_model
        if dg_socket is not None and not live_stt_socket_is_dead(dg_socket):
            return True
        if stt_send_failed or not websocket_active:
            return False
        dead_provider = provider_for_service(stt_service)
        if dead_provider:
            stt_failed_providers.add(dead_provider)
        if len(stt_failed_providers) > MAX_STT_FAILOVERS:
            return False
        service, next_language, next_model = get_stt_service_for_language(
            language, surface=STTServingSurface.PTT, exclude=frozenset(stt_failed_providers)
        )
        if service is None or provider_for_service(service) in stt_failed_providers:
            # The second check also covers a selector that ignores ``exclude``
            # and re-offers a provider this session already marked dead.
            return False
        try:
            if service == STTService.parakeet:
                # A provider is never offered its own failure as a fallback, so
                # the Modulate leg is omitted once it has died for this session.
                socket, actual_service = await connect_stt_socket_with_fallback(
                    primary_service=STTService.parakeet,
                    connect_primary=lambda: process_audio_parakeet(
                        stream_transcript,
                        language=next_language,
                        sample_rate=sample_rate,
                        channels=channels,
                        model=next_model,
                        keywords=context_keywords,
                        is_active=lambda: websocket_active,
                    ),
                    connect_modulate=(
                        None
                        if MODULATE_PROVIDER in stt_failed_providers
                        else lambda: process_audio_modulate(stream_transcript, sample_rate, next_language)
                    ),
                )
            elif service == STTService.modulate:
                socket = await process_audio_modulate(stream_transcript, sample_rate, next_language)
                actual_service = STTService.modulate
            else:
                return False
        except Exception:
            logger.exception('transcribe-stream: STT failover connect raised')
            return False
        if socket is None:
            return False
        # A provider can accept the upgrade and reject the stream ~150ms later;
        # treating that as a heal would report recovery for a session that is
        # already dead again.
        if not await fallback_socket_is_serving(socket):
            close_rejected_socket(socket)
            return False
        if actual_service == STTService.modulate:
            next_model = 'velma-2'
        previous_socket = dg_socket
        dg_socket = socket
        stt_service, stt_language, stt_model = actual_service, next_language, next_model
        record_fallback(
            component='stt_live_session',
            from_mode=dead_provider or 'unknown',
            to_mode=actual_service.value,
            reason='connection_lost',
            outcome='recovered',
        )
        logger.info(f'STT failover mid-session: {dead_provider} -> {actual_service.value}')
        if previous_socket is not None:
            try:
                previous_socket.finish()
            except Exception:
                logger.warning('transcribe-stream: failed to close the dead STT socket before failover')
        return True

    async def send_stt_audio_or_close(audio: bytes) -> bool:
        """Require the provider to accept audio before its caller discards it.

        A recoverable send-path death fails over to the next provider and the
        chunk is retried against the replacement socket instead of being
        dropped — the chunk stays the caller's until a socket accepted it.
        """
        if stt_send_failed:
            return False
        # Bounded retry, not a single attempt: ``failover_stt_socket`` enforces
        # MAX_STT_FAILOVERS, so the bound here is a backstop, not the limit.
        for _ in range(MAX_STT_FAILOVERS + 2):
            sent = await send_live_stt_audio(
                websocket,
                ptt_session,
                stt_socket=dg_socket,
                audio=audio,
                provider=serving_provider(),
                platform=x_app_platform,
                attempt_failover=failover_stt_socket,
            )
            if sent:
                return True
            if ptt_session.stt_terminal_failure:
                # The shared terminal already failed the journey attempt and
                # closed the client; adopt its verdict in the PTT state.
                _mark_stt_terminal()
                return False
            # The failover swapped the socket; retry the chunk against it.
        await close_stt_failure('send_failed')
        return False

    def record_stt_usage_once() -> None:
        """Settle the connect-time reservation after a successful provider drain."""
        nonlocal usage_recorded
        if usage_recorded or bytes_per_second <= 0:
            return
        actual_duration_ms = (
            compute_pcm_duration_ms(accepted_audio_bytes, sample_rate, channels) if accepted_audio_bytes > 0 else 0
        )
        if budget_reserved_ms > 0:
            settle_reserved_duration(uid, budget_reserved_ms, actual_duration_ms)
        elif actual_duration_ms > 0:
            # Fail-open path never reserved; keep force-record tracking.
            record_actual_duration(uid, actual_duration_ms)
        usage_recorded = True

    def refund_reservation_once() -> None:
        """Release an unused reservation when the session never drained successfully."""
        nonlocal usage_recorded
        if usage_recorded or budget_reserved_ms <= 0:
            return
        settle_reserved_duration(uid, budget_reserved_ms, 0)
        usage_recorded = True

    async def drain_stt_or_close() -> bool:
        """Finalize and await the selected provider's tail before sender teardown."""
        nonlocal stt_drained
        if stt_send_failed:
            return False
        if stt_drained:
            return True
        try:
            if dg_socket is None:
                raise RuntimeError('missing STT socket')
            dg_socket.finalize()
            await drain_stt_socket(dg_socket)
        except Exception:
            await close_stt_failure()
            return False
        stt_drained = True
        return True

    try:
        # Atomically reserve up to one session before opening a provider.
        # Probe-only check_budget + force-record at end lets concurrent WS
        # sessions each freeze the same remaining slice and overspend.
        try:
            allowed, reserved_ms, _used_ms, _remaining_ms = try_reserve_session_budget(
                uid, MAX_SESSION_DURATION_S * 1000
            )
            if not allowed:
                await websocket.close(code=1008, reason='Daily transcription budget exhausted')
                return
            if reserved_ms > 0:
                budget_reserved_ms = reserved_ms
                budget_remaining_ms = reserved_ms
        except Exception:
            pass  # Fail-open

        if stt_service == STTService.parakeet:
            dg_socket, stt_service = await connect_stt_socket_with_fallback(
                primary_service=STTService.parakeet,
                connect_primary=lambda: process_audio_parakeet(
                    stream_transcript,
                    language=stt_language,
                    sample_rate=sample_rate,
                    channels=channels,
                    model=stt_model,
                    keywords=context_keywords,
                    is_active=lambda: websocket_active,
                ),
                connect_modulate=lambda: process_audio_modulate(stream_transcript, sample_rate, stt_language),
            )
        elif stt_service == STTService.modulate:
            dg_socket = await process_audio_modulate(stream_transcript, sample_rate, stt_language)
        else:
            raise RuntimeError(f'Unsupported serving STT provider {stt_service!r}')

        if dg_socket is None:
            journey_attempt.fail('dependency_unavailable')
            logger.error(
                'transcribe-stream: failed to connect to STT provider uid=%s provider=%s', uid, stt_service.value
            )
            await websocket.close(code=1011, reason='Transcription service unavailable')
            return

        # Start segment sender task
        sender_task = asyncio.create_task(segment_sender())

        # Audio receive loop with audio-idle timeout.
        # Timeout is based on last *audio* frame, not last message — text-only
        # frames (e.g. "finalize") don't reset the idle clock.
        last_audio_time = asyncio.get_event_loop().time()
        while websocket_active:
            # Compute remaining idle budget based on last audio receipt
            now = asyncio.get_event_loop().time()
            remaining_idle = _WS_IDLE_TIMEOUT_S - (now - last_audio_time)
            if remaining_idle <= 0:
                logger.info(f'transcribe-stream: audio-idle timeout ({_WS_IDLE_TIMEOUT_S}s) uid={uid}')
                await websocket.close(code=1008, reason=f'Idle timeout: no audio for {_WS_IDLE_TIMEOUT_S}s')
                break

            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=remaining_idle)
            except asyncio.TimeoutError:
                logger.info(f'transcribe-stream: audio-idle timeout ({_WS_IDLE_TIMEOUT_S}s) uid={uid}')
                await websocket.close(code=1008, reason=f'Idle timeout: no audio for {_WS_IDLE_TIMEOUT_S}s')
                break
            except WebSocketDisconnect:
                client_disconnected = True
                break

            if message.get("type") == "websocket.disconnect":
                client_disconnected = True
                break

            # Handle text "finalize" message: flush remaining audio and await the provider's
            # final transcript. Finalization is terminal; clients close once they have received it.
            # Note: text frames do NOT reset the audio-idle timer.
            text_data = message.get("text")
            if text_data and text_data.strip() == "finalize":
                finalization_requested = True
                if dg_socket and not stt_send_failed:
                    if len(stt_audio_buffer) > 0:
                        if not await send_stt_audio_or_close(bytes(stt_audio_buffer)):
                            break
                        accepted_audio_bytes += len(stt_audio_buffer)
                        stt_audio_buffer.clear()
                    if await drain_stt_or_close():
                        record_stt_usage_once()
                    else:
                        break
                continue

            data = message.get("bytes")
            if data is None:
                continue

            if stt_drained:
                await websocket.close(code=1008, reason='Transcription already finalized')
                break

            last_audio_time = asyncio.get_event_loop().time()

            # Guard against oversized frames (5 MB matches REST endpoint limit)
            if len(data) > 5 * 1024 * 1024:
                logger.warning(f'transcribe-stream: oversized frame uid={uid} size={len(data)}')
                continue

            # In-session budget enforcement: check BEFORE incrementing received_audio_bytes
            # so that the triggering frame is not counted as consumed (it won't be sent upstream).
            if budget_remaining_ms is not None and bytes_per_second > 0:
                prospective_ms = compute_pcm_duration_ms(received_audio_bytes + len(data), sample_rate, channels)
                if prospective_ms > budget_remaining_ms:
                    logger.info(
                        f'transcribe-stream: budget exhausted mid-session uid={uid} elapsed={prospective_ms}ms remaining={budget_remaining_ms}ms'
                    )
                    await websocket.close(code=1008, reason='Daily transcription budget exhausted')
                    break

            received_audio_bytes += len(data)
            parity_capture.observe_audio("client", data)
            stt_audio_buffer.extend(data)

            # Flush to the selected provider in 30ms chunks.
            while len(stt_audio_buffer) >= stt_buffer_flush_size:
                chunk = bytes(stt_audio_buffer[:stt_buffer_flush_size])
                if not await send_stt_audio_or_close(chunk):
                    break
                del stt_audio_buffer[:stt_buffer_flush_size]
                accepted_audio_bytes += len(chunk)

    except WebSocketDisconnect:
        client_disconnected = True
    except Exception as e:
        logger.error(f'transcribe-stream: error uid={uid}: {e}')
        await close_stt_failure()
    finally:
        websocket_active = False

        # Flush remaining audio buffer
        if dg_socket and not stt_send_failed and not stt_drained and len(stt_audio_buffer) > 0:
            if await send_stt_audio_or_close(bytes(stt_audio_buffer)):
                accepted_audio_bytes += len(stt_audio_buffer)
                stt_audio_buffer.clear()

        # Await a healthy provider's final tail before stopping the segment sender.
        # A rejected send still gets a best-effort close but no final transcript or usage charge.
        if dg_socket and not stt_send_failed and await drain_stt_or_close():
            record_stt_usage_once()
        else:
            # Provider never drained successfully — refund the connect-time reservation.
            refund_reservation_once()

        if dg_socket and not stt_drained:
            try:
                await drain_stt_socket(dg_socket)
            except Exception:
                try:
                    dg_socket.finish()
                except Exception:
                    pass

        # Signal sender task to drain and stop, then wait for it
        loop.call_soon_threadsafe(segment_queue.put_nowait, _SENTINEL)
        if sender_task is not None:
            try:
                await asyncio.wait_for(sender_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass

        if not journey_attempt.finished:
            if client_disconnected:
                journey_attempt.cancel()
            elif stt_send_failed:
                journey_attempt.fail('provider_error')
            elif finalization_requested:
                journey_attempt.fail('empty_answer')
            else:
                journey_attempt.cancel()

        del stt_audio_buffer
        parity_capture.persist()


@router.post('/v2/files', response_model=List[FileChat], tags=['chat'])
@max_part_size(CHAT_FILE_MAX_PART_SIZE)
def upload_file_chat(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "file:upload")),
):
    thumbs_name = []
    files_chat = []
    for file in files:
        # Use a UUID-based temp file name to prevent path traversal via user-controlled filename
        safe_suffix = Path(file.filename).name if file.filename else "upload"
        temp_file = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}_{safe_suffix}"
        try:
            with temp_file.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            try:
                result = FileChatTool.upload(temp_file)
            except UnsupportedChatFileError as error:
                raise HTTPException(status_code=400, detail=str(error))

            thumb_name = result.get("thumbnail_name", "")
            if thumb_name != "":
                thumbs_name.append(thumb_name)

            filechat = FileChat(
                id=str(uuid.uuid4()),
                name=result.get("file_name", ""),
                mime_type=result.get("mime_type", ""),
                openai_file_id=result.get("file_id", ""),
                created_at=datetime.now(timezone.utc),
                thumb_name=thumb_name,
            )
            files_chat.append(filechat)
        finally:
            if temp_file.exists():
                temp_file.unlink()

    if len(thumbs_name) > 0:
        thumbs_path = storage.upload_multi_chat_files(thumbs_name, uid)
        for fc in files_chat:
            if not fc.is_image():
                continue
            thumb_path = thumbs_path.get(fc.thumb_name, "")
            fc.thumbnail = thumb_path
            # cleanup file thumb
            thumb_file = Path(fc.thumb_name)
            if thumb_file.exists():
                thumb_file.unlink()

    # save db
    files_chat_dict = [fc.model_dump() for fc in files_chat]

    chat_db.add_multi_files(uid, files_chat_dict)

    response = [fc.model_dump() for fc in files_chat]

    return response


# CLEANUP: Remove after new app goes to prod ----------------------------------------------------------


@router.post(
    '/v1/files',
    response_model=List[FileChat],
    tags=['chat'],
    operation_id='upload_file_chat_v1_files_post',
)
@max_part_size(CHAT_FILE_MAX_PART_SIZE)
def upload_file_chat_v1(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "file:upload")),
):
    thumbs_name = []
    files_chat = []
    for file in files:
        # Use a UUID-based temp file name to prevent path traversal via user-controlled filename
        safe_suffix = Path(file.filename).name if file.filename else "upload"
        temp_file = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}_{safe_suffix}"
        try:
            with temp_file.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            try:
                result = FileChatTool.upload(temp_file)
            except UnsupportedChatFileError as error:
                raise HTTPException(status_code=400, detail=str(error))

            thumb_name = result.get("thumbnail_name", "")
            if thumb_name != "":
                thumbs_name.append(thumb_name)

            filechat = FileChat(
                id=str(uuid.uuid4()),
                name=result.get("file_name", ""),
                mime_type=result.get("mime_type", ""),
                openai_file_id=result.get("file_id", ""),
                created_at=datetime.now(timezone.utc),
                thumb_name=thumb_name,
            )
            files_chat.append(filechat)
        finally:
            if temp_file.exists():
                temp_file.unlink()

    if len(thumbs_name) > 0:
        thumbs_path = storage.upload_multi_chat_files(thumbs_name, uid)
        for fc in files_chat:
            if not fc.is_image():
                continue
            thumb_path = thumbs_path.get(fc.thumb_name, "")
            fc.thumbnail = thumb_path
            # cleanup file thumb
            thumb_file = Path(fc.thumb_name)
            thumb_file.unlink()

    # save db
    files_chat_dict = [fc.model_dump() for fc in files_chat]

    chat_db.add_multi_files(uid, files_chat_dict)

    response = [fc.model_dump() for fc in files_chat]

    return response


@router.post(
    '/v1/messages/{message_id}/report',
    tags=['chat'],
    response_model=dict,
    operation_id='report_message_v1_messages__message_id__report_post',
)
def report_message_v1(message_id: str, uid: str = Depends(auth.get_current_user_uid)):
    result = chat_db.get_message(uid, message_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Message not found')
    message, msg_doc_id = result
    if message.sender != 'ai':
        raise HTTPException(status_code=400, detail='Only AI messages can be reported')
    if message.reported:
        raise HTTPException(status_code=400, detail='Message already reported')
    chat_db.report_message(uid, msg_doc_id)
    return {'message': 'Message reported'}


@router.delete(
    '/v1/messages',
    tags=['chat'],
    response_model=Message,
    operation_id='clear_chat_messages_v1_messages_delete',
)
def clear_chat_messages_v1(
    plugin_id: Optional[str] = None, app_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    compat_app_id = app_id or plugin_id
    if compat_app_id in ['null', '']:
        compat_app_id = None

    # get current chat session
    chat_session = chat_db.get_chat_session(uid, app_id=compat_app_id)
    chat_session_id = chat_session['id'] if chat_session else None

    err = chat_db.clear_chat(uid, app_id=compat_app_id, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')

    # clean thread chat file (v1 endpoint)
    if chat_session and chat_session.get('id'):
        try:
            fc_tool = FileChatTool(uid, chat_session['id'])
            fc_tool.cleanup()
        except ValueError:
            # Session not found, continue with cleanup
            pass

    # clear session
    if chat_session_id is not None:
        chat_db.delete_chat_session(uid, chat_session_id)

    return initial_message_util(uid, compat_app_id)


@router.post(
    '/v1/initial-message',
    tags=['chat'],
    response_model=Message,
    operation_id='create_initial_message_v1_initial_message_post',
)
def create_initial_message_v1(
    plugin_id: Optional[str] = None,
    app_id: Optional[str] = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:initial")),
):
    compat_app_id = app_id or plugin_id
    return initial_message_util(uid, compat_app_id)


# MARK: - Message Rating


@router.patch('/v2/messages/{message_id}/rating', tags=['chat'], response_model=ChatRatingResponse)
def rate_message(
    message_id: str,
    data: RateMessageRequest,
    x_app_platform: str | None = Header(None, alias='X-App-Platform'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Rate a chat message (thumbs up/down). Used by desktop client."""
    rating = data.rating

    snapshot = chat_db.update_message_rating(uid, message_id, rating) or {}
    value = rating if rating is not None else 0
    platform = (x_app_platform or '').strip().lower()
    if platform not in ('desktop', 'mobile'):
        platform = 'desktop'
    triage = extract_rating_triage_fields(snapshot)
    reason = data.reason.value if data.reason else None
    set_chat_message_rating_score(
        uid,
        message_id,
        value,
        reason=reason,
        platform=platform,
        notification_kind=triage.get('notification_kind'),
        app_id=triage.get('app_id'),
    )

    # Unified feedback ledger — the daily thumbs-down report reads from here.
    record_chat_message_feedback(
        uid,
        message_id,
        value,
        reason=reason,
        comment=data.comment,
        platform=platform,
    )

    # Try to submit feedback to LangSmith
    try:
        message_result = chat_db.get_message(uid, message_id)
        if message_result:
            message, _ = message_result
            langsmith_run_id = getattr(message, 'langsmith_run_id', None)
            if not langsmith_run_id and isinstance(message, dict):
                langsmith_run_id = message.get('langsmith_run_id')

            if langsmith_run_id:
                score = 1.0 if rating == 1 else (0.0 if rating == -1 else 0.5)
                submit_langsmith_feedback(
                    run_id=langsmith_run_id,
                    score=score,
                    key="chat_message_rating",
                )
    except Exception as e:
        logger.error(f"LangSmith feedback submission error (non-fatal): {e}")

    return {'status': 'ok'}


# MARK: - Chat Sharing


@router.post('/v2/messages/share', tags=['chat'], response_model=ShareChatMessagesResponse)
def share_chat_messages(
    data: ShareChatMessagesRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Create a shareable link for chat messages."""
    message_ids = data.message_ids
    if not message_ids:
        raise HTTPException(status_code=400, detail='No message IDs provided')

    # Validate messages belong to user
    for mid in message_ids:
        msg = chat_db.get_message(uid, mid)
        if not msg:
            raise HTTPException(status_code=404, detail=f'Message {mid} not found')

    display_name = get_user_display_name(uid)
    token = uuid.uuid4().hex
    result = store_chat_share(token, uid, display_name, message_ids)
    if result is None:
        raise HTTPException(status_code=500, detail='Failed to create share link')

    return {"url": share_links.build_share_url(f"/chat/{token}"), "token": token}


@router.get('/v2/messages/shared/{token}', tags=['chat'], response_model=SharedChatMessagesResponse)
def get_shared_chat_messages(token: str):
    """Public endpoint — get shared chat messages (no auth required)."""
    share_data = get_chat_share(token)
    if not share_data:
        raise HTTPException(status_code=404, detail='Share link expired or not found')

    sender_uid = share_data['uid']
    message_ids = share_data['message_ids']

    messages = []
    for mid in message_ids:
        msg_result = chat_db.get_message(sender_uid, mid)
        if msg_result:
            message, _ = msg_result
            messages.append(
                {
                    "id": message.id,
                    "text": message.text,
                    "sender": message.sender,
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                }
            )

    return {
        "sender_name": share_data['display_name'],
        "messages": messages,
        "count": len(messages),
    }
