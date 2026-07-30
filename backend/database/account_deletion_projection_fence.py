"""Durable account-deletion fence for external memory projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, cast

from database.store import get_document_store


def _store():
    return get_document_store()

ACCOUNT_DELETION_COLLECTION = "account_deletions"
ACCOUNT_DELETION_PROJECTION_FENCE_STATUSES = frozenset(
    {
        "deleting_auth",
        "pending",
        "retrying",
        "running",
        "failed",
        "completed",
    }
)


@dataclass(frozen=True)
class AccountDeletionProjectionFence:
    status: str | None
    blocks_projection_writes: bool


def read_account_deletion_projection_fence(uid: str) -> AccountDeletionProjectionFence:
    """Read the top-level deletion authority that survives the user-data wipe."""
    if not uid.strip():
        raise ValueError("uid is required")
    snapshot = _store().get(f"{ACCOUNT_DELETION_COLLECTION}/{uid}")
    if not snapshot.exists:
        return AccountDeletionProjectionFence(status=None, blocks_projection_writes=False)
    raw: object = snapshot.to_dict()
    payload = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    raw_status = payload.get("wipe_status")
    status = raw_status.strip() if isinstance(raw_status, str) and raw_status.strip() else None
    return AccountDeletionProjectionFence(
        status=status,
        blocks_projection_writes=status in ACCOUNT_DELETION_PROJECTION_FENCE_STATUSES,
    )


__all__ = [
    "ACCOUNT_DELETION_COLLECTION",
    "ACCOUNT_DELETION_PROJECTION_FENCE_STATUSES",
    "AccountDeletionProjectionFence",
    "read_account_deletion_projection_fence",
]
