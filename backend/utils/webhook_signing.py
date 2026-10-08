"""Sign outbound webhooks and chat-tool calls, and verify them on the receiving side (#20939).

A request from Omi to a developer's server carries no proof that Omi sent it, so receivers have
been trusting the ``uid`` in the query string or body. When the destination has a signing secret,
every request now carries three headers:

    X-Omi-Signature: t=<unix seconds>,<scheme>=<hex HMAC-SHA256>[,<scheme>=<hex, previous secret>]
    X-Omi-Event:     <webhook type, e.g. memory_created, or chat_tool>
    X-Omi-Delivery:  <delivery id; for webhooks the same value as Idempotency-Key>

Two schemes share the header and the per-destination secret:

``v1`` signs webhook deliveries. The signed string is ``"<t>.<uid>." + body``: the timestamp in
decimal ASCII, a dot, the ``uid`` Omi appended to the query string (the decoded value, UTF-8), a
dot, then exactly the body bytes on the wire. Binding ``uid`` matters because most bodies do not
carry it: without it a captured delivery could be replayed inside the tolerance window with
``?uid=<someone else>``. Every delivery Omi sends today has a ``uid``; a future event without one
signs with an empty segment (``"<t>.."``).

``v2`` signs chat-tool calls, which differ from webhooks in two ways: a GET tool carries its
arguments in the query string, and one app has many tool URLs under one secret. So ``v2`` binds
the whole request. The signed string is eight parts, the first seven each followed by one LF:

    v2 / <t> / <X-Omi-Delivery> / <X-Omi-Event> / <METHOD> / <canonical path> / <canonical query>

then exactly the body bytes (empty for GET). The literal ``v2`` first line keeps the two schemes
apart: a ``v1`` string starts with digits, so a signature made for one can never verify as the
other under the same secret. Host, scheme and port are not signed. ``uid`` is not a separate
part: it is inside the signed query (GET) or body (POST). See ``canonical_query`` and
``canonical_path`` for the exact encoding.

During a rotation grace window the header carries one signature per still-valid secret, so a
receiver that has switched to the new secret and one that has not both verify.

Everything from ``compute_signature`` down to ``verify_request`` is the receiver-side contract
and has no Omi dependencies, so the plugin SDK can carry an identical copy. The sender side used
by ``utils/webhooks.py``, ``utils/app_integrations.py`` and ``utils/retrieval/tools/app_tools.py``
follows it.
"""

import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Iterable, Mapping, Optional, Sequence, Union
from urllib.parse import parse_qsl, quote, unquote_to_bytes, urlsplit, urlunsplit

import httpx

SIGNATURE_HEADER = 'X-Omi-Signature'
EVENT_HEADER = 'X-Omi-Event'
DELIVERY_HEADER = 'X-Omi-Delivery'
SIGNATURE_VERSION = 'v1'
REQUEST_SIGNATURE_VERSION = 'v2'
CHAT_TOOL_EVENT = 'chat_tool'
SECRET_PREFIX = 'whsec_'
DEFAULT_TOLERANCE_SECONDS = 300

# A query as a receiver has it: the raw query string, or the decoded (name, value) pairs.
QueryInput = Union[str, Iterable[tuple[str, str]]]


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


def _signature_header_value(timestamp: int, version: str, signatures: Iterable[str]) -> str:
    return ','.join([f't={timestamp}', *(f'{version}={signature}' for signature in signatures)])


def sign(body: bytes, signing_secrets: Sequence[str], *, uid: str, timestamp: Optional[int] = None) -> str:
    """Build the ``X-Omi-Signature`` value: ``t=<ts>`` then one ``v1=`` per secret, current first."""
    if not signing_secrets:
        raise ValueError('at least one signing secret is required')
    ts = int(time.time()) if timestamp is None else int(timestamp)
    return _signature_header_value(
        ts, SIGNATURE_VERSION, (compute_signature(secret, ts, uid, body) for secret in signing_secrets)
    )


def _parse_signatures(value: str, version: str) -> tuple[Optional[int], list[str]]:
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
        elif key == version and item:
            signatures.append(item)
    return timestamp, signatures


def parse_signature_header(value: str) -> tuple[Optional[int], list[str]]:
    """Split a header value into its timestamp and the list of ``v1`` signatures.

    Unknown keys (such as ``v2``) are ignored, so each scheme's verifier sees only its own
    signatures. A missing or non-integer timestamp comes back as ``None``.
    """
    return _parse_signatures(value, SIGNATURE_VERSION)


def _header(headers: Mapping[str, str], name: str) -> Optional[str]:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def _is_fresh(timestamp: int, tolerance_seconds: int, now: Optional[float]) -> bool:
    current = time.time() if now is None else now
    return abs(current - timestamp) <= tolerance_seconds


def _matches(expected: str, candidates: Iterable[str]) -> bool:
    # Bytes on both sides: a hostile non-ASCII candidate is a clean mismatch, not a TypeError.
    wanted = expected.encode('utf-8')
    return any(hmac.compare_digest(wanted, candidate.encode('utf-8')) for candidate in candidates)


def verify(
    headers: Mapping[str, str],
    body: object,
    secret: str,
    *,
    uid: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """True when ``X-Omi-Signature`` carries a ``v1`` signature of ``body`` for ``uid`` that is fresh.

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
    if not _is_fresh(timestamp, tolerance_seconds, now):
        return False
    return _matches(compute_signature(secret, timestamp, uid, raw), signatures)


def canonical_query(pairs: Iterable[tuple[str, str]]) -> str:
    """The ``v2`` form of a query: from the decoded (name, value) pairs, in any order.

    Each name and value is UTF-8 encoded, every byte outside ``A-Z a-z 0-9 - . _ ~`` is written
    as ``%XX`` with uppercase hex (so space is ``%20`` and ``+`` is ``%2B``), the pairs are
    sorted by encoded name with a stable sort (repeated names keep their order, so a reordered
    list argument is a different request), and joined as ``name=value`` with ``&``. No Unicode
    normalisation is applied. A value that is not encodable (a lone surrogate) raises
    ``UnicodeEncodeError``.
    """
    encoded = [(quote(name, safe=''), quote(value, safe='')) for name, value in pairs]
    encoded.sort(key=lambda pair: pair[0])
    return '&'.join(f'{name}={value}' for name, value in encoded)


def canonical_path(path: str) -> str:
    """The ``v2`` form of a path: each ``/``-separated segment percent-decoded, then re-encoded.

    Uses the same byte rule as ``canonical_query``, so ``/tools/%7euser`` and ``/tools/~user``
    are the same path, and a decoded path (what most frameworks hand you) gives the same result
    as the raw one whenever the path has no encoded ``/`` or ``%``. An empty path is ``/``.
    """
    if not path:
        return '/'
    return '/'.join(quote(unquote_to_bytes(segment), safe='') for segment in path.split('/'))


def _query_pairs(query: QueryInput) -> list[tuple[str, str]]:
    if isinstance(query, str):
        return parse_qsl(query, keep_blank_values=True)
    return [(name, value) for name, value in query]


def request_string_to_sign(
    *,
    timestamp: int,
    delivery_id: str,
    event: str,
    method: str,
    path: str,
    query: QueryInput,
    body: bytes,
) -> bytes:
    """The exact bytes a ``v2`` signature covers (see the module docstring).

    ``query`` is the raw query string or its decoded pairs. Raises ``ValueError`` when a header
    part could break the line framing (CR, LF, non-ASCII or empty), and ``UnicodeEncodeError``
    for an unencodable query or path, so a malformed request can never be signed or verified.
    """
    header_parts = (delivery_id, event, method)
    if any(not part or not part.isascii() or not part.isprintable() for part in header_parts):
        raise ValueError('delivery id, event and method must be non-empty printable ASCII')
    lines = (
        REQUEST_SIGNATURE_VERSION,
        str(int(timestamp)),
        delivery_id,
        event,
        method.upper(),
        canonical_path(path),
        canonical_query(_query_pairs(query)),
    )
    return ''.join(f'{line}\n' for line in lines).encode('ascii') + bytes(body)


def compute_request_signature(
    secret: str,
    *,
    timestamp: int,
    delivery_id: str,
    event: str,
    method: str,
    path: str,
    query: QueryInput,
    body: bytes,
) -> str:
    """Hex ``v2`` signature; useful to build a signed request when testing your own endpoint."""
    message = request_string_to_sign(
        timestamp=timestamp, delivery_id=delivery_id, event=event, method=method, path=path, query=query, body=body
    )
    return hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()


def verify_request(
    headers: Mapping[str, str],
    body: object,
    secret: str,
    *,
    method: str,
    path: str,
    query: QueryInput,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """True when ``X-Omi-Signature`` carries a fresh ``v2`` signature of this exact request.

    Pass what the request arrived with: ``method``, the request ``path`` (the path Omi called;
    behind a proxy that rewrites paths, the public path), the ``query`` as the raw query string
    or the decoded pairs, and the raw ``body`` bytes (empty for GET). ``X-Omi-Delivery`` and
    ``X-Omi-Event`` are read from ``headers`` and are covered by the signature, so remembering
    delivery ids for the tolerance window rejects replays. A ``v1`` signature never satisfies
    this check. Malformed input of any kind is ``False``, never an exception.
    """
    if not isinstance(body, (bytes, bytearray, memoryview)):
        return False
    header = _header(headers, SIGNATURE_HEADER)
    delivery_id = _header(headers, DELIVERY_HEADER)
    event = _header(headers, EVENT_HEADER)
    if not header or not delivery_id or not event:
        return False
    timestamp, signatures = _parse_signatures(header, REQUEST_SIGNATURE_VERSION)
    if timestamp is None or not signatures:
        return False
    if not _is_fresh(timestamp, tolerance_seconds, now):
        return False
    try:
        expected = compute_request_signature(
            secret,
            timestamp=timestamp,
            delivery_id=delivery_id,
            event=event,
            method=method,
            path=path,
            query=query,
            body=bytes(body),
        )
    except (UnicodeError, ValueError, TypeError):
        return False
    return _matches(expected, signatures)


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


def signed_request(
    signing_secrets: Sequence[str],
    *,
    method: str,
    url: str,
    body: bytes,
    event: str,
    delivery_id: str,
    query_pairs: Optional[Iterable[tuple[str, str]]] = None,
    timestamp: Optional[int] = None,
) -> tuple[str, dict[str, str]]:
    """Sign one request with ``v2``: the URL to send and the three headers to add.

    The query goes on the wire in canonical form (``query_pairs`` when given, otherwise the
    query already in ``url``), so the bytes a receiver sees are the bytes that were signed and
    ``+`` versus ``%20`` cannot be read two ways. The signed path is the one httpx will send
    (dot segments resolved). The fragment is dropped, as httpx would drop it.
    """
    if not signing_secrets:
        raise ValueError('at least one signing secret is required')
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True) if query_pairs is None else list(query_pairs)
    target = urlunsplit(parts._replace(query=canonical_query(pairs), fragment=''))
    raw_path, _, raw_query = httpx.URL(target).raw_path.partition(b'?')
    sent_path = raw_path.decode('ascii')
    sent_query = raw_query.decode('ascii')
    ts = int(time.time()) if timestamp is None else int(timestamp)
    signatures = (
        compute_request_signature(
            secret,
            timestamp=ts,
            delivery_id=delivery_id,
            event=event,
            method=method,
            path=sent_path,
            query=sent_query,
            body=body,
        )
        for secret in signing_secrets
    )
    return target, {
        SIGNATURE_HEADER: _signature_header_value(ts, REQUEST_SIGNATURE_VERSION, signatures),
        EVENT_HEADER: event,
        DELIVERY_HEADER: delivery_id,
    }
