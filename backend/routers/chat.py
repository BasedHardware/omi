import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends

import database.chat as chat_db
from models.chat import Message, SendMessageRequest, MessageSender
from utils import auth
from utils.llm import qa_rag, initial_chat_message
from utils.plugins import get_plugin_by_id
from utils.rag import retrieve_rag_context

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
    message = Message(id=str(uuid.uuid4()), text=data.text, created_at=datetime.utcnow(), sender='human', type='text')
    chat_db.add_message(uid, message.dict())

    plugin = get_plugin_by_id(plugin_id)
    plugin_id = plugin.id if plugin else None

    messages = [Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]
    messages = filter_messages(messages, plugin_id)

    context_str, memories_id = retrieve_rag_context(uid, messages)
    response: str = qa_rag(context_str, messages, plugin)

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=response,
        created_at=datetime.utcnow(),
        sender='ai',
        plugin_id=plugin_id,
        type='text',
        memories=[],
    )
    # TODO: include sources used as memory.id reference
    chat_db.add_message(uid, ai_message.dict())
    return ai_message


def initial_message_util(uid: str, plugin_id: Optional[str] = None):
    plugin = get_plugin_by_id(plugin_id)

    text = initial_chat_message(plugin)
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.utcnow(),
        sender='ai',
        plugin_id=plugin_id,
        from_external_integration=False,
        type='text',
        memories=[],
    )
    chat_db.add_message(uid, ai_message.dict())
    return ai_message


@router.post('/v1/initial-message', tags=['chat'], response_model=Message)
def send_message(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    return initial_message_util(uid, plugin_id)


@router.get('/v1/messages', response_model=List[Message], tags=['chat'])
def get_messages(uid: str = Depends(auth.get_current_user_uid)):
    messages = chat_db.get_messages(uid)
    if not messages:
        return [initial_message_util(uid)]
    return messages
