"""Verify the ``X-Omi-Signature`` header Omi puts on signed webhook deliveries.

Receiver-side copy of ``backend/utils/webhook_signing.py`` (issue #20939). Keep the two in
step: the signed string is ``"<t>.<uid>." + body``, where ``t`` is the header's unix-second
timestamp, ``uid`` is the value Omi appended to the request's query string (empty if a delivery
has none) and ``body`` is exactly the request bytes. During a secret rotation the header carries
one ``v1=`` per still-valid secret, so verifying against either the new or the previous secret
succeeds for 24 hours.

Standard library only. Typical use::

    body = await request.body()          # raw bytes, never request.json()
    if not verify_signature(request.headers, body, OMI_WEBHOOK_SECRET, uid=uid):
        raise HTTPException(status_code=401)
"""

import hashlib
import hmac
import time
from typing import Mapping, Optional

SIGNATURE_HEADER = "X-Omi-Signature"
EVENT_HEADER = "X-Omi-Event"
DELIVERY_HEADER = "X-Omi-Delivery"
SIGNATURE_VERSION = "v1"
DEFAULT_TOLERANCE_SECONDS = 300


def compute_signature(secret: str, timestamp: int, uid: str, body: bytes) -> str:
    message = f"{timestamp}.{uid}.".encode("utf-8") + bytes(body)
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def parse_signature_header(value: str) -> tuple[Optional[int], list[str]]:
    """Split a header value into its timestamp and the list of ``v1`` signatures.

    Unknown keys are ignored so a future ``v2`` scheme does not break ``v1`` receivers.
    A missing or non-integer timestamp comes back as ``None``.
    """
    timestamp: Optional[int] = None
    signatures: list[str] = []
    for part in value.split(","):
        key, sep, item = part.strip().partition("=")
        if not sep:
            continue
        if key == "t":
            try:
                timestamp = int(item)
            except ValueError:
                return None, []
        elif key == SIGNATURE_VERSION and item:
            signatures.append(item)
    return timestamp, signatures


def _header(headers: Mapping[str, str], name: str) -> Optional[str]:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def verify_signature(
    headers: Mapping[str, str],
    body: object,
    secret: str,
    *,
    uid: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """True when ``X-Omi-Signature`` signs ``body`` for ``uid`` with ``secret`` and is fresh.

    ``body`` must be the raw request bytes (``bytes``, ``bytearray`` or ``memoryview``); a
    ``str`` from a re-serialized JSON object is refused because it never matches the wire bytes.
    ``uid`` is the value from the request's query string. A timestamp more than
    ``tolerance_seconds`` away from ``now`` in either direction is rejected so a captured
    delivery cannot be replayed later. The comparison is constant-time and runs on bytes, so a
    hostile non-ASCII header is a clean ``False`` rather than an exception.
    """
    if not isinstance(body, (bytes, bytearray, memoryview)):
        return False
    raw = bytes(body)
    header = _header(headers, SIGNATURE_HEADER)
    if not header:
        return False
    timestamp, signatures = parse_signature_header(header)
    if timestamp is None or not signatures:
        return False
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        return False
    expected = compute_signature(secret, timestamp, uid, raw).encode("utf-8")
    return any(hmac.compare_digest(expected, candidate.encode("utf-8")) for candidate in signatures)
