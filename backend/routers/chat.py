import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

import database.chat as chat_db
from database.plugins import record_plugin_usage
from models.app import App
from models.plugin import UsageHistoryType
from models.memory import Memory
from models.chat import Message, SendMessageRequest, MessageSender, ResponseMessage
from utils.apps import get_available_app_by_id
from utils.llm import initial_chat_message
from utils.other import endpoints as auth
from utils.retrieval.graph import execute_graph_chat

router = APIRouter()


def filter_messages(messages, plugin_id):
    print('filter_messages', len(messages), plugin_id)
    collected = []
    for message in messages:
        if message.sender == MessageSender.ai and message.plugin_id != plugin_id:
            break
        collected.append(message)
    print('filter_messages output:', len(collected))
    return collected


@router.post('/v1/messages', tags=['chat'], response_model=ResponseMessage)
def send_message(
        data: SendMessageRequest, plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    print('send_message', data.text, plugin_id, uid)
    message = Message(
        id=str(uuid.uuid4()), text=data.text, created_at=datetime.now(timezone.utc), sender='human', type='text'
    )
    chat_db.add_message(uid, message.dict())

    plugin = get_available_app_by_id(plugin_id, uid)
    plugin = App(**plugin) if plugin else None

    plugin_id = plugin.id if plugin else None

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

    resp = ai_message.dict()
    resp['ask_for_nps'] = ask_for_nps
    return resp


@router.delete('/v1/messages', tags=['chat'], response_model=Message)
def clear_chat_messages(uid: str = Depends(auth.get_current_user_uid)):
    err = chat_db.clear_chat(uid)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')
    return initial_message_util(uid)


def initial_message_util(uid: str, plugin_id: Optional[str] = None):
    plugin = get_available_app_by_id(plugin_id, uid)
    plugin = App(**plugin) if plugin else None
    text = initial_chat_message(uid, plugin)

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        plugin_id=plugin_id,
        from_external_integration=False,
        type='text',
        memories_id=[],
    )
    chat_db.add_message(uid, ai_message.dict())
    return ai_message


@router.post('/v1/initial-message', tags=['chat'], response_model=Message)
def send_message(plugin_id: Optional[str], uid: str = Depends(auth.get_current_user_uid)):
    return initial_message_util(uid, plugin_id)


@router.get('/v1/messages', response_model=List[Message], tags=['chat'])
def get_messages(uid: str = Depends(auth.get_current_user_uid)):
    messages = chat_db.get_messages(uid, limit=100, include_memories=True)  # for now retrieving first 100 messages
    if not messages:
        return [initial_message_util(uid)]
    return messages
