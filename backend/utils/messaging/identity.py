"""Pure, stable provider identity keys shared by storage and admission."""

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


def coerce_utc_datetime(value: Any) -> datetime | None:
    """Coerce a datetime or ISO timestamp string to a timezone-aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def key(*parts):
    return sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()


def advances_inbound_head(message, prior):
    """Provider time orders messages; Telegram IDs resolve its one-second clock ties."""
    if message.callback_id:
        return False
    before = coerce_utc_datetime(prior.get('received_at'))
    if before is None or message.received_at > before:
        return True
    if message.received_at < before:
        return False
    current_id, prior_id = message.provider_message_id, prior.get('provider_message_id', '')
    if message.channel == 'telegram' and current_id.isdecimal() and prior_id.isdecimal():
        return int(current_id) > int(prior_id)
    return current_id != prior_id  # other equal-clock messages use admission order
