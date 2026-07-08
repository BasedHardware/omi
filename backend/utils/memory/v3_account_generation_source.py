"""Canonical module for ``utils.memory.v3_account_generation_source`` (WS-G8b).

Neutral ``v3_account_generation_source`` is the source of truth. Legacy ``v3_account_generation_source`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from database.memory_collections import MemoryCollections

V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION = 1
V3_TRUSTED_ACCOUNT_GENERATION_SOURCE = 'memory_state_head'


class V3AccountGenerationFailureReason(str, Enum):
    MISSING_STATE_HEAD = 'missing_state_head'
    MALFORMED_STATE_HEAD = 'malformed_state_head'
    UNSUPPORTED_SCHEMA = 'unsupported_schema'
    UID_MISMATCH = 'uid_mismatch'
    SOURCE_MISMATCH = 'source_mismatch'
    MALFORMED_ACCOUNT_GENERATION = 'malformed_account_generation'
    READ_FAILED = 'read_failed'


class V3TrustedAccountGenerationReadError(RuntimeError):
    def __init__(self, reason: V3AccountGenerationFailureReason, message: str | None = None):
        super().__init__(message or reason.value)
        self.reason = reason


@dataclass(frozen=True)
class V3TrustedAccountGenerationResult:
    uid: str
    source_path: str
    account_generation: int | None = None
    head_commit_id: str | None = None
    commit_sequence: int | None = None
    source: str | None = None
    schema_version: int | None = None
    read_error_reason: V3AccountGenerationFailureReason | None = None

    def require_account_generation(self) -> int:
        if self.read_error_reason is not None or self.account_generation is None:
            raise V3TrustedAccountGenerationReadError(
                self.read_error_reason or V3AccountGenerationFailureReason.MALFORMED_ACCOUNT_GENERATION
            )
        return self.account_generation


_MALFORMED_SNAPSHOT_DATA = object()


def _snapshot_data(snapshot: Any) -> dict[str, Any] | None | object:
    if snapshot is None or getattr(snapshot, 'exists', False) is False:
        return None
    data = snapshot.to_dict()
    return cast(dict[str, Any], data) if isinstance(data, dict) else _MALFORMED_SNAPSHOT_DATA


def _fail(*, uid: str, source_path: str, reason: V3AccountGenerationFailureReason) -> V3TrustedAccountGenerationResult:
    return V3TrustedAccountGenerationResult(uid=uid, source_path=source_path, read_error_reason=reason)


def read_memory_v3_trusted_account_generation(*, uid: str, db_client: Any) -> V3TrustedAccountGenerationResult:
    """Read and validate the independent account-generation state-head source.

    Future `/v3` GET wiring must feed this returned generation into projection
    reads and then compare it with control/projection/cursor generations. It must
    not derive ``expected_account_generation`` from the projection state being
    verified or from the memory control decision document.
    """

    source_path = MemoryCollections(uid=uid).memory_state_head
    try:
        data = _snapshot_data(db_client.document(source_path).get())
    except Exception:
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.READ_FAILED)

    if data is None:
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.MISSING_STATE_HEAD)
    if data is _MALFORMED_SNAPSHOT_DATA:
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD)
    if not isinstance(data, dict):
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD)
    payload = cast(dict[str, Any], data)
    if payload.get('schema_version') != V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION:
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.UNSUPPORTED_SCHEMA)
    if payload.get('uid') != uid:
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.UID_MISMATCH)
    if payload.get('source') != V3_TRUSTED_ACCOUNT_GENERATION_SOURCE:
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.SOURCE_MISMATCH)

    account_generation = payload.get('account_generation')
    if isinstance(account_generation, bool) or not isinstance(account_generation, int) or account_generation < 0:
        return _fail(
            uid=uid,
            source_path=source_path,
            reason=V3AccountGenerationFailureReason.MALFORMED_ACCOUNT_GENERATION,
        )
    head_commit_id = payload.get('head_commit_id')
    commit_sequence = payload.get('commit_sequence')
    if not isinstance(head_commit_id, str) or not head_commit_id:
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD)
    if isinstance(commit_sequence, bool) or not isinstance(commit_sequence, int) or commit_sequence < 0:
        return _fail(uid=uid, source_path=source_path, reason=V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD)

    return V3TrustedAccountGenerationResult(
        uid=uid,
        source_path=source_path,
        account_generation=account_generation,
        head_commit_id=head_commit_id,
        commit_sequence=commit_sequence,
        source=V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
        schema_version=V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    )
