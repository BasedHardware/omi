import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends

import database.chat as chat_db
from models.chat import Message, SendMessageRequest
from utils import auth
from utils.llm import qa_rag, initial_chat_message
from utils.plugins import get_plugins_data
from utils.rag import retrieve_rag_context

router = APIRouter()


@router.post('/v1/messages', tags=['chat'], response_model=Message)
def send_message(data: SendMessageRequest, uid: str = Depends(auth.get_current_user_uid)):
    message = Message(
        id=str(uuid.uuid4()),
        text=data.text,
        created_at=datetime.utcnow(),
        sender='human',
        plugin_id=None,
        from_external_integration=False,
        type='text',
        memories=[],
    )
    chat_db.add_message(uid, message.dict())

    # TODO: handle plugin selected and filter only for that plugin
    messages = [Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]
    context_str, memories_id = retrieve_rag_context(uid, messages)
    # print('context_str', context_str)
    response: str = qa_rag(context_str, messages)
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=response,
        created_at=datetime.utcnow(),
        sender='ai',
        plugin_id=None,
        from_external_integration=False,
        type='text',
        memories=[],  # TODO: include sources used as memory.id reference
    )

    chat_db.add_message(uid, ai_message.dict())
    return ai_message


def initial_message_util(uid: str, plugin_id: Optional[str] = None):
    plugin = None
    if plugin_id:
        plugins = get_plugins_data(uid)
        plugin = next((p for p in plugins if p.id == plugin_id), None)

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
