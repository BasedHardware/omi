"""Durable account-deletion fence for external memory projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, cast

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status

ACCOUNT_DELETION_COLLECTION = "account_deletions"

# Sentinel: read kwargs the caller did not set must not be forwarded at all —
# the SDK distinguishes "unset" (gapic default retry) from an explicit None
# (retry disabled), so a plain None default would silently change behavior for
# every existing caller.
_UNSET = object()


@dataclass(frozen=True)
class AccountDeletionProjectionFence:
    status: str | None
    blocks_projection_writes: bool


def read_account_deletion_projection_fence(
    uid: str,
    *,
    db_client: Any,
    retry: Any = _UNSET,
    timeout: Any = _UNSET,
) -> AccountDeletionProjectionFence:
    """Read the top-level deletion authority that survives the user-data wipe.

    ``retry``/``timeout`` are thread-through read kwargs for callers that own a
    bounded per-attempt budget (the canonical apply-control boundary); unset by
    default, so every other caller keeps the SDK-default read behavior.
    """
    if not uid.strip():
        raise ValueError("uid is required")
    read_kwargs = {}
    if retry is not _UNSET:
        read_kwargs["retry"] = retry
    if timeout is not _UNSET:
        read_kwargs["timeout"] = timeout
    snapshot = db_client.document(f"{ACCOUNT_DELETION_COLLECTION}/{uid}").get(**read_kwargs)
    if not getattr(snapshot, "exists", False):
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
