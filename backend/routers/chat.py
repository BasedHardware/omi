import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends

import database.chat as chat_db
from models.chat import Message, SendMessageRequest
from utils import auth
from utils.llm import ask_agent

router = APIRouter()


@router.post('/v1/messages', tags=['chat'])
async def send_message(data: SendMessageRequest, uid: str = Depends(auth.get_current_user_uid)):
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
    messages = [Message(**msg) for msg in chat_db.get_messages(uid)]
    chat_db.add_message(uid, message.dict())

    # TODO: how to store the streamed response when completed?
    response: str = ask_agent(data.text, messages)
    if response:
        chat_db.add_message(uid, Message(
            id=str(uuid.uuid4()),
            text=response,
            created_at=datetime.utcnow(),
            sender='ai',
            plugin_id=None,
            from_external_integration=False,
            type='text',
            memories=[],  # TODO: include sources used
        ).dict())
    return {}


@router.get('/messages', response_model=List[Message], tags=['chat'])
def get_messages(uid: str = Depends(auth.get_current_user_uid)):
    return chat_db.get_messages(uid)
