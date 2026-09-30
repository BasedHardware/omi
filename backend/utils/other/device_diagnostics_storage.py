"""Private, bounded support bundles in the already bound private cloud bucket."""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from utils.other import storage

logger = logging.getLogger(__name__)


def save_bundle(uid: Any, bundle: Any) -> str:
    if not isinstance(uid, str):
        raise ValueError("uid must be a string")
    clean_uid = uid.strip()
    if not clean_uid or '/' in clean_uid or '\\' in clean_uid or '..' in clean_uid:
        raise ValueError("Invalid or empty uid")
    if not isinstance(bundle, (bytes, bytearray)):
        raise TypeError("bundle must be bytes")

    ticket = secrets.token_hex(6).upper()
    bucket = storage.get_private_cloud_sync_bucket()
    path = f'diagnostics/{clean_uid}/{ticket}.json'
    # The ticket lookup is private too. Neither object is served as a public URL.
    with storage.owner_storage_write_gate(clean_uid, bucket):
        bucket.blob(path).upload_from_string(bundle, content_type='application/json')
        bucket.blob(f'diagnostics/tickets/{ticket}.json').upload_from_string(
            json.dumps({'uid': clean_uid, 'path': path}), content_type='application/json'
        )
    return ticket


def read_bundle(ticket: Any) -> dict[str, Any] | None:
    if not isinstance(ticket, str):
        return None
    clean_ticket = ticket.strip().upper()
    if not clean_ticket:
        return None

    try:
        bucket = storage.get_private_cloud_sync_bucket()
        lookup = bucket.blob(f'diagnostics/tickets/{clean_ticket}.json')
        if not lookup.exists():
            return None
        raw_lookup = lookup.download_as_bytes()
        reference = json.loads(raw_lookup)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Corrupt diagnostics ticket lookup for ticket=%s: %s", clean_ticket, exc)
        return None

    if not isinstance(reference, dict):
        return None
    uid = reference.get('uid')
    path = reference.get('path')
    if not isinstance(uid, str) or not isinstance(path, str):
        return None
    clean_uid = uid.strip()
    if not clean_uid:
        return None

    expected_prefix = f'diagnostics/{clean_uid}/'
    expected_suffix = f'/{clean_ticket}.json'
    if not path.startswith(expected_prefix) or not path.endswith(expected_suffix) or '..' in path:
        return None

    try:
        blob = bucket.blob(path)
        if not blob.exists():
            return None
        raw_bundle = blob.download_as_bytes()
        payload = json.loads(raw_bundle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Corrupt diagnostics bundle payload for ticket=%s: %s", clean_ticket, exc)
        return None

    if not isinstance(payload, dict):
        return None
    return payload
