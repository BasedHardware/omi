"""Sign outbound webhook deliveries and verify them on the receiving side (#20939).

A webhook request carries no proof that Omi sent it, so receivers have been trusting the
``uid`` in the query string or body. When a destination has a signing secret, every delivery
now carries three headers:

    X-Omi-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256>[,v1=<hex for the previous secret>]
    X-Omi-Event:     <webhook type, e.g. memory_created>
    X-Omi-Delivery:  <delivery id; the same value as Idempotency-Key>

The signed string is ``"<t>.<uid>." + body``: the timestamp in decimal ASCII, a dot, the ``uid``
Omi appended to the query string (the decoded value, UTF-8), a dot, then exactly the body bytes
on the wire. Binding ``uid`` matters because most bodies do not carry it: without it a captured
delivery could be replayed inside the tolerance window with ``?uid=<someone else>``. Every
delivery Omi sends today has a ``uid``; a future event without one signs with an empty segment
(``"<t>.."``). During a rotation grace window the header carries one ``v1`` per still-valid
secret, so a receiver that has switched to the new secret and one that has not both verify.

Everything from ``compute_signature`` down to ``verify`` is the receiver-side contract and has
no Omi dependencies, so the plugin SDK can carry an identical copy. The ``signed_*`` helpers at
the end are the sender side used by ``utils/webhooks.py`` and ``utils/app_integrations.py``.
"""

import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Iterable, Mapping, Optional, Sequence

SIGNATURE_HEADER = 'X-Omi-Signature'
EVENT_HEADER = 'X-Omi-Event'
DELIVERY_HEADER = 'X-Omi-Delivery'
SIGNATURE_VERSION = 'v1'
SECRET_PREFIX = 'whsec_'
DEFAULT_TOLERANCE_SECONDS = 300


def generate_secret() -> str:
    """A new signing secret: 32 random bytes, URL-safe, with a recognisable prefix."""
    return SECRET_PREFIX + secrets.token_urlsafe(32)


def encode_json_body(payload: Any) -> bytes:
    """Serialize a JSON payload exactly the way httpx encodes ``json=``.

    Signing needs the body bytes before the request is built, and the bytes we sign must be
    the bytes we send, so the payload is serialized once here and sent as ``content=``.
    Matching httpx's encoding keeps signed and unsigned bodies byte-identical.
    """
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def compute_signature(secret: str, timestamp: int, uid: str, body: bytes) -> str:
    message = f'{timestamp}.{uid}.'.encode('utf-8') + bytes(body)
    return hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()


def sign(body: bytes, signing_secrets: Sequence[str], *, uid: str, timestamp: Optional[int] = None) -> str:
    """Build the ``X-Omi-Signature`` value: ``t=<ts>`` then one ``v1=`` per secret, current first."""
    if not signing_secrets:
        raise ValueError('at least one signing secret is required')
    ts = int(time.time()) if timestamp is None else int(timestamp)
    parts = [f't={ts}']
    parts.extend(f'{SIGNATURE_VERSION}={compute_signature(secret, ts, uid, body)}' for secret in signing_secrets)
    return ','.join(parts)


def parse_signature_header(value: str) -> tuple[Optional[int], list[str]]:
    """Split a header value into its timestamp and the list of ``v1`` signatures.

    Unknown keys are ignored so a future ``v2`` scheme does not break ``v1`` receivers.
    A missing or non-integer timestamp comes back as ``None``.
    """
    timestamp: Optional[int] = None
    signatures: list[str] = []
    for part in value.split(','):
        key, sep, item = part.strip().partition('=')
        if not sep:
            continue
        if key == 't':
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


def verify(
    headers: Mapping[str, str],
    body: object,
    secret: str,
    *,
    uid: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """True when ``X-Omi-Signature`` signs ``body`` for ``uid`` with ``secret`` and is fresh.

    ``body`` must be the raw request bytes (``bytes``, ``bytearray`` or ``memoryview``); it is
    typed ``object`` so that a ``str`` from a receiver that parsed and re-serialized the JSON is
    refused at runtime instead of hashing bytes that never matched the wire. ``uid`` is the value
    from the request's query string. A timestamp more than ``tolerance_seconds`` away from
    ``now`` in either direction is rejected so a captured delivery cannot be replayed later. The
    comparison is constant-time and runs on bytes, so a hostile non-ASCII header is a clean
    ``False`` rather than an exception.
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
    expected = compute_signature(secret, timestamp, uid, raw).encode('utf-8')
    return any(hmac.compare_digest(expected, candidate.encode('utf-8')) for candidate in signatures)


# --- sender side -------------------------------------------------------------------------------


def signature_headers(
    body: bytes,
    signing_secrets: Sequence[str],
    *,
    uid: str,
    event: str,
    delivery_id: str,
    timestamp: Optional[int] = None,
) -> dict[str, str]:
    return {
        SIGNATURE_HEADER: sign(body, signing_secrets, uid=uid, timestamp=timestamp),
        EVENT_HEADER: event,
        DELIVERY_HEADER: delivery_id,
    }


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    return _header(headers, name) is not None


def prepare_signed_body(request_kwargs: dict[str, Any], headers: dict[str, str]) -> bytes:
    """Fix the body bytes of a delivery that is about to be signed.

    A ``json=`` payload is serialized once and moved to ``content=`` so the signed bytes are the
    sent bytes; httpx would otherwise re-encode it per request. ``Content-Type`` is set the way
    httpx would have set it for ``json=``. A ``content=`` body is returned as-is.
    """
    if 'json' in request_kwargs:
        body = encode_json_body(request_kwargs.pop('json'))
        request_kwargs['content'] = body
        if not _has_header(headers, 'Content-Type'):
            headers['Content-Type'] = 'application/json'
        return body
    body = bytes(request_kwargs.get('content') or b'')
    request_kwargs['content'] = body
    return body


def signed_body_kwargs(
    signing_secrets: Optional[Iterable[str]],
    headers: dict[str, str],
    *,
    uid: str,
    event: str,
    delivery_id: str,
    json_payload: Any = None,
    content: Optional[bytes] = None,
    timestamp: Optional[int] = None,
) -> dict[str, Any]:
    """Body kwargs for one ``client.post`` call, adding signature headers when there is a secret.

    ``uid`` must be the value the caller put in the request's ``uid`` query parameter. Without a
    secret the body goes out exactly as before (``json=`` or ``content=``) and ``headers`` is
    left untouched, so destinations that never opted in see no change.
    """
    active = list(signing_secrets or ())
    if not active:
        return {'content': content} if content is not None else {'json': json_payload}
    request_kwargs: dict[str, Any] = {'content': content} if content is not None else {'json': json_payload}
    body = prepare_signed_body(request_kwargs, headers)
    headers.update(signature_headers(body, active, uid=uid, event=event, delivery_id=delivery_id, timestamp=timestamp))
    return request_kwargs
