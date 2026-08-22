"""Path-segment safety for the neutral storage port.

Logical paths are ``/``-delimited segment strings (``users/{uid}/people/{pid}``). A document id that
itself contains ``/`` silently splits into extra path segments: on Firestore ``.document(path)``
rejects the resulting odd-segment path, while the Mongo adapter mis-parses collection/parent/key
(``_doc_meta`` splits on ``/``) and writes to the wrong place. Client-provided ids must therefore be
validated before they are composed into a path — at the one place the individual segment is still
known, since the joined path string has already lost the segment boundaries.
"""

from __future__ import annotations


def ensure_id_segment(value: str, *, label: str = "document id") -> str:
    """Return ``value`` unchanged if it is a safe single path segment, else raise ``ValueError``.

    A segment must be a non-empty string with no ``/`` (Firestore likewise forbids ``/`` in a
    document id). Rejecting is deliberate over encoding: an encoded id would not round-trip with the
    reads elsewhere that address the same document by its raw id, so an unsafe id is refused rather
    than silently rewritten.
    """
    if not isinstance(value, str) or not value or "/" in value:
        raise ValueError(f"invalid {label}: must be a non-empty string without '/': {value!r}")
    return value


__all__ = ["ensure_id_segment"]
