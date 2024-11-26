import uuid
import threading
import time
from datetime import datetime, timezone
from typing import List

import database.chat as chat_db
from database.plugins import record_plugin_usage
from models.app import App
from models.plugin import UsageHistoryType
from models.memory import Memory
from models.chat import Message, SendMessageRequest, MessageSender, ResponseMessage
from models.transcript_segment import TranscriptSegment
from utils.retrieval.graph import execute_graph_chat
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
from utils.other.storage import get_syncing_file_temporal_signed_url, delete_syncing_temporal_file
from models.notification_message import NotificationMessage
import database.notifications as notification_db
from utils.notifications import send_notification

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
    plugin = None
    plugin_id = None

    messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]))
    response, ask_for_nps, memories = execute_graph_chat(uid, messages, plugin)  # plugin
    memories_id = []
    # check if the items in the memories list are dict
    if memories:
        converted_memories = []
        for m in memories[:5]:
            if isinstance(m, dict):
                converted_memories.append(Memory(**m))
            else:
                converted_memories.append(m)
        memories_id = [m.id for m in converted_memories]
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=response,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        plugin_id=plugin_id,
        type='text',
        memories_id=memories_id,
    )
    chat_db.add_message(uid, ai_message.dict())
    ai_message.memories = memories if len(memories) < 5 else memories[:5]
    if plugin_id:
        record_plugin_usage(uid, plugin_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

    ai_message_resp = ai_message.dict()

    ai_message_resp['ask_for_nps'] = ask_for_nps

    # send notification
    token = notification_db.get_token_only(uid)
    send_chat_message_notification(token, "Omi", None, ai_message.text)

    return [message.dict(), ai_message_resp]

def send_chat_message_notification(token: str, plugin_name: str, plugin_id: str, message: str):
    ai_message = NotificationMessage(
        text=message,
        plugin_id=plugin_id,
        from_integration='true',
        type='text',
        notification_type='plugin',
    )
    send_notification(token, plugin_name + ' says', message, NotificationMessage.get_message_as_dict(ai_message))
