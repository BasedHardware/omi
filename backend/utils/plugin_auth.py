"""Backend copy of plugin webhook/tool HMAC signing.

Canonical implementation lives in ``plugins/omi-plugin-sdk``
(``omi_plugin_sdk.auth``). Backend does not depend on that package, so this
module mirrors the algorithm:

    signature = hex(HMAC-SHA256(secret, f"{uid}.{timestamp}.".encode() + body))

Headers: X-Omi-Uid / X-Omi-Timestamp / X-Omi-Signature
Env: OMI_PLUGIN_WEBHOOK_SECRET
"""

from __future__ import annotations

import hmac
import logging
import os
import time
from hashlib import sha256

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = 'X-Omi-Signature'
UID_HEADER = 'X-Omi-Uid'
TIMESTAMP_HEADER = 'X-Omi-Timestamp'
WEBHOOK_SECRET_ENV = 'OMI_PLUGIN_WEBHOOK_SECRET'

_warned_missing_secret = False


def get_plugin_webhook_secret() -> str | None:
    raw = os.getenv(WEBHOOK_SECRET_ENV)
    if raw is None:
        return None
    secret = raw.strip()
    return secret or None


def sign_plugin_payload(*, secret: str, uid: str, timestamp: str, body: bytes = b'') -> str:
    message = f'{uid}.{timestamp}.'.encode('utf-8') + body
    return hmac.new(secret.encode('utf-8'), message, sha256).hexdigest()


def build_plugin_auth_headers(*, secret: str, uid: str, body: bytes = b'') -> dict[str, str]:
    timestamp = str(int(time.time()))
    signature = sign_plugin_payload(secret=secret, uid=uid, timestamp=timestamp, body=body)
    return {
        UID_HEADER: uid,
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: signature,
    }


def maybe_plugin_auth_headers(*, uid: str, body: bytes = b'') -> dict[str, str]:
    """Return signing headers when OMI_PLUGIN_WEBHOOK_SECRET is configured.

    When unset, returns {} and logs a one-time warning. Outbound delivery still
    proceeds (plugins may not all enforce yet); configure the secret in prod.
    """
    global _warned_missing_secret
    secret = get_plugin_webhook_secret()
    if not secret:
        if not _warned_missing_secret:
            logger.warning(
                '%s unset — outbound plugin calls are unsigned; '
                'plugins that enforce omi_plugin_sdk.auth will reject bare uid',
                WEBHOOK_SECRET_ENV,
            )
            _warned_missing_secret = True
        return {}
    return build_plugin_auth_headers(secret=secret, uid=uid, body=body)
