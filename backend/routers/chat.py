import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends

import database.chat as chat_db
from models.chat import Message, SendMessageRequest
from utils import auth
from utils.llm import qa_rag_prompt
from utils.rag import retrieve_rag_context

router = APIRouter()


@router.post('/v1/messages', tags=['chat'], response_model=Message)
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
    chat_db.add_message(uid, message.dict())

    messages = [Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]
    context_str, memories_id = retrieve_rag_context(uid, messages)
    # print('context_str', context_str)
    response: str = qa_rag_prompt(context_str, messages)
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


@router.get('/v1/messages', response_model=List[Message], tags=['chat'])
def get_messages(uid: str = Depends(auth.get_current_user_uid)):
    return chat_db.get_messages(uid)
