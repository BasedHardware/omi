"""Shared HMAC auth for Omi backend → plugin identity.

Canonical copy of the webhook/tool signing scheme. Backend keeps a matching
helper in ``backend/utils/plugin_auth.py`` (backend does not depend on this
package). Algorithm must stay in sync:

    signature = hex(HMAC-SHA256(secret, f"{uid}.{timestamp}.".encode() + body))

Headers:
    X-Omi-Uid / X-Omi-Timestamp / X-Omi-Signature

Bare query/body ``uid`` is an identity *hint*, never authentication.
"""

from __future__ import annotations

import hmac
import os
import time
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

SIGNATURE_HEADER = "X-Omi-Signature"
UID_HEADER = "X-Omi-Uid"
TIMESTAMP_HEADER = "X-Omi-Timestamp"
WEBHOOK_SECRET_ENV = "OMI_PLUGIN_WEBHOOK_SECRET"

_DEFAULT_MAX_AGE_SECONDS = 300


class PluginAuthError(Exception):
    """Raised when plugin request identity cannot be verified."""

    def __init__(self, message: str = "plugin auth failed", *, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_webhook_secret() -> str | None:
    raw = os.getenv(WEBHOOK_SECRET_ENV)
    if raw is None:
        return None
    secret = raw.strip()
    return secret or None


def sign_payload(*, secret: str, uid: str, timestamp: str, body: bytes = b"") -> str:
    if not secret or not uid or not timestamp:
        raise ValueError("secret, uid, and timestamp are required")
    message = f"{uid}.{timestamp}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, sha256).hexdigest()


def verify_payload(
    *,
    secret: str,
    uid: str,
    timestamp: str,
    body: bytes,
    signature: str,
    max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS,
    now: float | None = None,
) -> bool:
    if not secret or not uid or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > max_age_seconds:
        return False
    expected = sign_payload(secret=secret, uid=uid, timestamp=timestamp, body=body)
    return hmac.compare_digest(expected, signature)


def build_auth_headers(*, secret: str, uid: str, body: bytes = b"", now: float | None = None) -> dict[str, str]:
    timestamp = str(int(time.time() if now is None else now))
    signature = sign_payload(secret=secret, uid=uid, timestamp=timestamp, body=body)
    return {
        UID_HEADER: uid,
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: signature,
    }


def _header_get(headers: Mapping[Any, Any], name: str) -> str:
    # Support Starlette/FastAPI Headers (case-insensitive) and plain dicts.
    if hasattr(headers, "get"):
        value = headers.get(name)
        if value is None:
            value = headers.get(name.lower())
        if value is None and hasattr(headers, "get"):
            # brute case variants for plain dicts
            for key in headers:
                if str(key).lower() == name.lower():
                    value = headers[key]
                    break
        return "" if value is None else str(value).strip()
    return ""


def verify_headers(
    *,
    secret: str,
    headers: Mapping[Any, Any],
    body: bytes = b"",
    expected_uid: str | None = None,
    max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS,
    now: float | None = None,
) -> str:
    uid = _header_get(headers, UID_HEADER)
    timestamp = _header_get(headers, TIMESTAMP_HEADER)
    signature = _header_get(headers, SIGNATURE_HEADER)
    if not uid or not timestamp or not signature:
        raise PluginAuthError("missing plugin auth headers")
    if expected_uid is not None and expected_uid.strip() and not hmac.compare_digest(uid, expected_uid.strip()):
        raise PluginAuthError("uid mismatch")
    if not verify_payload(
        secret=secret,
        uid=uid,
        timestamp=timestamp,
        body=body,
        signature=signature,
        max_age_seconds=max_age_seconds,
        now=now,
    ):
        raise PluginAuthError("invalid plugin auth signature")
    return uid


def resolve_authenticated_uid(
    *,
    secret: str | None,
    header_map: Mapping[Any, Any],
    query_uid: str | None,
    body_uid: str | None,
    body: bytes = b"",
    allow_uid_only: bool = False,
    max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS,
    now: float | None = None,
) -> str:
    """Resolve a verified uid for a plugin request.

    When ``secret`` is set, HMAC headers are required. Query/body uid alone is
    never authentication unless ``allow_uid_only`` is explicitly True (legacy
    escape hatch — default False, fail-closed).
    """
    hinted = (query_uid or body_uid or "").strip() or None

    if secret:
        uid = verify_headers(
            secret=secret,
            headers=header_map,
            body=body,
            expected_uid=hinted,
            max_age_seconds=max_age_seconds,
            now=now,
        )
        return uid

    if allow_uid_only:
        if not hinted:
            raise PluginAuthError("uid required")
        return hinted

    raise PluginAuthError("authenticated uid required (uid query/body alone is not auth)")
