"""Pure, stable provider identity keys shared by storage and admission."""

from datetime import datetime, timezone
import json
from hashlib import sha256


def coerce_utc_datetime(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    return None


def key(*parts):
    return sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()


def advances_inbound_head(message, prior):
    """Provider time orders messages; Telegram IDs resolve its one-second clock ties."""
    if message.callback_id:
        return False
    before = coerce_utc_datetime(prior.get('received_at'))
    received_at = coerce_utc_datetime(message.received_at)
    if before is None or (received_at is not None and received_at > before):
        return True
    if received_at is not None and received_at < before:
        return False
    current_id, prior_id = message.provider_message_id, prior.get('provider_message_id', '')
    if message.channel == 'telegram' and current_id.isdecimal() and prior_id.isdecimal():
        return int(current_id) > int(prior_id)
    return current_id != prior_id  # other equal-clock messages use admission order
