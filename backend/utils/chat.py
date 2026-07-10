import base64
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional, Tuple

from fastapi import HTTPException

import database.chat as chat_db
import database.notifications as notification_db
import database.users as user_db
from database.apps import record_app_usage
from models.app import App, UsageHistoryType
from models.chat import ChatSession, Message, ResponseMessage, MessageConversation
from models.notification_message import NotificationMessage
from models.transcript_segment import TranscriptSegment
from utils.apps import get_available_app_by_id
from utils.executors import run_blocking, db_executor
from utils.conversation_helpers import extract_memory_ids
from utils.conversations.factory import deserialize_conversation
from utils.llm.chat import initial_chat_message
from utils.llm.persona import initial_persona_chat_message
from utils.notifications import send_notification
from utils.other.storage import get_syncing_file_temporal_signed_url, schedule_syncing_temporal_file_deletion
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream
from utils.stt.pre_recorded import (
    get_deepgram_model_for_language,
    postprocess_words,
    prerecorded,
    prerecorded_from_bytes,
)
from utils.llm.usage_tracker import track_usage, set_usage_context, reset_usage_context, Features
import logging

logger = logging.getLogger(__name__)


def acquire_chat_session(uid: str, app_id: Optional[str] = None):
    chat_session = chat_db.get_chat_session(uid, app_id=app_id)
    if chat_session is None:
        cs = ChatSession(id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc), plugin_id=app_id)
        chat_session = chat_db.add_chat_session(uid, cs.model_dump())
    return chat_session


def initial_message_util(uid: str, app_id: Optional[str] = None, chat_session_id: Optional[str] = None):
    logger.info(f'initial_message_util {app_id}')

    # init chat session — use provided session_id if available, otherwise acquire by app_id
    if chat_session_id:
        chat_session = chat_db.get_chat_session_by_id(uid, chat_session_id)
        if chat_session is None:
            raise HTTPException(status_code=404, detail='Chat session not found')
    else:
        chat_session = acquire_chat_session(uid, app_id=app_id)

    # Load previous messages — session-scoped when session_id is provided, app-scoped otherwise
    if chat_session_id:
        prev_messages = list(reversed(chat_db.get_messages(uid, limit=5, chat_session_id=chat_session_id)))
    else:
        prev_messages = list(reversed(chat_db.get_messages(uid, limit=5, app_id=app_id)))
    logger.info(f'initial_message_util returned {len(prev_messages)} prev messages for {app_id}')

    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None

    text: str
    if app and app.is_a_persona():
        text = initial_persona_chat_message(uid, app, [Message(**msg) for msg in prev_messages])
    else:
        prev_messages_str = ''
        if prev_messages:
            prev_messages_str = 'Previous conversation history:\n'
            prev_messages_str += Message.get_messages_as_string([Message(**msg) for msg in prev_messages])
        logger.info(f'initial_message_util {len(prev_messages_str)} {app_id}')
        text = initial_chat_message(uid, app, prev_messages_str)

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        app_id=app_id,
        from_external_integration=False,
        type='text',
        memories_id=[],
        chat_session_id=chat_session['id'],
    )
    chat_db.add_message(uid, ai_message.model_dump())
    chat_db.add_message_to_chat_session(uid, chat_session['id'], ai_message.id)
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
            if request_lower == 'auto' or request_lower == 'multi':
                return 'multi'
            return normalized

    user_language = user_db.get_user_language_preference(uid)
    if user_language:
        transcription_prefs = user_db.get_user_transcription_preferences(uid)
        single_language_mode = transcription_prefs.get('single_language_mode', False)
        if single_language_mode:
            return user_language
        return 'multi'

    return 'multi'


def transcribe_voice_message_segment(
    path: str,
    uid: str,
    language: str = 'multi',
) -> Tuple[Optional[str], Optional[str]]:
    url = get_syncing_file_temporal_signed_url(path)
    schedule_syncing_temporal_file_deletion(path)

    if not language:
        language = resolve_voice_message_language(uid, None)

    # Get the appropriate Deepgram model for this language
    stt_language, stt_model = get_deepgram_model_for_language(language)

    is_multi = stt_language == 'multi'
    try:
        if is_multi:
            words, detected_language = prerecorded(
                url, diarize=False, language=stt_language, return_language=True, model=stt_model
            )
        else:
            words = prerecorded(url, diarize=False, language=stt_language, return_language=False, model=stt_model)
            detected_language = stt_language
    except RuntimeError as e:
        logger.error(f'Voice message transcription failed for {path}: {e}')
        return None, stt_language if not is_multi else 'en'
    if not words:
        logger.info('no words')
        return None, detected_language
    transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    del words
    if not transcript_segments:
        logger.error('failed to get deepgram segments')
        return None, detected_language

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    transcript_segments.clear()
    if len(text) == 0:
        logger.info('voice message text is empty')
        return None, detected_language

    return text, detected_language


def transcribe_pcm_bytes(
    audio_bytes: bytes,
    uid: str,
    language: str = 'multi',
    encoding: str = 'linear16',
    sample_rate: int = 16000,
    channels: int = 1,
    keywords: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Transcribe raw PCM audio bytes directly via Deepgram pre-recorded API.

    Skips GCS upload and WAV conversion for maximum speed.
    Used by desktop PTT batch mode.
    """
    if not language:
        language = resolve_voice_message_language(uid, None)

    stt_language, stt_model = get_deepgram_model_for_language(language)
    is_multi = stt_language == 'multi'

    # Let RuntimeError propagate so the router can distinguish backend failure from no-speech
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

    if not words:
        logger.info('transcribe_pcm_bytes: no words')
        return None, detected_language

    transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    del words
    if not transcript_segments:
        logger.error('transcribe_pcm_bytes: failed to get segments')
        return None, detected_language

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    transcript_segments.clear()
    if len(text) == 0:
        logger.info('transcribe_pcm_bytes: text is empty')
        return None, detected_language

    return text, detected_language


def process_voice_message_segment(
    path: str,
    uid: str,
    language: str = 'multi',
):
    url = get_syncing_file_temporal_signed_url(path)
    schedule_syncing_temporal_file_deletion(path)

    if not language:
        language = resolve_voice_message_language(uid, None)

    # Get the appropriate Deepgram model for this language
    stt_language, stt_model = get_deepgram_model_for_language(language)

    try:
        words = prerecorded(url, diarize=False, language=stt_language, model=stt_model)
    except RuntimeError as e:
        logger.error(f'Voice message transcription failed for {path}: {e}')
        return []
    transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    del words
    if not transcript_segments:
        logger.error('failed to get deepgram segments')
        return []

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    transcript_segments.clear()
    if len(text) == 0:
        logger.info('voice message text is empty')
        return []

    # create message
    message = Message(
        id=str(uuid.uuid4()), text=text, created_at=datetime.now(timezone.utc), sender='human', type='text'
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
        sender='ai',
        app_id=app_id,
        type='text',
        memories_id=memories_id,
    )
    chat_db.add_message(uid, ai_message.model_dump())
    ai_message.memories = memories if len(memories) < 5 else memories[:5]
    if app_id:
        record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

    ai_message_resp = ai_message.model_dump()

    ai_message_resp['ask_for_nps'] = ask_for_nps

    # send notification
    send_chat_message_notification(uid, "omi", "omi", ai_message.text, ai_message.id)

    return [message.model_dump(), ai_message_resp]


async def process_voice_message_segment_stream(
    path: str,
    uid: str,
    language: str = 'multi',
) -> AsyncGenerator[str, None]:
    url = get_syncing_file_temporal_signed_url(path)
    schedule_syncing_temporal_file_deletion(path)

    if not language:
        language = resolve_voice_message_language(uid, None)

    # Get the appropriate Deepgram model for this language
    stt_language, stt_model = get_deepgram_model_for_language(language)

    try:
        words = prerecorded(url, diarize=False, language=stt_language, model=stt_model)
    except RuntimeError as e:
        logger.error(f'Voice message transcription failed for {path}: {e}')
        return
    transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    del words
    if not transcript_segments:
        logger.error('failed to get deepgram segments')
        return

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    transcript_segments.clear()
    if len(text) == 0:
        logger.info('voice message text is empty')
        return

    # create message
    message = Message(
        id=str(uuid.uuid4()), text=text, created_at=datetime.now(timezone.utc), sender='human', type='text'
    )

    chat_session = await run_blocking(db_executor, chat_db.get_chat_session, uid)
    chat_session = ChatSession(**chat_session) if chat_session else None

    if chat_session:
        message.chat_session_id = chat_session.id
        await run_blocking(db_executor, chat_db.add_message_to_chat_session, uid, chat_session.id, message.id)

    await run_blocking(db_executor, chat_db.add_message, uid, message.model_dump())

    # stream
    mdata = base64.b64encode(bytes(message.model_dump_json(), 'utf-8')).decode('utf-8')
    yield f"message: {mdata}\n\n"

    # not support plugin
    app = None
    app_id = None

    async def process_message(response: str, callback_data: dict):
        memories = callback_data.get('memories_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)
        langsmith_run_id = callback_data.get('langsmith_run_id')
        prompt_name = callback_data.get('prompt_name')
        prompt_commit = callback_data.get('prompt_commit')
        memories_id = []
        # check if the items in the conversations list are dict
        if memories:
            converted_memories = []
            for m in memories[:5]:
                if isinstance(m, dict):
                    converted_memories.append(deserialize_conversation(m))
                else:
                    converted_memories.append(m)
            memories_id = [str(getattr(m, 'id', '')) for m in converted_memories]
        ai_message = Message(
            id=str(uuid.uuid4()),
            text=response,
            created_at=datetime.now(timezone.utc),
            sender='ai',
            app_id=app_id,
            type='text',
            memories_id=memories_id,
            langsmith_run_id=langsmith_run_id,  # Store run_id for feedback tracking
            prompt_name=prompt_name,  # LangSmith prompt name for versioning
            prompt_commit=prompt_commit,  # LangSmith prompt commit for traceability
        )

        chat_session = await run_blocking(db_executor, chat_db.get_chat_session, uid)
        chat_session = ChatSession(**chat_session) if chat_session else None

        if chat_session:
            ai_message.chat_session_id = chat_session.id
            await run_blocking(db_executor, chat_db.add_message_to_chat_session, uid, chat_session.id, ai_message.id)

        await run_blocking(db_executor, chat_db.add_message, uid, ai_message.model_dump())
        ai_message.memories = [MessageConversation(**m) for m in (memories if len(memories) < 5 else memories[:5])]

        if app_id:
            await run_blocking(
                db_executor, record_app_usage, uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id
            )

        return ai_message, ask_for_nps

    messages = list(
        reversed([Message(**msg) for msg in await run_blocking(db_executor, chat_db.get_messages, uid, limit=10)])
    )
    callback_data = {}
    # Set usage context for streaming (can't use 'with' across yields)
    usage_token = set_usage_context(uid, Features.CHAT)
    try:
        async for chunk in execute_graph_chat_stream(uid, messages, app, cited=False, callback_data=callback_data):
            if chunk:
                data = chunk.replace("\n", "__CRLF__")
                yield f'{data}\n\n'

            else:
                response = callback_data.get('answer')
                if response:
                    ai_message, ask_for_nps = await process_message(response, callback_data)
                    ai_message_dict = ai_message.model_dump()
                    response_message = ResponseMessage(**ai_message_dict)
                    response_message.ask_for_nps = ask_for_nps
                    data = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode('utf-8')
                    yield f"done: {data}\n\n"

                    # send notification
                    send_chat_message_notification(uid, "omi", "omi", ai_message.text, ai_message.id)
    finally:
        reset_usage_context(usage_token)

    return


def send_chat_message_notification(user_id: str, app_name: str, app_id: str, message: str, message_id: str):
    ai_message = NotificationMessage(
        id=message_id,
        text=message,
        plugin_id=app_id,
        from_integration='true',
        type='text',
        notification_type='plugin',
        navigate_to=f'/chat/{app_id}',
    )
    send_notification(user_id, app_name + ' says', message, NotificationMessage.get_message_as_dict(ai_message))
