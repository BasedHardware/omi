import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import database.chat as chat_db
import database.llm_usage as llm_usage_db
from models.chat import ChatSession, Message, MessageSender, MessageType
from utils.conversation_helpers import extract_memory_ids
from utils.executors import critical_executor, db_executor, run_blocking
from utils.http_client import get_webhook_client
from utils.llm.usage_tracker import Features, reset_usage_context, set_usage_context
from utils.retrieval.graph import execute_chat_stream
from utils.subscription import enforce_chat_quota
from utils.twilio_service import send_sms
from services.channel_media import build_media_context

CHANNEL_MAX_REPLY_LENGTH = {'telegram': 4096, 'imessage': 2000, 'sms': 1600}
CHANNEL_MAX_INBOUND_LENGTH = 20000
LINK_TOKEN_PATTERN = re.compile(r'^[0-9a-f]{48}$')

NOT_LINKED_TEXT = (
    "This chat isn't linked to Omi yet. Open Omi, ask the core chat to connect this channel, "
    'then send the generated code here.'
)
HELP_TEXT = (
    'Commands: /help, /start CODE to link, /status, /unlink, and /signup. ' 'Anything else goes to your Omi core chat.'
)
SIGNUP_TEXT = (
    'Create an Omi account in the app, then ask the core chat to connect this channel. '
    'Download Omi at https://omi.me/download.'
)


class ChannelProviderError(RuntimeError):
    pass


def _setting(name: str) -> Optional[str]:
    value = os.getenv(name, '').strip()
    return value or None


def _constant_time_equal(left: Optional[str], right: Optional[str]) -> bool:
    return bool(left and right and hmac.compare_digest(left, right))


def verify_telegram_webhook(secret_header: Optional[str]) -> bool:
    return _constant_time_equal(secret_header, _setting('TELEGRAM_WEBHOOK_SECRET'))


def verify_sendblue_webhook(path_token: str, signing_secret: Optional[str]) -> bool:
    return _constant_time_equal(path_token, _setting('SENDBLUE_WEBHOOK_PATH_TOKEN')) and _constant_time_equal(
        signing_secret, _setting('SENDBLUE_WEBHOOK_SIGNING_SECRET')
    )


def verify_twilio_webhook(url: str, params: Dict[str, Any], signature: Optional[str]) -> bool:
    if not signature:
        return False
    from utils.twilio_service import validate_twilio_signature

    return validate_twilio_signature(url, params, signature)


def _safe_integer(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if abs(value) <= 9_007_199_254_740_991 else None
    if isinstance(value, float) and value.is_integer() and abs(value) <= 9_007_199_254_740_991:
        return int(value)
    return None


def parse_telegram_update(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    update_id = _safe_integer(body.get('update_id'))
    if update_id is None:
        raise ValueError('invalid Telegram update')
    message = body.get('message')
    if not isinstance(message, dict):
        return None
    message_id = _safe_integer(message.get('message_id'))
    sender = message.get('from')
    chat = message.get('chat')
    chat_id = _safe_integer(chat.get('id')) if isinstance(chat, dict) else None
    user_id = _safe_integer(sender.get('id')) if isinstance(sender, dict) else None
    text = message.get('text') or message.get('caption')
    attachments: List[Dict[str, Any]] = []
    photo = message.get('photo')
    if isinstance(photo, list) and photo:
        photo_file = photo[-1] if isinstance(photo[-1], dict) else {}
        if isinstance(photo_file.get('file_id'), str):
            attachments.append(
                {
                    'source': 'telegram',
                    'file_id': photo_file['file_id'],
                    'filename': 'photo.jpg',
                    'mime_type': 'image/jpeg',
                }
            )
    for field, default_name, default_mime in (
        ('document', 'document', 'application/octet-stream'),
        ('video', 'video.mp4', 'video/mp4'),
        ('audio', 'audio', 'audio/mpeg'),
        ('voice', 'voice.ogg', 'audio/ogg'),
        ('animation', 'animation.mp4', 'video/mp4'),
        ('video_note', 'video-note.mp4', 'video/mp4'),
    ):
        media = message.get(field)
        if isinstance(media, dict) and isinstance(media.get('file_id'), str):
            attachments.append(
                {
                    'source': 'telegram',
                    'file_id': media['file_id'],
                    'filename': str(media.get('file_name') or default_name),
                    'mime_type': str(media.get('mime_type') or default_mime),
                }
            )
    if message_id is None or chat_id is None or user_id is None or not isinstance(text, str):
        if message_id is None or chat_id is None or user_id is None or not attachments:
            return None
        text = ''
    text = text.strip()
    if not text and not attachments:
        return None
    if len(text) > CHANNEL_MAX_INBOUND_LENGTH:
        return None
    payload: Dict[str, Any] = {
        'event_id': str(update_id),
        'message_id': str(message_id),
        'channel_user_id': str(user_id),
        'channel_chat_id': str(chat_id),
        'text': text,
    }
    if attachments:
        payload['attachments'] = attachments
    if str(chat.get('type') if isinstance(chat, dict) else '') in {'group', 'supergroup'}:
        first_name = sender.get('first_name') if isinstance(sender, dict) else None
        last_name = sender.get('last_name') if isinstance(sender, dict) else None
        username = sender.get('username') if isinstance(sender, dict) else None
        sender_name = ' '.join(
            str(value).strip() for value in (first_name, last_name) if isinstance(value, str) and value.strip()
        )
        payload['sender_name'] = sender_name or (
            f'@{username}' if isinstance(username, str) and username else str(user_id)
        )
    return payload


def parse_sendblue_inbound(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if body.get('is_outbound') is True:
        return None
    message_handle = body.get('message_handle')
    sender = body.get('from_number')
    if not isinstance(message_handle, str) or not message_handle:
        return None
    if not isinstance(sender, str) or not sender or len(sender) > 254:
        return None
    text = body.get('content')
    text = text.strip() if isinstance(text, str) else ''
    media_url = body.get('media_url')
    if not text and not isinstance(media_url, str):
        return None
    if len(text) > CHANNEL_MAX_INBOUND_LENGTH:
        return None
    group_id = body.get('group_id')
    chat_id = group_id.strip() if isinstance(group_id, str) else ''
    payload: Dict[str, Any] = {
        'event_id': message_handle,
        'channel_user_id': sender,
        'channel_chat_id': chat_id or sender,
        'text': text,
    }
    if isinstance(media_url, str) and media_url.strip():
        payload['attachments'] = [
            {
                'source': 'imessage',
                'url': media_url.strip(),
                'filename': 'attachment',
                'mime_type': str(body.get('media_type') or 'application/octet-stream'),
            }
        ]
    return payload


def parse_twilio_sms_inbound(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    message_sid = body.get('MessageSid')
    sender = body.get('From')
    recipient = body.get('To')
    text = body.get('Body')
    if not isinstance(message_sid, str) or not message_sid:
        return None
    if not isinstance(sender, str) or not sender or len(sender) > 254:
        return None
    if not isinstance(recipient, str) or not recipient or len(recipient) > 254:
        return None
    text = text.strip() if isinstance(text, str) else ''
    media_count = body.get('NumMedia')
    try:
        media_count_value = max(0, min(10, int(media_count or 0)))
    except (TypeError, ValueError):
        media_count_value = 0
    attachments = []
    for index in range(media_count_value):
        media_url = body.get(f'MediaUrl{index}')
        if isinstance(media_url, str) and media_url.strip():
            attachments.append(
                {
                    'source': 'twilio',
                    'url': media_url.strip(),
                    'filename': f'attachment-{index + 1}',
                    'mime_type': str(body.get(f'MediaContentType{index}') or 'application/octet-stream'),
                }
            )
    if not text and attachments:
        text = ''
    if not text or len(text) > CHANNEL_MAX_INBOUND_LENGTH:
        if not attachments:
            return None
    payload: Dict[str, Any] = {
        'event_id': message_sid,
        'message_id': message_sid,
        'channel_user_id': sender,
        'channel_chat_id': sender,
        'text': text,
    }
    if attachments:
        payload['attachments'] = attachments
    return payload


def parse_twilio_conversation_inbound(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if body.get('EventType') != 'onMessageAdded' or body.get('Author') in {'omi', 'system'}:
        return None
    message_sid = body.get('MessageSid')
    conversation_sid = body.get('ConversationSid')
    author = body.get('Author')
    text = body.get('Body')
    if not isinstance(message_sid, str) or not message_sid:
        return None
    if not isinstance(conversation_sid, str) or not conversation_sid:
        return None
    if not isinstance(author, str) or not author:
        return None
    if len(message_sid) > 128 or len(conversation_sid) > 128 or len(author) > 254:
        return None
    text = text.strip() if isinstance(text, str) else ''
    if len(text) > CHANNEL_MAX_INBOUND_LENGTH:
        return None
    media = body.get('Media')
    if isinstance(media, str):
        try:
            media = json.loads(media)
        except (TypeError, ValueError):
            media = []
    attachments: List[Dict[str, Any]] = []
    if isinstance(media, list):
        for item in media[:10]:
            if not isinstance(item, dict):
                continue
            media_sid = item.get('Sid') or item.get('sid')
            media_url = item.get('Url') or item.get('url')
            service_sid = body.get('ChatServiceSid') or item.get('ServiceSid') or item.get('service_sid')
            if not isinstance(media_url, str) and isinstance(media_sid, str) and isinstance(service_sid, str):
                media_url = f'https://mcs.us1.twilio.com/v1/Services/{service_sid}/Media/{media_sid}'
            if not isinstance(media_url, str) or not media_url.strip():
                continue
            mime_type = item.get('ContentType') or item.get('content_type') or 'application/octet-stream'
            filename = item.get('Filename') or item.get('file_name') or 'attachment'
            attachments.append(
                {
                    'source': 'twilio',
                    'url': media_url.strip(),
                    'filename': str(filename),
                    'mime_type': str(mime_type),
                }
            )
    if not text and not attachments:
        return None
    payload: Dict[str, Any] = {
        'event_id': message_sid,
        'message_id': message_sid,
        'channel_user_id': author,
        'channel_chat_id': conversation_sid,
        'text': text,
        'provider_mode': 'twilio_conversations',
        'sender_name': author,
    }
    if attachments:
        payload['attachments'] = attachments
    return payload


def parse_channel_command(text: str) -> Optional[Tuple[str, str]]:
    if not text.startswith('/'):
        return None
    parts = text.split()
    head = parts[0].split('@', 1)[0].lower()
    return head, ' '.join(parts[1:]).strip()


def normalize_link_token(value: str) -> Optional[str]:
    token = ''.join(value.split()).lower()
    return token if LINK_TOKEN_PATTERN.fullmatch(token) else None


def sanitize_channel_reply(channel: str, text: str) -> str:
    value = text.strip()
    value = re.sub(r'```(?:[^\n]*)\n?(.*?)```', '', value, flags=re.DOTALL)
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', value)
    value = re.sub(r'^\s{0,3}#{1,6}\s+', '', value, flags=re.MULTILINE)
    value = re.sub(r'^\s*(?:[-*+]\s+|\d+\.\s+)', '', value, flags=re.MULTILINE)
    for marker in ('**', '__', '*', '_', '`'):
        value = re.sub(re.escape(marker) + r'([^' + re.escape(marker[0]) + r']+)' + re.escape(marker), r'\1', value)
    value = re.sub(r'\n{3,}', '\n\n', value).strip()
    limit = CHANNEL_MAX_REPLY_LENGTH[channel]
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + '…'
    return value or 'I could not generate a reply. Please try again.'


def link_instructions(channel: str, token: str, expires_at: datetime) -> str:
    expires = expires_at.astimezone(timezone.utc).strftime('%H:%M UTC')
    if channel == 'telegram':
        target = 'the Omi Telegram bot'
    elif channel == 'imessage':
        target = 'your Omi iMessage number'
    else:
        target = 'your Omi SMS number'
    return f'Send /start {token} to {target}. This code expires at {expires} and works once.'


def channel_sign_in_text(channel: str, token: str, expires_at: datetime) -> str:
    from urllib.parse import urlencode

    expires = expires_at.astimezone(timezone.utc).strftime('%H:%M UTC')
    sign_in_base_url = (_setting('CHANNEL_SIGN_IN_URL') or 'https://app.omi.me/login').rstrip('/')
    sign_in_url = sign_in_base_url + '?' + urlencode({'channel': channel, 'code': token})
    return (
        f"This chat isn't linked to Omi yet. Sign in here to connect it: {sign_in_url} "
        f'(the link expires at {expires}). If you prefer, send /start {token} after signing in.'
    )


def _persist_human_and_history(uid: str, channel: str, text: str) -> Tuple[List[Message], Optional[Any], str]:
    session_data = chat_db.get_chat_session(uid, app_id=None)
    chat_session = None
    session_id = ''
    if session_data:
        chat_session = ChatSession(**session_data)
        session_id = chat_session.id
    message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.human,
        app_id=None,
        from_external_integration=True,
        type=MessageType.text,
        chat_session_id=session_id or None,
        message_source=f'channel:{channel}',
    )
    chat_db.add_message(uid, message.model_dump())
    if session_id:
        chat_db.add_message_to_chat_session(uid, session_id, message.id)
    raw_messages = chat_db.get_cache_aligned_messages(uid, app_id=None, chat_session_id=session_id or None)
    messages = list(reversed(Message.deserialize_many_safe(raw_messages)))
    return messages, chat_session, message.id


async def generate_channel_reply(
    uid: str, channel: str, text: str, *, attachments: Optional[List[Dict[str, Any]]] = None
) -> str:
    media_context = await build_media_context(uid, attachments or [])
    if media_context:
        text = f'{text}\n\n{media_context}'.strip()
    await run_blocking(db_executor, enforce_chat_quota, uid, platform=channel)
    messages, chat_session, message_id = await run_blocking(db_executor, _persist_human_and_history, uid, channel, text)
    await run_blocking(
        db_executor,
        llm_usage_db.record_chat_quota_question,
        uid,
        idempotency_key=f'channel:{channel}:{message_id}',
        source=f'channel:{channel}',
        message_id=message_id,
        chat_session_id=chat_session.id if chat_session else None,
        platform=channel,
    )
    callback_data: Dict[str, Any] = {}
    usage_token = set_usage_context(uid, Features.CHAT)
    try:
        async for _ in execute_chat_stream(
            uid,
            messages,
            app=None,
            cited=True,
            callback_data=callback_data,
            chat_session=chat_session,
            platform=channel,
        ):
            pass
    finally:
        reset_usage_context(usage_token)
    response = callback_data.get('answer')
    if not isinstance(response, str) or not response.strip():
        raise ChannelProviderError('core chat returned no answer')
    cited_conversation_idxs = {int(index) for index in re.findall(r'\[(\d+)\]', response)}
    if cited_conversation_idxs:
        response = re.sub(r'\[\d+\]', '', response)
    memories = callback_data.get('memories_found', [])
    memories = [memories[index - 1] for index in cited_conversation_idxs if 0 < index <= len(memories)]
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=response,
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        app_id=None,
        from_external_integration=True,
        type=MessageType.text,
        memories_id=extract_memory_ids(memories) if memories else [],
        chat_session_id=chat_session.id if chat_session else None,
        message_source=f'channel:{channel}',
        langsmith_run_id=callback_data.get('langsmith_run_id'),
        prompt_name=callback_data.get('prompt_name'),
        prompt_commit=callback_data.get('prompt_commit'),
    )
    await run_blocking(db_executor, chat_db.add_message, uid, ai_message.model_dump())
    if chat_session:
        await run_blocking(db_executor, chat_db.add_message_to_chat_session, uid, chat_session.id, ai_message.id)
    return response


async def send_channel_message(
    channel: str,
    channel_chat_id: str,
    text: str,
    *,
    is_group: bool = False,
    provider_mode: Optional[str] = None,
) -> None:
    client = get_webhook_client()
    if channel == 'telegram':
        token = _setting('TELEGRAM_BOT_TOKEN')
        if not token:
            raise ChannelProviderError('Telegram credentials are not configured')
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        response = await client.post(url, json={'chat_id': channel_chat_id, 'text': text})
    elif channel == 'imessage':
        key_id = _setting('SENDBLUE_API_KEY_ID') or _setting('SENDBLUE_API_KEY')
        key_secret = _setting('SENDBLUE_API_KEY_SECRET') or _setting('SENDBLUE_SECRET_KEY')
        from_number = _setting('SENDBLUE_NUMBER')
        if not key_id or not key_secret or not from_number:
            raise ChannelProviderError('Sendblue credentials are not configured')
        endpoint = (
            'https://api.sendblue.com/api/send-group-message'
            if is_group
            else 'https://api.sendblue.com/api/send-message'
        )
        body = (
            {'group_id': channel_chat_id, 'from_number': from_number, 'content': text}
            if is_group
            else {'number': channel_chat_id, 'from_number': from_number, 'content': text}
        )
        response = await client.post(
            endpoint,
            headers={
                'sb-api-key-id': key_id,
                'sb-api-secret-key': key_secret,
                'content-type': 'application/json',
            },
            json=body,
        )
    elif provider_mode == 'twilio_conversations':
        account_sid = _setting('TWILIO_ACCOUNT_SID')
        auth_token = _setting('TWILIO_AUTH_TOKEN')
        if not account_sid or not auth_token or not re.fullmatch(r'CH[0-9a-fA-F]{32}', channel_chat_id):
            raise ChannelProviderError('Twilio Conversations credentials or conversation ID are not configured')
        url = f'https://conversations.twilio.com/v1/Conversations/{channel_chat_id}/Messages'
        response = await client.post(
            url,
            auth=(account_sid, auth_token),
            data={'Body': text},
        )
    else:
        try:
            await run_blocking(critical_executor, send_sms, channel_chat_id, text)
        except Exception as exc:
            raise ChannelProviderError('Twilio SMS delivery failed') from exc
        return
    if response.status_code < 200 or response.status_code >= 300:
        raise ChannelProviderError(f'{channel} provider returned HTTP {response.status_code}')
