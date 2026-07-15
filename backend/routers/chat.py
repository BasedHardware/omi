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
import database.conversations as conversations_db
import database.llm_usage as llm_usage_db
from database.apps import record_app_usage
from models.app import App, UsageHistoryType
from models.chat import (
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
    initial_message_util,
    process_voice_message_segment,
    process_voice_message_segment_stream,
    resolve_voice_message_language,
    transcribe_voice_message_segment,
    transcribe_pcm_bytes,
)
from utils.sync.files import retrieve_file_paths, decode_files_to_wav
from utils.stt.streaming import process_audio_dg, get_stt_service_for_language
from utils.stt.pre_recorded import get_prerecorded_service
from config.prerecorded_stt import TranscriptionOutcome
from utils.stt.outcomes import TranscriptionFailure, failure_from_exception
from utils.observability.transcription import TranscriptionAttempt
from utils.llm.goals import extract_and_update_goal_progress
from database.redis_db import try_acquire_goal_extraction_lock, check_rate_limit, store_chat_share, get_chat_share
from database.users import set_chat_message_rating_score
from utils.rate_limit_config import get_effective_limit, RATE_LIMIT_SHADOW
from utils.subscription import enforce_chat_quota, is_trial_paywalled
from utils.other import endpoints as auth, storage
from utils.other.chat_file import FileChatTool
from utils.multipart import (
    CHAT_FILE_MAX_PART_SIZE,
    MultipartMaxPartSizeRoute,
    VOICE_MESSAGE_MAX_PART_SIZE,
    max_part_size,
    parse_multipart_form,
)
from utils.retrieval.graph import execute_graph_chat, execute_chat_stream, execute_persona_chat_stream
from utils.llm.usage_tracker import set_usage_context, reset_usage_context, Features
from utils.users import get_user_display_name
from utils.log_sanitizer import sanitize_pii
from utils.observability import submit_langsmith_feedback
from utils.voice_duration_limiter import (
    compute_pcm_duration_ms,
    read_wav_duration_ms,
    try_consume_budget,
    check_budget,
    record_actual_duration,
)
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
    uid: str, data: SendMessageRequest, compat_app_id: Optional[str], detail: dict
) -> ResponseMessage:
    """Persist the user's question + a canned AI reply and return it.

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
    )
    chat_db.add_message(uid, user_msg.model_dump())

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
    )
    chat_db.add_message(uid, ai_msg.model_dump())
    return ResponseMessage(**ai_msg.model_dump(), ask_for_nps=False)


def _record_chat_quota_question_safe(
    uid: str,
    *,
    idempotency_key: str,
    source: str,
    message_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    platform: Optional[str] = None,
):
    try:
        llm_usage_db.record_chat_quota_question(
            uid,
            idempotency_key=idempotency_key,
            source=source,
            message_id=message_id,
            chat_session_id=chat_session_id,
            platform=platform,
        )
    except Exception:
        logger.exception('Failed to record chat quota question source=%s uid=%s', source, uid)


@router.post('/v2/messages', tags=['chat'], response_model=ResponseMessage)
def send_message(
    data: SendMessageRequest,
    plugin_id: Optional[str] = None,
    app_id: Optional[str] = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:send_message")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    # Hard cap: Free by question count, Architect by cost_usd. Operator enters
    # overage mode silently. If exceeded, instead of raising 402 (which mobile
    # clients render as a generic "having issues with the server" error), save
    # a canned AI reply and emit it as an SSE `done:` chunk — matching the
    # streaming contract this endpoint already uses — so mobile parses it like
    # any other reply. Desktop pre-checks via /v1/users/me/usage-quota and
    # never reaches here when over.
    try:
        enforce_chat_quota(uid, platform=x_app_platform)
    except HTTPException as exc:
        if exc.status_code != 402 or not isinstance(exc.detail, dict):
            raise
        if exc.detail.get('error') != 'quota_exceeded':
            raise
        _compat_id = app_id or plugin_id
        if _compat_id in ['null', '']:
            _compat_id = None
        response_msg = _build_quota_exceeded_reply(uid, data, _compat_id, exc.detail)

        def _quota_exceeded_stream():
            encoded = base64.b64encode(bytes(response_msg.model_dump_json(), 'utf-8')).decode('utf-8')
            yield f"done: {encoded}\n\n"

        return StreamingResponse(_quota_exceeded_stream(), media_type="text/event-stream")

    compat_app_id = app_id or plugin_id
    logger.info(f'send_message {sanitize_pii(data.text)} {compat_app_id} {uid}')

    if compat_app_id in ['null', '']:
        compat_app_id = None

    # get chat session
    chat_session = chat_db.get_chat_session(uid, app_id=compat_app_id)
    chat_session = ChatSession(**chat_session) if chat_session else None

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
        chat_db.add_message_to_chat_session(uid, chat_session.id, message.id)

    chat_db.add_message(uid, message.model_dump())
    _record_chat_quota_question_safe(
        uid,
        idempotency_key=f'v2_messages:{message.id}',
        source='v2_messages',
        message_id=message.id,
        chat_session_id=message.chat_session_id,
        platform=x_app_platform,
    )

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
                chat_db.get_messages(uid, limit=10, app_id=compat_app_id),
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

        # cited extraction
        cited_conversation_idxs = {int(i) for i in re.findall(r'\[(\d+)\]', response)}
        if len(cited_conversation_idxs) > 0:
            response = re.sub(r'\[\d+\]', '', response)
        memories = [memories[i - 1] for i in cited_conversation_idxs if 0 < i and i <= len(memories)]

        memories_id = extract_memory_ids(memories) if memories else []

        ai_message = Message(
            id=str(uuid.uuid4()),
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
        )
        if chat_session:
            ai_message.chat_session_id = chat_session.id
            chat_db.add_message_to_chat_session(uid, chat_session.id, ai_message.id)

        chat_db.add_message(uid, ai_message.model_dump())
        ai_message.memories = [MessageConversation(**m) for m in (memories if len(memories) < 5 else memories[:5])]
        if app_id:
            record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

        return ai_message, ask_for_nps

    async def generate_stream():
        callback_data = {}
        # Set usage context for streaming (can't use 'with' across yields)
        usage_token = set_usage_context(uid, Features.CHAT)
        try:
            async for chunk in execute_chat_stream(
                uid,
                messages,
                app,
                cited=True,
                callback_data=callback_data,
                chat_session=chat_session,
                context=data.context,
            ):
                if chunk:
                    msg = chunk.replace("\n", "__CRLF__")
                    yield f'{msg}\n\n'
                else:
                    response = callback_data.get('answer')
                    if response:
                        ai_message, ask_for_nps = process_message(response, callback_data)
                        ai_message_dict = ai_message.model_dump()
                        response_message = ResponseMessage(**ai_message_dict)
                        response_message.ask_for_nps = ask_for_nps
                        encoded_response = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode(
                            'utf-8'
                        )
                        yield f"done: {encoded_response}\n\n"
        finally:
            reset_usage_context(usage_token)

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


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
    app_id: Optional[str] = None, plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
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

    # clean thread chat file
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
    plugin_id: Optional[str] = None, app_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    compat_app_id = app_id or plugin_id
    if compat_app_id in ['null', '']:
        compat_app_id = None

    chat_session = chat_db.get_chat_session(uid, app_id=compat_app_id)
    chat_session_id = chat_session['id'] if chat_session else None

    messages = chat_db.get_messages(
        uid, limit=100, include_conversations=True, app_id=compat_app_id, chat_session_id=chat_session_id
    )
    logger.info(f'get_messages {len(messages)} {compat_app_id}')

    # Debug: Check for messages with ratings
    rated_messages = [m for m in messages if m.get('rating') is not None]
    if rated_messages:
        logger.info(f'📊 Messages with ratings: {len(rated_messages)}')
        for m in rated_messages[:5]:  # Show first 5
            logger.info(f"  - Message {m.get('id')}: rating={m.get('rating')}")

    if not messages:
        return [initial_message_util(uid, compat_app_id)]
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
    enforce_chat_quota(uid, platform=x_app_platform)

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
        first_wav = wav_paths[0]
        duration_ms = read_wav_duration_ms(first_wav)
        if duration_ms is not None:
            allowed, used_ms, remaining_ms = try_consume_budget(uid, duration_ms)
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
            async for chunk in process_voice_message_segment_stream(first_wav, uid, language=resolved_language):
                if chunk.startswith('message: '):
                    attempt.finish(TranscriptionOutcome.SUCCESS)
                if not quota_recorded and chunk.startswith('message: '):
                    payload = chunk.removeprefix('message: ').strip()
                    try:
                        message_data = json.loads(base64.b64decode(payload).decode('utf-8'))
                        await run_blocking(
                            db_executor,
                            _record_chat_quota_question_safe,
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
            attempt.finish(outcome)
        except Exception as error:
            failure = failure_from_exception(error, provider=stt_provider)
            attempt.finish(failure.outcome)
            raise _transcription_http_error(failure) from error
        finally:
            if not attempt.finished:
                attempt.finish(TranscriptionOutcome.UPSTREAM_ERROR)
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
            if filename.lower().endswith('.wav'):
                temp_path = f"/tmp/{uid}_{uuid.uuid4()}.wav"
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
        total_duration_ms = 0
        for wav_path in wav_paths:
            duration_ms = await run_blocking(storage_executor, read_wav_duration_ms, wav_path)
            if duration_ms is not None:
                total_duration_ms += duration_ms
        if total_duration_ms > 0:
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

    Receives binary PCM audio chunks, streams them to Deepgram, and returns
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
        - text "finalize": flush remaining audio + trigger Deepgram finalization
    Server sends: JSON arrays of transcript segments
        [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.5, "text": "Hello world",
          "is_user": false, "person_id": null}]
    """
    await websocket.accept()

    # Paywalled desktop users — close before opening DG connection so we don't
    # bill Deepgram for a PTT stream that wouldn't be allowed to chat anyway.
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

    # Daily budget check — reject if already exhausted before opening DG connection
    budget_remaining_ms = None  # None = fail-open (no enforcement)
    try:
        has_budget, used_ms, remaining_ms = check_budget(uid)
        if not has_budget:
            await websocket.close(code=1008, reason='Daily transcription budget exhausted')
            return
        budget_remaining_ms = remaining_ms
    except Exception:
        pass  # Fail-open

    websocket_active = True
    dg_socket = None
    sender_task = None
    stt_audio_buffer = bytearray()
    received_audio_bytes = 0  # Includes buffered bytes for admission/budget enforcement.
    accepted_audio_bytes = 0  # Only bytes the provider explicitly accepted.
    # A terminal provider failure after either audio handoff or finalization.
    stt_send_failed = False
    stt_finalized = False
    # 30ms flush threshold for Deepgram streaming quality (16-bit PCM = 2 bytes per sample per channel)
    bytes_per_second = sample_rate * channels * 2
    stt_buffer_flush_size = int(bytes_per_second * 0.03)

    # PTT transcribe-stream always uses Deepgram (lightweight, no conversation lifecycle).
    # get_stt_service_for_language resolves the language/model for the DG call.
    _, stt_language, stt_model = get_stt_service_for_language(language)
    context_keywords = _parse_context_keywords(keywords)

    loop = asyncio.get_running_loop()

    # Deepgram's on_message callback runs in a thread — bridge to async via
    # loop.call_soon_threadsafe so asyncio.Queue wakeups are reliable.
    _SENTINEL = object()
    segment_queue = asyncio.Queue()

    def stream_transcript(segments):
        loop.call_soon_threadsafe(segment_queue.put_nowait, segments)

    async def segment_sender():
        """Forward segments from the thread-safe queue to the WebSocket."""
        nonlocal websocket_active
        while websocket_active:
            try:
                segments = await asyncio.wait_for(segment_queue.get(), timeout=0.5)
                if segments is _SENTINEL:
                    break
                await websocket.send_json(segments)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning(f'transcribe-stream: segment_sender error uid={uid}: {e}')
                websocket_active = False
                break

    async def close_stt_failure() -> None:
        """Expose an unusable live-STT session before the caller drops audio."""
        nonlocal websocket_active, stt_send_failed
        if stt_send_failed:
            return
        stt_send_failed = True
        websocket_active = False
        logger.error('event=ptt_transcription_stream outcome=provider_terminal_failure')
        try:
            await websocket.close(code=1011, reason='Transcription service unavailable')
        except Exception:
            pass

    async def send_stt_audio_or_close(audio: bytes) -> bool:
        """Require the provider to accept audio before its caller discards it."""
        if stt_send_failed:
            return False
        try:
            accepted = dg_socket is not None and not dg_socket.is_connection_dead and dg_socket.send(audio) is True
        except Exception:
            accepted = False
        if accepted:
            return True

        await close_stt_failure()
        return False

    async def finalize_stt_or_close() -> bool:
        """Finalize exactly once and make a provider failure customer-visible."""
        nonlocal stt_finalized
        if stt_send_failed:
            return False
        if stt_finalized:
            return True
        try:
            if dg_socket is None:
                raise RuntimeError('missing STT socket')
            dg_socket.finalize()
        except Exception:
            await close_stt_failure()
            return False
        stt_finalized = True
        return True

    try:
        dg_socket = await process_audio_dg(
            stream_transcript,
            language=stt_language,
            sample_rate=sample_rate,
            channels=channels,
            model=stt_model,
            keywords=context_keywords,
            is_active=lambda: websocket_active,
        )

        if dg_socket is None:
            logger.error(f'transcribe-stream: failed to connect to Deepgram uid={uid}')
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
                break

            if message.get("type") == "websocket.disconnect":
                break

            # Handle text "finalize" message: flush remaining audio, finalize Deepgram,
            # wait for final transcript, then continue receiving (client closes when ready).
            # Note: text frames do NOT reset the audio-idle timer.
            text_data = message.get("text")
            if text_data and text_data.strip() == "finalize":
                if dg_socket and not stt_send_failed:
                    if len(stt_audio_buffer) > 0:
                        if not await send_stt_audio_or_close(bytes(stt_audio_buffer)):
                            break
                        accepted_audio_bytes += len(stt_audio_buffer)
                        stt_audio_buffer.clear()
                    if await finalize_stt_or_close():
                        await asyncio.sleep(0.3)
                    else:
                        break
                continue

            data = message.get("bytes")
            if data is None:
                continue

            last_audio_time = asyncio.get_event_loop().time()

            # Guard against oversized frames (5 MB matches REST endpoint limit)
            if len(data) > 5 * 1024 * 1024:
                logger.warning(f'transcribe-stream: oversized frame uid={uid} size={len(data)}')
                continue

            # In-session budget enforcement: check BEFORE incrementing received_audio_bytes
            # so that the triggering frame is not counted as consumed (it won't be sent to DG).
            if budget_remaining_ms is not None and bytes_per_second > 0:
                prospective_ms = compute_pcm_duration_ms(received_audio_bytes + len(data), sample_rate, channels)
                if prospective_ms > budget_remaining_ms:
                    logger.info(
                        f'transcribe-stream: budget exhausted mid-session uid={uid} elapsed={prospective_ms}ms remaining={budget_remaining_ms}ms'
                    )
                    await websocket.close(code=1008, reason='Daily transcription budget exhausted')
                    break

            received_audio_bytes += len(data)
            stt_audio_buffer.extend(data)

            # Flush to Deepgram in 30ms chunks
            while len(stt_audio_buffer) >= stt_buffer_flush_size:
                chunk = bytes(stt_audio_buffer[:stt_buffer_flush_size])
                if not await send_stt_audio_or_close(chunk):
                    break
                del stt_audio_buffer[:stt_buffer_flush_size]
                accepted_audio_bytes += len(chunk)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f'transcribe-stream: error uid={uid}: {e}')
    finally:
        websocket_active = False

        # Flush remaining audio buffer
        if dg_socket and not stt_send_failed and len(stt_audio_buffer) > 0:
            if await send_stt_audio_or_close(bytes(stt_audio_buffer)):
                accepted_audio_bytes += len(stt_audio_buffer)
                stt_audio_buffer.clear()

        # Finalize only healthy streams to get the last transcript segment, then
        # always close DG. A rejected send can leave SafeDeepgramSocket's
        # keepalive thread running, so it still needs finish() even though a
        # final transcript would be misleading.
        if dg_socket and not stt_send_failed:
            finalized_before_teardown = stt_finalized
            if await finalize_stt_or_close():
                # Record only audio from a terminally successful stream,
                # including a successful tail flush. Do this immediately after
                # the provider accepts finalization: a disconnected client can
                # cancel the transcript-drain sleep below, but it must not
                # turn a successful provider handoff into missing usage.
                if accepted_audio_bytes > 0 and bytes_per_second > 0:
                    actual_duration_ms = compute_pcm_duration_ms(accepted_audio_bytes, sample_rate, channels)
                    record_actual_duration(uid, actual_duration_ms)
                if not finalized_before_teardown:
                    # Brief wait for final transcript callback.
                    await asyncio.sleep(0.3)

        if dg_socket:
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

        del stt_audio_buffer


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

            result = FileChatTool.upload(temp_file)

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


@router.post('/v1/files', response_model=List[FileChat], tags=['chat'])
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

            result = FileChatTool.upload(temp_file)

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


@router.post('/v1/messages/{message_id}/report', tags=['chat'], response_model=dict)
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


@router.delete('/v1/messages', tags=['chat'], response_model=Message)
def clear_chat_messages(
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


@router.post('/v1/initial-message', tags=['chat'], response_model=Message)
def create_initial_message(
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
    uid: str = Depends(auth.get_current_user_uid),
):
    """Rate a chat message (thumbs up/down). Used by desktop client."""
    rating = data.rating

    # Update rating on the message document
    chat_db.update_message_rating(uid, message_id, rating)

    # Also store in analytics collection
    value = rating if rating is not None else 0
    set_chat_message_rating_score(uid, message_id, value, platform='mobile')

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

    return {"url": f"https://h.omi.me/chat/{token}", "token": token}


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
