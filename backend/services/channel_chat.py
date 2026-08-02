import hmac
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


def parse_telegram_update(body: Dict[str, Any]) -> Optional[Dict[str, str]]:
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
    text = message.get('text')
    if message_id is None or chat_id is None or user_id is None or not isinstance(text, str):
        return None
    text = text.strip()
    if not text or len(text) > CHANNEL_MAX_INBOUND_LENGTH:
        return None
    return {
        'event_id': str(update_id),
        'message_id': str(message_id),
        'channel_user_id': str(user_id),
        'channel_chat_id': str(chat_id),
        'text': text,
    }


def parse_sendblue_inbound(body: Dict[str, Any]) -> Optional[Dict[str, str]]:
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
    return {
        'event_id': message_handle,
        'channel_user_id': sender,
        'channel_chat_id': chat_id or sender,
        'text': text or 'I received an attachment, but I cannot read it yet.',
    }


def parse_twilio_sms_inbound(body: Dict[str, Any]) -> Optional[Dict[str, str]]:
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
    if not text and media_count not in {'0', 0, None}:
        text = 'I received an attachment, but I cannot read it yet.'
    if not text or len(text) > CHANNEL_MAX_INBOUND_LENGTH:
        return None
    return {
        'event_id': message_sid,
        'message_id': message_sid,
        'channel_user_id': sender,
        'channel_chat_id': sender,
        'text': text,
    }


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
    sign_in_url = 'https://omi.me/login?' + urlencode({'channel': channel, 'code': token})
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


async def generate_channel_reply(uid: str, channel: str, text: str) -> str:
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


async def send_channel_message(channel: str, channel_chat_id: str, text: str) -> None:
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
        response = await client.post(
            'https://api.sendblue.com/api/send-message',
            headers={
                'sb-api-key-id': key_id,
                'sb-api-secret-key': key_secret,
                'content-type': 'application/json',
            },
            json={'number': channel_chat_id, 'from_number': from_number, 'content': text},
        )
    else:
        try:
            await run_blocking(critical_executor, send_sms, channel_chat_id, text)
        except Exception as exc:
            raise ChannelProviderError('Twilio SMS delivery failed') from exc
        return
    if response.status_code < 200 or response.status_code >= 300:
        raise ChannelProviderError(f'{channel} provider returned HTTP {response.status_code}')
