"""Sanctioned persistence-client handle for dependency injection at the boundary.

Some callers outside ``database/`` (routers, a few utils) do not run persistence ops themselves
but must thread a client into ``database/``-side abstractions that legitimately distinguish an
injected client from ``None`` (e.g. the canonical-write fail-closed safety gate). They import the
client from here instead of from ``database._client`` so the persistence-boundary guard can keep
forbidding ``database._client`` / Firestore-SDK imports everywhere but ``database/``.

This is a pass-through handle ONLY. The guard also forbids raw ``.document()`` / ``.collection()``
/ ``.collection_group()`` / ``.transaction()`` calls outside ``database/``, so holding this handle
cannot be used to run an op outside the boundary — it can only be forwarded as ``db_client=``.
"""

from ._client import db

__all__ = ["db"]
