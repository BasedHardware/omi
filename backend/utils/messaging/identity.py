"""Pure, stable provider identity keys shared by storage and admission."""

import json
from hashlib import sha256


def key(*parts):
    return sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()


def advances_inbound_head(message, prior):
    """Provider time orders messages; Telegram IDs resolve its one-second clock ties."""
    if message.callback_id:
        return False
    before = prior.get('received_at')
    if before is None or message.received_at > before:
        return True
    if message.received_at < before:
        return False
    current_id, prior_id = message.provider_message_id, prior.get('provider_message_id', '')
    if message.channel == 'telegram' and current_id.isdecimal() and prior_id.isdecimal():
        return int(current_id) > int(prior_id)
    return current_id != prior_id  # other equal-clock messages use admission order
