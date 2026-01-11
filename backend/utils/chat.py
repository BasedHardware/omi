import threading
import time
import base64
import uuid
from datetime import datetime, timezone
from typing import List, AsyncGenerator

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
from utils.stt.pre_recorded import deepgram_prerecorded, postprocess_words


def transcribe_voice_message_segment(path: str):
    url = get_syncing_file_temporal_signed_url(path)

    def delete_file():
        time.sleep(480)
        delete_syncing_temporal_file(path)

    threading.Thread(target=delete_file).start()

    words = deepgram_prerecorded(url, diarize=False)
    transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    if not transcript_segments:
        print('failed to get deepgram segments')
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

    words = deepgram_prerecorded(url, diarize=False)
    transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    if not transcript_segments:
        print('failed to get deepgram segments')
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
    url = get_syncing_file_temporal_signed_url(path)

    def delete_file():
        time.sleep(480)
        delete_syncing_temporal_file(path)

    threading.Thread(target=delete_file).start()

    words = deepgram_prerecorded(url, diarize=False)
    transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
    if not transcript_segments:
        print('failed to get deepgram segments')
        return

    text = " ".join([segment.text for segment in transcript_segments]).strip()
    if len(text) == 0:
        print('voice message text is empty')
        return

    # create message
    message = Message(
        id=str(uuid.uuid4()), text=text, created_at=datetime.now(timezone.utc), sender='human', type='text'
    )

    chat_session = chat_db.get_chat_session(uid)
    chat_session = ChatSession(**chat_session) if chat_session else None

    if chat_session:
        message.chat_session_id = chat_session.id
        chat_db.add_message_to_chat_session(uid, chat_session.id, message.id)

    chat_db.add_message(uid, message.dict())

    # stream
    mdata = base64.b64encode(bytes(message.model_dump_json(), 'utf-8')).decode('utf-8')
    yield f"message: {mdata}\n\n"

    # not support plugin
    app = None
    app_id = None

    def process_message(response: str, callback_data: dict):
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
            langsmith_run_id=langsmith_run_id,  # Store run_id for feedback tracking
            prompt_name=prompt_name,  # LangSmith prompt name for versioning
            prompt_commit=prompt_commit,  # LangSmith prompt commit for traceability
        )

        chat_session = chat_db.get_chat_session(uid)
        chat_session = ChatSession(**chat_session) if chat_session else None

        if chat_session:
            ai_message.chat_session_id = chat_session.id
            chat_db.add_message_to_chat_session(uid, chat_session.id, ai_message.id)

        chat_db.add_message(uid, ai_message.dict())
        ai_message.memories = [MessageConversation(**m) for m in (memories if len(memories) < 5 else memories[:5])]

        if app_id:
            record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

        return ai_message, ask_for_nps

    messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]))
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

                # send notification
                send_chat_message_notification(uid, "omi", "omi", ai_message.text, ai_message.id)

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
