"""Identifier-only EXP-004 measurements. Client rules deny this server-owned collection."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

RETENTION_DAYS = 60


def get_data_plane_firestore_client() -> Any:
    # Resolved at call time: this module is imported on the capture path, and many
    # suites stub `database._client` with only the clients they exercise.
    from database._client import get_data_plane_firestore_client as _get_client

    return _get_client()


def write_jev_shadow(
    uid: str, record_id: str, record: dict[str, Any], *, deadline: float, firestore_client: Any = None
) -> None:
    """No prompts, transcript, quotes, candidate content or user names belong here."""
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    now = datetime.now(timezone.utc)
    ref = client.collection('users').document(uid).collection('jev_shadow').document(record_id)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    ref.set(
        {**record, 'created_at': now, 'expire_at': now + timedelta(days=RETENTION_DAYS)}, retry=None, timeout=remaining
    )
