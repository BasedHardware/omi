from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import database.ai_clone as clone_db
from utils.llm.clone import generate_clone_reply
from utils.other import endpoints as auth
from utils.executors import db_executor, llm_executor, run_blocking
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────────


class GenerateReplyRequest(BaseModel):
    platform: str  # imessage | telegram | whatsapp
    sender: str
    message: str
    conversation_history: Optional[list[dict]] = None


class GenerateReplyResponse(BaseModel):
    reply: str
    message_id: str


class CloneSettings(BaseModel):
    enabled: bool = False
    auto_reply: bool = False
    platforms: dict = {}


class UpdateMessageRequest(BaseModel):
    status: str  # approved | dismissed | sent
    edited_reply: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get('/v1/ai-clone/settings')
async def get_settings(uid: str = Depends(auth.get_current_user_uid)):
    settings = await run_blocking(db_executor, clone_db.get_clone_settings, uid)
    return settings


@router.put('/v1/ai-clone/settings')
async def update_settings(
    body: CloneSettings,
    uid: str = Depends(auth.get_current_user_uid),
):
    await run_blocking(db_executor, clone_db.update_clone_settings, uid, body.model_dump())
    return {'status': 'ok'}


@router.post('/v1/ai-clone/generate-reply', response_model=GenerateReplyResponse)
async def generate_reply(
    body: GenerateReplyRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail='message cannot be empty')

    # Generate reply using user's memories
    reply = await run_blocking(
        llm_executor,
        generate_clone_reply,
        uid,
        body.sender,
        body.message,
        body.platform,
        body.conversation_history,
    )

    # Persist the incoming message + draft
    message_doc = {
        'platform': body.platform,
        'sender': body.sender,
        'incoming': body.message,
        'draft_reply': reply,
        'status': 'pending',  # pending | approved | dismissed | sent
        'conversation_history': body.conversation_history or [],
    }
    message_id = await run_blocking(db_executor, clone_db.save_clone_message, uid, message_doc)

    return GenerateReplyResponse(reply=reply, message_id=message_id)


@router.get('/v1/ai-clone/messages')
async def get_messages(
    limit: int = 50,
    uid: str = Depends(auth.get_current_user_uid),
):
    messages = await run_blocking(db_executor, clone_db.get_clone_messages, uid, limit)
    return messages


@router.patch('/v1/ai-clone/messages/{message_id}')
async def update_message(
    message_id: str,
    body: UpdateMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    updates: dict = {
        'status': body.status,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    if body.edited_reply is not None:
        updates['final_reply'] = body.edited_reply
    await run_blocking(db_executor, clone_db.update_clone_message, uid, message_id, updates)
    return {'status': 'ok'}
