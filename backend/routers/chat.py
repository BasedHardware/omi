import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

import database.chat as chat_db
from models.chat import Message, SendMessageRequest, MessageSender
from utils.llm import qa_rag, initial_chat_message
from utils.other import endpoints as auth
from utils.plugins import get_plugin_by_id
from utils.retrieval.rag import retrieve_rag_context

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


@router.post('/v1/messages', tags=['chat'], response_model=Message)
def send_message(
        data: SendMessageRequest, plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    message = Message(id=str(uuid.uuid4()), text=data.text, created_at=datetime.now(timezone.utc), sender='human',
                      type='text')
    chat_db.add_message(uid, message.dict())

    plugin = get_plugin_by_id(plugin_id)
    plugin_id = plugin.id if plugin else None

    messages = [Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]
    messages = filter_messages(messages, plugin_id)

    context_str, memories = retrieve_rag_context(uid, messages)
    response: str = qa_rag(uid, context_str, messages, plugin)

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=response,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        plugin_id=plugin_id,
        type='text',
        # only store the 5 most relevant memories
        memories_id=[m.id for m in (memories if len(memories) < 5 else memories[:5])],
    )
    chat_db.add_message(uid, ai_message.dict())
    ai_message.memories = memories if len(memories) < 5 else memories[:5]
    return ai_message


@router.delete('/v1/messages', tags=['chat'], response_model=Message)
def clear_chat_messages(uid: str = Depends(auth.get_current_user_uid)):
    err = chat_db.clear_chat(uid)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')
    return initial_message_util(uid)


def initial_message_util(uid: str, plugin_id: Optional[str] = None):
    plugin = get_plugin_by_id(plugin_id)
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
