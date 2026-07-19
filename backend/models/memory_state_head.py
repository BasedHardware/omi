"""Shared schema for the trusted canonical fields on ``memory_state/head``.

The state-head document also carries legacy-ledger metadata.  Writers must
therefore preserve these trusted fields rather than replacing the whole
document with only their own metadata.
"""

from __future__ import annotations

from typing import Any, Mapping

MEMORY_STATE_HEAD_SCHEMA_VERSION = 1
MEMORY_STATE_HEAD_SOURCE = "memory_state_head"


def trusted_memory_state_head_fields(
    *,
    uid: str,
    account_generation: Any,
    head_commit_id: Any,
    commit_sequence: Any,
) -> dict[str, Any] | None:
    """Return the trusted fields only when they satisfy the shared contract."""
    if not uid:
        return None
    if isinstance(account_generation, bool) or not isinstance(account_generation, int) or account_generation < 0:
        return None
    if not isinstance(head_commit_id, str) or not head_commit_id:
        return None
    if isinstance(commit_sequence, bool) or not isinstance(commit_sequence, int) or commit_sequence < 0:
        return None
    return {
        "schema_version": MEMORY_STATE_HEAD_SCHEMA_VERSION,
        "uid": uid,
        "source": MEMORY_STATE_HEAD_SOURCE,
        "account_generation": account_generation,
        "head_commit_id": head_commit_id,
        "commit_sequence": commit_sequence,
    }


def trusted_memory_state_head_fields_from_state(state: Mapping[str, Any], *, uid: str) -> dict[str, Any] | None:
    """Validate and extract trusted fields from a state-head document."""
    if (
        state.get("schema_version") != MEMORY_STATE_HEAD_SCHEMA_VERSION
        or state.get("uid") != uid
        or state.get("source") != MEMORY_STATE_HEAD_SOURCE
    ):
        return None
    return trusted_memory_state_head_fields(
        uid=uid,
        account_generation=state.get("account_generation"),
        head_commit_id=state.get("head_commit_id"),
        commit_sequence=state.get("commit_sequence"),
    )


def trusted_memory_state_head_fields_from_control(control: Mapping[str, Any], *, uid: str) -> dict[str, Any] | None:
    """Build trusted fields from the canonical apply-control record for repair."""
    if control.get("uid") != uid:
        return None
    return trusted_memory_state_head_fields(
        uid=uid,
        account_generation=control.get("account_generation"),
        head_commit_id=control.get("head_commit_id"),
        commit_sequence=control.get("commit_sequence"),
    )
