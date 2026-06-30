"""
Telegram Bot API integration for AI Clone.

Each Omi user creates a bot via @BotFather, pastes the token into the desktop
app, and Omi registers a per-user webhook so Telegram delivers incoming DMs
directly to the backend. Replies are sent via the Bot API.

Per-user bot token is stored in:
  users/{uid}/ai_clone/settings.platforms.telegram.bot_token

Env vars:
  TELEGRAM_BOT_API_BASE — override to use a self-hosted Bot API server
                          (defaults to https://api.telegram.org)
"""

import logging
import os

import httpx

import database.ai_clone as clone_db
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

BOT_API_BASE = os.environ.get('TELEGRAM_BOT_API_BASE', 'https://api.telegram.org')


def _bot_url(token: str, method: str) -> str:
    return f'{BOT_API_BASE}/bot{token}/{method}'


def _get_bot_token(uid: str) -> str | None:
    settings = clone_db.get_platform_settings(uid, 'telegram') or {}
    return settings.get('bot_token')


async def connect(uid: str, bot_token: str, webhook_url: str) -> dict:
    """
    Validate bot_token with Telegram, register the per-user webhook, persist settings.
    Returns {'bot_username': str, 'bot_name': str}.
    Raises ValueError('invalid_bot_token') if the token is rejected by Telegram.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        me_resp = await client.get(_bot_url(bot_token, 'getMe'))
        if me_resp.status_code != 200:
            raise ValueError('invalid_bot_token')
        me = me_resp.json().get('result', {})

        wh_resp = await client.post(
            _bot_url(bot_token, 'setWebhook'),
            json={'url': webhook_url, 'allowed_updates': ['message']},
        )
        wh_resp.raise_for_status()

    await run_blocking(
        db_executor,
        clone_db.update_platform_settings,
        uid,
        'telegram',
        {
            'connected': True,
            'bot_token': bot_token,
            'bot_username': me.get('username', ''),
            'bot_name': me.get('first_name', ''),
        },
    )
    return {'bot_username': me.get('username', ''), 'bot_name': me.get('first_name', '')}


async def disconnect(uid: str) -> None:
    """Remove the Telegram webhook and clear stored settings."""
    token = await run_blocking(db_executor, _get_bot_token, uid)
    if token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(_bot_url(token, 'deleteWebhook'))
        except Exception:
            pass
    await run_blocking(
        db_executor,
        clone_db.update_platform_settings,
        uid,
        'telegram',
        {'connected': False, 'bot_token': None},
    )


async def send_message(uid: str, chat_id: int, text: str) -> bool:
    """Send a message via the user's bot token. Returns True on success."""
    token = await run_blocking(db_executor, _get_bot_token, uid)
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _bot_url(token, 'sendMessage'),
                json={'chat_id': chat_id, 'text': text},
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f'Telegram Bot API send error uid={uid}: {e}')
        return False
