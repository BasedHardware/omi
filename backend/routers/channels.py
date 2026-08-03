import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

import database.channels as channels_db
from database.phone_calls import get_primary_phone_number
from services.channel_chat import (
    HELP_TEXT,
    channel_sign_in_text,
    link_instructions,
    NOT_LINKED_TEXT,
    SIGNUP_TEXT,
    ChannelProviderError,
    generate_channel_reply,
    normalize_link_token,
    parse_channel_command,
    parse_sendblue_inbound,
    parse_twilio_conversation_inbound,
    parse_twilio_sms_inbound,
    parse_telegram_update,
    sanitize_channel_reply,
    send_channel_message,
    verify_sendblue_webhook,
    verify_telegram_webhook,
    verify_twilio_webhook,
)
from utils.executors import db_executor, run_blocking
from utils.multipart import PHONE_CALL_MAX_PART_SIZE, parse_multipart_form
from utils.other import endpoints as auth

router = APIRouter()


class LinkChannelResponse(BaseModel):
    channel: str
    code: str
    expires_at: datetime
    instructions: str


class ClaimChannelRequest(BaseModel):
    code: str


class ChannelBindingResponse(BaseModel):
    channel: str
    linked_at: datetime


class ChannelStatusResponse(BaseModel):
    bindings: list[ChannelBindingResponse]
    phone_registered: bool


class ChannelRevokeResponse(BaseModel):
    status: str
    revoked: int


def _channel_or_400(channel: str) -> str:
    normalized = channel.strip().lower()
    if normalized not in channels_db.CHANNELS:
        raise HTTPException(status_code=400, detail='Unsupported channel')
    return normalized


def _binding_response(binding: Dict[str, Any]) -> ChannelBindingResponse:
    linked_at = binding.get('linked_at')
    if not isinstance(linked_at, datetime):
        linked_at = datetime.now(timezone.utc)
    return ChannelBindingResponse(channel=str(binding['channel']), linked_at=linked_at)


@router.post('/v1/channels/{channel}/link', response_model=LinkChannelResponse, tags=['channels'])
async def issue_channel_link(
    channel: str, uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'channels:link'))
) -> LinkChannelResponse:
    channel = _channel_or_400(channel)
    token, expires_at = await run_blocking(db_executor, channels_db.issue_link_token, uid, channel)
    instructions = link_instructions(channel, token, expires_at)
    return LinkChannelResponse(channel=channel, code=token, expires_at=expires_at, instructions=instructions)


@router.post('/v1/channels/{channel}/claim', response_model=ChannelBindingResponse, tags=['channels'])
async def claim_channel_link(
    channel: str,
    request: ClaimChannelRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'channels:claim')),
) -> ChannelBindingResponse:
    channel = _channel_or_400(channel)
    token = normalize_link_token(request.code)
    if not token:
        raise HTTPException(status_code=400, detail='Invalid or expired link code')
    try:
        binding = await run_blocking(db_executor, channels_db.claim_link_token, uid, channel, token)
    except channels_db.ChannelBindingConflict:
        raise HTTPException(status_code=409, detail='This channel is already linked to another account')
    except channels_db.ChannelLinkError:
        raise HTTPException(status_code=400, detail='Invalid or expired link code')
    return _binding_response(binding)


@router.get('/v1/channels', response_model=ChannelStatusResponse, tags=['channels'])
async def get_channel_status(
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'channels:status'))
) -> ChannelStatusResponse:
    bindings = await run_blocking(db_executor, channels_db.list_bindings, uid)
    phone = await run_blocking(db_executor, get_primary_phone_number, uid)
    return ChannelStatusResponse(
        bindings=[_binding_response(binding) for binding in bindings],
        phone_registered=phone is not None,
    )


@router.delete('/v1/channels/{channel}', response_model=ChannelRevokeResponse, tags=['channels'])
async def revoke_channel(
    channel: str, uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'channels:unlink'))
) -> ChannelRevokeResponse:
    channel = _channel_or_400(channel)
    count = await run_blocking(db_executor, channels_db.revoke_channel, uid, channel)
    return ChannelRevokeResponse(status='ok', revoked=count)


async def _send_and_record(
    channel: str,
    event_id: str,
    channel_chat_id: str,
    reply: str,
    *,
    is_group: bool = False,
    provider_mode: Optional[str] = None,
) -> None:
    reply = sanitize_channel_reply(channel, reply)
    await run_blocking(
        db_executor,
        channels_db.update_webhook_event,
        channel,
        event_id,
        {
            'status': 'ready',
            'reply': reply,
            'channel_chat_id': channel_chat_id,
            'is_group': is_group,
            'provider_mode': provider_mode,
        },
    )
    try:
        await send_channel_message(channel, channel_chat_id, reply, is_group=is_group, provider_mode=provider_mode)
    except ChannelProviderError:
        raise HTTPException(status_code=503, detail='Channel delivery unavailable')
    await run_blocking(db_executor, channels_db.update_webhook_event, channel, event_id, {'status': 'delivered'})


async def _duplicate_event_response(channel: str, event_id: str, event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not event or event.get('status') != 'ready' or not event.get('reply') or not event.get('channel_chat_id'):
        return {'status': 'duplicate'}
    await _send_and_record(
        channel,
        event_id,
        str(event['channel_chat_id']),
        str(event['reply']),
        is_group=bool(event.get('is_group')),
        provider_mode=str(event['provider_mode']) if event.get('provider_mode') else None,
    )
    return {'status': 'redelivered'}


async def _channel_reply(channel: str, payload: Dict[str, Any]) -> str:
    channel_user_id = payload['channel_user_id']
    channel_chat_id = payload['channel_chat_id']
    text = payload['text']
    is_group = channel_chat_id != channel_user_id

    command = parse_channel_command(text)
    binding_args = (channel, channel_user_id, channel_chat_id) if is_group else (channel, channel_user_id)
    binding = await run_blocking(db_executor, channels_db.get_binding, *binding_args)
    if command:
        name, argument = command
        if name in {'/help'}:
            return HELP_TEXT
        if name in {'/signup', '/new'}:
            return SIGNUP_TEXT
        if name == '/status':
            return 'This chat is linked to your Omi account.' if binding else NOT_LINKED_TEXT
        if name in {'/unlink', '/logout'}:
            if not binding:
                return NOT_LINKED_TEXT
            revoke_args = (channel, channel_user_id, channel_chat_id) if is_group else (channel, channel_user_id)
            revoked = await run_blocking(db_executor, channels_db.revoke_binding, *revoke_args)
            return 'This channel is disconnected.' if revoked else NOT_LINKED_TEXT
        if name in {'/start', '/link'} and argument:
            token = normalize_link_token(argument)
            if not token:
                return 'That link code is invalid or expired. Ask the Omi core chat for a new one.'
            try:
                await run_blocking(
                    db_executor,
                    channels_db.consume_link_token,
                    channel,
                    token,
                    channel_user_id,
                    channel_chat_id,
                )
            except channels_db.ChannelBindingConflict:
                return 'This channel is already linked to another Omi account. Disconnect it there first.'
            except channels_db.ChannelLinkError:
                return 'That link code is invalid or expired. Ask the Omi core chat for a new one.'
            return 'This channel is now linked to your Omi account. Send /help for commands.'
        if name.startswith('/'):
            return HELP_TEXT

    if not binding:
        token, expires_at = await run_blocking(
            db_executor,
            channels_db.issue_claim_token,
            channel,
            channel_user_id,
            channel_chat_id,
        )
        return channel_sign_in_text(channel, token, expires_at)
    try:
        sender_name = payload.get('sender_name')
        prompt_text = text
        if is_group:
            prompt_text = f"{sender_name or channel_user_id}: {text}".strip()
        return await generate_channel_reply(
            binding['uid'],
            channel,
            prompt_text,
            attachments=payload.get('attachments'),
        )
    except Exception:
        return 'I could not complete that request. Please try again.'


async def _handle_payload(channel: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    event_id = payload['event_id']
    created, existing = await run_blocking(db_executor, channels_db.claim_webhook_event, channel, event_id)
    if not created:
        return await _duplicate_event_response(channel, event_id, existing)
    reply = await _channel_reply(channel, payload)
    await _send_and_record(
        channel,
        event_id,
        payload['channel_chat_id'],
        reply,
        is_group=payload['channel_chat_id'] != payload['channel_user_id'],
        provider_mode=payload.get('provider_mode'),
    )
    return {'status': 'delivered'}


@router.post('/v1/webhooks/telegram', tags=['channels'])
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None, alias='X-Telegram-Bot-Api-Secret-Token'),
) -> Dict[str, Any]:
    if not verify_telegram_webhook(x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=401, detail='Invalid webhook signature')
    try:
        body = await request.json()
        payload = parse_telegram_update(body)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail='Invalid Telegram update')
    if payload is None:
        return {'status': 'ignored'}
    return await _handle_payload('telegram', payload)


@router.post('/v1/webhooks/sendblue/{path_token}', tags=['channels'])
async def sendblue_webhook(
    path_token: str,
    request: Request,
    sb_signing_secret: Optional[str] = Header(None, alias='sb-signing-secret'),
) -> Dict[str, Any]:
    if not verify_sendblue_webhook(path_token, sb_signing_secret):
        raise HTTPException(status_code=401, detail='Invalid webhook signature')
    try:
        body = await request.json()
        payload = parse_sendblue_inbound(body)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail='Invalid Sendblue update')
    if payload is None:
        return {'status': 'ignored'}
    return await _handle_payload('imessage', payload)


@router.post('/v1/webhooks/twilio/sms', tags=['channels'])
async def twilio_sms_webhook(request: Request) -> Dict[str, Any]:
    base_api_url = os.getenv('BASE_API_URL', '').rstrip('/')
    url = f'{base_api_url}{request.url.path}' if base_api_url else str(request.url)
    signature = request.headers.get('X-Twilio-Signature')
    form_data = await parse_multipart_form(request, max_part_size=PHONE_CALL_MAX_PART_SIZE)
    params = {str(key): str(value) for key, value in form_data.multi_items()}
    if not verify_twilio_webhook(url, params, signature):
        raise HTTPException(status_code=403, detail='Invalid Twilio signature')
    payload = parse_twilio_sms_inbound(params)
    if payload is None:
        return {'status': 'ignored'}
    return await _handle_payload('sms', payload)


@router.post('/v1/webhooks/twilio/conversations', tags=['channels'])
async def twilio_conversations_webhook(request: Request) -> Dict[str, Any]:
    base_api_url = os.getenv('BASE_API_URL', '').rstrip('/')
    url = f'{base_api_url}{request.url.path}' if base_api_url else str(request.url)
    signature = request.headers.get('X-Twilio-Signature')
    form_data = await parse_multipart_form(request, max_part_size=PHONE_CALL_MAX_PART_SIZE)
    params = {str(key): str(value) for key, value in form_data.multi_items()}
    if not verify_twilio_webhook(url, params, signature):
        raise HTTPException(status_code=403, detail='Invalid Twilio signature')
    payload = parse_twilio_conversation_inbound(params)
    if payload is None:
        return {'status': 'ignored'}
    return await _handle_payload('sms', payload)
