"""Authenticated, read-only just-in-time rollout decision contract."""

from __future__ import annotations

from datetime import datetime
import json

from fastapi import APIRouter, Depends, FastAPI, Response
from pydantic import BaseModel, ConfigDict, Field

from utils.jit_rollout import (
    JITDecisionReason,
    JITDecisionStage,
    JITErrorClass,
    JITRolloutDecision,
    TriState,
    resolve_jit_rollout,
)
from utils.other.endpoints import get_current_user_uid
from utils.executors import db_executor, run_blocking
from utils.memory.jit_trigger_snapshot import read_authoritative_trigger_snapshot

router = APIRouter()
_DECISION_PATH = '/v1/jit/rollout-decision'
_TRIGGER_SNAPSHOT_PATH = '/v1/jit/trigger-snapshot'


class JITRolloutDecisionEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rollout: TriState
    kill_switch: TriState
    effective: TriState
    reason: JITDecisionReason
    error_class: JITErrorClass
    cache_hit: bool
    cache_ttl_seconds: int

    @classmethod
    def from_decision(cls, decision: JITRolloutDecision) -> 'JITRolloutDecisionEnvelope':
        return cls(
            rollout=decision.rollout,
            kill_switch=decision.kill_switch,
            effective=decision.effective,
            reason=decision.reason,
            error_class=decision.error_class,
            cache_hit=decision.cache_hit,
            cache_ttl_seconds=decision.cache_ttl_seconds,
        )


class JITTriggerActionEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str
    prompt: str


class JITTriggerSnapshotRowEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    memory_id: str
    item_revision: int
    updated_at: datetime
    trigger_condition_json: str
    action: JITTriggerActionEnvelope
    wakeup_budget_per_day: int | None = None


class JITTriggerSnapshotEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    owner_id: str
    account_generation: int = Field(ge=0)
    head_commit_id: str
    commit_sequence: int = Field(ge=0)
    snapshot_revision: str
    complete: bool
    rows: list[JITTriggerSnapshotRowEnvelope]
    failure_reason: str | None = None


def _disabled_trigger_snapshot(uid: str) -> JITTriggerSnapshotEnvelope:
    """Return a content-free receipt whenever trigger authority is absent."""

    return JITTriggerSnapshotEnvelope(
        owner_id=uid,
        account_generation=0,
        head_commit_id='',
        commit_sequence=0,
        snapshot_revision='',
        complete=False,
        rows=[],
        failure_reason='rollout_not_enabled',
    )


@router.get(_DECISION_PATH, response_model=JITRolloutDecisionEnvelope)
async def get_jit_rollout_decision(
    uid: str = Depends(get_current_user_uid),
) -> JITRolloutDecisionEnvelope:
    decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    return JITRolloutDecisionEnvelope.from_decision(decision)


@router.get(_TRIGGER_SNAPSHOT_PATH, response_model=JITTriggerSnapshotEnvelope)
async def get_jit_trigger_snapshot(
    response: Response,
    uid: str = Depends(get_current_user_uid),
) -> JITTriggerSnapshotEnvelope:
    """Return an exhaustive action-bearing watchlist only for admitted owners."""

    response.headers['Cache-Control'] = 'no-store'
    decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    if not decision.permits_work:
        return _disabled_trigger_snapshot(uid)
    snapshot = await run_blocking(db_executor, read_authoritative_trigger_snapshot, uid)
    # A flag or kill switch can flip while the blocking exhaustive scan is in
    # flight. Re-resolve uncached immediately before releasing an actionable
    # snapshot, matching the canonical prompt-snapshot authority fence.
    final_decision = await resolve_jit_rollout(
        uid,
        stage=JITDecisionStage.READ_ONLY,
        force_refresh=True,
    )
    if not final_decision.permits_work:
        return _disabled_trigger_snapshot(uid)
    return JITTriggerSnapshotEnvelope(
        owner_id=snapshot.owner_id,
        account_generation=snapshot.account_generation,
        head_commit_id=snapshot.head_commit_id,
        commit_sequence=snapshot.commit_sequence,
        snapshot_revision=snapshot.snapshot_revision,
        complete=snapshot.complete,
        rows=[
            JITTriggerSnapshotRowEnvelope(
                memory_id=row.memory_id,
                item_revision=row.item_revision,
                updated_at=row.updated_at,
                trigger_condition_json=json.dumps(row.trigger_condition, sort_keys=True, separators=(',', ':')),
                action=JITTriggerActionEnvelope.model_validate(row.action.model_dump()),
                wakeup_budget_per_day=row.wakeup_budget_per_day,
            )
            for row in snapshot.rows
        ],
        failure_reason=snapshot.failure_reason,
    )


def validate_jit_rollout_contract(app: FastAPI) -> None:
    """Fail startup if a factory omits, unauthenticates, or mutates this route."""

    expected = {
        _DECISION_PATH: JITRolloutDecisionEnvelope,
        _TRIGGER_SNAPSHOT_PATH: JITTriggerSnapshotEnvelope,
    }
    for path, response_model in expected.items():
        matches = [route for route in app.routes if getattr(route, 'path', None) == path]
        if len(matches) != 1:
            raise RuntimeError(f'JIT contract must expose exactly one read-only GET route at {path}')
        route = matches[0]
        dependencies = getattr(getattr(route, 'dependant', None), 'dependencies', [])
        dependency_calls = {getattr(dependency, 'call', None) for dependency in dependencies}
        if (
            getattr(route, 'methods', set()) != {'GET'}
            or getattr(route, 'response_model', None) is not response_model
            or get_current_user_uid not in dependency_calls
        ):
            raise RuntimeError(f'JIT contract must be authenticated, typed, and read-only at {path}')


__all__ = [
    'JITRolloutDecisionEnvelope',
    'JITTriggerSnapshotEnvelope',
    'router',
    'validate_jit_rollout_contract',
]
