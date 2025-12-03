import threading
import time
import base64
import uuid
from datetime import datetime, timezone
from typing import List, AsyncGenerator, Optional

import database.chat as chat_db
import database.notifications as notification_db
from database.apps import record_app_usage
from models.chat import ChatSession, Message, ResponseMessage, MessageConversation
from models.conversation import Conversation
from models.notification_message import NotificationMessage
from models.app import UsageHistoryType
from models.transcript_segment import TranscriptSegment
from utils.notifications import send_notification
from utils.other.storage import get_syncing_file_temporal_signed_url, delete_syncing_temporal_file
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing


def transcribe_voice_message_segment(path: str):
    url = get_syncing_file_temporal_signed_url(path)

    def delete_file():
        time.sleep(480)
        delete_syncing_temporal_file(path)

    threading.Thread(target=delete_file).start()

    words, language = fal_whisperx(url, 3, 2, True)
    transcript_segments: List[TranscriptSegment] = fal_postprocessing(words, 0)
    if not transcript_segments:
        print('failed to get fal segments')
        return None

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    if len(text) == 0:
        print('voice message text is empty')
        return None

    return text


def process_voice_message_segment(path: str, uid: str):
    url = get_syncing_file_temporal_signed_url(path)

    def delete_file():
        time.sleep(480)
        delete_syncing_temporal_file(path)

    threading.Thread(target=delete_file).start()

    words, language = fal_whisperx(url, 3, 2, True)
    transcript_segments: List[TranscriptSegment] = fal_postprocessing(words, 0)
    if not transcript_segments:
        print('failed to get fal segments')
        return []

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    if len(text) == 0:
        print('voice message text is empty')
        return []

    # create message
    message = Message(
        id=str(uuid.uuid4()), text=text, created_at=datetime.now(timezone.utc), sender='human', type='text'
    )
    chat_db.add_message(uid, message.dict())

    # not support plugin
    app = None
    app_id = None

    messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]))
    response, ask_for_nps, memories = execute_graph_chat(uid, messages, app)  # app
    memories_id = []
    # check if the items in the conversations list are dict
    if memories:
        converted_memories = []
        for m in memories[:5]:
            if isinstance(m, dict):
                converted_memories.append(Conversation(**m))
            else:
                converted_memories.append(m)
        memories_id = [m.id for m in converted_memories]
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=response,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        app_id=app_id,
        type='text',
        memories_id=memories_id,
    )
    chat_db.add_message(uid, ai_message.dict())
    ai_message.memories = memories if len(memories) < 5 else memories[:5]
    if app_id:
        record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

    ai_message_resp = ai_message.dict()

    ai_message_resp['ask_for_nps'] = ask_for_nps

    # send notification
    send_chat_message_notification(uid, "omi", "omi", ai_message.text, ai_message.id)

    return [message.dict(), ai_message_resp]


async def process_voice_message_segment_stream(path: str, uid: str) -> AsyncGenerator[str, None]:
    """
    Process voice message and stream response.
    Voice messages always go to the most recent Omi session (app_id=None).
    """
    url = get_syncing_file_temporal_signed_url(path)

    def delete_file():
        time.sleep(480)
        delete_syncing_temporal_file(path)

    threading.Thread(target=delete_file).start()

    words = fal_whisperx(audio_url=url, diarize=False, chunk_level="segment")
    transcript_segments: List[TranscriptSegment] = fal_postprocessing(words, 0)
    if not transcript_segments:
        print('failed to get fal segments')
        return

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    if len(text) == 0:
        print('voice message text is empty')
        return

    # Voice messages always go to most recent Omi session (app_id=None)
    chat_session = chat_db.get_chat_session(uid, app_id=None)
    if not chat_session:
        # No Omi session exists, create one
        chat_session = chat_db.create_chat_session(uid, app_id=None, title='New Chat')
    chat_session_obj = ChatSession(**chat_session) if chat_session else None

    # Create message
    message = Message(
        id=str(uuid.uuid4()), text=text, created_at=datetime.now(timezone.utc), sender='human', type='text'
    )

    if chat_session_obj:
        message.chat_session_id = chat_session_obj.id
        chat_db.add_message_to_chat_session(uid, chat_session_obj.id, message.id)
        # Update session activity
        try:
            chat_db.update_session_activity(uid, chat_session_obj.id)
        except:
            pass

    chat_db.add_message(uid, message.dict())

    # Stream
    mdata = base64.b64encode(bytes(message.model_dump_json(), 'utf-8')).decode('utf-8')
    yield f"message: {mdata}\n\n"

    # Voice messages don't support plugins
    app = None
    app_id = None

    def process_message(response: str, callback_data: dict):
        memories = callback_data.get('memories_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)
        memories_id = []
        # check if the items in the conversations list are dict
        if memories:
            converted_memories = []
            for m in memories[:5]:
                if isinstance(m, dict):
                    converted_memories.append(Conversation(**m))
                else:
                    converted_memories.append(m)
            memories_id = [m.id for m in converted_memories]

        ai_message = Message(
            id=str(uuid.uuid4()),
            text=response,
            created_at=datetime.now(timezone.utc),
            sender='ai',
            app_id=app_id,
            type='text',
            memories_id=memories_id,
        )

        if chat_session_obj:
            ai_message.chat_session_id = chat_session_obj.id
            chat_db.add_message_to_chat_session(uid, chat_session_obj.id, ai_message.id)
            # Update session activity after AI response
            try:
                chat_db.update_session_activity(uid, chat_session_obj.id)
            except:
                pass

        chat_db.add_message(uid, ai_message.dict())
        ai_message.memories = [MessageConversation(**m) for m in (memories if len(memories) < 5 else memories[:5])]

        if app_id:
            record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

        return ai_message, ask_for_nps

    # Get messages from the session for context
    messages = list(
        reversed(
            [
                Message(**msg)
                for msg in chat_db.get_messages(
                    uid, limit=10, app_id=None, chat_session_id=chat_session_obj.id if chat_session_obj else None
                )
            ]
        )
    )

    callback_data = {}
    async for chunk in execute_graph_chat_stream(uid, messages, app, cited=False, callback_data=callback_data):
        if chunk:
            data = chunk.replace("\n", "__CRLF__")
            yield f'{data}\n\n'

        else:
            response = callback_data.get('answer')
            if response:
                ai_message, ask_for_nps = process_message(response, callback_data)
                ai_message_dict = ai_message.dict()
                response_message = ResponseMessage(**ai_message_dict)
                response_message.ask_for_nps = ask_for_nps
                data = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode('utf-8')
                yield f"done: {data}\n\n"

                # Send notification with session context
                send_chat_message_notification(
                    uid,
                    "omi",
                    "omi",
                    ai_message.text,
                    ai_message.id,
                    session_id=chat_session_obj.id if chat_session_obj else None,
                )

    return


def send_chat_message_notification(
    user_id: str, app_name: str, app_id: str, message: str, message_id: str, session_id: Optional[str] = None
):
    """
    Send notification with session routing.
    Falls back gracefully if session_id not provided.
    """
    # Build URL with query param for session
    base_path = f'/chat/{app_id or "omi"}'
    if session_id:
        navigate_to = f'{base_path}?session_id={session_id}'
    else:
        navigate_to = base_path

    ai_message = NotificationMessage(
        id=message_id,
        text=message,
        plugin_id=app_id,
        from_integration='true',
        type='text',
        notification_type='plugin',
        navigate_to=navigate_to,
    )
    send_notification(user_id, app_name + ' says', message, NotificationMessage.get_message_as_dict(ai_message))
