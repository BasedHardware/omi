"""Verify the ``X-Omi-Signature`` header Omi puts on signed webhooks and chat-tool calls.

Receiver-side copy of ``backend/utils/webhook_signing.py`` (issue #20939). Keep the two in step.
Two schemes share the header and the per-destination secret:

``v1`` (webhooks, ``verify_signature``): the signed string is ``"<t>.<uid>." + body``, where
``t`` is the header's unix-second timestamp, ``uid`` is the value Omi appended to the request's
query string (empty if a delivery has none) and ``body`` is exactly the request bytes.

``v2`` (chat-tool calls, ``verify_request``): the signed string is eight parts, the first seven
each followed by one LF: ``v2``, ``t``, ``X-Omi-Delivery``, ``X-Omi-Event``, the method, the
canonical path, the canonical query, then exactly the body bytes (empty for GET). It binds the
whole request, so a captured call cannot be replayed with other arguments, against a sibling
tool's URL or with another method. Read ``uid`` from the query (GET) or body (POST) only after
it verifies.

During a secret rotation the header carries one signature per still-valid secret, so verifying
against either the new or the previous secret succeeds for 24 hours.

Standard library only. Typical use::

    body = await request.body()          # raw bytes, never request.json()
    if not verify_request(
        request.headers, body, OMI_SIGNING_SECRET,
        method=request.method,
        path=request.url.path,
        query=request.query_params.multi_items(),
    ):
        raise HTTPException(status_code=401)
"""

import hashlib
import hmac
import time
from typing import Iterable, Mapping, Optional, Union
from urllib.parse import parse_qsl, quote, unquote_to_bytes

SIGNATURE_HEADER = "X-Omi-Signature"
EVENT_HEADER = "X-Omi-Event"
DELIVERY_HEADER = "X-Omi-Delivery"
SIGNATURE_VERSION = "v1"
REQUEST_SIGNATURE_VERSION = "v2"
CHAT_TOOL_EVENT = "chat_tool"
DEFAULT_TOLERANCE_SECONDS = 300

# A query as a receiver has it: the raw query string, or the decoded (name, value) pairs.
QueryInput = Union[str, Iterable[tuple[str, str]]]


def compute_signature(secret: str, timestamp: int, uid: str, body: bytes) -> str:
    message = f"{timestamp}.{uid}.".encode("utf-8") + bytes(body)
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _parse_signatures(value: str, version: str) -> tuple[Optional[int], list[str]]:
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
    wanted = expected.encode("utf-8")
    return any(hmac.compare_digest(wanted, candidate.encode("utf-8")) for candidate in candidates)


def verify_signature(
    headers: Mapping[str, str],
    body: object,
    secret: str,
    *,
    uid: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """True when ``X-Omi-Signature`` carries a ``v1`` signature of ``body`` for ``uid`` that is fresh.

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
    encoded = [(quote(name, safe=""), quote(value, safe="")) for name, value in pairs]
    encoded.sort(key=lambda pair: pair[0])
    return "&".join(f"{name}={value}" for name, value in encoded)


def canonical_path(path: str) -> str:
    """The ``v2`` form of a path: each ``/``-separated segment percent-decoded, then re-encoded.

    Uses the same byte rule as ``canonical_query``, so ``/tools/%7euser`` and ``/tools/~user``
    are the same path, and a decoded path (what most frameworks hand you) gives the same result
    as the raw one whenever the path has no encoded ``/`` or ``%``. An empty path is ``/``.
    """
    if not path:
        return "/"
    return "/".join(quote(unquote_to_bytes(segment), safe="") for segment in path.split("/"))


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
        raise ValueError("delivery id, event and method must be non-empty printable ASCII")
    lines = (
        REQUEST_SIGNATURE_VERSION,
        str(int(timestamp)),
        delivery_id,
        event,
        method.upper(),
        canonical_path(path),
        canonical_query(_query_pairs(query)),
    )
    return "".join(f"{line}\n" for line in lines).encode("ascii") + bytes(body)


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
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


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
