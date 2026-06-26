"""
Telethon-based Telegram integration for AI Clone.

Uses MTProto (the official Telegram protocol) to connect to the user's
*personal* Telegram account — not a bot. Messages from real contacts
arrive and replies are sent as the actual user.

Requires env vars:
  TELEGRAM_API_ID   — from https://my.telegram.org/apps
  TELEGRAM_API_HASH — from https://my.telegram.org/apps
"""

import datetime
import logging
import os

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User

import database.ai_clone as clone_db
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

API_ID = int(os.environ.get('TELEGRAM_API_ID', '0') or '0')
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')

# In-memory client cache: uid -> authenticated TelegramClient
_clients: dict[str, TelegramClient] = {}
# Pending clients waiting for OTP verification: phone -> TelegramClient
_pending_clients: dict[str, TelegramClient] = {}


def _get_session_string(uid: str) -> str | None:
    settings = clone_db.get_platform_settings(uid, 'telegram') or {}
    return settings.get('session_string')


def _save_session_string(uid: str, session_string: str, display_name: str, phone: str) -> None:
    clone_db.update_platform_settings(
        uid,
        'telegram',
        {
            'connected': True,
            'session_string': session_string,
            'display_name': display_name,
            'phone': phone,
        },
    )


async def get_client(uid: str) -> TelegramClient | None:
    """Return an authenticated TelegramClient for this user, or None if not connected."""
    if not API_ID or not API_HASH:
        logger.warning('TELEGRAM_API_ID / TELEGRAM_API_HASH not configured')
        return None

    if uid in _clients:
        client = _clients[uid]
        if client.is_connected():
            return client
        # reconnect
        await client.connect()
        if await client.is_user_authorized():
            return client
        del _clients[uid]

    session_str = await run_blocking(db_executor, _get_session_string, uid)
    if not session_str:
        return None

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        del _clients[uid]
        return None

    _clients[uid] = client
    return client


async def send_code(phone: str) -> dict:
    """
    Start phone auth — sends an OTP to the user's Telegram app.
    Returns a phone_code_hash needed for verify_code().
    """
    if not API_ID or not API_HASH:
        raise RuntimeError('TELEGRAM_API_ID / TELEGRAM_API_HASH not set')

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    result = await client.send_code_request(phone)

    # Stash the temporary client keyed by phone so verify_code can reuse it
    _pending_clients[phone] = client
    return {'phone_code_hash': result.phone_code_hash}


async def verify_code(uid: str, phone: str, code: str, phone_code_hash: str) -> dict:
    """
    Complete phone auth. On success, saves session to Firestore and caches client.
    Returns {'display_name': str, 'phone': str}.
    """
    client = _pending_clients.pop(phone, None)
    if client is None:
        # Re-create if the server restarted between send_code and verify_code
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()

    await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)

    me: User = await client.get_me()
    display_name = ' '.join(filter(None, [me.first_name, me.last_name])) or me.username or phone
    session_str = client.session.save()

    await run_blocking(db_executor, _save_session_string, uid, session_str, display_name, phone)
    _clients[uid] = client

    return {'display_name': display_name, 'phone': phone}


async def disconnect(uid: str) -> None:
    """Revoke session and remove from cache."""
    client = _clients.pop(uid, None)
    if client:
        try:
            await client.log_out()
        except Exception:
            pass

    await run_blocking(
        db_executor,
        clone_db.update_platform_settings,
        uid,
        'telegram',
        {
            'connected': False,
            'session_string': None,
        },
    )


async def send_message(uid: str, chat_id: int, text: str) -> bool:
    """Send a reply as the authenticated user. Returns True on success."""
    client = await get_client(uid)
    if not client:
        return False
    try:
        await client.send_message(chat_id, text)
        return True
    except Exception as e:
        logger.error(f'Telegram send error for uid={uid}: {e}')
        return False


async def poll_new_messages(uid: str, after_timestamp: float) -> list[dict]:
    """
    Fetch private messages newer than after_timestamp (Unix epoch).
    Returns list of {sender, sender_id, chat_id, message, timestamp}.
    """
    client = await get_client(uid)
    if not client:
        return []

    results = []
    cutoff = datetime.datetime.fromtimestamp(after_timestamp, tz=datetime.timezone.utc)

    async for dialog in client.iter_dialogs():
        # Only private (person-to-person) chats
        if not dialog.is_user:
            continue
        entity = dialog.entity
        if getattr(entity, 'bot', False):
            continue  # skip bots

        async for msg in client.iter_messages(dialog, limit=5):
            if msg.date <= cutoff:
                break
            if msg.out or not msg.message:
                continue  # skip sent messages and non-text
            sender_name = (
                ' '.join(
                    filter(
                        None,
                        [
                            getattr(entity, 'first_name', None),
                            getattr(entity, 'last_name', None),
                        ],
                    )
                )
                or getattr(entity, 'username', None)
                or str(dialog.id)
            )

            results.append(
                {
                    'sender': sender_name,
                    'sender_id': dialog.id,
                    'chat_id': dialog.id,
                    'message': msg.message,
                    'timestamp': msg.date.timestamp(),
                }
            )

    return results
