"""Canonical module for ``utils.memory.v3_account_generation_source`` (WS-G8b).

Neutral ``v3_account_generation_source`` is the source of truth. Legacy ``v17_v3_account_generation_source`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from database.v17_collections import V17Collections

V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION = 1
V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE = 'v17_memory_state_head'


class V17V3AccountGenerationFailureReason(str, Enum):
    MISSING_STATE_HEAD = 'missing_state_head'
    MALFORMED_STATE_HEAD = 'malformed_state_head'
    UNSUPPORTED_SCHEMA = 'unsupported_schema'
    UID_MISMATCH = 'uid_mismatch'
    SOURCE_MISMATCH = 'source_mismatch'
    MALFORMED_ACCOUNT_GENERATION = 'malformed_account_generation'
    READ_FAILED = 'read_failed'


class V17V3TrustedAccountGenerationReadError(RuntimeError):
    def __init__(self, reason: V17V3AccountGenerationFailureReason, message: str | None = None):
        super().__init__(message or reason.value)
        self.reason = reason


@dataclass(frozen=True)
class V17V3TrustedAccountGenerationResult:
    uid: str
    source_path: str
    account_generation: int | None = None
    head_commit_id: str | None = None
    commit_sequence: int | None = None
    source: str | None = None
    schema_version: int | None = None
    read_error_reason: V17V3AccountGenerationFailureReason | None = None

    def require_account_generation(self) -> int:
        if self.read_error_reason is not None or self.account_generation is None:
            raise V17V3TrustedAccountGenerationReadError(
                self.read_error_reason or V17V3AccountGenerationFailureReason.MALFORMED_ACCOUNT_GENERATION
            )
        return self.account_generation


_MALFORMED_SNAPSHOT_DATA = object()


def _snapshot_data(snapshot) -> dict[str, Any] | None | object:
    if snapshot is None or getattr(snapshot, 'exists', False) is False:
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else _MALFORMED_SNAPSHOT_DATA


def _fail(
    *, uid: str, source_path: str, reason: V17V3AccountGenerationFailureReason
) -> V17V3TrustedAccountGenerationResult:
    return V17V3TrustedAccountGenerationResult(uid=uid, source_path=source_path, read_error_reason=reason)


def read_v17_v3_trusted_account_generation(*, uid: str, db_client) -> V17V3TrustedAccountGenerationResult:
    """Read and validate the independent account-generation state-head source.

    Future `/v3` GET wiring must feed this returned generation into projection
    reads and then compare it with control/projection/cursor generations. It must
    not derive ``expected_account_generation`` from the projection state being
    verified or from the V17 control decision document.
    """

    source_path = V17Collections(uid=uid).memory_state_head
    try:
        data = _snapshot_data(db_client.document(source_path).get())
    except Exception:
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.READ_FAILED)

    if data is None:
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.MISSING_STATE_HEAD)
    if data is _MALFORMED_SNAPSHOT_DATA:
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD)
    if not isinstance(data, dict):
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD)
    if data.get('schema_version') != V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION:
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.UNSUPPORTED_SCHEMA)
    if data.get('uid') != uid:
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.UID_MISMATCH)
    if data.get('source') != V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE:
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.SOURCE_MISMATCH)

    account_generation = data.get('account_generation')
    if isinstance(account_generation, bool) or not isinstance(account_generation, int) or account_generation < 0:
        return _fail(
            uid=uid,
            source_path=source_path,
            reason=V17V3AccountGenerationFailureReason.MALFORMED_ACCOUNT_GENERATION,
        )
    head_commit_id = data.get('head_commit_id')
    commit_sequence = data.get('commit_sequence')
    if not isinstance(head_commit_id, str) or not head_commit_id:
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD)
    if isinstance(commit_sequence, bool) or not isinstance(commit_sequence, int) or commit_sequence < 0:
        return _fail(uid=uid, source_path=source_path, reason=V17V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD)

    return V17V3TrustedAccountGenerationResult(
        uid=uid,
        source_path=source_path,
        account_generation=account_generation,
        head_commit_id=head_commit_id,
        commit_sequence=commit_sequence,
        source=V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
        schema_version=V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    )


# Neutral symbol aliases (V17 names remain valid via shim)
V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION = V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION
V3_TRUSTED_ACCOUNT_GENERATION_SOURCE = V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE
V3AccountGenerationFailureReason = V17V3AccountGenerationFailureReason
V3TrustedAccountGenerationReadError = V17V3TrustedAccountGenerationReadError
V3TrustedAccountGenerationResult = V17V3TrustedAccountGenerationResult
