"""Opaque pagination cursors for hosted MCP list tools.

A cursor is a base64url-encoded JSON document::

    {"v": 1, "k": <tool kind>, "u": <uid>, "p": <position>, "f": <filters fingerprint>}

``k`` binds the cursor to the tool that minted it, ``u`` blocks cross-user
reuse, and ``f`` is a fingerprint of the validated filter arguments so a
cursor minted for one filtered view cannot silently resume a different one.
The payload is not signed: a forged cursor only lets its owner page through
their own data, the same thing the ``offset`` argument already allows.

Position shapes:

- ``{"offset": n}`` — for backends that only accept an offset. ``n`` is the
  next item position in the same space the ``offset`` argument already uses.
- ``{"ts": str, "id": str}`` — a (timestamp, document id) keyset: the screen
  activity query stores ``timestamp`` strings and orders by
  ``(timestamp, __name__)``; the conversation list serializes ``created_at``
  as RFC 3339 and orders by ``(created_at, __name__)``.
- ``{"uml": str}`` — an opaque ``MemoryService.read_page`` continuation
  cursor for the memory list's keyset path.
"""

import base64
import hashlib
import json
import binascii
from datetime import datetime
from typing import Any, Dict, List, Tuple

from google.api_core.datetime_helpers import DatetimeWithNanoseconds

from utils.mcp_server.errors import ToolExecutionError

CURSOR_VERSION = 1
CURSOR_MAX_OFFSET = 100_000
CURSOR_MAX_TOKEN_CHARS = 4096

_INVALID = "Invalid cursor"


def _invalid_cursor() -> ToolExecutionError:
    return ToolExecutionError(_INVALID, code=-32602)


def _fingerprint(filters: Dict[str, Any]) -> str:
    canonical = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def encode_cursor(*, kind: str, uid: str, position: Dict[str, Any], filters: Dict[str, Any]) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "k": kind,
        "u": uid,
        "p": position,
        "f": _fingerprint(filters),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: Any, *, kind: str, uid: str, filters: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a client-supplied cursor and return its position payload.

    Raises ``ToolExecutionError(-32602)`` for malformed tokens and for cursors
    minted for a different tool, user, or filter set.
    """
    if not isinstance(token, str) or not token or len(token) > CURSOR_MAX_TOKEN_CHARS:
        raise _invalid_cursor()
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        payload = json.loads(raw)
    except (ValueError, binascii.Error):
        raise _invalid_cursor()
    if not isinstance(payload, dict):
        raise _invalid_cursor()
    if (
        payload.get("v") != CURSOR_VERSION
        or payload.get("k") != kind
        or payload.get("u") != uid
        or payload.get("f") != _fingerprint(filters)
        or not isinstance(payload.get("p"), dict)
    ):
        raise _invalid_cursor()
    return payload["p"]


def offset_position(position: Dict[str, Any], *, maximum: int = CURSOR_MAX_OFFSET) -> int:
    """Extract a validated ``{"offset": n}`` position."""
    offset = position.get("offset")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0 or offset > maximum:
        raise _invalid_cursor()
    return offset


def keyset_position(position: Dict[str, Any]) -> Tuple[str, str]:
    """Extract a validated ``{"ts", "id"}`` keyset position."""
    timestamp = position.get("ts")
    doc_id = position.get("id")
    if (
        not isinstance(timestamp, str)
        or not timestamp
        or not isinstance(doc_id, str)
        or not doc_id.strip()
        or "/" in doc_id
    ):
        raise _invalid_cursor()
    return timestamp, doc_id


def uml_position(position: Dict[str, Any]) -> str:
    """Extract a validated ``{"uml": str}`` memory-page position."""
    cursor = position.get("uml")
    if not isinstance(cursor, str) or not cursor or len(cursor) > CURSOR_MAX_TOKEN_CHARS:
        raise _invalid_cursor()
    return cursor


def serialize_timestamp(value: Any) -> str:
    """Serialize a Firestore timestamp for a cursor position.

    ``DatetimeWithNanoseconds.rfc3339()`` keeps nanosecond precision so a
    round-tripped boundary value cannot drift inside ``start_after``.
    """
    rfc3339 = getattr(value, "rfc3339", None)
    if callable(rfc3339):
        return str(rfc3339())
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def timestamp_keyset_position(position: Dict[str, Any]) -> Tuple[datetime, str]:
    """Extract a ``{"ts", "id"}`` position as a (datetime, doc id) keyset."""
    timestamp, doc_id = keyset_position(position)
    try:
        return DatetimeWithNanoseconds.from_rfc3339(timestamp), doc_id
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise _invalid_cursor()
    return parsed, doc_id


# Kept for the conversation-list call sites; the same ``{"ts", "id"}`` keyset
# serves the action-item sync feed ordered on ``updated_at``.
conversation_keyset_position = timestamp_keyset_position


def offset_page(fetched: List[Any], limit: int) -> Tuple[List[Any], int, bool]:
    """Slice a ``limit + 1`` lookahead fetch into (page, consumed, has_more).

    ``consumed`` is the number of fetched items the page covers, i.e. the
    amount by which the next offset advances. ``has_more`` is true only when
    the lookahead row exists, so a backend whose offset counts the same units
    it returns never emits a dangling cursor.
    """
    page = fetched[:limit]
    consumed = len(page)
    has_more = len(fetched) > limit
    return page, consumed, has_more


def resolve_offset_cursor(
    arguments: Dict[str, Any],
    *,
    kind: str,
    uid: str,
    filters: Dict[str, Any],
    offset: int,
) -> int:
    """Resolve the effective offset from a ``cursor`` argument, if present.

    ``cursor`` and a non-zero ``offset`` are mutually exclusive: accepting
    both would make the resume position ambiguous.
    """
    token = arguments.get("cursor")
    if token is None:
        return offset
    if offset != 0:
        raise ToolExecutionError("cursor and offset are mutually exclusive.", code=-32602)
    return offset_position(decode_cursor(token, kind=kind, uid=uid, filters=filters))
