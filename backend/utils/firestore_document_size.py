"""Firestore's documented per-document storage size, for writes near the 1 MiB ceiling."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

# Firestore rejects any write that would leave a document above 1 MiB.
FIRESTORE_MAX_DOCUMENT_BYTES = 1_048_576
# Used when a test double exposes no string document path.
_FALLBACK_DOCUMENT_NAME_BYTES = 256


def estimate_firestore_document_bytes(data: Mapping[str, Any], document_path: str | None) -> int:
    """Firestore's documented storage size of one document.

    Document name: each path segment plus one byte, plus 16. Document: the
    fields plus 32. Field: name (UTF-8 plus one) plus value. Strings are UTF-8
    plus one; booleans and null one; numbers and timestamps eight; geo points
    sixteen; bytes their length; arrays the sum of their values; maps are sized
    like an embedded document (their fields plus 32). See
    https://firebase.google.com/docs/firestore/storage-size.
    """
    if document_path:
        name_bytes = sum(len(part.encode('utf-8')) + 1 for part in document_path.split('/')) + 16
    else:
        name_bytes = _FALLBACK_DOCUMENT_NAME_BYTES
    return name_bytes + 32 + sum(len(str(key).encode('utf-8')) + 1 + _value_bytes(value) for key, value in data.items())


def _value_bytes(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 1
    if isinstance(value, (int, float, datetime)):
        return 8
    if isinstance(value, str):
        return len(value.encode('utf-8')) + 1
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    if isinstance(value, Mapping):
        # A map is sized like an embedded document: its fields plus 32 bytes.
        return 32 + sum(len(str(key).encode('utf-8')) + 1 + _value_bytes(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return sum(_value_bytes(item) for item in value)
    if hasattr(value, 'latitude') and hasattr(value, 'longitude'):
        return 16
    path = getattr(value, 'path', None)
    if isinstance(path, str):
        # A document reference is stored as its full name, like a document name.
        return sum(len(part.encode('utf-8')) + 1 for part in path.split('/')) + 16
    # Any other SDK value: its text form, floored so a terse repr is never cheaper
    # than the widest fixed-size value Firestore stores.
    return max(len(str(value).encode('utf-8')) + 1, 16)
