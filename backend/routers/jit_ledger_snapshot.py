"""Authoritative desktop prompt snapshot for the canonical knowledge ledger."""

from __future__ import annotations

from enum import Enum
from typing import Any

from database._client import get_firestore_client
from fastapi import APIRouter, Depends
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
from utils.other.endpoints import get_current_user_uid

router = APIRouter()
_SNAPSHOT_PATH = "/v1/jit/knowledge-ledger/prompt-snapshot"


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


@router.get(_SNAPSHOT_PATH, response_model=LedgerPromptSnapshotEnvelope)
async def get_knowledge_ledger_prompt_snapshot(
    uid: str = Depends(get_current_user_uid),
) -> LedgerPromptSnapshotEnvelope:
    decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    if not decision.permits_work:
        return _disabled_snapshot(decision)
    db_client = get_firestore_client()
    snapshot = await run_blocking(db_executor, _build_enabled_snapshot, uid, db_client=db_client)
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


__all__ = [
    "LedgerPromptSnapshotEnvelope",
    "LedgerPromptSnapshotMode",
    "_build_enabled_snapshot",
    "router",
]
