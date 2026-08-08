"""Durable account-deletion fence for external memory projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, cast

from database.store import get_document_store
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status


def _store():
    return get_document_store()

ACCOUNT_DELETION_COLLECTION = "account_deletions"


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
    status = normalize_account_deletion_status(marker_exists=True, raw_status=payload.get("wipe_status"))
    return AccountDeletionProjectionFence(
        status=status,
        blocks_projection_writes=account_deletion_blocks_access(status),
    )


__all__ = [
    "ACCOUNT_DELETION_COLLECTION",
    "AccountDeletionProjectionFence",
    "read_account_deletion_projection_fence",
]
