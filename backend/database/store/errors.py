"""Neutral storage-port errors (backend-agnostic).

Adapters translate their backend's native error to these so the domain never catches a
Firestore/Mongo-specific exception type. Keep this list minimal — one entry per contract-level
failure the domain actually branches on.
"""

from __future__ import annotations


class StoreError(RuntimeError):
    """Base class for neutral storage-port errors."""


class AlreadyExists(StoreError):
    """A ``create`` was refused because a document already exists at the path.

    Firestore raises ``google.api_core.exceptions.AlreadyExists`` / ``Conflict``; Mongo raises
    ``DuplicateKeyError``. Both map here so callers can implement create-once / idempotency without
    importing a backend SDK.
    """


class NotFound(StoreError):
    """An ``update`` addressed a path that has no document.

    ``update`` requires the target to exist (unlike ``set``, which upserts). Firestore raises
    ``google.api_core.exceptions.NotFound``; Mongo reports ``matched_count == 0``. Both map here so
    the domain can branch on "updated a document that was concurrently deleted / never created"
    identically on every backend, instead of one backend raising and another silently no-op'ing.
    """


__all__ = ["StoreError", "AlreadyExists", "NotFound"]
