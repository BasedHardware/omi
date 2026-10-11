"""Messaging rollout is off unless both the switch and exact uid cohort admit it."""

import json
import os
from urllib.parse import quote


def cohort_enabled(uid):
    return os.getenv('OMI_MESSAGING_CHANNELS', 'off').lower() == 'on' and uid in {
        value.strip() for value in os.getenv('OMI_MESSAGING_CHANNELS_UIDS', '').split(',') if value.strip()
    }


def public_link_fields(channel, proof):
    """Deep link and public address from server config, keyed by the requested channel.

    ``OMI_MESSAGING_LINK_TARGETS`` is a JSON object. A channel entry may set ``address``
    and ``deep_link_template`` containing ``{proof}``. Missing or malformed config yields
    empty fields so the app can fall back to its flag payload. The proof is URL-encoded
    and never logged here.
    """
    raw = os.getenv('OMI_MESSAGING_LINK_TARGETS', '')
    try:
        targets = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return None, None
    row = targets.get(channel) if isinstance(targets, dict) else None
    if not isinstance(row, dict):
        return None, None
    address = row.get('address')
    address = address.strip() if isinstance(address, str) and address.strip() else None
    template = row.get('deep_link_template')
    deep_link = None
    if isinstance(template, str) and '{proof}' in template and ' ' not in template and len(template) <= 300:
        deep_link = template.replace('{proof}', quote(proof, safe=''))
        if address and '{address}' in deep_link:
            deep_link = deep_link.replace('{address}', quote(address, safe=''))
    return deep_link, address
