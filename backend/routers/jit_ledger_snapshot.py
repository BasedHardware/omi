"""Authoritative desktop prompt snapshot for the canonical knowledge ledger."""

from __future__ import annotations

from enum import Enum
from typing import Any

from database._client import get_data_plane_firestore_client
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from models.memories import MemoryDB
from utils.executors import db_executor, run_blocking
from utils.jit_rollout import JITDecisionStage, JITRolloutDecision, TriState, resolve_jit_rollout
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION
from utils.memory.knowledge_ledger_migration import (
    MAX_LEDGER_PROMPT_PROJECTION_ROWS,
    read_ledger_migration_completion,
    read_ledger_prompt_projection_receipt,
)
from utils.memory.jit_ledger_mirror_snapshot import (
    DEFAULT_MIRROR_PAGE_SIZE,
    MAX_MIRROR_PAGE_SIZE,
    MIRROR_SCHEMA_VERSION,
    read_authoritative_ledger_mirror_page,
)
from models.memory_evidence import SourceState
from models.product_memory import MemoryItemStatus
from utils.other.endpoints import get_current_user_uid

router = APIRouter()
_SNAPSHOT_PATH = "/v1/jit/knowledge-ledger/prompt-snapshot"
_MIRROR_SNAPSHOT_PATH = "/v1/jit/knowledge-ledger/mirror-snapshot"


class LedgerPromptSnapshotMode(str, Enum):
    enabled = "enabled"
    compatibility = "compatibility"
    disabled = "disabled"
    killed = "killed"
    unknown = "unknown"


class LedgerPromptSnapshotEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = LEDGER_SCHEMA_VERSION
    mode: LedgerPromptSnapshotMode
    reason: str = Field(max_length=64)
    source_head_commit_id: str | None = Field(default=None, max_length=256)
    rows: list[MemoryDB] = Field(default_factory=list, max_length=MAX_LEDGER_PROMPT_PROJECTION_ROWS)


class LedgerMirrorAliasEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias_memory_id: str = Field(min_length=1, max_length=256)
    canonical_memory_id: str = Field(min_length=1, max_length=256)
    source_memory_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(pattern="^(canonical_memory_id|superseded_by)$")


class LedgerMirrorRowEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1, max_length=256)
    item_revision: int = Field(ge=1)
    status: MemoryItemStatus
    source_state: SourceState
    canonical_memory_id: str | None = Field(default=None, min_length=1, max_length=256)
    content_purged: bool
    memory: MemoryDB | None = None


class LedgerMirrorSnapshotEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = MIRROR_SCHEMA_VERSION
    owner_id: str
    account_generation: int = Field(ge=0)
    source_generation: int = Field(ge=0)
    writer_epoch: int = Field(ge=0)
    head_commit_id: str
    commit_sequence: int = Field(ge=0)
    epoch_id: str
    page_revision: str
    chain_revision: str
    scanned_count: int = Field(ge=0)
    projected_count: int = Field(ge=0)
    rows: list[LedgerMirrorRowEnvelope] = Field(default_factory=list, max_length=MAX_MIRROR_PAGE_SIZE)
    aliases: list[LedgerMirrorAliasEnvelope] = Field(default_factory=list)
    next_cursor: str | None = None
    final_page: bool = False
    failure_reason: str | None = None


def _disabled_mirror_snapshot(uid: str, reason: str) -> LedgerMirrorSnapshotEnvelope:
    return LedgerMirrorSnapshotEnvelope(
        owner_id=uid,
        account_generation=0,
        source_generation=0,
        writer_epoch=0,
        head_commit_id="",
        commit_sequence=0,
        epoch_id="",
        page_revision="",
        chain_revision="",
        scanned_count=0,
        projected_count=0,
        failure_reason=reason,
    )


def _disabled_snapshot(decision: JITRolloutDecision) -> LedgerPromptSnapshotEnvelope:
    if decision.kill_switch == TriState.ENABLED:
        mode = LedgerPromptSnapshotMode.killed
    elif decision.effective == TriState.DISABLED:
        mode = LedgerPromptSnapshotMode.disabled
    else:
        mode = LedgerPromptSnapshotMode.unknown
    return LedgerPromptSnapshotEnvelope(mode=mode, reason=decision.reason.value)


def _build_enabled_snapshot(
    uid: str,
    *,
    db_client: Any,
) -> LedgerPromptSnapshotEnvelope:
    completion = read_ledger_migration_completion(uid, db_client=db_client)
    if completion is None:
        return LedgerPromptSnapshotEnvelope(
            mode=LedgerPromptSnapshotMode.compatibility,
            reason="migration_incomplete",
        )

    receipt = read_ledger_prompt_projection_receipt(
        uid,
        db_client=db_client,
        completion=completion,
    )
    if receipt is None:
        return LedgerPromptSnapshotEnvelope(
            mode=LedgerPromptSnapshotMode.compatibility,
            reason="projection_receipt_stale",
        )

    return LedgerPromptSnapshotEnvelope(
        mode=LedgerPromptSnapshotMode.enabled,
        reason="migration_complete_zero_legacy",
        source_head_commit_id=receipt.source_head_commit_id,
        rows=receipt.rows,
    )


def _build_enabled_snapshot_with_default_client(uid: str) -> LedgerPromptSnapshotEnvelope:
    """Acquire and use the synchronous Firestore client off the event loop."""

    return _build_enabled_snapshot(uid, db_client=get_data_plane_firestore_client())


def _build_enabled_mirror_page_with_default_client(
    uid: str,
    cursor: str | None,
    page_size: int,
):
    return read_authoritative_ledger_mirror_page(
        uid,
        cursor=cursor,
        page_size=page_size,
        firestore_client=get_data_plane_firestore_client(),
    )


@router.get(_SNAPSHOT_PATH, response_model=LedgerPromptSnapshotEnvelope)
async def get_knowledge_ledger_prompt_snapshot(
    response: Response,
    uid: str = Depends(get_current_user_uid),
) -> LedgerPromptSnapshotEnvelope:
    response.headers["Cache-Control"] = "no-store"
    decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    if not decision.permits_work:
        return _disabled_snapshot(decision)
    snapshot = await run_blocking(db_executor, _build_enabled_snapshot_with_default_client, uid)
    if snapshot.mode != LedgerPromptSnapshotMode.enabled:
        return snapshot
    # A flag or kill switch can flip while the blocking receipt reads are in
    # flight. Re-resolve uncached immediately before releasing authority.
    final_decision = await resolve_jit_rollout(
        uid,
        stage=JITDecisionStage.READ_ONLY,
        force_refresh=True,
    )
    if not final_decision.permits_work:
        return _disabled_snapshot(final_decision)
    return snapshot


@router.get(_MIRROR_SNAPSHOT_PATH, response_model=LedgerMirrorSnapshotEnvelope)
async def get_knowledge_ledger_mirror_snapshot(
    response: Response,
    cursor: str | None = None,
    page_size: int = DEFAULT_MIRROR_PAGE_SIZE,
    uid: str = Depends(get_current_user_uid),
) -> LedgerMirrorSnapshotEnvelope:
    response.headers["Cache-Control"] = "no-store"
    decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    if not decision.permits_work:
        return _disabled_mirror_snapshot(uid, "rollout_not_enabled")
    page = await run_blocking(
        db_executor,
        _build_enabled_mirror_page_with_default_client,
        uid,
        cursor,
        page_size,
    )
    final_decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY, force_refresh=True)
    if not final_decision.permits_work:
        return _disabled_mirror_snapshot(uid, "rollout_not_enabled")
    if page.fence is None:
        return _disabled_mirror_snapshot(uid, page.failure_reason or "mirror_unavailable")
    fence = page.fence
    return LedgerMirrorSnapshotEnvelope(
        owner_id=fence.owner_id,
        account_generation=fence.account_generation,
        source_generation=fence.source_generation,
        writer_epoch=fence.writer_epoch,
        head_commit_id=fence.head_commit_id,
        commit_sequence=fence.commit_sequence,
        epoch_id=fence.epoch_id,
        page_revision=page.page_revision,
        chain_revision=page.chain_revision,
        scanned_count=page.scanned_count,
        projected_count=page.projected_count,
        rows=[
            LedgerMirrorRowEnvelope(
                memory_id=row.memory_id,
                item_revision=row.item_revision,
                status=row.status,
                source_state=row.source_state,
                canonical_memory_id=row.canonical_memory_id,
                content_purged=row.content_purged,
                memory=row.memory,
            )
            for row in page.rows
        ],
        aliases=[LedgerMirrorAliasEnvelope(**alias.__dict__) for alias in page.aliases],
        next_cursor=page.next_cursor,
        final_page=page.final_page,
        failure_reason=page.failure_reason,
    )


__all__ = [
    "LedgerPromptSnapshotEnvelope",
    "LedgerPromptSnapshotMode",
    "LedgerMirrorSnapshotEnvelope",
    "_build_enabled_snapshot",
    "router",
]
