from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import database.channels as channels_db
from database.phone_calls import get_primary_phone_number
from utils.phone_registration import start_phone_verification_for_chat


def _uid(config: Optional[RunnableConfig]) -> Optional[str]:
    if not config:
        return None
    configurable = config.get('configurable')
    if not isinstance(configurable, dict):
        return None
    value = configurable.get('user_id')
    return str(value) if value else None


def _channel(value: Optional[str]) -> Optional[str]:
    normalized = value.strip().lower() if value else ''
    return normalized if normalized in channels_db.CHANNELS else None


def _redact_phone(value: str) -> str:
    return value[:2] + '***' + value[-4:] if len(value) > 6 else '***'


@tool
def manage_messaging_channels(
    action: str,
    channel: Optional[str] = None,
    phone_number: Optional[str] = None,
    config: Optional[RunnableConfig] = None,
) -> str:
    """Manage Telegram, iMessage, SMS, and verified phone connections for the user's Omi account.

    Use this tool when the user asks to connect, link, check, or disconnect Telegram, iMessage, or SMS,
    or asks Omi to start registering their own phone number. The phone number must be supplied
    explicitly for start_phone_verification. Never ask for or accept a verification code here.

    Actions:
    - link: issue a short-lived one-time channel link code; requires channel.
    - status: show connected channels and whether a phone is registered.
    - unlink: disconnect one channel; requires channel.
    - start_phone_verification: start the existing phone verification call; requires phone_number.
    """
    uid = _uid(config)
    if not uid:
        return 'I could not identify your Omi account.'
    action = action.strip().lower()
    selected_channel = _channel(channel)
    if channel and not selected_channel:
        return 'Choose Telegram, iMessage, or SMS.'

    if action == 'link':
        if not selected_channel:
            return 'Tell me whether you want to connect Telegram, iMessage, or SMS.'
        token, expires_at = channels_db.issue_link_token(uid, selected_channel)
        if selected_channel == 'telegram':
            return f'Send /start {token} to the Omi Telegram bot. It expires at {expires_at:%H:%M UTC} and works once.'
        target = 'iMessage' if selected_channel == 'imessage' else 'SMS'
        return f'Send /start {token} as a message to the Omi {target} number. It expires at {expires_at:%H:%M UTC} and works once.'

    if action == 'status':
        bindings = channels_db.list_bindings(uid)
        connected = ', '.join(sorted(str(binding['channel']) for binding in bindings)) or 'no messaging channels'
        phone = get_primary_phone_number(uid)
        phone_status = (
            f'phone {_redact_phone(str(phone.get("phone_number", "")))} registered'
            if phone and phone.get('phone_number')
            else 'no phone registered'
        )
        return f'Connected: {connected}; {phone_status}.'

    if action == 'unlink':
        if not selected_channel:
            return 'Tell me whether you want to disconnect Telegram, iMessage, or SMS.'
        count = channels_db.revoke_channel(uid, selected_channel)
        return (
            f'{selected_channel.title()} disconnected.' if count else f'{selected_channel.title()} was not connected.'
        )

    if action == 'start_phone_verification':
        if not phone_number:
            return 'Tell me the phone number to register in international format, for example +15551234567.'
        return start_phone_verification_for_chat(uid, phone_number)

    return 'Use link, status, unlink, or start_phone_verification.'
