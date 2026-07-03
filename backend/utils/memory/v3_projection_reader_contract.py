"""Canonical module for ``utils.memory.v3_projection_reader_contract`` (WS-G8b).

Neutral ``v3_projection_reader_contract`` is the source of truth. Legacy ``v3_projection_reader_contract`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION = 1
V3_COMPATIBILITY_PROJECTION_SOURCE = 'memory_items_projection'
V3_COMPATIBILITY_PROJECTION_VERSION = 'v3_memorydb_compatibility'


class V3ProjectionFailureReason(str, Enum):
    MISSING_PROJECTION_STATE = 'missing_projection_state'
    MALFORMED_PROJECTION_STATE = 'malformed_projection_state'
    UNSUPPORTED_PROJECTION_SCHEMA = 'unsupported_projection_schema'
    PROJECTION_NOT_READY = 'projection_not_ready'
    UID_MISMATCH = 'uid_mismatch'
    SOURCE_MISMATCH = 'source_mismatch'
    ACCOUNT_GENERATION_MISMATCH = 'account_generation_mismatch'
    FENCE_MISMATCH = 'fence_mismatch'
    INCOMPLETE_CONVERGENCE = 'incomplete_convergence'
    ITEM_FENCE_MISMATCH = 'item_fence_mismatch'
    INVALID_PROJECTION_PAYLOAD = 'invalid_projection_payload'
    OFFSET_UNSUPPORTED = 'offset_unsupported'
    LIMIT_OUT_OF_RANGE = 'limit_out_of_range'
    CURSOR_MISMATCH = 'cursor_mismatch'


class V3ProjectionReadError(RuntimeError):
    def __init__(self, reason: V3ProjectionFailureReason, message: str | None = None):
        super().__init__(message or reason.value)
        self.reason = reason


@dataclass(frozen=True)
class V3ProjectionCursor:
    created_at: datetime
    memory_id: str
    account_generation: int
    projection_generation: int
    projection_commit_id: str


@dataclass(frozen=True)
class V3ProjectionReadRequest:
    uid: str
    limit: int
    expected_account_generation: int
    cursor: V3ProjectionCursor | None = None
    offset: int | None = None
    include_archive: bool = False


@dataclass(frozen=True)
class V3ProjectionState:
    uid: str
    account_generation: int
    projection_generation: int
    source_commit_id: str
    source_version: str
    projection_commit_id: str
    projection_version: str
    source_evidence_fence: str
    projection_evidence_fence: str
    freshness_fence_generation: int
    tombstone_fence_generation: int
    vector_cleanup_fence_generation: int
    empty_projection: bool


@dataclass(frozen=True)
class V3ProjectionPage:
    items: list[dict[str, Any]]
    next_cursor: V3ProjectionCursor | None
    account_generation: int
    projection_generation: int
    source_commit_id: str
    source_version: str
    projection_commit_id: str
    projection_version: str
    empty_projection: bool
