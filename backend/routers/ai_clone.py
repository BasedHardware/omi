from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import database.ai_clone as clone_db
from utils.integrations import telegram_client as tg
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


class TelegramSendCodeRequest(BaseModel):
    phone: str


class TelegramVerifyRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str


class TelegramSendRequest(BaseModel):
    chat_id: int
    text: str


# ── Core endpoints ──────────────────────────────────────────────────────────────


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

    reply = await run_blocking(
        llm_executor,
        generate_clone_reply,
        uid,
        body.sender,
        body.message,
        body.platform,
        body.conversation_history,
    )

    message_doc = {
        'platform': body.platform,
        'sender': body.sender,
        'incoming': body.message,
        'draft_reply': reply,
        'status': 'pending',
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


# ── Telegram personal-account auth (Telethon MTProto) ─────────────────────────


@router.post('/v1/ai-clone/telegram/send-code')
async def telegram_send_code(
    body: TelegramSendCodeRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Send OTP to the user's personal Telegram account via MTProto."""
    try:
        result = await tg.send_code(body.phone)
        return result  # {'phone_code_hash': str}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f'Telegram send_code error uid={uid}: {e}')
        raise HTTPException(status_code=500, detail='Failed to send code')


@router.post('/v1/ai-clone/telegram/verify')
async def telegram_verify(
    body: TelegramVerifyRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Verify OTP and establish Telethon session for the user."""
    try:
        result = await tg.verify_code(uid, body.phone, body.code, body.phone_code_hash)
        return result  # {'display_name': str, 'phone': str}
    except Exception as e:
        logger.error(f'Telegram verify error uid={uid}: {e}')
        raise HTTPException(status_code=400, detail='Verification failed — check code and try again')


@router.post('/v1/ai-clone/telegram/disconnect')
async def telegram_disconnect(uid: str = Depends(auth.get_current_user_uid)):
    """Log out of Telegram and remove the session."""
    await tg.disconnect(uid)
    return {'status': 'ok'}


@router.get('/v1/ai-clone/telegram/messages')
async def telegram_poll_messages(
    since: float = 0,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Return personal Telegram DMs newer than `since` (Unix timestamp).
    The desktop polls this every 15s to surface new messages.
    """
    try:
        messages = await tg.poll_new_messages(uid, since)
        return {'messages': messages}
    except Exception as e:
        logger.error(f'Telegram poll error uid={uid}: {e}')
        return {'messages': []}


@router.post('/v1/ai-clone/telegram/send')
async def telegram_send(
    body: TelegramSendRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Send a message from the user's personal Telegram account."""
    ok = await tg.send_message(uid, body.chat_id, body.text)
    if not ok:
        raise HTTPException(status_code=503, detail='Not connected to Telegram or send failed')
    return {'status': 'ok'}
