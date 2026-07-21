import base64
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional, Tuple

from fastapi import HTTPException

import database.chat as chat_db
import database.users as user_db
from database.apps import record_app_usage
from models.app import App, UsageHistoryType
from models.chat import ChatSession, Message, ResponseMessage, MessageConversation
from models.notification_message import NotificationMessage
from models.transcript_segment import TranscriptSegment
from utils.apps import get_available_app_by_id
from utils.executors import db_executor, run_blocking, storage_executor, sync_executor
from utils.conversation_helpers import extract_memory_ids
from utils.conversations.factory import deserialize_conversation
from utils.llm.chat import initial_chat_message
from utils.llm.persona import initial_persona_chat_message
from utils.notifications import send_notification, send_notification_async
from utils.observability.fallback import record_fallback
from utils.other.storage import (
    get_syncing_file_temporal_signed_url,
    schedule_syncing_temporal_file_deletion,
)
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream
from utils.stt.pre_recorded import (
    postprocess_words,
    prerecorded,
    prerecorded_from_bytes,
    get_prerecorded_service,
)
from utils.stt.outcomes import (
    TranscriptionFailure,
    TranscriptionOutcome,
    empty_unexpected_failure,
    failure_from_exception,
)
from utils.stt.vad import (
    VADAudioDecodeError,
    VADProcessingError,
    linear16_pcm_is_silent,
    vad_is_empty_strict,
)
from utils.llm.usage_tracker import (
    track_usage,
    set_usage_context,
    reset_usage_context,
    Features,
)
import logging

logger = logging.getLogger(__name__)


def acquire_chat_session(uid: str, app_id: Optional[str] = None):
    chat_session = chat_db.get_chat_session(uid, app_id=app_id)
    if chat_session is None:
        cs = ChatSession(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            plugin_id=app_id,
        )
        chat_session = chat_db.add_chat_session(uid, cs.model_dump())
    return chat_session


def initial_message_util(uid: str, app_id: Optional[str] = None, chat_session_id: Optional[str] = None):
    logger.info(f"initial_message_util {app_id}")

    # init chat session — use provided session_id if available, otherwise acquire by app_id
    if chat_session_id:
        chat_session = chat_db.get_chat_session_by_id(uid, chat_session_id)
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
    else:
        chat_session = acquire_chat_session(uid, app_id=app_id)

    # Load previous messages — session-scoped when session_id is provided, app-scoped otherwise
    if chat_session_id:
        prev_messages = list(reversed(chat_db.get_messages(uid, limit=5, chat_session_id=chat_session_id)))
    else:
        prev_messages = list(reversed(chat_db.get_messages(uid, limit=5, app_id=app_id)))
    logger.info(f"initial_message_util returned {len(prev_messages)} prev messages for {app_id}")

    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None

    text: str
    if app and app.is_a_persona():
        text = initial_persona_chat_message(uid, app, [Message(**msg) for msg in prev_messages])
    else:
        prev_messages_str = ""
        if prev_messages:
            prev_messages_str = "Previous conversation history:\n"
            prev_messages_str += Message.get_messages_as_string([Message(**msg) for msg in prev_messages])
        logger.info(f"initial_message_util {len(prev_messages_str)} {app_id}")
        text = initial_chat_message(uid, app, prev_messages_str)

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender="ai",
        app_id=app_id,
        from_external_integration=False,
        type="text",
        memories_id=[],
        chat_session_id=chat_session["id"],
    )
    chat_db.add_message(uid, ai_message.model_dump())
    chat_db.add_message_to_chat_session(uid, chat_session["id"], ai_message.id)
    return ai_message


def resolve_voice_message_language(uid: str, request_language: Optional[str]) -> str:
    """
    Determine language selection for voice message transcription.

    Returns a single language string: either a specific language code (e.g., 'en', 'es')
    or 'multi' for auto-detection mode.
    """
    if request_language:
        normalized = request_language.strip()
        if normalized:
            request_lower = normalized.lower()
            if request_lower == "auto" or request_lower == "multi":
                return "multi"
            return normalized

    user_language = user_db.get_user_language_preference(uid)
    if user_language:
        transcription_prefs = user_db.get_user_transcription_preferences(uid)
        single_language_mode = transcription_prefs.get("single_language_mode", False)
        if single_language_mode:
            return user_language
        return "multi"

    return "multi"


def _prepare_voice_message_url(path: str) -> str:
    """Create the signed input URL and schedule its cleanup on the storage lane."""
    url = get_syncing_file_temporal_signed_url(path)
    schedule_syncing_temporal_file_deletion(path)
    return url


def _validated_wav_is_silent(path: str, *, provider: str) -> bool:
    """Return strict VAD silence without converting decode failures to silence."""

    try:
        return vad_is_empty_strict(path)
    except VADAudioDecodeError as error:
        raise TranscriptionFailure(
            TranscriptionOutcome.INVALID_INPUT,
            provider=provider,
            retryable=False,
        ) from error
    except Exception as error:
        raise TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider=provider) from error


def _transcribe_voice_message_url(
    url: str,
    path: str,
    language: str,
    detect_language: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    """Run the synchronous prerecorded-STT pipeline for one signed URL."""
    provider, stt_language, stt_model = get_prerecorded_service(language)
    is_multi = stt_language == "multi"
    try:
        if is_multi and detect_language:
            words, detected_language = prerecorded(
                url,
                diarize=False,
                language=stt_language,
                return_language=True,
                model=stt_model,
            )
        else:
            words = prerecorded(
                url,
                diarize=False,
                language=stt_language,
                return_language=False,
                model=stt_model,
            )
            detected_language = stt_language
    except Exception as error:
        failure = failure_from_exception(error, provider=provider)
        logger.warning(
            "Voice message transcription failed: outcome=%s provider=%s retryable=%s",
            failure.outcome.value,
            failure.provider,
            failure.retryable,
        )
        raise failure from error

    if not words:
        raise empty_unexpected_failure(provider)
    try:
        transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    except Exception as error:
        raise TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider=provider) from error
    del words
    if not transcript_segments:
        raise empty_unexpected_failure(provider)

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    transcript_segments.clear()
    if len(text) == 0:
        raise empty_unexpected_failure(provider)

    return text, detected_language


def transcribe_voice_message_segment(
    path: str,
    uid: str,
    language: str = "multi",
) -> Tuple[Optional[str], Optional[str]]:
    if not language:
        language = resolve_voice_message_language(uid, None)
    provider, provider_language, _ = get_prerecorded_service(language)
    # Schedule deletion before the VAD gate as well: silence is a valid
    # terminal outcome, not a reason to retain temporary customer audio.
    url = _prepare_voice_message_url(path)
    if _validated_wav_is_silent(path, provider=provider):
        detected_language = provider_language if provider_language != "multi" else None
        return None, detected_language

    return _transcribe_voice_message_url(url, path, language)


def transcribe_pcm_bytes(
    audio_bytes: bytes,
    uid: str,
    language: str = "multi",
    encoding: str = "linear16",
    sample_rate: int = 16000,
    channels: int = 1,
    keywords: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Transcribe raw PCM audio bytes through the selected pre-recorded STT provider.

    Skips GCS upload and WAV conversion for maximum speed.
    Used by desktop PTT batch mode.
    """
    if not language:
        language = resolve_voice_message_language(uid, None)

    provider, stt_language, stt_model = get_prerecorded_service(language)
    is_multi = stt_language == "multi"

    if encoding == "linear16":
        try:
            if linear16_pcm_is_silent(audio_bytes, sample_rate=sample_rate, channels=channels):
                return None, stt_language if not is_multi else None
        except VADAudioDecodeError as error:
            raise TranscriptionFailure(
                TranscriptionOutcome.INVALID_INPUT,
                provider=provider,
                retryable=False,
            ) from error
        except VADProcessingError as error:
            raise TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider=provider) from error

    try:
        if is_multi:
            result = prerecorded_from_bytes(
                audio_bytes,
                sample_rate=sample_rate,
                diarize=False,
                encoding=encoding,
                channels=channels,
                language=stt_language,
                model=stt_model,
                return_language=True,
                keywords=keywords,
            )
            words, detected_language = result
        else:
            words = prerecorded_from_bytes(
                audio_bytes,
                sample_rate=sample_rate,
                diarize=False,
                encoding=encoding,
                channels=channels,
                language=stt_language,
                model=stt_model,
                keywords=keywords,
            )
            detected_language = stt_language
    except Exception as error:
        raise failure_from_exception(error, provider=provider) from error

    if not words:
        raise empty_unexpected_failure(provider)

    try:
        transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    except Exception as error:
        raise TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider=provider) from error
    del words
    if not transcript_segments:
        raise empty_unexpected_failure(provider)

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    transcript_segments.clear()
    if len(text) == 0:
        raise empty_unexpected_failure(provider)

    return text, detected_language


def process_voice_message_segment(
    path: str,
    uid: str,
    language: str = "multi",
):
    if not language:
        language = resolve_voice_message_language(uid, None)
    text, _detected_language = transcribe_voice_message_segment(path, uid, language)
    if text is None:
        return []

    # create message
    message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text",
    )
    chat_db.add_message(uid, message.model_dump())

    # not support plugin
    app = None
    app_id = None

    messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]))
    with track_usage(uid, Features.CHAT):
        response, ask_for_nps, memories = execute_graph_chat(uid, messages, app)  # app
    memories_id = extract_memory_ids(memories) if memories else []
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=response,
        created_at=datetime.now(timezone.utc),
        sender="ai",
        app_id=app_id,
        type="text",
        memories_id=memories_id,
    )
    chat_db.add_message(uid, ai_message.model_dump())
    ai_message.memories = memories if len(memories) < 5 else memories[:5]
    if app_id:
        record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

    ai_message_resp = ai_message.model_dump()

    ai_message_resp["ask_for_nps"] = ask_for_nps

    # send notification
    send_chat_message_notification(uid, "omi", "omi", ai_message.text, ai_message.id)

    return [message.model_dump(), ai_message_resp]


CHAT_STREAM_ERROR_TEXT = "Sorry, something went wrong while generating a response. Please try again."


def _new_stream_error_message(app_id: Optional[str], chat_session: Optional[ChatSession]) -> Message:
    """Construct (but do not persist) the canned fallback AI message."""
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=CHAT_STREAM_ERROR_TEXT,
        created_at=datetime.now(timezone.utc),
        sender="ai",
        app_id=app_id,
        type="text",
    )
    if chat_session:
        ai_message.chat_session_id = chat_session.id
    return ai_message


def build_stream_error_reply(
    uid: str,
    app_id: Optional[str] = None,
    chat_session: Optional[ChatSession] = None,
) -> ResponseMessage:
    """Persist and return a graceful fallback AI reply for a chat turn that
    failed mid-stream without producing an answer.

    Without this, the SSE stream ends as a clean 200 with no ``done:`` frame and
    every client renders a blank assistant bubble. Mirrors
    ``_build_quota_exceeded_reply``: the reply is persisted so the message the
    client renders from the ``done:`` frame stays consistent with server-side
    history (clients persist what they receive). The user's message is already
    persisted by the caller, so only the AI reply is saved here. The raw
    exception is logged upstream in ``execute_*_chat_stream`` and is never
    surfaced to the client.
    """
    ai_message = _new_stream_error_message(app_id, chat_session)
    if chat_session:
        chat_db.add_message_to_chat_session(uid, chat_session.id, ai_message.id)
    chat_db.add_message(uid, ai_message.model_dump())
    return ResponseMessage(**ai_message.model_dump(), ask_for_nps=False)


async def emit_stream_error_fallback(
    uid: str,
    app_id: Optional[str],
    chat_session: Optional[ChatSession],
    *,
    label: str,
    error_recorded: bool,
) -> str:
    """Build the SSE ``done:`` frame for a chat stream that ended without an answer.

    The pipeline failed mid-stream (raw error already logged in
    ``execute_*_chat_stream``); this emits a graceful fallback so every client
    renders real text instead of a blank bubble. ``label`` distinguishes the
    calling surface (e.g. ``'chat'`` / ``'voice_chat'``) in server-side logs.

    This is a fail-open correctness degrade (real LLM answer -> canned text), so
    it records the shared fallback metric exactly once. Normal path persists the
    reply and reports ``degraded``; if the Firestore write itself fails we still
    emit an in-memory ``done:`` frame (unpersisted -- client/server history
    diverges for this turn) and report ``exhausted``. Returns the full
    ``"done: ...\\n\\n"`` frame.
    """
    logger.error(
        "%s stream ended without an answer for uid=%s (error=%s)",
        label,
        uid,
        error_recorded,
    )
    try:
        fallback = await run_blocking(db_executor, build_stream_error_reply, uid, app_id, chat_session)
        outcome = "degraded"
    except Exception as persist_exc:
        logger.error(
            "%s stream fallback persistence failed for uid=%s: %s",
            label,
            uid,
            type(persist_exc).__name__,
        )
        ai_message = _new_stream_error_message(app_id, chat_session)
        fallback = ResponseMessage(**ai_message.model_dump(), ask_for_nps=False)
        outcome = "exhausted"
    record_fallback(
        component="other",
        from_mode="llm_answer",
        to_mode="canned_reply",
        reason="other",
        outcome=outcome,
    )
    encoded_response = base64.b64encode(bytes(fallback.model_dump_json(), "utf-8")).decode("utf-8")
    return f"done: {encoded_response}\n\n"


async def process_voice_message_segment_stream(
    path: str,
    uid: str,
    language: str = "multi",
    platform: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    if not language:
        language = await run_blocking(db_executor, resolve_voice_message_language, uid, None)
    provider, _, _ = get_prerecorded_service(language)
    # The storage lifecycle must cover silent files too. Keep both signing and
    # deletion scheduling on the storage executor before VAD decides whether
    # transcription should proceed.
    url = await run_blocking(storage_executor, _prepare_voice_message_url, path)
    is_silent = await run_blocking(
        sync_executor,
        _validated_wav_is_silent,
        path,
        provider=provider,
    )
    if is_silent:
        return

    text, _detected_language = await run_blocking(
        sync_executor,
        _transcribe_voice_message_url,
        url,
        path,
        language,
        False,
    )
    if text is None:
        return

    # create message
    message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text",
    )

    chat_session = await run_blocking(db_executor, chat_db.get_chat_session, uid)
    chat_session = ChatSession(**chat_session) if chat_session else None

    if chat_session:
        message.chat_session_id = chat_session.id
        await run_blocking(
            db_executor,
            chat_db.add_message_to_chat_session,
            uid,
            chat_session.id,
            message.id,
        )

    await run_blocking(db_executor, chat_db.add_message, uid, message.model_dump())

    # stream
    mdata = base64.b64encode(bytes(message.model_dump_json(), "utf-8")).decode("utf-8")
    yield f"message: {mdata}\n\n"

    # not support plugin
    app = None
    app_id = None

    async def process_message(response: str, callback_data: dict):
        memories = callback_data.get("memories_found", [])
        ask_for_nps = callback_data.get("ask_for_nps", False)
        langsmith_run_id = callback_data.get("langsmith_run_id")
        prompt_name = callback_data.get("prompt_name")
        prompt_commit = callback_data.get("prompt_commit")
        memories_id = []
        # check if the items in the conversations list are dict
        if memories:
            converted_memories = []
            for m in memories[:5]:
                if isinstance(m, dict):
                    converted_memories.append(deserialize_conversation(m))
                else:
                    converted_memories.append(m)
            memories_id = [str(getattr(m, "id", "")) for m in converted_memories]
        ai_message = Message(
            id=str(uuid.uuid4()),
            text=response,
            created_at=datetime.now(timezone.utc),
            sender="ai",
            app_id=app_id,
            type="text",
            memories_id=memories_id,
            langsmith_run_id=langsmith_run_id,  # Store run_id for feedback tracking
            prompt_name=prompt_name,  # LangSmith prompt name for versioning
            prompt_commit=prompt_commit,  # LangSmith prompt commit for traceability
        )

        chat_session = await run_blocking(db_executor, chat_db.get_chat_session, uid)
        chat_session = ChatSession(**chat_session) if chat_session else None

        if chat_session:
            ai_message.chat_session_id = chat_session.id
            await run_blocking(
                db_executor,
                chat_db.add_message_to_chat_session,
                uid,
                chat_session.id,
                ai_message.id,
            )

        await run_blocking(db_executor, chat_db.add_message, uid, ai_message.model_dump())
        ai_message.memories = [MessageConversation(**m) for m in (memories if len(memories) < 5 else memories[:5])]

        if app_id:
            await run_blocking(
                db_executor,
                record_app_usage,
                uid,
                app_id,
                UsageHistoryType.chat_message_sent,
                message_id=ai_message.id,
            )

        return ai_message, ask_for_nps

    messages = list(
        reversed([Message(**msg) for msg in await run_blocking(db_executor, chat_db.get_messages, uid, limit=10)])
    )
    callback_data = {}
    answered = False
    # Set usage context for streaming (can't use 'with' across yields)
    usage_token = set_usage_context(uid, Features.CHAT)
    try:
        async for chunk in execute_graph_chat_stream(
            uid,
            messages,
            app,
            cited=False,
            callback_data=callback_data,
            platform=platform,
        ):
            if chunk:
                data = chunk.replace("\n", "__CRLF__")
                yield f"{data}\n\n"

            else:
                response = callback_data.get("answer")
                if response:
                    ai_message, ask_for_nps = await process_message(response, callback_data)
                    ai_message_dict = ai_message.model_dump()
                    response_message = ResponseMessage(**ai_message_dict)
                    response_message.ask_for_nps = ask_for_nps
                    data = base64.b64encode(bytes(response_message.model_dump_json(), "utf-8")).decode("utf-8")
                    yield f"done: {data}\n\n"
                    answered = True

                    # send notification
                    await send_chat_message_notification_async(uid, "omi", "omi", ai_message.text, ai_message.id)

        if not answered:
            yield await emit_stream_error_fallback(
                uid,
                app_id,
                chat_session,
                label="voice_chat",
                error_recorded=bool(callback_data.get("error")),
            )
    finally:
        reset_usage_context(usage_token)

    return


def _chat_message_notification(
    app_id: str,
    message: str,
    message_id: str,
) -> NotificationMessage:
    return NotificationMessage(
        id=message_id,
        text=message,
        plugin_id=app_id,
        from_integration="true",
        type="text",
        notification_type="plugin",
        navigate_to=f"/chat/{app_id}",
    )


def send_chat_message_notification(user_id: str, app_name: str, app_id: str, message: str, message_id: str):
    ai_message = _chat_message_notification(app_id, message, message_id)
    send_notification(
        user_id,
        app_name + " says",
        message,
        NotificationMessage.get_message_as_dict(ai_message),
    )


async def send_chat_message_notification_async(
    user_id: str,
    app_name: str,
    app_id: str,
    message: str,
    message_id: str,
) -> None:
    """Async notification boundary for streaming chat responses."""
    ai_message = _chat_message_notification(app_id, message, message_id)
    await send_notification_async(
        user_id,
        app_name + " says",
        message,
        NotificationMessage.get_message_as_dict(ai_message),
    )
