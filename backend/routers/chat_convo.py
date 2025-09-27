import uuid
import re
import base64
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import database.chat_convo as chat_convo_db
import database.conversations as conversations_db
from models.chat_convo import (
    ConversationChatMessage,
    SendConversationMessageRequest,
    MessageSender,
    ConversationChatResponse,
    ConversationReference,
)
from utils.other import endpoints as auth
from utils.retrieval.graph_convos import execute_conversation_chat_stream  # We'll create this

router = APIRouter()


def _validate_conversation_access(uid: str, conversation_id: str) -> dict:
    """Validate that user has access to the conversation"""
    conversation = chat_convo_db.get_conversation_data(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail='Conversation not found')
    return conversation


@router.post(
    '/v2/conversations/{conversation_id}/chat/messages',
    tags=['conversation-chat'],
    response_model=ConversationChatResponse,
)
def send_conversation_message(
    conversation_id: str,
    data: SendConversationMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Send a message in a conversation-specific chat with streaming response"""
    print('send_conversation_message', conversation_id, data.text, uid)

    # Validate conversation access
    conversation = _validate_conversation_access(uid, conversation_id)

    # Ensure the conversation_id matches between URL and request body
    if data.conversation_id != conversation_id:
        raise HTTPException(status_code=400, detail='Conversation ID mismatch')

    # Create human message
    message = ConversationChatMessage(
        id=str(uuid.uuid4()),
        text=data.text,
        created_at=datetime.now(timezone.utc),
        sender='human',
        type='text',
        conversation_id=conversation_id,
    )

    # Store human message
    chat_convo_db.add_conversation_message(uid, message.dict())

    # Get recent messages for context (last 10 messages)
    messages = list(
        reversed(
            [
                ConversationChatMessage(**msg)
                for msg in chat_convo_db.get_conversation_messages(uid, conversation_id, limit=10)
            ]
        )
    )

    def process_message(response: str, callback_data: dict):
        """Process the AI response and create the AI message"""
        memories = callback_data.get('memories_found', [])
        action_items = callback_data.get('action_items_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)

        # Extract cited indices from response
        cited_memory_idxs = {int(i) for i in re.findall(r'\[(\d+)\]', response)}
        if len(cited_memory_idxs) > 0:
            response = re.sub(r'\[\d+\]', '', response)

        # Get referenced memories and action items
        memories_id = []
        action_items_id = []

        if memories and cited_memory_idxs:
            referenced_memories = [memories[i - 1] for i in cited_memory_idxs if 0 < i <= len(memories)]
            memories_id = [m.get('id') for m in referenced_memories if m.get('id')]

        # Create AI message
        ai_message = ConversationChatMessage(
            id=str(uuid.uuid4()),
            text=response,
            created_at=datetime.now(timezone.utc),
            sender='ai',
            type='text',
            conversation_id=conversation_id,
            memories_id=memories_id,
            action_items_id=action_items_id,
        )

        # Store AI message
        chat_convo_db.add_conversation_message(uid, ai_message.dict())

        return ai_message, ask_for_nps

    async def generate_stream():
        """Generate streaming response"""
        callback_data = {}
        async for chunk in execute_conversation_chat_stream(
            uid, conversation_id, messages, callback_data=callback_data
        ):
            if chunk:
                msg = chunk.replace("\n", "__CRLF__")
                yield f'{msg}\n\n'
            else:
                response = callback_data.get('answer')
                if response:
                    ai_message, ask_for_nps = process_message(response, callback_data)
                    ai_message_dict = ai_message.dict()

                    # Add conversation reference
                    conversation_ref = ConversationReference(
                        id=conversation['id'],
                        title=conversation.get('title', 'Untitled Conversation'),
                        created_at=conversation['created_at'],
                    )

                    response_message = ConversationChatResponse(**ai_message_dict)
                    response_message.ask_for_nps = ask_for_nps
                    response_message.conversation = conversation_ref

                    data = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode('utf-8')
                    yield f"done: {data}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


@router.get(
    '/v2/conversations/{conversation_id}/chat/messages',
    response_model=List[ConversationChatMessage],
    tags=['conversation-chat'],
)
def get_conversation_messages(
    conversation_id: str, limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)
):
    """Get all messages in a conversation chat"""
    # Validate conversation access
    _validate_conversation_access(uid, conversation_id)

    messages = chat_convo_db.get_conversation_messages(
        uid, conversation_id, limit=limit, offset=offset, include_references=True
    )
    print('get_conversation_messages', len(messages), conversation_id)

    return messages


@router.post(
    '/v2/conversations/{conversation_id}/chat/messages/{message_id}/report',
    tags=['conversation-chat'],
    response_model=dict,
)
def report_conversation_message(conversation_id: str, message_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Report a message in conversation chat"""
    # Validate conversation access
    _validate_conversation_access(uid, conversation_id)

    message, msg_doc_id = chat_convo_db.get_conversation_message(uid, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail='Message not found')
    if message.sender != 'ai':
        raise HTTPException(status_code=400, detail='Only AI messages can be reported')
    if message.reported:
        raise HTTPException(status_code=400, detail='Message already reported')
    if message.conversation_id != conversation_id:
        raise HTTPException(status_code=400, detail='Message does not belong to this conversation')

    chat_convo_db.report_conversation_message(uid, msg_doc_id)
    return {'message': 'Message reported'}


@router.delete('/v2/conversations/{conversation_id}/chat/messages', tags=['conversation-chat'])
def clear_conversation_chat(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Clear all messages in a conversation chat"""
    # Validate conversation access
    _validate_conversation_access(uid, conversation_id)

    err = chat_convo_db.clear_conversation_chat(uid, conversation_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear conversation chat')

    return {'message': 'Conversation chat cleared successfully'}


@router.get('/v2/conversations/{conversation_id}/chat/context', tags=['conversation-chat'])
def get_conversation_context(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get context information for a conversation (transcript, memories, action items)"""
    # Validate conversation access
    conversation = _validate_conversation_access(uid, conversation_id)

    # Use our proper context extraction logic
    from database.vector_db_convos import get_conversation_context

    context = get_conversation_context(uid, conversation_id)

    return {
        'conversation': {
            'id': conversation['id'],
            'title': context['conversation_title'],
            'summary': context['summary'],
            'transcript': context['transcript'],
            'created_at': conversation['created_at'],
        },
        'memories': context['memories'],
        'action_items': context['action_items'],
        'context_items_count': len(context['memories']) + len(context['action_items']),
    }
