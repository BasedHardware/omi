from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

import database.ai_clone as clone_db
from utils.integrations import telegram_client as tg
from utils.integrations import whatsapp_client as wa
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
    auto_reply: bool = True
    platforms: dict = {}


class UpdateMessageRequest(BaseModel):
    status: str  # sent | dismissed
    edited_reply: Optional[str] = None


class TelegramConnectRequest(BaseModel):
    bot_token: str


class TelegramSendRequest(BaseModel):
    chat_id: int
    text: str


class WhatsAppSendRequest(BaseModel):
    to: str  # recipient phone number in E.164 format, e.g. +15551234567
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
    """
    Generate a reply draft in the user's voice and save it to the message log.
    Called by the desktop for iMessage (the only platform where reply generation
    happens on-device after polling). Telegram and WhatsApp are webhook-driven and
    auto-reply without hitting this endpoint.
    """
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
    limit: int = Query(50, ge=1, le=500),
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
        'updated_at': datetime.now(timezone.utc),
    }
    if body.edited_reply is not None:
        updates['final_reply'] = body.edited_reply
    await run_blocking(db_executor, clone_db.update_clone_message, uid, message_id, updates)
    return {'status': 'ok'}


# ── Telegram Bot API ───────────────────────────────────────────────────────────


@router.post('/v1/ai-clone/telegram/connect')
async def telegram_connect(
    body: TelegramConnectRequest,
    request: Request,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Validate the user's Telegram bot token and register the per-user webhook.
    The webhook URL is derived from the incoming request's base URL so it works
    in both local dev (with a tunnel) and production automatically.
    """
    webhook_url = f'{request.base_url}v1/ai-clone/telegram/webhook/{uid}'
    try:
        result = await tg.connect(uid, body.bot_token, str(webhook_url))
        return result  # {'bot_username': str, 'bot_name': str}
    except ValueError as e:
        if str(e) == 'invalid_bot_token':
            raise HTTPException(status_code=400, detail='Invalid bot token — create one at @BotFather')
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f'Telegram connect error uid={uid}: {e}')
        raise HTTPException(status_code=500, detail='Failed to connect Telegram bot')


@router.post('/v1/ai-clone/telegram/disconnect')
async def telegram_disconnect(uid: str = Depends(auth.get_current_user_uid)):
    """Remove the Telegram webhook and delete the stored bot token."""
    await tg.disconnect(uid)
    return {'status': 'ok'}


@router.post('/v1/ai-clone/telegram/webhook/{uid}')
async def telegram_webhook_receive(uid: str, request: Request):
    """
    Receive incoming Telegram messages from the Bot API webhook.
    Generates a reply using the user's memories and sends it immediately —
    no desktop approval step.
    Meta expects a 200 response quickly; reply generation runs inline but
    returns 200 regardless to avoid Telegram retry storms.
    """
    try:
        payload = await request.json()
        message = payload.get('message', {})
        text = (message.get('text') or '').strip()
        chat_id = (message.get('chat') or {}).get('id')
        from_info = message.get('from') or {}
        sender_name = (
            ' '.join(filter(None, [from_info.get('first_name'), from_info.get('last_name')]))
            or from_info.get('username')
            or 'Unknown'
        )

        if text and chat_id:
            reply = await run_blocking(
                llm_executor,
                generate_clone_reply,
                uid,
                sender_name,
                text,
                'telegram',
                None,
            )
            await tg.send_message(uid, chat_id, reply)
            message_doc = {
                'platform': 'telegram',
                'sender': sender_name,
                'chat_identifier': str(chat_id),
                'incoming': text,
                'draft_reply': reply,
                'status': 'sent',
                'conversation_history': [],
            }
            await run_blocking(db_executor, clone_db.save_clone_message, uid, message_doc)
    except Exception as e:
        logger.error(f'Telegram webhook error uid={uid}: {e}')
    return {'ok': True}


@router.post('/v1/ai-clone/telegram/send')
async def telegram_send(
    body: TelegramSendRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Send a message via the user's Telegram bot. Used for desktop-initiated sends."""
    ok = await tg.send_message(uid, body.chat_id, body.text)
    if not ok:
        raise HTTPException(status_code=503, detail='Telegram bot not configured or send failed')
    return {'status': 'ok'}


# ── WhatsApp Cloud API (bot, webhook-driven) ───────────────────────────────────


@router.get('/v1/ai-clone/whatsapp/webhook')
async def whatsapp_webhook_verify(request: Request):
    """Meta webhook verification handshake."""
    params = dict(request.query_params)
    if params.get('hub.verify_token') != wa.VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail='Invalid verify token')
    return int(params.get('hub.challenge', 0))


@router.post('/v1/ai-clone/whatsapp/webhook/{uid}')
async def whatsapp_webhook_receive(uid: str, request: Request):
    """
    Receive incoming WhatsApp messages from Meta. Generates a reply and sends
    it immediately — no desktop approval step.
    """
    try:
        payload = await request.json()
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                for msg in value.get('messages', []):
                    if msg.get('type') != 'text':
                        continue
                    sender = msg.get('from', '')
                    text = (msg.get('text') or {}).get('body', '').strip()
                    contact_name = next(
                        (
                            c.get('profile', {}).get('name', sender)
                            for c in value.get('contacts', [])
                            if c.get('wa_id') == sender
                        ),
                        sender,
                    )
                    if text:
                        reply = await run_blocking(
                            llm_executor,
                            generate_clone_reply,
                            uid,
                            contact_name,
                            text,
                            'whatsapp',
                            None,
                        )
                        await wa.send_message(sender, reply)
                        message_doc = {
                            'platform': 'whatsapp',
                            'sender': contact_name,
                            'chat_identifier': sender,
                            'incoming': text,
                            'draft_reply': reply,
                            'status': 'sent',
                            'conversation_history': [],
                        }
                        await run_blocking(db_executor, clone_db.save_clone_message, uid, message_doc)
    except Exception as e:
        logger.error(f'WhatsApp webhook error uid={uid}: {e}')
    return {'status': 'ok'}


@router.post('/v1/ai-clone/whatsapp/send')
async def whatsapp_send(
    body: WhatsAppSendRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Send a WhatsApp message via the Cloud API on behalf of the user's bot number."""
    ok = await wa.send_message(body.to, body.text)
    if not ok:
        raise HTTPException(status_code=503, detail='WhatsApp not configured or send failed')
    return {'status': 'ok'}
