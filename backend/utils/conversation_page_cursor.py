"""Versioned, query-bound conversation bookmarks; no bookmark-document read."""

import base64
import copy
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone

from google.api_core.datetime_helpers import DatetimeWithNanoseconds


def query_scope(parameters: dict) -> str:
    return hashlib.sha256(json.dumps(parameters, sort_keys=True, default=str).encode()).hexdigest()


def _ttl() -> int:
    try:
        return max(1, int(os.getenv('FSR_CONVERSATION_CURSOR_TTL_SECONDS', '3600')))
    except ValueError:
        return 3600


def _signature(payload: bytes) -> bytes:
    secret = os.environ.get('ENCRYPTION_SECRET')
    if not secret:
        raise ValueError('cursor signing unavailable')
    return hmac.digest(secret.encode(), b'conversation-list-cursor-v1:' + payload, 'sha256')


def encode_cursor(timestamp: datetime, document_id: str, scope: str) -> str:
    if timestamp.tzinfo is None:
        raise ValueError('cursor ordering key must be a timezone-aware timestamp')
    # Firestore timestamps can contain nanoseconds; datetime.isoformat loses them.
    stamp = (
        timestamp.rfc3339()
        if isinstance(timestamp, DatetimeWithNanoseconds)
        else timestamp.astimezone(timezone.utc).isoformat()
    )
    payload = json.dumps(
        {'v': 1, 'ts': stamp, 'id': document_id, 'scope': scope, 'issued': int(time.time())},
        separators=(',', ':'),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(_signature(payload) + payload).decode().rstrip('=')


def decode_cursor(token: str, scope: str) -> tuple[datetime, str]:
    """Reject bad, expired, cross-user/filter or tampered cursors as ValueError."""
    try:
        if not 0 < len(token) <= 4096:
            raise ValueError('invalid cursor size')
        packed = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
        signature, payload = packed[:32], packed[32:]
        if not hmac.compare_digest(signature, _signature(payload)):
            raise ValueError('invalid cursor signature')
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get('v') != 1 or data.get('scope') != scope:
            raise ValueError('invalid cursor scope or version')
        issued = data['issued']
        age = time.time() - issued if type(issued) is int else -1
        # Tolerate ~1 minute of issuer-ahead clock skew so a cursor minted on a
        # slightly fast pod does not fail decode on a slower one.
        if age < -60 or age > _ttl():
            raise ValueError('expired cursor')
        document_id = data['id']
        if not isinstance(document_id, str) or not document_id or '/' in document_id or document_id in {'.', '..'}:
            raise ValueError('invalid cursor document id')
        if len(document_id.encode()) > 1500:
            raise ValueError('invalid cursor document id')
        stamp = data['ts']
        # Accept the two encodings produced above, preserving Firestore precision.
        if stamp.endswith('+00:00'):
            stamp = stamp[:-6] + 'Z'
        return DatetimeWithNanoseconds.from_rfc3339(stamp), document_id
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError) as error:
        raise ValueError('invalid or expired conversation cursor') from error


class BookmarkDict(dict):
    """Cursor dict whose ``__deepcopy__`` keeps Firestore timestamp precision.

    ``BaseQuery._cursor_helper`` deep-copies the bookmark before compiling it,
    and ``copy.deepcopy`` truncates a ``DatetimeWithNanoseconds`` to
    microseconds, so an offset-by-one-visibility boundary could otherwise
    re-serve the boundary row on every page. Copy everything else normally.
    """

    def __deepcopy__(self, memo):
        # Values are exactly the ordering key (DatetimeWithNanoseconds, immutable)
        # and the doc id (str) today; if a mutable value ever lands here it must
        # be added to the copy branch below, not passed through.
        out = BookmarkDict()
        for key, value in self.items():
            if isinstance(value, DatetimeWithNanoseconds):
                out[key] = value
            else:
                out[key] = copy.deepcopy(value, memo)
        return out
