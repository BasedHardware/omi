"""jsonb codec for Firestore-shaped documents.

Batch documents carry Firestore-native values that JSON cannot hold (``datetime`` for TTL / audit stamps,
``bytes``). They are stored as one-key tagged objects and restored on read, so a document round-trips with
the types the store code wrote. ``$datetime`` and ``$bytes`` are reserved key names. Datetimes keep
microseconds and their offset; Firestore's nanosecond remainder is not representable in ``datetime``.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

_DATETIME = '$datetime'
_BYTES = '$bytes'


def _default(value: Any) -> Any:
    if isinstance(value, datetime):
        return {_DATETIME: value.isoformat()}
    if isinstance(value, (bytes, bytearray)):
        return {_BYTES: base64.b64encode(bytes(value)).decode('ascii')}
    raise TypeError(f'{type(value).__name__} is not storable in the job store')


def _hook(obj: dict) -> Any:
    if len(obj) == 1:
        if _DATETIME in obj:
            return datetime.fromisoformat(obj[_DATETIME])
        if _BYTES in obj:
            return base64.b64decode(obj[_BYTES])
    return obj


def dumps(value: Any) -> str:
    return json.dumps(value, default=_default)


def loads(text: str | bytes) -> Any:
    return json.loads(text, object_hook=_hook)


def canonical(value: Any) -> str:
    """Key-order-independent encoding, for comparing a Firestore document with its Postgres copy."""
    return json.dumps(value, default=_default, sort_keys=True, separators=(',', ':'))
