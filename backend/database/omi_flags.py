"""Omi feature-flag store: a dedicated Firestore database, never the customer-data project.

Dev and prod share the customer Firestore, so flags live in their own project
(``OMI_FLAGS_FIRESTORE_PROJECT``, optional ``OMI_FLAGS_FIRESTORE_DATABASE``) where
only the flag writer can write. Unset project means the store is unconfigured and
every reader falls back to its previous source. Runtime docs:
``backend/docs/runbooks/omi-flags.md``.

Layout:
- ``omi_flags/{key}``: one runtime rule per flag (see ``utils.omi_flags.FlagRule``).
- ``omi_flags_meta/state``: ``{version}``, bumped by every write; readers poll it.
- ``omi_flags_audit/{auto}``: append-only change log written in the same transaction.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database.redis_connection import create_bounded_redis_client

FLAGS_COLLECTION = 'omi_flags'
META_COLLECTION = 'omi_flags_meta'
META_DOC = 'state'
AUDIT_COLLECTION = 'omi_flags_audit'
REDIS_VERSION_KEY = 'omi_flags:version'
# Serving reads are bounded: a slow store must not stall the request that triggered the refresh.
READ_TIMEOUT_SECONDS = 3.0
REDIS_TIMEOUT_SECONDS = 0.25


def store_target() -> tuple[str, str] | None:
    """(project, database) of the flag store, or None when unconfigured. Read at call time."""
    project = os.getenv('OMI_FLAGS_FIRESTORE_PROJECT', '').strip()
    if not project:
        return None
    database = os.getenv('OMI_FLAGS_FIRESTORE_DATABASE', '').strip() or '(default)'
    return project, database


@lru_cache(maxsize=4)
def _client_for(project: str, database: str) -> Any:
    # Runtime identity (ADC): the flag project grants read to the serving SAs and write only to the writer.
    return firestore.Client(project=project, database=database)


def flags_client() -> Any | None:
    target = store_target()
    return _client_for(*target) if target else None


def read_version(client: Any) -> int:
    snap = client.collection(META_COLLECTION).document(META_DOC).get(timeout=READ_TIMEOUT_SECONDS)
    data = snap.to_dict() if snap.exists else None
    return int((data or {}).get('version') or 0)


def read_all(client: Any) -> tuple[int, dict[str, dict[str, Any]]]:
    """Version first, then rules: a write racing the read is picked up by the next version poll."""
    version = read_version(client)
    rules = {
        doc.id: doc.to_dict() or {} for doc in client.collection(FLAGS_COLLECTION).stream(timeout=READ_TIMEOUT_SECONDS)
    }
    return version, rules


@lru_cache(maxsize=1)
def _redis() -> Any:
    # Bounded sockets: a blackholed Redis must not hang the refresh that holds the snapshot lock.
    return create_bounded_redis_client(REDIS_TIMEOUT_SECONDS)


def read_redis_version() -> int | None:
    """Fast-path change signal. None on a miss or any Redis error (the Firestore poll still runs)."""
    try:
        raw = _redis().get(REDIS_VERSION_KEY)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def publish_redis_version(version: int) -> bool:
    try:
        _redis().set(REDIS_VERSION_KEY, str(version))
        return True
    except Exception:
        return False


def read_audit(client: Any, key: str, limit: int = 20) -> list[dict[str, Any]]:
    rows = [
        doc.to_dict() or {}
        for doc in client.collection(AUDIT_COLLECTION).where(filter=FieldFilter('key', '==', key)).stream()
    ]
    rows.sort(key=lambda row: row.get('version') or 0, reverse=True)
    return rows[:limit]


def write_rule(client: Any, key: str, rule: dict[str, Any] | None, *, actor: str, reason: str) -> int:
    """Replace (or delete, when ``rule`` is None) one flag, bump the version and audit it atomically."""
    meta_ref = client.collection(META_COLLECTION).document(META_DOC)
    flag_ref = client.collection(FLAGS_COLLECTION).document(key)
    audit_ref = client.collection(AUDIT_COLLECTION).document()

    @firestore.transactional
    def apply(transaction: Any) -> int:
        meta = meta_ref.get(transaction=transaction)
        current = flag_ref.get(transaction=transaction)
        version = int(((meta.to_dict() if meta.exists else None) or {}).get('version') or 0) + 1
        before = current.to_dict() if current.exists else None
        now = datetime.now(timezone.utc)
        after = (
            None if rule is None else {**rule, 'key': key, 'version': version, 'updated_at': now, 'updated_by': actor}
        )
        if after is None:
            transaction.delete(flag_ref)
        else:
            transaction.set(flag_ref, after)
        transaction.set(meta_ref, {'version': version, 'updated_at': now})
        transaction.set(
            audit_ref,
            {
                'key': key,
                'version': version,
                'actor': actor,
                'reason': reason,
                'at': now,
                'before': before,
                'after': after,
            },
        )
        return version

    return apply(client.transaction())
